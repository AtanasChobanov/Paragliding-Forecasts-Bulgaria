"""Source-aware offline validation and quarantine for canonical weather samples."""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field

from ...storage.sqlite import DatabaseConfigurationError, open_read_only_database
from ..atmosphere.catalogue import CatalogueError, load_catalogue
from ..atmosphere.contracts import (
    ArtifactReference,
    AtmosphericContract,
    RawManifest,
    StageManifest,
)
from .artifacts import WeatherArtifactStore, stage_input_fingerprint
from .serialization import canonical_json_bytes, sha256_bytes
from .spatial import CanonicalSiteSampleBatch, SiteAlignedSample

WEATHER_VALIDATOR_VERSION = "source-aware-weather-validator/2"
POLICY_RESOURCE = "weather-validation-policy.json"
FIELD_RANGES: dict[str, tuple[float, float]] = {
    "air_temperature_k": (150.0, 350.0),
    "dew_point_temperature_k": (150.0, 350.0),
    "relative_humidity_percent": (0.0, 100.0),
    "cloud_cover_percent": (0.0, 100.0),
    "air_pressure_pa": (1_000.0, 110_000.0),
    "geopotential_height_msl_m": (-500.0, 30_000.0),
    "wind_speed_m_s": (0.0, 150.0),
    "wind_u_m_s": (-150.0, 150.0),
    "wind_v_m_s": (-150.0, 150.0),
    "wind_direction_degrees_from_north": (0.0, 360.0),
}


class WeatherValidationError(RuntimeError):
    """The immutable validation boundary cannot be established or verified."""


class WeatherValidationReason(AtmosphericContract):
    code: str = Field(pattern=r"^[a-z0-9_]+$")
    message: str
    sample_identity_key: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    field_code: str | None = None
    severity: Literal["missing", "quarantine"]


class WeatherSourceSnapshot(AtmosphericContract):
    code: str
    provider_name: str
    dataset_name: str
    source_kind: Literal["forecast", "reanalysis"]
    base_url: str
    is_active: bool
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ValidationSnapshot(AtmosphericContract):
    validation_snapshot_schema_version: Literal[1] = 1
    run_key: str
    validator_version: str = WEATHER_VALIDATOR_VERSION
    policy_version: str
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source: WeatherSourceSnapshot
    upstream_boundary: ArtifactReference
    raw_manifest: ArtifactReference
    exact_upstream_hashes: tuple[str, ...] = Field(min_length=1)


class AcceptedWeatherSamples(AtmosphericContract):
    accepted_weather_samples_schema_version: Literal[1] = 1
    run_key: str
    input_samples: ArtifactReference
    samples: tuple[SiteAlignedSample, ...]


class QuarantinedWeatherSamples(AtmosphericContract):
    quarantined_weather_samples_schema_version: Literal[1] = 1
    run_key: str
    input_samples: ArtifactReference
    samples: tuple[SiteAlignedSample, ...]
    reasons: tuple[WeatherValidationReason, ...]


class MissingWeatherEvidence(AtmosphericContract):
    missing_weather_evidence_schema_version: Literal[1] = 1
    run_key: str
    reasons: tuple[WeatherValidationReason, ...]


class WeatherValidationReport(AtmosphericContract):
    weather_validation_report_schema_version: Literal[1] = 1
    run_key: str
    validator_version: str = WEATHER_VALIDATOR_VERSION
    policy_version: str
    source_code: str
    samples_seen: int = Field(ge=0)
    samples_accepted: int = Field(ge=0)
    samples_quarantined: int = Field(ge=0)
    missing_reason_count: int = Field(ge=0)
    quarantine_reason_count: int = Field(ge=0)
    disposition: Literal["complete", "quarantined"]


class _SourcePolicy(AtmosphericContract):
    source_kind: Literal["forecast", "reanalysis"]
    lead_hours: Literal["required", "forbidden"]
    required_profile_pressures_pa: tuple[int, ...] = Field(min_length=1)
    required_profile_field_codes: tuple[str, ...] = Field(min_length=1)
    nullable_field_codes: tuple[str, ...]
    max_terrain_mismatch_m: float = Field(gt=0)
    max_point_grid_distance_km: float = Field(gt=0)


class _ValidationPolicy(AtmosphericContract):
    policy_version: str
    sources: dict[str, _SourcePolicy] = Field(min_length=1)


def load_validation_policy() -> tuple[_ValidationPolicy, str]:
    payload = (
        files("paragliding_forecasts_ml.ingestion.weather.resources")
        .joinpath(POLICY_RESOURCE)
        .read_bytes()
    )
    try:
        policy = _ValidationPolicy.model_validate_json(payload, strict=True)
    except Exception as error:
        raise WeatherValidationError("Packaged weather validation policy is invalid.") from error
    return policy, sha256_bytes(payload)


def load_weather_source(
    database_url: str, source_code: str, project_root: Path | None = None
) -> WeatherSourceSnapshot:
    try:
        connection = open_read_only_database(database_url, project_root)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                """
                SELECT code, provider_name, dataset_name, source_kind, base_url, is_active
                FROM weather_sources WHERE code = ?
                """,
                (source_code,),
            ).fetchone()
        finally:
            connection.close()
    except (DatabaseConfigurationError, sqlite3.Error) as error:
        raise WeatherValidationError(
            "DATABASE_URL must identify a migrated database with weather_sources."
        ) from error
    if row is None:
        raise WeatherValidationError(f"Weather source is not registered: {source_code}.")
    payload = {
        "code": str(row["code"]),
        "provider_name": str(row["provider_name"]),
        "dataset_name": str(row["dataset_name"]),
        "source_kind": str(row["source_kind"]),
        "base_url": str(row["base_url"]),
        "is_active": bool(row["is_active"]),
    }
    return WeatherSourceSnapshot(**payload, sha256=sha256_bytes(canonical_json_bytes(payload)))


def _stage_manifest(store: WeatherArtifactStore, reference: ArtifactReference) -> StageManifest:
    store.verify_reference(reference, expected_root=store.interim_dir)
    try:
        return StageManifest.model_validate_json(
            (store.project_root / reference.relative_path).read_bytes(), strict=True
        )
    except Exception as error:
        raise WeatherValidationError(
            "Stage manifest is not a valid atmospheric contract."
        ) from error


def _find_raw_manifest(
    store: WeatherArtifactStore, reference: ArtifactReference
) -> ArtifactReference:
    if reference.artifact_key == "raw_manifest":
        store.verify_raw_manifest(reference)
        return reference
    manifest = _stage_manifest(store, reference)
    for item in manifest.inputs:
        try:
            return _find_raw_manifest(store, item)
        except WeatherValidationError:
            continue
    raise WeatherValidationError("Spatial boundary does not lead to an immutable raw manifest.")


def _spatial_samples_reference(manifest: StageManifest) -> ArtifactReference:
    if manifest.stage != "spatial" or manifest.disposition != "complete":
        raise WeatherValidationError("weather-validate requires a complete spatial stage manifest.")
    matches = [
        item for item in manifest.outputs if item.artifact_key == "canonical_site_sample_batch"
    ]
    if len(matches) != 1:
        raise WeatherValidationError("Spatial stage must expose one canonical-site sample batch.")
    return matches[0]


def _load_samples(
    store: WeatherArtifactStore, reference: ArtifactReference, run_key: str
) -> tuple[SiteAlignedSample, ...]:
    """Load S05 v2 directly or convert the old coverage-bearing v1 evidence in memory."""

    path = store.verify_reference(reference, expected_root=store.interim_dir)
    try:
        payload = json.loads(path.read_bytes())
        version = payload.get("canonical_site_sample_batch_schema_version")
        if version == 2:
            batch = CanonicalSiteSampleBatch.model_validate_json(path.read_bytes(), strict=True)
            samples = batch.samples
        elif version == 1:
            raw_samples = payload["samples"]
            if not isinstance(raw_samples, list):
                raise ValueError("v1 samples must be an array")
            samples = tuple(
                SiteAlignedSample.model_validate_json(
                    json.dumps(
                        {key: value for key, value in item.items() if key != "coverage_status"}
                    ),
                    strict=True,
                )
                for item in raw_samples
            )
        else:
            raise ValueError("unsupported sample schema version")
    except (KeyError, TypeError, ValueError) as error:
        raise WeatherValidationError(
            "Canonical site samples have an unsupported S05 contract."
        ) from error
    if payload.get("run_key") != run_key:
        raise WeatherValidationError("Canonical site samples belong to another run.")
    return samples


def _grid_distance_reasons(
    store: WeatherArtifactStore,
    reference: ArtifactReference,
    samples: tuple[SiteAlignedSample, ...],
    policy: _SourcePolicy,
) -> list[WeatherValidationReason]:
    """Verify S05 retains valid point-footprint/grid distance evidence."""

    try:
        payload = json.loads(
            store.verify_reference(reference, expected_root=store.interim_dir).read_bytes()
        )
        point_footprints = payload["point_footprints"]
    except (KeyError, TypeError, ValueError) as error:
        raise WeatherValidationError(
            "Spatial artifact lacks readable point-footprint evidence."
        ) from error
    if not isinstance(point_footprints, list):
        raise WeatherValidationError("Spatial point-footprint evidence has the wrong shape.")
    by_key = {
        item.get("footprint_key"): item
        for item in point_footprints
        if isinstance(item, dict) and isinstance(item.get("footprint_key"), str)
    }
    reasons: list[WeatherValidationReason] = []
    for sample in samples:
        footprint = by_key.get(sample.point_footprint_key)
        if not isinstance(footprint, dict) or footprint.get("site_id") != sample.site_id:
            reasons.append(
                _reason(
                    "point_footprint_mismatch",
                    "Sample does not reference a point footprint for its reviewed site.",
                    sample,
                )
            )
            continue
        nodes = footprint.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            reasons.append(
                _reason(
                    "point_footprint_nodes_missing",
                    "Point footprint has no grid-node distance evidence.",
                    sample,
                )
            )
            continue
        distances = [node.get("distance_km") for node in nodes if isinstance(node, dict)]
        if (
            len(distances) != len(nodes)
            or any(not isinstance(value, (int, float)) or value < 0 for value in distances)
            or any(value > policy.max_point_grid_distance_km for value in distances)
        ):
            reasons.append(
                _reason(
                    "point_grid_distance_invalid",
                    "Point-footprint grid distances violate the source policy.",
                    sample,
                )
            )
    return reasons


def _verify_raw_payloads(
    store: WeatherArtifactStore, manifest: RawManifest
) -> list[WeatherValidationReason]:
    """Verify the source-owned role, content type, and stable payload shape."""

    reasons: list[WeatherValidationReason] = []
    for artifact in manifest.artifacts:
        path = store.verify_reference(artifact, expected_root=store.raw_dir)
        content = path.read_bytes()
        if manifest.source_id != "noaa_gfs_0p25_aws_grib2":
            if not artifact.media_type:
                reasons.append(
                    WeatherValidationReason(
                        code="payload_media_type_missing",
                        message="Raw payload has no declared media type.",
                        severity="quarantine",
                    )
                )
            continue
        if artifact.artifact_key.startswith("gfs_idx_"):
            expected_type = "text/plain"
            invalid_shape = not content.strip()
            shape_code = "payload_empty_index"
        elif artifact.artifact_key.startswith("gfs_grib_"):
            expected_type = "application/x-grib2"
            invalid_shape = content[:4] != b"GRIB"
            shape_code = "payload_magic_mismatch"
        elif artifact.artifact_key == "gfs_collection_record":
            expected_type = "application/json"
            try:
                record = json.loads(content)
                invalid_shape = not isinstance(record, dict)
            except (TypeError, ValueError):
                invalid_shape = True
            shape_code = "payload_json_shape_mismatch"
        else:
            reasons.append(
                WeatherValidationReason(
                    code="payload_role_unknown",
                    message="GFS raw manifest contains an unknown artifact role.",
                    severity="quarantine",
                )
            )
            continue
        if artifact.media_type != expected_type:
            reasons.append(
                WeatherValidationReason(
                    code="payload_media_type_mismatch",
                    message="GFS artifact media type is incompatible with its artifact role.",
                    severity="quarantine",
                )
            )
        elif invalid_shape:
            reasons.append(
                WeatherValidationReason(
                    code=shape_code,
                    message="GFS payload does not satisfy the required artifact shape.",
                    severity="quarantine",
                )
            )
    return reasons


def _below_terrain_exclusions(
    store: WeatherArtifactStore, reference: ArtifactReference
) -> frozenset[tuple[int, str, float]]:
    """Return S05's explicit non-penalizing below-terrain level exclusions."""

    try:
        payload = json.loads(
            store.verify_reference(reference, expected_root=store.interim_dir).read_bytes()
        )
        exclusions = payload["pressure_level_exclusions"]
    except (KeyError, TypeError, ValueError) as error:
        raise WeatherValidationError(
            "Spatial artifact lacks readable pressure-level exclusion evidence."
        ) from error
    if not isinstance(exclusions, list):
        raise WeatherValidationError("Pressure-level exclusions have the wrong shape.")
    return frozenset(
        (int(item["site_id"]), str(item["valid_at_utc"]), float(item["pressure_pa"]))
        for item in exclusions
        if isinstance(item, dict) and item.get("code") == "below_site_or_model_terrain"
    )


def _reason(
    code: str, message: str, sample: SiteAlignedSample, field: str | None = None
) -> WeatherValidationReason:
    return WeatherValidationReason(
        code=code,
        message=message,
        sample_identity_key=sample.sample_identity_key,
        field_code=field,
        severity="quarantine",
    )


def _check_sample(
    sample: SiteAlignedSample,
    policy: _SourcePolicy,
    *,
    below_terrain_exclusions: frozenset[tuple[int, str, float]] = frozenset(),
) -> tuple[list[WeatherValidationReason], list[WeatherValidationReason]]:
    quarantine: list[WeatherValidationReason] = []
    missing: list[WeatherValidationReason] = []
    seen: set[tuple[str, str | None, float | None]] = set()
    fields = (
        *sample.fields,
        *(field for profile in sample.profile_levels for field in profile.fields),
    )
    for field in fields:
        key = (field.field_code, field.dimension, field.pressure_pa)
        if key in seen:
            quarantine.append(
                _reason(
                    "duplicate_field",
                    "A sample contains a duplicate field identity.",
                    sample,
                    field.field_code,
                )
            )
        seen.add(key)
        try:
            expected_unit = load_catalogue().field_unit(field.field_code)
        except CatalogueError:
            quarantine.append(
                _reason(
                    "unknown_field",
                    "Field is not in the canonical catalogue.",
                    sample,
                    field.field_code,
                )
            )
            continue
        if field.canonical_unit != expected_unit:
            quarantine.append(
                _reason(
                    "canonical_unit_mismatch",
                    "Field canonical unit differs from the catalogue.",
                    sample,
                    field.field_code,
                )
            )
        if field.canonical_value is not None and not math.isfinite(field.canonical_value):
            quarantine.append(
                _reason("non_finite_value", "Field value is not finite.", sample, field.field_code)
            )
        field_range = FIELD_RANGES.get(field.field_code)
        if (
            field.canonical_value is not None
            and field_range is not None
            and not field_range[0] <= field.canonical_value <= field_range[1]
        ):
            quarantine.append(
                _reason(
                    "field_value_out_of_range",
                    "Field value exceeds the canonical physical range.",
                    sample,
                    field.field_code,
                )
            )
        if field.field_code in policy.nullable_field_codes:
            continue
        if field.canonical_value is None and field.quality_state not in {
            "missing",
            "sentinel_missing",
        }:
            quarantine.append(
                _reason(
                    "missing_value_quality_mismatch",
                    "Null field value lacks an explicit missing quality state.",
                    sample,
                    field.field_code,
                )
            )
    if sample.terrain.absolute_mismatch_m > policy.max_terrain_mismatch_m:
        quarantine.append(
            _reason(
                "terrain_elevation_mismatch",
                "Model and reviewed site elevation exceed the source policy limit.",
                sample,
            )
        )
    expected_pressures = tuple(sorted(policy.required_profile_pressures_pa, reverse=True))
    actual_pressures = tuple(profile.pressure_pa for profile in sample.profile_levels)
    if actual_pressures != tuple(sorted(actual_pressures, reverse=True)) or len(
        actual_pressures
    ) != len(set(actual_pressures)):
        quarantine.append(
            _reason(
                "profile_order_or_duplicate",
                "Profile levels must be uniquely ordered from high to low pressure.",
                sample,
            )
        )
    profiles = {profile.pressure_pa: profile for profile in sample.profile_levels}
    for pressure in expected_pressures:
        profile = profiles.get(float(pressure))
        if profile is None:
            if (sample.site_id, sample.valid_at_utc, float(pressure)) in below_terrain_exclusions:
                missing.append(
                    WeatherValidationReason(
                        code="profile_below_terrain",
                        message="Required profile is explicitly below reviewed site or model terrain.",
                        sample_identity_key=sample.sample_identity_key,
                        severity="missing",
                    )
                )
            else:
                quarantine.append(
                    _reason(
                        "required_profile_missing",
                        f"Required {pressure} Pa profile is absent.",
                        sample,
                    )
                )
            continue
        by_field = {field.field_code: field for field in profile.fields}
        for field_code in policy.required_profile_field_codes:
            field = by_field.get(field_code)
            if field is None or field.canonical_value is None:
                quarantine.append(
                    _reason(
                        "required_profile_field_missing",
                        "Required profile core field is missing.",
                        sample,
                        field_code,
                    )
                )
    try:
        valid_at = datetime.fromisoformat(sample.valid_at_utc)
        reference_at = datetime.fromisoformat(sample.reference_at_utc)
        expected_local_date = valid_at.astimezone(ZoneInfo("Europe/Sofia")).date().isoformat()
    except ValueError:
        quarantine.append(
            _reason("time_axis_invalid", "Sample time axis is not canonical UTC.", sample)
        )
    else:
        if sample.valid_local_date != expected_local_date:
            quarantine.append(
                _reason(
                    "local_date_mismatch", "Local date does not match the valid UTC time.", sample
                )
            )
        if policy.lead_hours == "required" and sample.lead_hours is not None:
            expected_valid = reference_at.timestamp() + sample.lead_hours * 3600
            if not math.isclose(valid_at.timestamp(), expected_valid, abs_tol=1.0):
                quarantine.append(
                    _reason(
                        "lead_time_mismatch",
                        "Forecast reference, lead, and valid times disagree.",
                        sample,
                    )
                )
    if policy.lead_hours == "required" and sample.lead_hours is None:
        quarantine.append(
            _reason("lead_hours_missing", "Forecast sample must declare lead hours.", sample)
        )
    if policy.lead_hours == "forbidden" and sample.lead_hours is not None:
        quarantine.append(
            _reason(
                "lead_hours_forbidden",
                "Reanalysis sample must not declare forecast lead hours.",
                sample,
            )
        )
    if not quarantine and not fields:
        missing.append(
            WeatherValidationReason(
                code="no_fields",
                message="Sample has no available fields.",
                sample_identity_key=sample.sample_identity_key,
                severity="missing",
            )
        )
    return quarantine, missing


def validate_weather_run(
    store: WeatherArtifactStore,
    spatial_manifest_reference: ArtifactReference,
    *,
    database_url: str,
    occurred_at_utc: str,
    project_root: Path | None = None,
) -> ArtifactReference:
    """Validate one immutable S05 boundary and write partitioned S06 evidence."""

    del project_root
    store.verify_boundary(spatial_manifest_reference)
    spatial_manifest = _stage_manifest(store, spatial_manifest_reference)
    samples_reference = _spatial_samples_reference(spatial_manifest)
    raw_reference = _find_raw_manifest(store, spatial_manifest_reference)
    raw_manifest = store.verify_raw_manifest(raw_reference)
    source = load_weather_source(database_url, raw_manifest.source_id, store.project_root)
    policy, policy_sha256 = load_validation_policy()
    source_policy = policy.sources.get(raw_manifest.source_id)
    if source_policy is None or not source.is_active:
        raise WeatherValidationError(
            "Raw source is not active in the validation policy and registry."
        )
    if (
        source.source_kind != raw_manifest.source_kind
        or source.source_kind != source_policy.source_kind
    ):
        raise WeatherValidationError(
            "Raw source kind conflicts with the registry or validation policy."
        )
    samples = _load_samples(store, samples_reference, store.run_key)
    below_terrain_exclusions = _below_terrain_exclusions(store, samples_reference)
    grid_reasons = _grid_distance_reasons(store, samples_reference, samples, source_policy)
    payload_reasons = _verify_raw_payloads(store, raw_manifest)
    accepted: list[SiteAlignedSample] = []
    quarantined: list[SiteAlignedSample] = []
    quarantine_reasons = list(grid_reasons)
    missing_reasons: list[WeatherValidationReason] = []
    seen_samples: set[str] = set()
    for sample in samples:
        sample_reasons, sample_missing = _check_sample(
            sample, source_policy, below_terrain_exclusions=below_terrain_exclusions
        )
        if sample.sample_identity_key in seen_samples:
            sample_reasons.append(
                _reason("duplicate_sample", "Sample identity occurs more than once.", sample)
            )
        seen_samples.add(sample.sample_identity_key)
        if payload_reasons:
            sample_reasons.extend(payload_reasons)
        sample_reasons.extend(
            reason
            for reason in grid_reasons
            if reason.sample_identity_key == sample.sample_identity_key
        )
        if sample_reasons:
            quarantined.append(sample)
            quarantine_reasons.extend(sample_reasons)
        else:
            accepted.append(sample)
        missing_reasons.extend(sample_missing)
    configuration = {
        "policy_version": policy.policy_version,
        "policy_sha256": policy_sha256,
        "source_registry_sha256": source.sha256,
        "source_code": source.code,
    }
    fingerprint = stage_input_fingerprint(
        stage="validator",
        producer_version=WEATHER_VALIDATOR_VERSION,
        inputs=(spatial_manifest_reference,),
        configuration=configuration,
    )
    existing = store.existing_stage_manifest("validator", WEATHER_VALIDATOR_VERSION, fingerprint)
    if existing is not None:
        return existing
    directory = store.begin_stage("validator", WEATHER_VALIDATOR_VERSION, fingerprint)
    snapshot = store.write_stage_model(
        directory,
        "validation-snapshot.json",
        "validation_snapshot",
        ValidationSnapshot(
            run_key=store.run_key,
            policy_version=policy.policy_version,
            policy_sha256=policy_sha256,
            source=source,
            upstream_boundary=spatial_manifest_reference,
            raw_manifest=raw_reference,
            exact_upstream_hashes=tuple(
                sorted(
                    {
                        spatial_manifest_reference.sha256,
                        samples_reference.sha256,
                        raw_reference.sha256,
                        *(item.sha256 for item in raw_manifest.artifacts),
                    }
                )
            ),
        ),
    )
    accepted_reference = store.write_stage_model(
        directory,
        "accepted-samples.json",
        "accepted_weather_samples",
        AcceptedWeatherSamples(
            run_key=store.run_key, input_samples=samples_reference, samples=tuple(accepted)
        ),
        record_count=len(accepted),
    )
    missing_reference = store.write_stage_model(
        directory,
        "missing-evidence.json",
        "missing_weather_evidence",
        MissingWeatherEvidence(run_key=store.run_key, reasons=tuple(missing_reasons)),
        record_count=len(missing_reasons),
    )
    quarantined_reference = store.write_stage_model(
        directory,
        "quarantined-samples.json",
        "quarantined_weather_samples",
        QuarantinedWeatherSamples(
            run_key=store.run_key,
            input_samples=samples_reference,
            samples=tuple(quarantined),
            reasons=tuple(quarantine_reasons),
        ),
        record_count=len(quarantined),
    )
    disposition: Literal["complete", "quarantined"] = "quarantined" if quarantined else "complete"
    report_reference = store.write_stage_model(
        directory,
        "validation-report.json",
        "weather_validation_report",
        WeatherValidationReport(
            run_key=store.run_key,
            policy_version=policy.policy_version,
            source_code=source.code,
            samples_seen=len(samples),
            samples_accepted=len(accepted),
            samples_quarantined=len(quarantined),
            missing_reason_count=len(missing_reasons),
            quarantine_reason_count=len(quarantine_reasons),
            disposition=disposition,
        ),
    )
    return store.write_stage_manifest(
        directory,
        StageManifest(
            run_key=store.run_key,
            stage="validator",
            producer_version=WEATHER_VALIDATOR_VERSION,
            input_fingerprint_sha256=fingerprint,
            inputs=(spatial_manifest_reference,),
            outputs=(
                snapshot,
                accepted_reference,
                missing_reference,
                quarantined_reference,
                report_reference,
            ),
            configuration=configuration,
            disposition=disposition,
            started_at_utc=occurred_at_utc,
            completed_at_utc=occurred_at_utc,
        ),
    )


def validation_version(store: WeatherArtifactStore, reference: ArtifactReference) -> str:
    """Return the producer version of one verified validator stage."""

    return _stage_manifest(store, reference).producer_version


def validation_upstream_boundary(
    store: WeatherArtifactStore, reference: ArtifactReference
) -> ArtifactReference:
    """Return the one spatial boundary that a validator boundary verified."""

    manifest = _stage_manifest(store, reference)
    if manifest.stage != "validator" or len(manifest.inputs) != 1:
        raise WeatherValidationError("Validation boundary has an invalid upstream manifest shape.")
    return manifest.inputs[0]


def validation_disposition(store: WeatherArtifactStore, reference: ArtifactReference) -> str:
    manifest = _stage_manifest(store, reference)
    return manifest.disposition
