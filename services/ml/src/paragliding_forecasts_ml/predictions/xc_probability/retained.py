"""Read the persisted GFS daily-feature boundary without replaying ingestion."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import UTC, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from ...ingestion.atmosphere.contracts import (
    UUID_V4_PATTERN,
    ArtifactReference,
    RawManifest,
    StageManifest,
    validate_utc_timestamp,
)
from ...ingestion.gfs.models import GFS_SOURCE_ID, sofia_window_instants
from ...ingestion.weather.artifacts import WeatherArtifactStore
from ...ingestion.weather.features.contracts import (
    DailyFeatureSnapshot,
    DailyFeatureSnapshotBatch,
    HourlyFeatureSnapshotBatch,
)
from ...ingestion.weather.features.policy import load_feature_policy
from ...ingestion.weather.persistence_models import WeatherPersistenceReceipt
from ...ingestion.weather.serialization import canonical_json_bytes, sha256_bytes
from ...ingestion.weather.state import RunStateLedger
from ...storage.sqlite import (
    configured_database_url,
    open_read_only_database,
    resolve_database_path,
)
from .inputs import ForecastInput, Observation, validate_features
from .policy import LAYER_BOUNDS, XcPolicy


def _observations(snapshot: DailyFeatureSnapshot, policy: XcPolicy) -> tuple[Observation, ...]:
    daily = {field.feature_key: field for field in snapshot.daily_fields}
    layers = {
        (layer.layer_base_agl_m, layer.layer_top_agl_m): {
            field.feature_key: field for field in layer.fields
        }
        for layer in snapshot.profile_layers
    }
    result = []
    for spec in policy.required_features:
        fields = daily if spec.scope == "daily" else layers.get(LAYER_BOUNDS[spec.scope], {})
        field = fields.get(spec.feature_key)
        if field is None:
            result.append(
                Observation(
                    feature_id=spec.feature_id,
                    value=None,
                    canonical_unit=spec.canonical_unit,
                    quality_state="missing",
                    missing_reason="required_feature_absent",
                    provenance={"feature_present": False},
                )
            )
            continue
        if any(
            getattr(field, key) != getattr(spec, key)
            for key in ("field_code", "canonical_unit", "variant", "statistic", "derivation_method")
        ):
            raise ValueError(f"Retained feature identity or units differ: {spec.feature_id}.")
        result.append(
            Observation(
                feature_id=spec.feature_id,
                value=field.canonical_value,
                canonical_unit=field.canonical_unit,
                quality_state=field.quality_state,
                missing_reason=field.missing_reason,
                provenance=field.model_dump(mode="json"),
            )
        )
    return tuple(result)


def _read_reference(
    store: WeatherArtifactStore, reference: ArtifactReference, *, raw: bool = False
) -> bytes:
    path = store.verify_reference(
        reference, expected_root=store.raw_dir if raw else store.interim_dir
    )
    data = path.read_bytes()
    if len(data) != reference.byte_count or sha256_bytes(data) != reference.sha256:
        raise ValueError("Retained weather artifact changed while it was being read.")
    return data


def _output(stage: StageManifest, key: str) -> ArtifactReference:
    reference = next((item for item in stage.outputs if item.artifact_key == key), None)
    if reference is None:
        raise ValueError(f"Effective weather stage is missing {key}.")
    return reference


def _read_run(
    connection: sqlite3.Connection,
    root: Path,
    database_identity: str,
    run_key: str,
    policy: XcPolicy,
    feature_policy_sha: str,
) -> list[ForecastInput]:
    runs = connection.execute(
        """SELECT r.id, r.run_key, r.product_run_id, r.status, r.target_local_date,
                  r.operational_use_allowed, r.raw_manifest_path, r.raw_manifest_sha256,
                  r.feature_manifest_path, r.feature_manifest_sha256, r.persistence_input_sha256,
                  r.pipeline_version, p.reference_at_utc, p.source_product_key,
                  s.code AS source_id, s.source_kind
           FROM weather_ingestion_runs r
           JOIN weather_product_runs p ON p.id = r.product_run_id
           JOIN weather_sources s ON s.id = p.source_id
           WHERE r.run_key = ?""",
        (run_key,),
    ).fetchall()
    if len(runs) != 1:
        raise ValueError(f"Expected one persisted GFS run for {run_key}.")
    run = runs[0]
    reference = validate_utc_timestamp(run["reference_at_utc"])
    cycle = datetime.fromisoformat(reference)
    target = datetime.fromisoformat(run["target_local_date"]).date()
    horizon = (target - cycle.date()).days
    if (
        run["status"] != "succeeded"
        or run["source_id"] != GFS_SOURCE_ID
        or run["source_kind"] != "forecast"
        or run["operational_use_allowed"] != 1
        or cycle.time() != time(6)
        or horizon not in policy.horizons
        or target.isoformat() != run["target_local_date"]
    ):
        raise ValueError("XC prediction requires an authorized, succeeded GFS 06Z D+1/D+2/D+3 run.")

    store = WeatherArtifactStore(run_key, project_root=root)
    state = RunStateLedger(store).load_state()

    def evidence(name: str) -> ArtifactReference:
        event = state.effective_event(name)
        if event is None or event.evidence is None:
            raise ValueError(f"Missing effective weather evidence: {name}.")
        return event.evidence

    def stage(ref: ArtifactReference, name: str) -> StageManifest:
        result = StageManifest.model_validate_json(_read_reference(store, ref))
        if (
            ref.artifact_key != "stage_manifest"
            or result.run_key != run_key
            or result.stage != name
            or result.disposition != "complete"
        ):
            raise ValueError(f"Invalid effective weather stage: {name}.")
        return result

    raw_ref = evidence("raw_complete")
    if (raw_ref.artifact_key, raw_ref.relative_path, raw_ref.sha256) != (
        "raw_manifest",
        run["raw_manifest_path"],
        run["raw_manifest_sha256"],
    ):
        raise ValueError("Raw manifest lineage differs from the persisted GFS run.")
    raw = RawManifest.model_validate_json(_read_reference(store, raw_ref, raw=True))
    if (
        raw.run_key,
        raw.source_id,
        raw.source_kind,
        raw.source_product_key,
        raw.reference_at_utc,
        raw.status,
    ) != (
        run_key,
        GFS_SOURCE_ID,
        "forecast",
        run["source_product_key"],
        reference,
        "complete",
    ):
        raise ValueError("Retained raw metadata differs from the persisted GFS identity.")

    feature_ref = evidence("features_built")
    persistence_ref = evidence("persisted")
    persistence = stage(persistence_ref, "persistence")
    receipt_ref = _output(persistence, "weather_persistence_receipt")
    receipt = WeatherPersistenceReceipt.model_validate_json(_read_reference(store, receipt_ref))
    if (
        receipt.run_key != run_key
        or receipt.source_id != GFS_SOURCE_ID
        or receipt.source_product_key != run["source_product_key"]
        or receipt.target_local_date != target.isoformat()
        or receipt.database_identity != database_identity
        or receipt.pipeline_version != run["pipeline_version"]
        or receipt.persistence_version != persistence.producer_version
        or receipt.persistence_input_sha256 != run["persistence_input_sha256"]
        or persistence.configuration.get("persistence_input_sha256")
        != receipt.persistence_input_sha256
        or persistence.configuration.get("usage_policy_sha256") != receipt.usage_policy_sha256
        or receipt.feature_manifest != feature_ref
        or feature_ref not in persistence.inputs
        or (feature_ref.relative_path, feature_ref.sha256)
        != (run["feature_manifest_path"], run["feature_manifest_sha256"])
    ):
        raise ValueError("Persistence receipt, feature boundary and SQLite lineage disagree.")

    feature = stage(feature_ref, "feature_builder")
    validated_ref = evidence("validated")
    if (
        feature.producer_version != policy.feature_builder_version
        or feature.configuration.get("feature_builder_version") != policy.feature_builder_version
        or feature.configuration.get("feature_contract_version") != policy.feature_contract_version
        or feature.configuration.get("policy_version") != policy.weather_policy_version
        or feature.configuration.get("policy_sha256") != feature_policy_sha
        or feature.configuration.get("validator_manifest_sha256") != validated_ref.sha256
        or validated_ref not in feature.inputs
    ):
        raise ValueError("XC prediction requires effective weather feature builder v5/contract 3.")
    daily_ref = _output(feature, "daily_feature_snapshot_batch")
    hourly_ref = _output(feature, "hourly_feature_snapshot_batch")
    daily = DailyFeatureSnapshotBatch.model_validate_json(_read_reference(store, daily_ref))
    hourly = HourlyFeatureSnapshotBatch.model_validate_json(_read_reference(store, hourly_ref))
    days = {snapshot.site_id: snapshot for snapshot in daily.snapshots}
    hours = {snapshot.sample_identity_key: snapshot for snapshot in hourly.snapshots}
    if (
        daily.run_key != run_key
        or hourly.run_key != run_key
        or not days
        or len(days) != len(daily.snapshots)
        or len(hours) != len(hourly.snapshots)
        or len(days) != receipt.table_counts.get("weather_daily_feature_snapshots")
    ):
        raise ValueError(
            "Retained feature batches have inconsistent run, site or sample identities."
        )

    rows_by_site = _persisted_hours(connection, run["id"])
    if set(rows_by_site) != set(days):
        raise ValueError("Retained daily features and persisted sites disagree.")
    valid_times = sofia_window_instants(target.isoformat())
    cutoff = datetime.combine(cycle.date(), time(16), ZoneInfo("Europe/Sofia")).astimezone(UTC)
    lineage = {
        "source_id": GFS_SOURCE_ID,
        "source_product_key": run["source_product_key"],
        "operational_use_allowed": True,
        "feature_builder_version": policy.feature_builder_version,
        "feature_contract_version": policy.feature_contract_version,
        "weather_policy_sha256": feature_policy_sha,
        "usage_policy_sha256": receipt.usage_policy_sha256,
        "persistence_input_sha256": receipt.persistence_input_sha256,
        "references": [
            ref.model_dump(mode="json")
            for ref in (raw_ref, persistence_ref, receipt_ref, feature_ref, daily_ref, hourly_ref)
        ],
    }
    result = []
    for site_id, snapshot in sorted(days.items()):
        rows = rows_by_site[site_id]
        samples = [hours[key] for key in snapshot.input_sample_identity_keys]
        if (
            snapshot.run_key != run_key
            or snapshot.local_date != target.isoformat()
            or snapshot.source_product_key != run["source_product_key"]
            or snapshot.feature_contract_version != policy.feature_contract_version
            or len({row["daily_id"] for row in rows}) != 1
            or tuple(row["valid_at_utc"] for row in rows) != valid_times
            or tuple(sorted(sample.valid_at_utc for sample in samples)) != valid_times
            or any(
                (
                    sample.run_key,
                    sample.site_id,
                    sample.valid_local_date,
                    sample.point_footprint_key,
                    sample.neighbourhood_footprint_key,
                    sample.feature_contract_version,
                )
                != (
                    run_key,
                    site_id,
                    snapshot.local_date,
                    snapshot.point_footprint_key,
                    snapshot.neighbourhood_footprint_key,
                    policy.feature_contract_version,
                )
                for sample in samples
            )
        ):
            raise ValueError(
                "Daily XC inputs require eleven matching hours from the same run and site."
            )
        ready = []
        for row in rows:
            if (
                row["sample_run_id"] != run["id"]
                or row["sample_footprint_id"] != row["point_footprint_id"]
                or row["purpose"] != "point"
                or row["product_run_id"] != run["product_run_id"]
                or row["feature_contract_version"] != policy.feature_contract_version
                or row["lead_hours"]
                != (datetime.fromisoformat(row["valid_at_utc"]) - cycle).total_seconds() / 3600
            ):
                raise ValueError("Persisted XC hourly sample has inconsistent forecast lineage.")
            timestamp = validate_utc_timestamp(row["required_inputs_last_modified_at_utc"])
            if not cycle <= datetime.fromisoformat(timestamp) <= cutoff:
                raise ValueError(
                    "Required GFS inputs must be ready by the 16:00 Europe/Sofia cutoff."
                )
            ready.append(timestamp)
        record = ForecastInput(
            run_key=run_key,
            site_id=site_id,
            site_slug=rows[0]["site_slug"],
            target_local_date=target.isoformat(),
            issue_local_date=cycle.date().isoformat(),
            horizon_days=horizon,
            cycle_reference_utc=reference,
            issue_cutoff_utc=cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
            source_ready_at_utc=max(ready),
            valid_times_utc=valid_times,
            observations=_observations(snapshot, policy),
            source_lineage={
                **lineage,
                "daily_snapshot_sha256": sha256_bytes(canonical_json_bytes(snapshot)),
                "input_sample_identity_keys": list(snapshot.input_sample_identity_keys),
                "hourly_source_ready_at_utc": ready,
            },
        )
        validate_features(record, policy, require_available=False)
        result.append(record)
    return result


def _persisted_hours(connection: sqlite3.Connection, run_id: int) -> dict[int, list[sqlite3.Row]]:
    result: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in connection.execute(
        """SELECT d.id AS daily_id, d.point_footprint_id, d.feature_contract_version,
                  f.site_id, f.purpose, s.slug AS site_slug, x.ingestion_run_id AS sample_run_id,
                  x.point_footprint_id AS sample_footprint_id, v.product_run_id,
                  v.valid_at_utc, v.lead_hours, v.required_inputs_last_modified_at_utc
           FROM weather_daily_feature_snapshots d
           JOIN weather_sampling_footprints f ON f.id = d.point_footprint_id
           JOIN sites s ON s.id = f.site_id
           LEFT JOIN weather_daily_feature_snapshot_inputs i ON i.daily_feature_snapshot_id = d.id
           LEFT JOIN weather_point_samples x ON x.id = i.weather_point_sample_id
           LEFT JOIN weather_product_valid_times v ON v.id = x.product_valid_time_id
           WHERE d.ingestion_run_id = ? ORDER BY f.site_id, v.valid_at_utc""",
        (run_id,),
    ):
        result[row["site_id"]].append(row)
    return result


def read_retained_inputs(
    run_keys: tuple[str, ...], *, project_root: Path, policy: XcPolicy, database_url: str | None
) -> tuple[ForecastInput, ...]:
    """Read exact v5 inputs and verify their bounded weather and SQLite lineage."""
    if (
        not run_keys
        or len(set(run_keys)) != len(run_keys)
        or any(UUID_V4_PATTERN.fullmatch(key) is None for key in run_keys)
    ):
        raise ValueError("Pass one or more distinct lowercase UUID v4 GFS run keys.")
    root = project_root.resolve()
    url = configured_database_url(database_url)
    database_identity = resolve_database_path(url, root).relative_to(root).as_posix()
    _, feature_policy_sha = load_feature_policy(f"{policy.weather_policy_version}.json")
    with closing(open_read_only_database(url, root)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN")
        return tuple(
            row
            for key in sorted(run_keys)
            for row in _read_run(
                connection, root, database_identity, key, policy, feature_policy_sha
            )
        )
