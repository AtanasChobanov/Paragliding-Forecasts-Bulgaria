"""Read the verified S06 weather evidence and its effective persistence lineage."""

import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import date, datetime, time
from math import isfinite
from pathlib import Path
from zoneinfo import ZoneInfo

from ...ingestion.atmosphere.contracts import (
    UUID_V4_PATTERN,
    ArtifactReference,
    RawManifest,
    StageManifest,
    validate_utc_timestamp,
)
from ...ingestion.gfs.models import GFS_SOURCE_ID
from ...ingestion.weather.artifacts import WeatherArtifactStore
from ...ingestion.weather.features.aggregation import FlyingWindow, sofia_flying_window
from ...ingestion.weather.features.contracts import DailyFeatureSnapshotBatch
from ...ingestion.weather.features.policy import load_feature_policy
from ...ingestion.weather.persistence_models import WeatherPersistenceReceipt
from ...ingestion.weather.serialization import sha256_bytes
from ...ingestion.weather.spatial import SampledField, SiteAlignedSample
from ...ingestion.weather.state import RunStateLedger
from ...ingestion.weather.validation import AcceptedWeatherSamples, ValidationSnapshot
from ...storage.sqlite import (
    configured_database_url,
    open_read_only_database,
    resolve_database_path,
)
from .models import FIELD_UNITS, FieldKey, ForecastDay, Observation, observation_layout

SELECTORS = {
    ("precipitation_amount_mm", "interval", None): ("rain", {"apcp"}),
    ("convective_available_potential_energy_j_per_kg", "convection", "surface"): (
        "cape",
        {"cape_surface"},
    ),
    ("convective_inhibition_magnitude_j_per_kg", "convection", "surface"): (
        "cin",
        {"cin_surface"},
    ),
    ("cloud_cover_percent", "surface", "low"): ("low_cloud", {"lcdc"}),
    ("relative_humidity_percent", "surface", "2m_above_ground"): ("humidity", {"rh_2m"}),
    ("wind_speed_m_s", "surface", "10m_above_ground"): ("wind", {"ugrd_10m", "vgrd_10m"}),
}


def _sample_fields(
    samples: tuple[SiteAlignedSample, ...], window: FlyingWindow
) -> tuple[Observation, ...]:
    layout = observation_layout(window)
    expected = set(layout)
    fields: dict[tuple[str, FieldKey, str | None], SampledField] = {}
    unresolved: set[tuple[str, FieldKey, str | None]] = set()
    for sample in samples:
        for field in sample.fields:
            selector = SELECTORS.get((field.field_code, field.grain, field.dimension))
            if selector is None:
                continue
            key, source_selectors = selector
            if field.canonical_unit != FIELD_UNITS[key]:
                raise ValueError(f"Unexpected unit for retained OD field {key}.")
            if set(field.source_selector_keys) != source_selectors or field.pressure_pa is not None:
                raise ValueError(f"Unexpected native identity for retained OD field {key}.")
            if key == "rain":
                start, end = field.interval_start_utc, field.interval_end_utc
                if (
                    start is None
                    or end is None
                    or validate_utc_timestamp(start) >= validate_utc_timestamp(end)
                    or end != sample.valid_at_utc
                    or field.statistic_type != "accumulation"
                ):
                    raise ValueError("Invalid retained OD precipitation interval.")
                locator = (start, key, end)
                if locator not in expected:
                    unresolved.update(
                        slot
                        for slot in layout
                        if slot[1] == "rain"
                        and slot[2] is not None
                        and start < slot[2]
                        and end > slot[0]
                    )
                    continue
            else:
                if any(
                    value is not None
                    for value in (
                        field.interval_start_utc,
                        field.interval_end_utc,
                        field.statistic_type,
                    )
                ):
                    raise ValueError(f"Expected instantaneous retained OD field {key}.")
                locator = (sample.valid_at_utc, key, None)
                if locator not in expected:
                    continue
            if locator in fields:
                raise ValueError(f"Duplicate retained OD field or interval: {locator}.")
            fields[locator] = field

    observations = []
    for locator in layout:
        start, key, end = locator
        field = fields.get(locator)
        value = field.canonical_value if field is not None else None
        reason = None
        if field is None:
            reason = "interval_unresolved" if locator in unresolved else "field_absent"
        elif field.quality_state not in {"real", "derived"} or value is None:
            reason = field.missing_reason or "value_unavailable"
        elif not isfinite(value) or value < 0 or (FIELD_UNITS[key] == "%" and value > 100):
            reason = field.missing_reason or "invalid_value"
        observations.append(
            Observation(
                key=key,
                valid_at_utc=start,
                interval_end_utc=end,
                unit=FIELD_UNITS[key],
                value=value if reason is None else None,
                quality=field.quality_state if field else "missing",
                missing_reason=reason,
                source_selector_keys=field.source_selector_keys if field else (),
                source_raw_artifact_keys=field.source_raw_artifact_keys if field else (),
                source_native_message_references=field.source_native_message_references
                if field
                else (),
            )
        )
    return tuple(observations)


def _retained_batches(
    root: Path, run: sqlite3.Row, database_identity: str
) -> tuple[AcceptedWeatherSamples, DailyFeatureSnapshotBatch, dict]:
    run_key = run["run_key"]
    store = WeatherArtifactStore(run_key, project_root=root)
    state = RunStateLedger(store).load_state()
    references = []

    def read(ref: ArtifactReference) -> bytes:
        path = store.verify_reference(
            ref,
            expected_root=store.raw_dir
            if ref.artifact_key == "raw_manifest"
            else store.interim_dir,
        )
        payload = path.read_bytes()
        if len(payload) != ref.byte_count or sha256_bytes(payload) != ref.sha256:
            raise ValueError(f"Retained OD artifact changed while reading {ref.artifact_key}.")
        references.append(ref.model_dump(mode="json"))
        return payload

    def event_ref(name: str) -> ArtifactReference:
        event = state.effective_event(name)
        if event is None or event.evidence is None:
            raise ValueError(f"Missing effective OD source evidence: {name}.")
        return event.evidence

    def stage(event: str, name: str) -> tuple[ArtifactReference, StageManifest]:
        ref = event_ref(event)
        manifest = StageManifest.model_validate_json(read(ref))
        if (ref.artifact_key, manifest.stage, manifest.disposition, manifest.run_key) != (
            "stage_manifest",
            name,
            "complete",
            run_key,
        ):
            raise ValueError(f"Invalid effective OD source stage: {name}.")
        return ref, manifest

    def output(manifest: StageManifest, key: str) -> ArtifactReference:
        matches = [ref for ref in manifest.outputs if ref.artifact_key == key]
        if len(matches) != 1:
            raise ValueError(f"Expected one OD source output: {key}.")
        return matches[0]

    raw_ref = event_ref("raw_complete")
    if (raw_ref.artifact_key, raw_ref.relative_path, raw_ref.sha256) != (
        "raw_manifest",
        run["raw_manifest_path"],
        run["raw_manifest_sha256"],
    ):
        raise ValueError("OD raw manifest reference differs from SQLite.")
    raw = RawManifest.model_validate_json(read(raw_ref))
    if (
        raw.run_key,
        raw.source_id,
        raw.source_kind,
        raw.status,
        raw.source_product_key,
        raw.reference_at_utc,
    ) != (
        run_key,
        GFS_SOURCE_ID,
        "forecast",
        "complete",
        run["source_product_key"],
        run["reference_at_utc"],
    ):
        raise ValueError("OD raw manifest identity differs from SQLite.")

    spatial_ref, spatial = stage("spatially_aligned", "spatial")
    validator_ref, validator = stage("validated", "validator")
    validation = ValidationSnapshot.model_validate_json(
        read(output(validator, "validation_snapshot"))
    )
    accepted_ref = output(validator, "accepted_weather_samples")
    accepted = AcceptedWeatherSamples.model_validate_json(read(accepted_ref))
    if (
        validation.run_key != run_key
        or validation.validator_version != validator.producer_version
        or validation.source.code != GFS_SOURCE_ID
        or validation.source.source_kind != "forecast"
        or validation.raw_manifest != raw_ref
        or validation.upstream_boundary != spatial_ref
        or spatial_ref not in validator.inputs
        or accepted.run_key != run_key
        or accepted.input_samples != output(spatial, "canonical_site_sample_batch")
    ):
        raise ValueError("OD accepted samples and validation lineage disagree.")

    feature_ref, feature = stage("features_built", "feature_builder")
    weather_policy, weather_sha = load_feature_policy("weather-feature-policy-v5.json")
    expected_config = {
        "feature_builder_version": weather_policy.feature_builder_version,
        "feature_contract_version": weather_policy.feature_contract_version,
        "policy_version": weather_policy.policy_version,
        "policy_sha256": weather_sha,
        "validator_manifest_sha256": validator_ref.sha256,
    }
    if (
        feature.producer_version != weather_policy.feature_builder_version
        or any(feature.configuration.get(key) != value for key, value in expected_config.items())
        or validator_ref not in feature.inputs
        or accepted_ref not in feature.inputs
        or (feature_ref.relative_path, feature_ref.sha256)
        != (run["feature_manifest_path"], run["feature_manifest_sha256"])
    ):
        raise ValueError("OD requires the effective v5/contract 3 feature lineage.")
    daily = DailyFeatureSnapshotBatch.model_validate_json(
        read(output(feature, "daily_feature_snapshot_batch"))
    )
    _, persistence = stage("persisted", "persistence")
    receipt = WeatherPersistenceReceipt.model_validate_json(
        read(output(persistence, "weather_persistence_receipt"))
    )
    if (
        receipt.run_key != run_key
        or receipt.source_id != GFS_SOURCE_ID
        or receipt.source_product_key != run["source_product_key"]
        or receipt.target_local_date != run["target_local_date"]
        or receipt.database_identity != database_identity
        or receipt.pipeline_version != run["pipeline_version"]
        or receipt.persistence_version != persistence.producer_version
        or receipt.persistence_input_sha256 != run["persistence_input_sha256"]
        or receipt.persistence_input_sha256
        != persistence.configuration.get("persistence_input_sha256")
        or receipt.usage_policy_sha256 != persistence.configuration.get("usage_policy_sha256")
        or receipt.feature_manifest != feature_ref
        or feature_ref not in persistence.inputs
        or daily.run_key != run_key
        or len(daily.snapshots) != receipt.table_counts.get("weather_daily_feature_snapshots")
    ):
        raise ValueError("OD persistence receipt, feature batch and SQLite lineage disagree.")
    return (
        accepted,
        daily,
        {
            "run_key": run_key,
            "database_identity": database_identity,
            "usage_policy_sha256": receipt.usage_policy_sha256,
            "persistence_input_sha256": receipt.persistence_input_sha256,
            "references": references,
        },
    )


def _read_run(
    connection: sqlite3.Connection, root: Path, database_identity: str, run_key: str
) -> tuple[list[ForecastDay], dict]:
    run = connection.execute(
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
    ).fetchone()
    if run is None:
        raise ValueError(f"Unknown persisted OD run: {run_key}.")
    cycle = datetime.fromisoformat(validate_utc_timestamp(run["reference_at_utc"]))
    issue = cycle.astimezone(ZoneInfo("Europe/Sofia")).date()
    target = date.fromisoformat(run["target_local_date"])
    horizon = (target - issue).days
    if (
        run["status"] != "succeeded"
        or run["source_id"] != GFS_SOURCE_ID
        or run["source_kind"] != "forecast"
        or run["operational_use_allowed"] != 1
        or cycle.time() != time(6)
        or horizon not in (1, 2, 3)
        or target.isoformat() != run["target_local_date"]
    ):
        raise ValueError("OD requires an authorized, succeeded GFS 06Z D+1/D+2/D+3 run.")

    window = sofia_flying_window(target)
    accepted, daily, source = _retained_batches(root, run, database_identity)
    samples_by_site = defaultdict(list)
    for sample in accepted.samples:
        samples_by_site[sample.site_id].append(sample)
    rows_by_site = defaultdict(list)
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
        (run["id"],),
    ):
        rows_by_site[row["site_id"]].append(row)
    days = {day.site_id: day for day in daily.snapshots}
    if (
        not days
        or len(days) != len(daily.snapshots)
        or set(days) != set(rows_by_site)
        or set(days) != set(samples_by_site)
        or len({sample.sample_identity_key for sample in accepted.samples}) != len(accepted.samples)
    ):
        raise ValueError("OD retained and persisted site or sample identities disagree.")

    result = []
    for site_id, day in sorted(days.items()):
        samples = tuple(sorted(samples_by_site[site_id], key=lambda item: item.valid_at_utc))
        rows = rows_by_site[site_id]
        if (
            day.run_key != run_key
            or day.local_date != target.isoformat()
            or day.source_product_key != run["source_product_key"]
            or day.feature_contract_version != "weather-feature-contract/3"
            or set(day.input_sample_identity_keys)
            != {sample.sample_identity_key for sample in samples}
            or len(day.input_sample_identity_keys) != len(samples)
            or tuple(sample.valid_at_utc for sample in samples) != window.expected_instants_utc
            or tuple(row["valid_at_utc"] for row in rows) != window.expected_instants_utc
            or len({row["daily_id"] for row in rows}) != 1
        ):
            raise ValueError(f"OD site {site_id} does not have eleven matching retained hours.")
        ready = []
        for row, sample in zip(rows, samples, strict=True):
            lead = (datetime.fromisoformat(sample.valid_at_utc) - cycle).total_seconds() / 3600
            if (
                sample.reference_at_utc != run["reference_at_utc"]
                or sample.valid_local_date != day.local_date
                or sample.point_footprint_key != day.point_footprint_key
                or sample.neighbourhood_footprint_key != day.neighbourhood_footprint_key
                or sample.lead_hours != lead
                or row["lead_hours"] != lead
                or row["sample_run_id"] != run["id"]
                or row["sample_footprint_id"] != row["point_footprint_id"]
                or row["purpose"] != "point"
                or row["product_run_id"] != run["product_run_id"]
                or row["feature_contract_version"] != day.feature_contract_version
            ):
                raise ValueError(f"OD site {site_id} has inconsistent forecast lineage.")
            stamp = row["required_inputs_last_modified_at_utc"]
            if stamp is None:
                raise ValueError(
                    f"OD site {site_id} lacks source readiness at {sample.valid_at_utc}."
                )
            ready.append(validate_utc_timestamp(stamp))
        result.append(
            ForecastDay(
                run_key=run_key,
                site_id=site_id,
                site_slug=rows[0]["site_slug"],
                point_footprint_key=day.point_footprint_key,
                target_local_date=target.isoformat(),
                source_product_key=run["source_product_key"],
                issue_local_date=issue.isoformat(),
                cycle_reference_utc=run["reference_at_utc"],
                horizon_days=horizon,
                window_start_utc=window.interval_start_utc,
                window_end_utc=window.interval_end_utc,
                hourly_source_ready_at_utc=tuple(ready),
                source_ready_at_utc=max(ready),
                observations=_sample_fields(samples, window),
            )
        )
    return result, source


def read_inputs(
    run_keys: list[str], *, project_root: Path, database_url: str | None
) -> tuple[list[ForecastDay], list[dict]]:
    if (
        not run_keys
        or len(set(run_keys)) != len(run_keys)
        or any(UUID_V4_PATTERN.fullmatch(key) is None for key in run_keys)
    ):
        raise ValueError("Pass one or more distinct lowercase UUID v4 GFS run keys.")
    url = configured_database_url(database_url)
    database_identity = (
        resolve_database_path(url, project_root).relative_to(project_root).as_posix()
    )
    days, sources = [], []
    with closing(open_read_only_database(url, project_root)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN")
        for key in sorted(run_keys):
            inputs, source = _read_run(connection, project_root, database_identity, key)
            days.extend(inputs)
            sources.append(source)
    return days, sources
