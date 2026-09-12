"""Atomic, source-neutral persistence for verified weather feature boundaries."""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from paragliding_forecasts_ml.storage.sqlite import (
    DatabaseConfigurationError,
    configured_database_url,
    open_writable_database,
    resolve_database_path,
)

from ..atmosphere.contracts import ArtifactReference, RawManifest, RequestPlan, StageManifest
from .artifacts import ArtifactError, WeatherArtifactStore, stage_input_fingerprint
from .features.contracts import (
    DailyFeatureSnapshot,
    DailyFeatureSnapshotBatch,
    FeatureQualityReport,
    FeatureValue,
    HourlyFeatureSnapshot,
    HourlyFeatureSnapshotBatch,
)
from .persistence_models import (
    WEATHER_PERSISTENCE_VERSION,
    WeatherPersistenceFailure,
    WeatherPersistenceReceipt,
    WeatherUsagePolicy,
    load_weather_usage_policy,
)
from .serialization import canonical_json_bytes, sha256_bytes
from .spatial import CanonicalSiteSampleBatch, SamplingFootprint, SiteAlignedSample
from .state import RunStateLedger, StateError
from .validation import (
    AcceptedWeatherSamples,
    ValidationSnapshot,
    validation_upstream_boundary,
)


class WeatherPersistenceError(RuntimeError):
    """Weather artifacts, policy, configuration, or SQLite facts are incompatible."""


MAPPING_REGISTRY_VERSION = "weather-persistence-mapping/1"

# These explicit registries are intentionally complete. Unknown active feature keys
# fail preparation rather than being silently dropped from an immutable run.
HOURLY_POINT_COLUMNS = {
    "air_temperature_2m_k": "air_temperature_2m_k",
    "dew_point_temperature_2m_k": "dew_point_temperature_2m_k",
    "relative_humidity_2m_percent": "relative_humidity_2m_percent",
    "specific_humidity_2m_kg_per_kg": "specific_humidity_2m_kg_per_kg",
    "surface_pressure_pa": "surface_pressure_pa",
    "mean_sea_level_pressure_pa": "mean_sea_level_pressure_pa",
    "wind_u_10m_m_s": "wind_u_10m_m_s",
    "wind_v_10m_m_s": "wind_v_10m_m_s",
    "wind_speed_10m_m_s": "wind_speed_10m_m_s",
    "wind_direction_10m_degrees_from_north": "wind_direction_10m_degrees_from_north",
    "provider_boundary_layer_height_agl_m": "provider_boundary_layer_height_agl_m",
    "provider_cloud_base_agl_m": "provider_cloud_base_agl_m",
    "total_column_water_vapour_kg_m2": "total_column_water_vapour_kg_m2",
    "mixed_layer_lcl_agl_m": "mixed_layer_lcl_agl_m",
    "pbl_minus_lcl_m": "pbl_minus_lcl_m",
    "surface_buoyancy_flux_kinematic_m2_s3": "surface_buoyancy_flux_kinematic_m2_s3",
    "convective_velocity_scale_m_s": "convective_velocity_scale_m_s",
}
CONVECTION_FEATURE_KEYS = {
    "surface_cape_j_per_kg": "cape_j_per_kg",
    "surface_cin_magnitude_j_per_kg": "cin_magnitude_j_per_kg",
}
DAILY_COLUMNS = {
    "air_temperature_2m_mean_k": "air_temperature_2m_mean_k",
    "air_temperature_2m_min_k": "air_temperature_2m_min_k",
    "air_temperature_2m_max_k": "air_temperature_2m_max_k",
    "dew_point_temperature_2m_mean_k": "dew_point_temperature_2m_mean_k",
    "relative_humidity_2m_mean_percent": "relative_humidity_2m_mean_percent",
    "relative_humidity_2m_max_percent": "relative_humidity_2m_max_percent",
    "surface_pressure_mean_pa": "surface_pressure_mean_pa",
    "mean_sea_level_pressure_mean_pa": "mean_sea_level_pressure_mean_pa",
    "wind_u_10m_mean_m_s": "wind_u_10m_mean_m_s",
    "wind_v_10m_mean_m_s": "wind_v_10m_mean_m_s",
    "wind_speed_10m_mean_m_s": "wind_speed_10m_mean_m_s",
    "wind_speed_10m_max_m_s": "wind_speed_10m_max_m_s",
    "wind_direction_10m_mean_degrees_from_north": "wind_direction_10m_mean_degrees_from_north",
    "provider_boundary_layer_height_agl_mean_m": "provider_boundary_layer_height_agl_mean_m",
    "provider_boundary_layer_height_agl_max_m": "provider_boundary_layer_height_agl_max_m",
    "provider_cloud_base_agl_mean_m": "provider_cloud_base_agl_mean_m",
    "provider_cloud_base_agl_min_m": "provider_cloud_base_agl_min_m",
    "provider_cloud_base_agl_max_m": "provider_cloud_base_agl_max_m",
    "mixed_layer_lcl_agl_mean_m": "mixed_layer_lcl_agl_mean_m",
    "mixed_layer_lcl_agl_min_m": "mixed_layer_lcl_agl_min_m",
    "mixed_layer_lcl_agl_max_m": "mixed_layer_lcl_agl_max_m",
    "pbl_minus_lcl_mean_m": "pbl_minus_lcl_mean_m",
    "pbl_minus_lcl_max_m": "pbl_minus_lcl_max_m",
    "surface_buoyancy_flux_kinematic_mean_m2_s3": "surface_buoyancy_flux_kinematic_mean_m2_s3",
    "surface_buoyancy_flux_kinematic_max_m2_s3": "surface_buoyancy_flux_kinematic_max_m2_s3",
    "convective_velocity_scale_mean_m_s": "convective_velocity_scale_mean_m_s",
    "convective_velocity_scale_max_m_s": "convective_velocity_scale_max_m_s",
    "total_column_water_vapour_mean_kg_m2": "total_column_water_vapour_mean_kg_m2",
    "total_cloud_cover_mean_percent": "total_cloud_cover_mean_percent",
    "total_cloud_cover_max_percent": "total_cloud_cover_max_percent",
    "low_cloud_cover_mean_percent": "low_cloud_cover_mean_percent",
    "low_cloud_cover_max_percent": "low_cloud_cover_max_percent",
    "mid_cloud_cover_mean_percent": "mid_cloud_cover_mean_percent",
    "high_cloud_cover_mean_percent": "high_cloud_cover_mean_percent",
    "precipitation_total_mm": "precipitation_total_mm",
    "precipitation_max_hourly_mm": "precipitation_max_hourly_mm",
    "shortwave_radiation_mean_w_m2": "shortwave_radiation_mean_w_m2",
    "shortwave_radiation_max_w_m2": "shortwave_radiation_max_w_m2",
    "surface_sensible_heat_flux_mean_w_m2": "surface_sensible_heat_flux_mean_w_m2",
    "surface_latent_heat_flux_mean_w_m2": "surface_latent_heat_flux_mean_w_m2",
    "cape_max_j_per_kg": "cape_max_j_per_kg",
    "cin_magnitude_max_j_per_kg": "cin_magnitude_max_j_per_kg",
    "neighbourhood_pressure_gradient_mean_pa_per_km": "neighbourhood_pressure_gradient_mean_pa_per_km",
    "neighbourhood_pressure_gradient_max_pa_per_km": "neighbourhood_pressure_gradient_max_pa_per_km",
    "neighbourhood_low_level_divergence_mean_s_inverse": "neighbourhood_low_level_divergence_mean_s_inverse",
    "neighbourhood_low_level_divergence_min_s_inverse": "neighbourhood_low_level_divergence_min_s_inverse",
}
LAYER_COLUMNS = {
    "temperature_lapse_rate_mean_k_per_km": "temperature_lapse_rate_mean_k_per_km",
    "temperature_lapse_rate_max_k_per_km": "temperature_lapse_rate_max_k_per_km",
    "relative_humidity_mean_percent": "relative_humidity_mean_percent",
    "specific_humidity_mean_kg_per_kg": "specific_humidity_mean_kg_per_kg",
    "wind_u_mean_m_s": "wind_u_mean_m_s",
    "wind_v_mean_m_s": "wind_v_mean_m_s",
    "wind_speed_mean_m_s": "wind_speed_mean_m_s",
    "wind_speed_max_m_s": "wind_speed_max_m_s",
    "wind_direction_mean_degrees_from_north": "wind_direction_mean_degrees_from_north",
    "wind_shear_mean_m_s_per_km": "wind_shear_mean_m_s_per_km",
    "wind_shear_max_m_s_per_km": "wind_shear_max_m_s_per_km",
    "vertical_velocity_mean_pa_s": "vertical_velocity_mean_pa_s",
    "vertical_velocity_min_pa_s": "vertical_velocity_min_pa_s",
}

_REQUIRED_TABLE_COLUMNS = {
    "weather_sources": {
        "id",
        "code",
        "provider_name",
        "dataset_name",
        "source_kind",
        "base_url",
        "is_active",
    },
    "weather_ingestion_runs": {
        "id",
        "run_key",
        "product_run_id",
        "feature_manifest_path",
        "feature_manifest_sha256",
        "persistence_input_sha256",
        "status",
    },
    "weather_product_runs": {
        "id",
        "source_id",
        "source_product_key",
        "reference_at_utc",
        "available_at_utc",
    },
    "weather_product_valid_times": {"id", "product_run_id", "valid_at_utc", "lead_hours"},
    "weather_grids": {"id", "source_id", "grid_key"},
    "weather_grid_points": {"id", "grid_id", "latitude_deg", "longitude_deg"},
    "weather_sampling_footprints": {
        "id",
        "site_id",
        "grid_id",
        "purpose",
        "sampling_method",
        "sampling_method_version",
        "radius_km",
    },
    "weather_sampling_footprint_nodes": {
        "footprint_id",
        "grid_point_id",
        "distance_km",
        "interpolation_weight",
    },
    "weather_point_samples": {
        "id",
        "ingestion_run_id",
        "product_valid_time_id",
        "point_footprint_id",
        "coverage_status",
    },
    "weather_point_profile_levels": {"id", "weather_point_sample_id", "pressure_pa"},
    "weather_point_convection_measurements": {
        "id",
        "weather_point_sample_id",
        "parcel_method",
        "calculation_method",
    },
    "weather_point_interval_measurements": {
        "id",
        "weather_point_sample_id",
        "field_code",
        "component",
        "statistic_type",
    },
    "weather_daily_feature_snapshots": {
        "id",
        "ingestion_run_id",
        "point_footprint_id",
        "neighbourhood_footprint_id",
        "feature_contract_version",
    },
    "weather_daily_feature_snapshot_inputs": {
        "daily_feature_snapshot_id",
        "weather_point_sample_id",
    },
    "weather_daily_feature_profile_layers": {
        "id",
        "daily_feature_snapshot_id",
        "layer_base_agl_m",
        "layer_top_agl_m",
    },
    "weather_field_provenance": {"id", "missing_reason_code", "statistic_type"},
}


@dataclass(frozen=True)
class PreparedWeatherPersistence:
    store: WeatherArtifactStore
    ledger: RunStateLedger
    raw_manifest_reference: ArtifactReference
    raw_manifest: RawManifest
    request_plan: RequestPlan
    validation_manifest_reference: ArtifactReference
    validation_manifest: StageManifest
    feature_manifest_reference: ArtifactReference
    feature_manifest: StageManifest
    spatial_batch: CanonicalSiteSampleBatch
    accepted: AcceptedWeatherSamples
    hourly: HourlyFeatureSnapshotBatch
    daily: DailyFeatureSnapshotBatch
    quality_report: FeatureQualityReport
    usage_policy: WeatherUsagePolicy
    usage_policy_sha256: str
    pipeline_version: str
    persistence_input_sha256: str


def _output_reference(manifest: StageManifest, artifact_key: str) -> ArtifactReference:
    matches = [item for item in manifest.outputs if item.artifact_key == artifact_key]
    if len(matches) != 1:
        raise WeatherPersistenceError(f"Stage must expose exactly one {artifact_key} output.")
    return matches[0]


def _load_model(store: WeatherArtifactStore, reference: ArtifactReference, model_type):
    try:
        path = store.verify_reference(reference)
        return model_type.model_validate_json(path.read_bytes(), strict=True)
    except (ArtifactError, OSError, TypeError, ValueError) as error:
        raise WeatherPersistenceError(
            f"Artifact {reference.artifact_key} is not a valid persistence input."
        ) from error


def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _effective_stage(ledger: RunStateLedger, stage: str):
    event = ledger.latest_stage_event(ledger.load_events(), stage)  # type: ignore[arg-type]
    if event is None or event.evidence is None:
        raise WeatherPersistenceError(f"Persistence requires a complete {stage} state boundary.")
    return event


def _collect_pipeline_versions(
    store: WeatherArtifactStore, root: ArtifactReference
) -> tuple[str, ...]:
    versions: set[str] = set()
    visited: set[str] = set()

    def visit(reference: ArtifactReference) -> None:
        if reference.sha256 in visited:
            return
        visited.add(reference.sha256)
        if reference.artifact_key == "raw_manifest":
            manifest = store.verify_raw_manifest(reference)
            versions.add(manifest.collector_version)
            return
        if reference.artifact_key != "stage_manifest":
            store.verify_reference(reference)
            return
        manifest = store.read_stage_manifest(reference)
        versions.add(manifest.producer_version)
        for item in manifest.inputs:
            visit(item)

    visit(root)
    return tuple(sorted(versions))


def _validate_mapping_parity(
    hourly: HourlyFeatureSnapshotBatch, daily: DailyFeatureSnapshotBatch
) -> None:
    hourly_keys = {field.feature_key for snapshot in hourly.snapshots for field in snapshot.fields}
    expected_hourly = set(HOURLY_POINT_COLUMNS) | set(CONVECTION_FEATURE_KEYS)
    if hourly_keys != expected_hourly:
        raise WeatherPersistenceError(
            "Active hourly feature contract does not match the explicit persistence registry."
        )
    daily_keys = {
        field.feature_key for snapshot in daily.snapshots for field in snapshot.daily_fields
    }
    if daily_keys != set(DAILY_COLUMNS):
        raise WeatherPersistenceError(
            "Active daily feature contract does not match the explicit persistence registry."
        )
    layer_keys = {
        field.feature_key
        for snapshot in daily.snapshots
        for layer in snapshot.profile_layers
        for field in layer.fields
    }
    if layer_keys != set(LAYER_COLUMNS):
        raise WeatherPersistenceError(
            "Active profile-layer feature contract does not match the explicit persistence registry."
        )


def prepare_weather_persistence(
    run_key: str,
    usage_policy_path: Path | None,
    *,
    project_root: Path | None = None,
) -> PreparedWeatherPersistence:
    """Verify all immutable offline inputs before any SQLite write lock is acquired."""

    root = (project_root or Path.cwd()).resolve()
    try:
        store = WeatherArtifactStore(run_key, project_root=root)
        ledger = RunStateLedger(store)
        events = ledger.load_events()
    except (ArtifactError, StateError, OSError) as error:
        raise WeatherPersistenceError("Weather state ledger cannot be verified.") from error
    if not events:
        raise WeatherPersistenceError("Weather run has no state ledger.")
    validation_event = _effective_stage(ledger, "validated")
    feature_event = _effective_stage(ledger, "features_built")
    try:
        validation_manifest = store.read_stage_manifest(validation_event.evidence)
        feature_manifest = store.read_stage_manifest(feature_event.evidence)
    except ArtifactError as error:
        raise WeatherPersistenceError(
            "Validated or feature boundary cannot be verified."
        ) from error
    if validation_manifest.disposition != "complete" or feature_manifest.disposition != "complete":
        raise WeatherPersistenceError(
            "Persistence requires complete validation and feature boundaries."
        )
    if validation_event.evidence not in feature_manifest.inputs:
        raise WeatherPersistenceError(
            "Feature boundary does not consume the effective validation boundary."
        )

    validation_snapshot = _load_model(
        store, _output_reference(validation_manifest, "validation_snapshot"), ValidationSnapshot
    )
    accepted = _load_model(
        store,
        _output_reference(validation_manifest, "accepted_weather_samples"),
        AcceptedWeatherSamples,
    )
    hourly = _load_model(
        store,
        _output_reference(feature_manifest, "hourly_feature_snapshot_batch"),
        HourlyFeatureSnapshotBatch,
    )
    daily = _load_model(
        store,
        _output_reference(feature_manifest, "daily_feature_snapshot_batch"),
        DailyFeatureSnapshotBatch,
    )
    report = _load_model(
        store, _output_reference(feature_manifest, "feature_quality_report"), FeatureQualityReport
    )
    spatial_reference = validation_upstream_boundary(store, validation_event.evidence)
    spatial_manifest = store.read_stage_manifest(spatial_reference)
    spatial = _load_model(
        store,
        _output_reference(spatial_manifest, "canonical_site_sample_batch"),
        CanonicalSiteSampleBatch,
    )
    try:
        raw_manifest = store.verify_raw_manifest(validation_snapshot.raw_manifest)
        request_path = store.verify_reference(
            raw_manifest.request_plan, expected_root=store.raw_dir
        )
        request_plan = RequestPlan.model_validate_json(request_path.read_bytes(), strict=True)
        usage_policy, usage_policy_sha256 = load_weather_usage_policy(
            usage_policy_path,
            expected_source_id=raw_manifest.source_id,
            project_root=root,
        )
    except (ArtifactError, OSError, TypeError, ValueError) as error:
        raise WeatherPersistenceError(
            "Raw manifest, request plan, or weather usage policy is invalid."
        ) from error

    all_run_keys = {
        raw_manifest.run_key,
        request_plan.run_key,
        accepted.run_key,
        hourly.run_key,
        daily.run_key,
        report.run_key,
        spatial.run_key,
    }
    if all_run_keys != {run_key}:
        raise WeatherPersistenceError(
            "Persistence artifacts do not belong to the requested weather run."
        )
    if raw_manifest.status != "complete":
        raise WeatherPersistenceError("Only a complete raw manifest can be persisted.")
    if (
        raw_manifest.source_id != validation_snapshot.source.code
        or raw_manifest.source_id != request_plan.source_id
    ):
        raise WeatherPersistenceError(
            "Source identity drifts between raw/request/validation artifacts."
        )
    if len(accepted.samples) != len(hourly.snapshots) or report.hourly_snapshot_count != len(
        hourly.snapshots
    ):
        raise WeatherPersistenceError("Accepted/hourly feature counters do not reconcile.")
    if report.daily_snapshot_count != len(daily.snapshots) or not daily.snapshots:
        raise WeatherPersistenceError("Daily feature counters do not reconcile.")
    if {item.sample_identity_key for item in accepted.samples} != {
        item.sample_identity_key for item in hourly.snapshots
    }:
        raise WeatherPersistenceError(
            "Hourly feature snapshots do not exactly cover accepted samples."
        )
    if {item.sample_identity_key for item in accepted.samples} != {
        item.sample_identity_key for item in spatial.samples
    }:
        raise WeatherPersistenceError("Accepted samples do not exactly cover spatial evidence.")
    if len({item.local_date for item in daily.snapshots}) != 1:
        raise WeatherPersistenceError(
            "One persisted weather run must have exactly one target local date."
        )
    if any(item.source_product_key != raw_manifest.source_product_key for item in daily.snapshots):
        raise WeatherPersistenceError(
            "Daily feature source-product identity does not match the raw manifest."
        )
    _validate_mapping_parity(hourly, daily)

    versions = _collect_pipeline_versions(store, feature_event.evidence)
    pipeline_version = "|".join((*versions, WEATHER_PERSISTENCE_VERSION))
    fingerprint = sha256_bytes(
        canonical_json_bytes(
            {
                "schema_version": 1,
                "raw_manifest": raw_manifest.request_plan.model_dump(mode="json"),
                "raw_manifest_reference": validation_snapshot.raw_manifest.model_dump(mode="json"),
                "validation_manifest": validation_event.evidence.model_dump(mode="json"),
                "feature_manifest": feature_event.evidence.model_dump(mode="json"),
                "usage_policy_sha256": usage_policy_sha256,
                "mapping_registry_version": MAPPING_REGISTRY_VERSION,
                "pipeline_version": pipeline_version,
                "grid_key": spatial.grid_key,
            }
        )
    )
    return PreparedWeatherPersistence(
        store=store,
        ledger=ledger,
        raw_manifest_reference=validation_snapshot.raw_manifest,
        raw_manifest=raw_manifest,
        request_plan=request_plan,
        validation_manifest_reference=validation_event.evidence,
        validation_manifest=validation_manifest,
        feature_manifest_reference=feature_event.evidence,
        feature_manifest=feature_manifest,
        spatial_batch=spatial,
        accepted=accepted,
        hourly=hourly,
        daily=daily,
        quality_report=report,
        usage_policy=usage_policy,
        usage_policy_sha256=usage_policy_sha256,
        pipeline_version=pipeline_version,
        persistence_input_sha256=fingerprint,
    )


def _require_schema(connection: sqlite3.Connection) -> None:
    for table, expected in _REQUIRED_TABLE_COLUMNS.items():
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
        columns = {str(row[1]) for row in rows}
        if not expected <= columns:
            missing = ", ".join(sorted(expected - columns))
            raise WeatherPersistenceError(
                f"SQLite migration is missing required {table} columns: {missing}."
            )
    foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()
    if foreign_keys is None or int(foreign_keys[0]) != 1:
        raise WeatherPersistenceError(
            "SQLite foreign-key enforcement must be enabled for weather persistence."
        )


def _row_id(
    connection: sqlite3.Connection, query: str, parameters: tuple[Any, ...], label: str
) -> int | None:
    row = connection.execute(query, parameters).fetchone()
    if row is None:
        return None
    return int(row[0])


def _same(left: Any, right: Any) -> bool:
    return left == right or (left is None and right is None)


def _insert(connection: sqlite3.Connection, table: str, values: dict[str, Any]) -> int:
    columns = tuple(values)
    placeholders = ", ".join("?" for _ in columns)
    cursor = connection.execute(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        tuple(values[column] for column in columns),
    )
    return int(cursor.lastrowid)


@dataclass(frozen=True)
class _CapturedRow:
    table: str
    row_id: int
    values: dict[str, Any]


class _CaptureCursor:
    def __init__(self, *, lastrowid: int = 0, row: tuple[int] | None = None) -> None:
        self.lastrowid = lastrowid
        self._row = row

    def fetchone(self) -> tuple[int] | None:
        return self._row


class _ExpectedGraphCapture:
    """Read-through SQLite facade that records the rows an insertion would create.

    Replay must never issue writes against the configured database.  The facade
    delegates every SELECT to that database, assigns synthetic IDs to the new
    run graph, and rejects an attempt to create shared rows.  The resulting
    graph is therefore the exact insert-shaped expectation for comparison with
    the persisted run graph.
    """

    _SHARED_TABLES = frozenset(
        {
            "weather_product_runs",
            "weather_product_valid_times",
            "weather_grids",
            "weather_grid_points",
            "weather_sampling_footprints",
            "weather_sampling_footprint_nodes",
        }
    )
    _INSERT = re.compile(
        r"^\\s*INSERT INTO ([a-z_]+) \\(([^)]+)\\) VALUES", re.IGNORECASE | re.DOTALL
    )

    def __init__(self, source: sqlite3.Connection) -> None:
        self._source = source
        self._rows: list[_CapturedRow] = []
        self._next_id = -1
        self._columns: dict[str, tuple[str, ...]] = {}

    @property
    def rows(self) -> tuple[_CapturedRow, ...]:
        return tuple(self._rows)

    def _table_columns(self, table: str) -> tuple[str, ...]:
        cached = self._columns.get(table)
        if cached is not None:
            return cached
        rows = self._source.execute(f"PRAGMA table_info({table})").fetchall()
        columns = tuple(str(row[1]) for row in rows)
        if not columns:
            raise WeatherPersistenceError(f"Cannot capture unknown SQLite table {table!r}.")
        self._columns[table] = columns
        return columns

    def execute(self, statement: str, parameters: tuple[Any, ...] = ()) -> Any:
        normalized = statement.lstrip().upper()
        if normalized.startswith("SELECT CHANGES()"):
            return _CaptureCursor(row=(1,))
        if normalized.startswith(("SELECT", "PRAGMA")):
            return self._source.execute(statement, parameters)
        match = self._INSERT.match(statement)
        if match is not None:
            table = match.group(1)
            if table in self._SHARED_TABLES:
                raise WeatherPersistenceError(
                    "Exact replay would require creating missing shared weather evidence."
                )
            columns = tuple(item.strip() for item in match.group(2).split(","))
            if len(columns) != len(parameters):
                raise WeatherPersistenceError("Captured persistence insert has mismatched values.")
            values = {column: None for column in self._table_columns(table) if column != "id"}
            values.update(dict(zip(columns, parameters, strict=True)))
            row_id = self._next_id
            self._next_id -= 1
            self._rows.append(_CapturedRow(table=table, row_id=row_id, values=values))
            return _CaptureCursor(lastrowid=row_id)
        if normalized.startswith("UPDATE WEATHER_INGESTION_RUNS"):
            return _CaptureCursor()
        raise WeatherPersistenceError(
            "Expected-graph capture received an unsupported SQLite statement."
        )


def _captured_rows_by_table(rows: tuple[_CapturedRow, ...]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        result.setdefault(row.table, []).append({"id": row.row_id, **row.values})
    return result


def _canonical_graph_item(value: dict[str, Any]) -> bytes:
    return canonical_json_bytes(value)


def _canonical_run_graph(rows: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Remove surrogate IDs while retaining every persisted semantic value."""

    samples = {int(row["id"]): row for row in rows.get("weather_point_samples", [])}
    profiles = {int(row["id"]): row for row in rows.get("weather_point_profile_levels", [])}
    convection = {
        int(row["id"]): row for row in rows.get("weather_point_convection_measurements", [])
    }
    intervals = {int(row["id"]): row for row in rows.get("weather_point_interval_measurements", [])}
    daily = {int(row["id"]): row for row in rows.get("weather_daily_feature_snapshots", [])}
    layers = {int(row["id"]): row for row in rows.get("weather_daily_feature_profile_layers", [])}

    def values(row: dict[str, Any], *excluded: str) -> dict[str, Any]:
        return {key: value for key, value in row.items() if key not in {"id", *excluded}}

    def sample_key(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "product_valid_time_id": row["product_valid_time_id"],
            "point_footprint_id": row["point_footprint_id"],
        }

    def profile_key(row: dict[str, Any]) -> dict[str, Any]:
        sample = samples.get(int(row["weather_point_sample_id"]))
        if sample is None:
            raise WeatherPersistenceError("Persisted profile has no run point-sample owner.")
        return {"sample": sample_key(sample), "pressure_pa": row["pressure_pa"]}

    def convection_key(row: dict[str, Any]) -> dict[str, Any]:
        sample = samples.get(int(row["weather_point_sample_id"]))
        if sample is None:
            raise WeatherPersistenceError("Persisted convection row has no run point-sample owner.")
        return {
            "sample": sample_key(sample),
            "parcel_method": row["parcel_method"],
            "calculation_method": row["calculation_method"],
            "calculation_method_version": row["calculation_method_version"],
            "layer_bottom_pressure_from_ground_pa": row["layer_bottom_pressure_from_ground_pa"],
            "layer_top_pressure_from_ground_pa": row["layer_top_pressure_from_ground_pa"],
        }

    def interval_key(row: dict[str, Any]) -> dict[str, Any]:
        sample = samples.get(int(row["weather_point_sample_id"]))
        if sample is None:
            raise WeatherPersistenceError("Persisted interval has no run point-sample owner.")
        return {
            "sample": sample_key(sample),
            "field_code": row["field_code"],
            "component": row["component"],
            "statistic_type": row["statistic_type"],
            "interval_start_utc": row["interval_start_utc"],
            "interval_end_utc": row["interval_end_utc"],
        }

    def daily_key(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "point_footprint_id": row["point_footprint_id"],
            "feature_contract_version": row["feature_contract_version"],
        }

    def layer_key(row: dict[str, Any]) -> dict[str, Any]:
        owner = daily.get(int(row["daily_feature_snapshot_id"]))
        if owner is None:
            raise WeatherPersistenceError("Persisted daily layer has no run daily-snapshot owner.")
        return {
            "daily": daily_key(owner),
            "layer_base_agl_m": row["layer_base_agl_m"],
            "layer_top_agl_m": row["layer_top_agl_m"],
        }

    def records(table: str, result: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(result, key=_canonical_graph_item)

    graph = {
        "weather_point_samples": records(
            "weather_point_samples",
            [
                {
                    "identity": sample_key(row),
                    "values": values(
                        row,
                        "ingestion_run_id",
                        "product_valid_time_id",
                        "point_footprint_id",
                    ),
                }
                for row in samples.values()
            ],
        ),
        "weather_point_profile_levels": records(
            "weather_point_profile_levels",
            [
                {
                    "identity": profile_key(row),
                    "values": values(row, "weather_point_sample_id", "pressure_pa"),
                }
                for row in profiles.values()
            ],
        ),
        "weather_point_convection_measurements": records(
            "weather_point_convection_measurements",
            [
                {
                    "identity": convection_key(row),
                    "values": values(
                        row,
                        "weather_point_sample_id",
                        "parcel_method",
                        "calculation_method",
                        "calculation_method_version",
                        "layer_bottom_pressure_from_ground_pa",
                        "layer_top_pressure_from_ground_pa",
                    ),
                }
                for row in convection.values()
            ],
        ),
        "weather_point_interval_measurements": records(
            "weather_point_interval_measurements",
            [
                {
                    "identity": interval_key(row),
                    "values": values(
                        row,
                        "weather_point_sample_id",
                        "field_code",
                        "component",
                        "statistic_type",
                        "interval_start_utc",
                        "interval_end_utc",
                    ),
                }
                for row in intervals.values()
            ],
        ),
        "weather_daily_feature_snapshots": records(
            "weather_daily_feature_snapshots",
            [
                {
                    "identity": daily_key(row),
                    "values": values(
                        row,
                        "ingestion_run_id",
                        "point_footprint_id",
                        "feature_contract_version",
                    ),
                }
                for row in daily.values()
            ],
        ),
        "weather_daily_feature_snapshot_inputs": records(
            "weather_daily_feature_snapshot_inputs",
            [
                {
                    "daily": daily_key(daily[int(row["daily_feature_snapshot_id"])]),
                    "sample": sample_key(samples[int(row["weather_point_sample_id"])]),
                }
                for row in rows.get("weather_daily_feature_snapshot_inputs", [])
            ],
        ),
        "weather_daily_feature_profile_layers": records(
            "weather_daily_feature_profile_layers",
            [
                {
                    "identity": layer_key(row),
                    "values": values(
                        row,
                        "daily_feature_snapshot_id",
                        "layer_base_agl_m",
                        "layer_top_agl_m",
                    ),
                }
                for row in layers.values()
            ],
        ),
    }

    owner_columns = (
        ("weather_point_sample_id", "sample", samples, sample_key),
        ("point_profile_level_id", "profile", profiles, profile_key),
        ("point_convection_measurement_id", "convection", convection, convection_key),
        ("point_interval_measurement_id", "interval", intervals, interval_key),
        ("daily_feature_snapshot_id", "daily", daily, daily_key),
        ("daily_feature_profile_layer_id", "layer", layers, layer_key),
    )
    provenance: list[dict[str, Any]] = []
    for row in rows.get("weather_field_provenance", []):
        owners = [
            (name, mapping[int(row[column])], key)
            for column, name, mapping, key in owner_columns
            if row.get(column) is not None
        ]
        if len(owners) != 1:
            raise WeatherPersistenceError("Persisted provenance must have exactly one run owner.")
        name, owner, key = owners[0]
        provenance.append(
            {
                "owner": {"kind": name, "identity": key(owner)},
                "values": values(row, *(column for column, *_ in owner_columns)),
            }
        )
    graph["weather_field_provenance"] = records("weather_field_provenance", provenance)
    return graph


def _load_persisted_run_rows(
    connection: sqlite3.Connection, run_id: int
) -> dict[str, list[dict[str, Any]]]:
    def rows(statement: str, parameters: tuple[Any, ...]) -> list[dict[str, Any]]:
        return [dict(item) for item in connection.execute(statement, parameters).fetchall()]

    result = {
        "weather_point_samples": rows(
            "SELECT * FROM weather_point_samples WHERE ingestion_run_id = ?", (run_id,)
        ),
        "weather_daily_feature_snapshots": rows(
            "SELECT * FROM weather_daily_feature_snapshots WHERE ingestion_run_id = ?", (run_id,)
        ),
    }
    sample_ids = [int(row["id"]) for row in result["weather_point_samples"]]
    daily_ids = [int(row["id"]) for row in result["weather_daily_feature_snapshots"]]

    def owned_rows(table: str, owner_column: str, identifiers: list[int]) -> list[dict[str, Any]]:
        if not identifiers:
            return []
        placeholders = ", ".join("?" for _ in identifiers)
        return rows(
            f"SELECT * FROM {table} WHERE {owner_column} IN ({placeholders})",
            tuple(identifiers),
        )

    result["weather_point_profile_levels"] = owned_rows(
        "weather_point_profile_levels", "weather_point_sample_id", sample_ids
    )
    result["weather_point_convection_measurements"] = owned_rows(
        "weather_point_convection_measurements", "weather_point_sample_id", sample_ids
    )
    result["weather_point_interval_measurements"] = owned_rows(
        "weather_point_interval_measurements", "weather_point_sample_id", sample_ids
    )
    result["weather_daily_feature_snapshot_inputs"] = owned_rows(
        "weather_daily_feature_snapshot_inputs", "daily_feature_snapshot_id", daily_ids
    )
    result["weather_daily_feature_profile_layers"] = owned_rows(
        "weather_daily_feature_profile_layers", "daily_feature_snapshot_id", daily_ids
    )
    profile_ids = [int(row["id"]) for row in result["weather_point_profile_levels"]]
    convection_ids = [int(row["id"]) for row in result["weather_point_convection_measurements"]]
    interval_ids = [int(row["id"]) for row in result["weather_point_interval_measurements"]]
    layer_ids = [int(row["id"]) for row in result["weather_daily_feature_profile_layers"]]
    provenance_clauses: list[str] = []
    provenance_parameters: list[int] = []
    for column, identifiers in (
        ("weather_point_sample_id", sample_ids),
        ("point_profile_level_id", profile_ids),
        ("point_convection_measurement_id", convection_ids),
        ("point_interval_measurement_id", interval_ids),
        ("daily_feature_snapshot_id", daily_ids),
        ("daily_feature_profile_layer_id", layer_ids),
    ):
        if identifiers:
            placeholders = ", ".join("?" for _ in identifiers)
            provenance_clauses.append(f"{column} IN ({placeholders})")
            provenance_parameters.extend(identifiers)
    result["weather_field_provenance"] = (
        rows(
            f"SELECT * FROM weather_field_provenance WHERE {' OR '.join(provenance_clauses)}",
            tuple(provenance_parameters),
        )
        if provenance_clauses
        else []
    )
    return result


def _capture_expected_run_graph(
    connection: sqlite3.Connection, prepared: PreparedWeatherPersistence
) -> dict[str, list[dict[str, Any]]]:
    capture = _ExpectedGraphCapture(connection)
    _insert_graph(capture, prepared)  # type: ignore[arg-type]
    return _canonical_run_graph(_captured_rows_by_table(capture.rows))


def _graph_sha256(graph: dict[str, list[dict[str, Any]]]) -> str:
    return sha256_bytes(canonical_json_bytes(graph))


def _field_variant(value: Any) -> str:
    dimension = getattr(value, "dimension", None) or getattr(value, "variant", None)
    return {"2m_above_ground": "2m", "10m_above_ground": "10m"}.get(
        dimension, dimension or "canonical"
    )


def _missing_reason(value: Any) -> str | None:
    explicit = getattr(value, "missing_reason", None)
    if explicit is not None:
        return explicit
    quality = value.quality_state
    if quality == "unsupported":
        return "source_field_unavailable"
    if quality in {"missing", "sentinel_missing", "invalid_payload"}:
        return "source_value_missing"
    return None


def _source_provenance(field: Any, *, reference_at_utc: str) -> dict[str, Any]:
    return {
        "field_code": field.field_code,
        "field_variant": _field_variant(field),
        "quality_state": field.quality_state,
        "missing_reason_code": _missing_reason(field),
        "source_reference_at_utc": reference_at_utc,
        "native_field_name": ";".join(field.source_selector_keys),
        "native_unit": field.canonical_unit,
        "native_value": None,
        "native_sign_convention": None,
        "native_step_type": field.statistic_type,
        "step_start_hours": None,
        "step_end_hours": None,
        "statistic_type": field.statistic_type,
        "normalization_method": field.normalization_method,
        "normalization_version": field.normalization_version,
        "derivation_method": field.derivation_method,
        "derivation_version": field.derivation_version,
        "raw_artifact_key": ";".join(field.source_raw_artifact_keys),
        "native_message_reference": ";".join(field.source_native_message_references),
    }


def _feature_provenance(value: FeatureValue) -> dict[str, Any]:
    return {
        "field_code": value.field_code,
        "field_variant": _field_variant(value),
        "quality_state": value.quality_state,
        "missing_reason_code": _missing_reason(value),
        "source_reference_at_utc": None,
        "native_field_name": None,
        "native_unit": value.canonical_unit,
        "native_value": None,
        "native_sign_convention": None,
        "native_step_type": None,
        "step_start_hours": None,
        "step_end_hours": None,
        "statistic_type": value.statistic,
        "normalization_method": None,
        "normalization_version": None,
        "derivation_method": value.derivation_method,
        "derivation_version": value.derivation_version,
        "raw_artifact_key": None,
        "native_message_reference": None,
    }


def _verify_source(connection: sqlite3.Connection, prepared: PreparedWeatherPersistence) -> int:
    row = connection.execute(
        """
        SELECT id, provider_name, dataset_name, source_kind, base_url, is_active
        FROM weather_sources WHERE code = ?
        """,
        (prepared.raw_manifest.source_id,),
    ).fetchone()
    if row is None:
        raise WeatherPersistenceError(
            "Weather source must be reviewed configuration, not persistence-created."
        )
    source = _load_model(
        prepared.store,
        _output_reference(prepared.validation_manifest, "validation_snapshot"),
        ValidationSnapshot,
    ).source
    expected = (
        source.provider_name,
        source.dataset_name,
        source.source_kind,
        source.base_url,
        int(source.is_active),
    )
    actual = (str(row[1]), str(row[2]), str(row[3]), str(row[4]), int(row[5]))
    if actual != expected:
        raise WeatherPersistenceError(
            "Reviewed weather source configuration conflicts with immutable validation evidence."
        )
    return int(row[0])


def _resolve_product_run(
    connection: sqlite3.Connection, source_id: int, prepared: PreparedWeatherPersistence
) -> int:
    manifest = prepared.raw_manifest
    row = connection.execute(
        """SELECT id, reference_at_utc, available_at_utc FROM weather_product_runs
           WHERE source_id = ? AND source_product_key = ?""",
        (source_id, manifest.source_product_key),
    ).fetchone()
    expected = (manifest.reference_at_utc, manifest.available_at_utc)
    if row is not None:
        if (row[1], row[2]) != expected:
            raise WeatherPersistenceError(
                "Weather product natural key collides with different immutable timing."
            )
        return int(row[0])
    return _insert(
        connection,
        "weather_product_runs",
        {
            "source_id": source_id,
            "source_product_key": manifest.source_product_key,
            "reference_at_utc": manifest.reference_at_utc,
            "available_at_utc": manifest.available_at_utc,
        },
    )


def _resolve_grid(connection: sqlite3.Connection, source_id: int, grid_key: str) -> int:
    existing = _row_id(
        connection,
        "SELECT id FROM weather_grids WHERE source_id = ? AND grid_key = ?",
        (source_id, grid_key),
        "weather grid",
    )
    if existing is not None:
        return existing
    return _insert(connection, "weather_grids", {"source_id": source_id, "grid_key": grid_key})


def _verify_site_config(connection: sqlite3.Connection, snapshot: Any) -> None:
    row = connection.execute(
        """SELECT latitude_deg, longitude_deg, coordinate_reference, reference_elevation_msl_m,
                  elevation_reference
           FROM weather_site_sampling_configs WHERE site_id = ?""",
        (snapshot.site_id,),
    ).fetchone()
    if row is None:
        raise WeatherPersistenceError(
            f"Site {snapshot.site_id} lacks approved weather sampling configuration."
        )
    expected = (
        snapshot.latitude_deg,
        snapshot.longitude_deg,
        snapshot.coordinate_reference,
        snapshot.reference_elevation_msl_m,
        snapshot.elevation_reference,
    )
    if tuple(row) != expected:
        raise WeatherPersistenceError(
            f"Site {snapshot.site_id} configuration conflicts with immutable spatial evidence."
        )


def _resolve_grid_point(connection: sqlite3.Connection, grid_id: int, node: Any) -> int:
    row = connection.execute(
        """SELECT id FROM weather_grid_points
           WHERE grid_id = ? AND latitude_deg = ? AND longitude_deg = ?""",
        (grid_id, node.latitude_deg, node.longitude_deg),
    ).fetchone()
    if row is not None:
        return int(row[0])
    return _insert(
        connection,
        "weather_grid_points",
        {
            "grid_id": grid_id,
            "latitude_deg": node.latitude_deg,
            "longitude_deg": node.longitude_deg,
            "model_elevation_msl_m": None,
        },
    )


def _verify_footprint_nodes(
    connection: sqlite3.Connection, footprint_id: int, grid_id: int, footprint: SamplingFootprint
) -> None:
    actual = connection.execute(
        """SELECT gp.latitude_deg, gp.longitude_deg, node.distance_km, node.interpolation_weight
           FROM weather_sampling_footprint_nodes AS node
           INNER JOIN weather_grid_points AS gp ON gp.id = node.grid_point_id
           WHERE node.footprint_id = ? ORDER BY gp.latitude_deg, gp.longitude_deg""",
        (footprint_id,),
    ).fetchall()
    expected = sorted(
        (
            node.latitude_deg,
            node.longitude_deg,
            node.distance_km,
            node.interpolation_weight,
        )
        for node in footprint.nodes
    )
    if [tuple(row) for row in actual] != expected:
        raise WeatherPersistenceError(
            "Weather sampling-footprint natural key collides with different immutable nodes."
        )


def _resolve_footprint(
    connection: sqlite3.Connection, grid_id: int, footprint: SamplingFootprint
) -> int:
    row = connection.execute(
        """SELECT id, radius_km FROM weather_sampling_footprints
           WHERE site_id = ? AND grid_id = ? AND purpose = ? AND sampling_method = ?
             AND sampling_method_version = ?
             AND ((radius_km IS NULL AND ? IS NULL) OR radius_km = ?)""",
        (
            footprint.site_id,
            grid_id,
            footprint.purpose,
            footprint.sampling_method,
            footprint.sampling_method_version,
            footprint.radius_km,
            footprint.radius_km,
        ),
    ).fetchone()
    if row is not None and not _same(row[1], footprint.radius_km):
        raise WeatherPersistenceError(
            "Weather sampling footprint identity collides with different radius semantics."
        )
    if row is None:
        footprint_id = _insert(
            connection,
            "weather_sampling_footprints",
            {
                "site_id": footprint.site_id,
                "grid_id": grid_id,
                "purpose": footprint.purpose,
                "sampling_method": footprint.sampling_method,
                "sampling_method_version": footprint.sampling_method_version,
                "radius_km": footprint.radius_km,
            },
        )
        for node in footprint.nodes:
            point_id = _resolve_grid_point(connection, grid_id, node)
            _insert(
                connection,
                "weather_sampling_footprint_nodes",
                {
                    "footprint_id": footprint_id,
                    "grid_point_id": point_id,
                    "distance_km": node.distance_km,
                    "interpolation_weight": node.interpolation_weight,
                },
            )
        return footprint_id
    footprint_id = int(row[0])
    _verify_footprint_nodes(connection, footprint_id, grid_id, footprint)
    return footprint_id


def _resolve_shared_rows(
    connection: sqlite3.Connection, prepared: PreparedWeatherPersistence
) -> tuple[int, dict[str, int]]:
    source_id = _verify_source(connection, prepared)
    _resolve_product_run(connection, source_id, prepared)
    grid_id = _resolve_grid(connection, source_id, prepared.spatial_batch.grid_key)
    for snapshot in prepared.spatial_batch.site_configs:
        _verify_site_config(connection, snapshot)
    footprint_ids: dict[str, int] = {}
    for footprint in (
        *prepared.spatial_batch.point_footprints,
        *prepared.spatial_batch.neighbourhood_footprints,
    ):
        if footprint.footprint_key in footprint_ids:
            raise WeatherPersistenceError("Spatial evidence has duplicate footprint keys.")
        footprint_ids[footprint.footprint_key] = _resolve_footprint(connection, grid_id, footprint)
    return source_id, footprint_ids


def _product_run_id(
    connection: sqlite3.Connection, source_id: int, prepared: PreparedWeatherPersistence
) -> int:
    result = _row_id(
        connection,
        "SELECT id FROM weather_product_runs WHERE source_id = ? AND source_product_key = ?",
        (source_id, prepared.raw_manifest.source_product_key),
        "product run",
    )
    if result is None:
        raise WeatherPersistenceError("Product run disappeared inside persistence transaction.")
    return result


def _resolve_valid_time(
    connection: sqlite3.Connection, product_run_id: int, sample: SiteAlignedSample
) -> int:
    row = connection.execute(
        """SELECT id, lead_hours FROM weather_product_valid_times
           WHERE product_run_id = ? AND valid_at_utc = ?""",
        (product_run_id, sample.valid_at_utc),
    ).fetchone()
    if row is not None:
        if not _same(row[1], sample.lead_hours):
            raise WeatherPersistenceError(
                "Weather valid-time natural key collides with different lead hours."
            )
        return int(row[0])
    return _insert(
        connection,
        "weather_product_valid_times",
        {
            "product_run_id": product_run_id,
            "valid_at_utc": sample.valid_at_utc,
            "lead_hours": sample.lead_hours,
        },
    )


def _point_column_for_source_field(field: Any) -> str | None:
    return {
        ("air_temperature_k", "2m"): "air_temperature_2m_k",
        ("dew_point_temperature_k", "2m"): "dew_point_temperature_2m_k",
        ("relative_humidity_percent", "2m"): "relative_humidity_2m_percent",
        ("specific_humidity_kg_per_kg", "2m"): "specific_humidity_2m_kg_per_kg",
        ("air_pressure_pa", "surface"): "surface_pressure_pa",
        ("air_pressure_pa", "mean_sea_level"): "mean_sea_level_pressure_pa",
        ("wind_u_m_s", "10m"): "wind_u_10m_m_s",
        ("wind_v_m_s", "10m"): "wind_v_10m_m_s",
        ("wind_speed_m_s", "10m"): "wind_speed_10m_m_s",
        ("wind_direction_degrees_from_north", "10m"): "wind_direction_10m_degrees_from_north",
        (
            "provider_boundary_layer_height_agl_m",
            "canonical",
        ): "provider_boundary_layer_height_agl_m",
        ("provider_cloud_base_agl_m", "canonical"): "provider_cloud_base_agl_m",
        ("total_column_water_vapour_kg_m2", "canonical"): "total_column_water_vapour_kg_m2",
        ("cloud_cover_percent", "total"): "total_cloud_cover_percent",
        ("cloud_cover_percent", "low"): "low_cloud_cover_percent",
        ("cloud_cover_percent", "mid"): "mid_cloud_cover_percent",
        ("cloud_cover_percent", "high"): "high_cloud_cover_percent",
    }.get((field.field_code, _field_variant(field)))


def _insert_provenance(
    connection: sqlite3.Connection, owner_column: str, owner_id: int, values: dict[str, Any]
) -> None:
    if owner_column not in {
        "weather_point_sample_id",
        "point_convection_measurement_id",
        "point_interval_measurement_id",
        "point_profile_level_id",
        "daily_feature_snapshot_id",
        "daily_feature_profile_layer_id",
    }:
        raise WeatherPersistenceError("Unknown weather-field provenance owner.")
    _insert(connection, "weather_field_provenance", {owner_column: owner_id, **values})


def _hourly_by_key(snapshot: HourlyFeatureSnapshot) -> dict[str, FeatureValue]:
    values = {item.feature_key: item for item in snapshot.fields}
    if len(values) != len(snapshot.fields):
        raise WeatherPersistenceError("Hourly feature snapshot contains duplicate keys.")
    return values


def _insert_point_sample(
    connection: sqlite3.Connection,
    run_id: int,
    product_valid_time_id: int,
    sample: SiteAlignedSample,
    snapshot: HourlyFeatureSnapshot,
    footprint_ids: dict[str, int],
) -> int:
    point_footprint_id = footprint_ids.get(sample.point_footprint_key)
    if point_footprint_id is None:
        raise WeatherPersistenceError("Hourly sample references an unknown point footprint.")
    point_values: dict[str, Any] = {}
    source_identities: set[tuple[str, str]] = set()
    source_fields = [field for field in sample.fields if field.grain == "surface"]
    for field in source_fields:
        column = _point_column_for_source_field(field)
        if column is None:
            raise WeatherPersistenceError(
                f"No point-sample destination is registered for {field.field_code}/{_field_variant(field)}."
            )
        if column in point_values and point_values[column] != field.canonical_value:
            raise WeatherPersistenceError(
                "Two source fields map to one conflicting point-sample column."
            )
        point_values[column] = field.canonical_value
        source_identities.add((field.field_code, _field_variant(field)))
    feature_values = _hourly_by_key(snapshot)
    for key, column in HOURLY_POINT_COLUMNS.items():
        value = feature_values[key]
        identity = (value.field_code, _field_variant(value))
        existing = point_values.get(column)
        if column in point_values and existing != value.canonical_value:
            raise WeatherPersistenceError(
                f"Source and feature artifacts disagree for hourly {key}."
            )
        point_values[column] = value.canonical_value
        if identity not in source_identities:
            # The feature value will receive a derived/unsupported provenance row below.
            continue
    if point_values.get("provider_boundary_layer_height_agl_m") is not None:
        point_values["provider_boundary_layer_method"] = "provider/1"
    if point_values.get("provider_cloud_base_agl_m") is not None:
        point_values["provider_cloud_base_method"] = "provider/1"
    sample_id = _insert(
        connection,
        "weather_point_samples",
        {
            "ingestion_run_id": run_id,
            "product_valid_time_id": product_valid_time_id,
            "point_footprint_id": point_footprint_id,
            "coverage_status": "complete",
            **point_values,
        },
    )
    for field in source_fields:
        _insert_provenance(
            connection,
            "weather_point_sample_id",
            sample_id,
            _source_provenance(field, reference_at_utc=sample.reference_at_utc),
        )
    for key, column in HOURLY_POINT_COLUMNS.items():
        value = feature_values[key]
        if (value.field_code, _field_variant(value)) not in source_identities:
            _insert_provenance(
                connection,
                "weather_point_sample_id",
                sample_id,
                _feature_provenance(value),
            )
    _insert_profile_levels(connection, sample_id, sample)
    _insert_convection_measurements(connection, sample_id, sample)
    _insert_interval_measurements(connection, sample_id, sample)
    return sample_id


def _insert_profile_levels(
    connection: sqlite3.Connection, sample_id: int, sample: SiteAlignedSample
) -> None:
    columns = {
        "geopotential_height_msl_m": "geopotential_height_msl_m",
        "air_temperature_k": "air_temperature_k",
        "dew_point_temperature_k": "dew_point_temperature_k",
        "relative_humidity_percent": "relative_humidity_percent",
        "specific_humidity_kg_per_kg": "specific_humidity_kg_per_kg",
        "wind_u_m_s": "wind_u_m_s",
        "wind_v_m_s": "wind_v_m_s",
        "wind_speed_m_s": "wind_speed_m_s",
        "wind_direction_degrees_from_north": "wind_direction_degrees_from_north",
        "vertical_velocity_pa_s": "vertical_velocity_pa_s",
    }
    for level in sample.profile_levels:
        values: dict[str, Any] = {
            "weather_point_sample_id": sample_id,
            "pressure_pa": level.pressure_pa,
            "geopotential_height_msl_m": level.geopotential_height_msl_m,
            "level_height_site_agl_m": level.level_height_agl_m,
        }
        for field in level.fields:
            column = columns.get(field.field_code)
            if column is None:
                raise WeatherPersistenceError(
                    f"No profile destination is registered for {field.field_code}."
                )
            if column == "geopotential_height_msl_m":
                if field.canonical_value != level.geopotential_height_msl_m:
                    raise WeatherPersistenceError(
                        "Profile height field disagrees with its S05 level identity."
                    )
                continue
            if column in values and values[column] != field.canonical_value:
                raise WeatherPersistenceError(
                    "Two profile fields map to one conflicting database column."
                )
            values[column] = field.canonical_value
        level_id = _insert(connection, "weather_point_profile_levels", values)
        for field in level.fields:
            _insert_provenance(
                connection,
                "point_profile_level_id",
                level_id,
                _source_provenance(field, reference_at_utc=sample.reference_at_utc),
            )


def _convection_identity(field: Any) -> tuple[str, str, float | None, float | None]:
    if field.dimension == "surface":
        return ("surface", "provider", None, None)
    if field.dimension == "180-0_mb_above_ground":
        return ("mixed_layer", "provider", 0.0, 18000.0)
    raise WeatherPersistenceError(f"Unsupported convection parcel dimension: {field.dimension!r}.")


def _insert_convection_measurements(
    connection: sqlite3.Connection, sample_id: int, sample: SiteAlignedSample
) -> None:
    grouped: dict[tuple[str, str, float | None, float | None], list[Any]] = {}
    for field in sample.fields:
        if field.grain == "convection":
            grouped.setdefault(_convection_identity(field), []).append(field)
    for (parcel_method, calculation_method, bottom, top), fields in grouped.items():
        values: dict[str, Any] = {
            "weather_point_sample_id": sample_id,
            "parcel_method": parcel_method,
            "calculation_method": calculation_method,
            "calculation_method_version": None,
            "layer_bottom_pressure_from_ground_pa": bottom,
            "layer_top_pressure_from_ground_pa": top,
        }
        for field in fields:
            column = {
                "convective_available_potential_energy_j_per_kg": "cape_j_per_kg",
                "convective_inhibition_magnitude_j_per_kg": "cin_magnitude_j_per_kg",
            }.get(field.field_code)
            if column is None:
                raise WeatherPersistenceError(f"Unsupported convection field: {field.field_code}.")
            if column in values and values[column] != field.canonical_value:
                raise WeatherPersistenceError(
                    "Conflicting convection values share one physical identity."
                )
            values[column] = field.canonical_value
        measurement_id = _insert(connection, "weather_point_convection_measurements", values)
        for field in fields:
            _insert_provenance(
                connection,
                "point_convection_measurement_id",
                measurement_id,
                _source_provenance(field, reference_at_utc=sample.reference_at_utc),
            )


def _insert_interval_measurements(
    connection: sqlite3.Connection, sample_id: int, sample: SiteAlignedSample
) -> None:
    for field in sample.fields:
        if field.grain != "interval":
            continue
        if (
            field.interval_start_utc is None
            or field.interval_end_utc is None
            or field.statistic_type is None
        ):
            raise WeatherPersistenceError(
                "Canonical interval evidence must have complete temporal semantics."
            )
        component = "total" if field.field_code == "precipitation_amount_mm" else "not_applicable"
        measurement_id = _insert(
            connection,
            "weather_point_interval_measurements",
            {
                "weather_point_sample_id": sample_id,
                "field_code": field.field_code,
                "component": component,
                "interval_start_utc": field.interval_start_utc,
                "interval_end_utc": field.interval_end_utc,
                "statistic_type": field.statistic_type,
                "canonical_value": field.canonical_value,
            },
        )
        _insert_provenance(
            connection,
            "point_interval_measurement_id",
            measurement_id,
            _source_provenance(field, reference_at_utc=sample.reference_at_utc),
        )


def _daily_values(snapshot: DailyFeatureSnapshot) -> dict[str, FeatureValue]:
    values = {item.feature_key: item for item in snapshot.daily_fields}
    if set(values) != set(DAILY_COLUMNS):
        raise WeatherPersistenceError(
            "Daily feature snapshot does not have the active persistence key set."
        )
    return values


def _insert_daily_snapshot(
    connection: sqlite3.Connection,
    run_id: int,
    snapshot: DailyFeatureSnapshot,
    footprint_ids: dict[str, int],
    point_sample_ids: dict[str, int],
) -> int:
    point_footprint_id = footprint_ids.get(snapshot.point_footprint_key)
    neighbourhood_footprint_id = footprint_ids.get(snapshot.neighbourhood_footprint_key)
    if point_footprint_id is None or neighbourhood_footprint_id is None:
        raise WeatherPersistenceError(
            "Daily feature references an unknown point or neighbourhood footprint."
        )
    fields = _daily_values(snapshot)
    daily_id = _insert(
        connection,
        "weather_daily_feature_snapshots",
        {
            "ingestion_run_id": run_id,
            "point_footprint_id": point_footprint_id,
            "neighbourhood_footprint_id": neighbourhood_footprint_id,
            "feature_contract_version": snapshot.feature_contract_version,
            **{column: fields[key].canonical_value for key, column in DAILY_COLUMNS.items()},
        },
    )
    for field in fields.values():
        _insert_provenance(
            connection,
            "daily_feature_snapshot_id",
            daily_id,
            _feature_provenance(field),
        )
    if len(snapshot.input_sample_identity_keys) != 11:
        raise WeatherPersistenceError(
            "A daily weather feature must link exactly eleven hourly samples."
        )
    for identity in snapshot.input_sample_identity_keys:
        sample_id = point_sample_ids.get(identity)
        if sample_id is None:
            raise WeatherPersistenceError(
                "Daily feature input is absent from the persisted hourly sample graph."
            )
        _insert(
            connection,
            "weather_daily_feature_snapshot_inputs",
            {"daily_feature_snapshot_id": daily_id, "weather_point_sample_id": sample_id},
        )
    for layer in snapshot.profile_layers:
        layer_values = {item.feature_key: item for item in layer.fields}
        if set(layer_values) - set(LAYER_COLUMNS):
            raise WeatherPersistenceError(
                "Daily profile layer includes an unknown persistence key."
            )
        layer_id = _insert(
            connection,
            "weather_daily_feature_profile_layers",
            {
                "daily_feature_snapshot_id": daily_id,
                "layer_base_agl_m": layer.layer_base_agl_m,
                "layer_top_agl_m": layer.layer_top_agl_m,
                **{
                    column: layer_values[key].canonical_value
                    for key, column in LAYER_COLUMNS.items()
                    if key in layer_values
                },
            },
        )
        for field in layer.fields:
            _insert_provenance(
                connection,
                "daily_feature_profile_layer_id",
                layer_id,
                _feature_provenance(field),
            )
    return daily_id


def _expected_counts(prepared: PreparedWeatherPersistence) -> dict[str, int]:
    samples = {item.sample_identity_key: item for item in prepared.accepted.samples}
    hourly = {item.sample_identity_key: item for item in prepared.hourly.snapshots}
    provenance = 0
    profile_levels = 0
    convection = 0
    intervals = 0
    for identity, sample in samples.items():
        snapshot = hourly[identity]
        source_fields = [field for field in sample.fields if field.grain == "surface"]
        provenance += len(source_fields)
        source_identities = {(field.field_code, _field_variant(field)) for field in source_fields}
        provenance += sum(
            (value.field_code, _field_variant(value)) not in source_identities
            for key, value in _hourly_by_key(snapshot).items()
            if key in HOURLY_POINT_COLUMNS
        )
        profile_levels += len(sample.profile_levels)
        provenance += sum(len(level.fields) for level in sample.profile_levels)
        convection_groups = {
            _convection_identity(field) for field in sample.fields if field.grain == "convection"
        }
        convection += len(convection_groups)
        provenance += sum(field.grain == "convection" for field in sample.fields)
        intervals += sum(field.grain == "interval" for field in sample.fields)
        provenance += sum(field.grain == "interval" for field in sample.fields)
    daily_layers = sum(len(item.profile_layers) for item in prepared.daily.snapshots)
    daily_inputs = sum(len(item.input_sample_identity_keys) for item in prepared.daily.snapshots)
    provenance += sum(len(item.daily_fields) for item in prepared.daily.snapshots)
    provenance += sum(
        len(layer.fields) for item in prepared.daily.snapshots for layer in item.profile_layers
    )
    return {
        "weather_ingestion_runs": 1,
        "weather_point_samples": len(samples),
        "weather_point_profile_levels": profile_levels,
        "weather_point_convection_measurements": convection,
        "weather_point_interval_measurements": intervals,
        "weather_daily_feature_snapshots": len(prepared.daily.snapshots),
        "weather_daily_feature_snapshot_inputs": daily_inputs,
        "weather_daily_feature_profile_layers": daily_layers,
        "weather_field_provenance": provenance,
    }


def _run_metadata(prepared: PreparedWeatherPersistence) -> dict[str, Any]:
    return {
        "target_local_date": prepared.daily.snapshots[0].local_date,
        "ingestion_method": prepared.request_plan.ingestion_method,
        "request_purpose": prepared.request_plan.request_purpose,
        "source_url": prepared.raw_manifest.source_url,
        "permission_basis": prepared.usage_policy.permission_basis,
        "permission_reference": prepared.usage_policy.permission_reference,
        "attribution_text": prepared.raw_manifest.attribution_text,
        "model_training_allowed": int(prepared.usage_policy.model_training_allowed),
        "operational_use_allowed": int(prepared.usage_policy.operational_use_allowed),
        "raw_manifest_path": prepared.raw_manifest_reference.relative_path,
        "raw_manifest_sha256": prepared.raw_manifest_reference.sha256,
        "feature_manifest_path": prepared.feature_manifest_reference.relative_path,
        "feature_manifest_sha256": prepared.feature_manifest_reference.sha256,
        "persistence_input_sha256": prepared.persistence_input_sha256,
        "pipeline_version": prepared.pipeline_version,
    }


def _existing_run(connection: sqlite3.Connection, run_key: str):
    return connection.execute(
        """SELECT id, product_run_id, status, target_local_date, ingestion_method, request_purpose,
                  source_url, permission_basis, permission_reference, attribution_text,
                  model_training_allowed, operational_use_allowed, raw_manifest_path,
                  raw_manifest_sha256, feature_manifest_path, feature_manifest_sha256,
                  persistence_input_sha256, pipeline_version
           FROM weather_ingestion_runs WHERE run_key = ?""",
        (run_key,),
    ).fetchone()


def _verify_existing_run(
    connection: sqlite3.Connection, prepared: PreparedWeatherPersistence, row: Any
) -> dict[str, int]:
    if str(row[2]) != "succeeded":
        raise WeatherPersistenceError(
            "Existing weather run is not a terminal succeeded immutable graph."
        )
    metadata = _run_metadata(prepared)
    existing = {
        "target_local_date": row[3],
        "ingestion_method": row[4],
        "request_purpose": row[5],
        "source_url": row[6],
        "permission_basis": row[7],
        "permission_reference": row[8],
        "attribution_text": row[9],
        "model_training_allowed": row[10],
        "operational_use_allowed": row[11],
        "raw_manifest_path": row[12],
        "raw_manifest_sha256": row[13],
        "feature_manifest_path": row[14],
        "feature_manifest_sha256": row[15],
        "persistence_input_sha256": row[16],
        "pipeline_version": row[17],
    }
    if existing != metadata:
        raise WeatherPersistenceError(
            "Existing run_key conflicts with immutable persistence input or usage policy."
        )
    run_id = int(row[0])
    expected = _expected_counts(prepared)
    actual = {
        "weather_ingestion_runs": 1,
        "weather_point_samples": _row_id(
            connection,
            "SELECT count(*) FROM weather_point_samples WHERE ingestion_run_id = ?",
            (run_id,),
            "samples",
        ),
        "weather_point_profile_levels": _row_id(
            connection,
            """SELECT count(*) FROM weather_point_profile_levels AS profile
                           INNER JOIN weather_point_samples AS sample ON sample.id = profile.weather_point_sample_id
                           WHERE sample.ingestion_run_id = ?""",
            (run_id,),
            "profiles",
        ),
        "weather_point_convection_measurements": _row_id(
            connection,
            """SELECT count(*) FROM weather_point_convection_measurements AS item
                           INNER JOIN weather_point_samples AS sample ON sample.id = item.weather_point_sample_id
                           WHERE sample.ingestion_run_id = ?""",
            (run_id,),
            "convection",
        ),
        "weather_point_interval_measurements": _row_id(
            connection,
            """SELECT count(*) FROM weather_point_interval_measurements AS item
                           INNER JOIN weather_point_samples AS sample ON sample.id = item.weather_point_sample_id
                           WHERE sample.ingestion_run_id = ?""",
            (run_id,),
            "intervals",
        ),
        "weather_daily_feature_snapshots": _row_id(
            connection,
            "SELECT count(*) FROM weather_daily_feature_snapshots WHERE ingestion_run_id = ?",
            (run_id,),
            "daily",
        ),
        "weather_daily_feature_snapshot_inputs": _row_id(
            connection,
            """SELECT count(*) FROM weather_daily_feature_snapshot_inputs AS item
                           INNER JOIN weather_daily_feature_snapshots AS daily ON daily.id = item.daily_feature_snapshot_id
                           WHERE daily.ingestion_run_id = ?""",
            (run_id,),
            "daily inputs",
        ),
        "weather_daily_feature_profile_layers": _row_id(
            connection,
            """SELECT count(*) FROM weather_daily_feature_profile_layers AS item
                           INNER JOIN weather_daily_feature_snapshots AS daily ON daily.id = item.daily_feature_snapshot_id
                           WHERE daily.ingestion_run_id = ?""",
            (run_id,),
            "daily layers",
        ),
        "weather_field_provenance": _row_id(
            connection,
            """SELECT count(*) FROM weather_field_provenance AS provenance
                           LEFT JOIN weather_point_samples AS sample ON sample.id = provenance.weather_point_sample_id
                           LEFT JOIN weather_point_profile_levels AS profile ON profile.id = provenance.point_profile_level_id
                           LEFT JOIN weather_point_convection_measurements AS convection ON convection.id = provenance.point_convection_measurement_id
                           LEFT JOIN weather_point_interval_measurements AS interval ON interval.id = provenance.point_interval_measurement_id
                           LEFT JOIN weather_daily_feature_snapshots AS daily ON daily.id = provenance.daily_feature_snapshot_id
                           LEFT JOIN weather_daily_feature_profile_layers AS layer ON layer.id = provenance.daily_feature_profile_layer_id
                           LEFT JOIN weather_daily_feature_snapshots AS layer_daily ON layer_daily.id = layer.daily_feature_snapshot_id
                           LEFT JOIN weather_point_samples AS profile_sample ON profile_sample.id = profile.weather_point_sample_id
                           LEFT JOIN weather_point_samples AS convection_sample ON convection_sample.id = convection.weather_point_sample_id
                           LEFT JOIN weather_point_samples AS interval_sample ON interval_sample.id = interval.weather_point_sample_id
                           WHERE sample.ingestion_run_id = ? OR profile_sample.ingestion_run_id = ?
                              OR convection_sample.ingestion_run_id = ? OR interval_sample.ingestion_run_id = ?
                              OR daily.ingestion_run_id = ? OR layer_daily.ingestion_run_id = ?""",
            (run_id, run_id, run_id, run_id, run_id, run_id),
            "provenance",
        ),
    }
    if actual != expected:
        raise WeatherPersistenceError(
            "Existing weather graph does not match the expected immutable row counts."
        )
    expected_graph = _capture_expected_run_graph(connection, prepared)
    actual_graph = _canonical_run_graph(_load_persisted_run_rows(connection, run_id))
    if actual_graph != expected_graph:
        raise WeatherPersistenceError(
            "Existing weather graph conflicts with the complete immutable persistence input."
        )
    return actual, _graph_sha256(expected_graph)


def _insert_run(
    connection: sqlite3.Connection, product_run_id: int, prepared: PreparedWeatherPersistence
) -> int:
    metadata = _run_metadata(prepared)
    return _insert(
        connection,
        "weather_ingestion_runs",
        {
            "run_key": prepared.store.run_key,
            "product_run_id": product_run_id,
            "status": "running",
            "source_url": metadata["source_url"],
            "permission_basis": metadata["permission_basis"],
            "permission_reference": metadata["permission_reference"],
            "attribution_text": metadata["attribution_text"],
            "model_training_allowed": metadata["model_training_allowed"],
            "operational_use_allowed": metadata["operational_use_allowed"],
            "raw_manifest_path": metadata["raw_manifest_path"],
            "raw_manifest_sha256": metadata["raw_manifest_sha256"],
            "feature_manifest_path": None,
            "feature_manifest_sha256": None,
            "persistence_input_sha256": None,
            "pipeline_version": metadata["pipeline_version"],
            "started_at_utc": prepared.raw_manifest.retrieved_at_utc,
            "completed_at_utc": None,
            "target_local_date": metadata["target_local_date"],
            "ingestion_method": metadata["ingestion_method"],
            "request_purpose": metadata["request_purpose"],
            "samples_seen": len(prepared.accepted.samples),
            "samples_accepted": len(prepared.accepted.samples),
            "samples_rejected": 0,
            "samples_quarantined": 0,
            "samples_deduplicated": 0,
            "error_summary": None,
            "notes": None,
        },
    )


def _insert_graph(
    connection: sqlite3.Connection, prepared: PreparedWeatherPersistence
) -> dict[str, int]:
    source_id, footprint_ids = _resolve_shared_rows(connection, prepared)
    product_run_id = _product_run_id(connection, source_id, prepared)
    run_id = _insert_run(connection, product_run_id, prepared)
    hourly = {item.sample_identity_key: item for item in prepared.hourly.snapshots}
    sample_ids: dict[str, int] = {}
    for sample in sorted(
        prepared.accepted.samples, key=lambda item: (item.site_id, item.valid_at_utc)
    ):
        sample_ids[sample.sample_identity_key] = _insert_point_sample(
            connection,
            run_id,
            _resolve_valid_time(connection, product_run_id, sample),
            sample,
            hourly[sample.sample_identity_key],
            footprint_ids,
        )
    for snapshot in sorted(prepared.daily.snapshots, key=lambda item: item.site_id):
        _insert_daily_snapshot(connection, run_id, snapshot, footprint_ids, sample_ids)
    metadata = _run_metadata(prepared)
    connection.execute(
        """UPDATE weather_ingestion_runs
           SET status = 'succeeded', feature_manifest_path = ?, feature_manifest_sha256 = ?,
               persistence_input_sha256 = ?, completed_at_utc = ?
           WHERE id = ? AND status = 'running'""",
        (
            metadata["feature_manifest_path"],
            metadata["feature_manifest_sha256"],
            metadata["persistence_input_sha256"],
            _now_utc(),
            run_id,
        ),
    )
    if connection.execute("SELECT changes()").fetchone()[0] != 1:
        raise WeatherPersistenceError(
            "Weather ingestion run did not reach succeeded terminal state."
        )
    return _expected_counts(prepared)


def _database_identity(database_url: str, root: Path) -> str:
    path = resolve_database_path(database_url, root)
    try:
        return path.relative_to(root).as_posix()
    except ValueError as error:
        raise WeatherPersistenceError(
            "Configured SQLite database escapes the repository root."
        ) from error


def _publish_receipt(
    prepared: PreparedWeatherPersistence,
    *,
    database_identity: str,
    disposition: str,
    table_counts: dict[str, int],
    persisted_graph_sha256: str,
    completed_at_utc: str,
) -> ArtifactReference:
    configuration = {
        "mapping_registry_version": MAPPING_REGISTRY_VERSION,
        "usage_policy_sha256": prepared.usage_policy_sha256,
        "persistence_input_sha256": prepared.persistence_input_sha256,
    }
    fingerprint = stage_input_fingerprint(
        stage="persistence",
        producer_version=WEATHER_PERSISTENCE_VERSION,
        inputs=(prepared.feature_manifest_reference,),
        configuration=configuration,
    )
    existing = prepared.store.existing_stage_manifest(
        "persistence", WEATHER_PERSISTENCE_VERSION, fingerprint
    )
    if existing is not None:
        return existing
    reasons = Counter()
    for snapshot in prepared.hourly.snapshots:
        for field in snapshot.fields:
            if field.missing_reason is not None:
                reasons[field.missing_reason] += 1
    for snapshot in prepared.daily.snapshots:
        for field in (
            *snapshot.daily_fields,
            *(item for layer in snapshot.profile_layers for item in layer.fields),
        ):
            if field.missing_reason is not None:
                reasons[field.missing_reason] += 1
    receipt = WeatherPersistenceReceipt(
        run_key=prepared.store.run_key,
        source_id=prepared.raw_manifest.source_id,
        source_product_key=prepared.raw_manifest.source_product_key,
        target_local_date=prepared.daily.snapshots[0].local_date,
        database_identity=database_identity,
        feature_manifest=prepared.feature_manifest_reference,
        usage_policy_sha256=prepared.usage_policy_sha256,
        persistence_input_sha256=prepared.persistence_input_sha256,
        pipeline_version=prepared.pipeline_version,
        disposition=disposition,
        table_counts=table_counts,
        persisted_graph_sha256=persisted_graph_sha256,
        missing_quality_count=prepared.quality_report.quality_counts.get("missing", 0),
        unsupported_quality_count=prepared.quality_report.quality_counts.get("unsupported", 0),
        missing_reason_counts=dict(sorted(reasons.items())),
        completed_at_utc=completed_at_utc,
    )
    directory = prepared.store.begin_stage("persistence", WEATHER_PERSISTENCE_VERSION, fingerprint)
    receipt_reference = prepared.store.write_stage_model(
        directory, "persistence-receipt.json", "weather_persistence_receipt", receipt
    )
    return prepared.store.write_stage_manifest(
        directory,
        StageManifest(
            run_key=prepared.store.run_key,
            stage="persistence",
            producer_version=WEATHER_PERSISTENCE_VERSION,
            input_fingerprint_sha256=fingerprint,
            inputs=(prepared.feature_manifest_reference,),
            outputs=(receipt_reference,),
            configuration=configuration,
            disposition="complete",
            started_at_utc=completed_at_utc,
            completed_at_utc=completed_at_utc,
        ),
    )


def _safe_failure_detail(error: Exception) -> str:
    message = " ".join(str(error).splitlines()).strip()
    return f"{type(error).__name__}: {message[:400]}" if message else type(error).__name__


def _failure_kind(error: Exception) -> str:
    message = str(error).lower()
    if "conflict" in message:
        return "conflict"
    if "migration" in message or "schema" in message or "foreign-key" in message:
        return "schema_preflight"
    return "transaction"


def _publish_failure_evidence(
    prepared: PreparedWeatherPersistence,
    error: Exception,
    *,
    occurred_at_utc: str,
    failure_kind: str | None = None,
) -> ArtifactReference:
    """Publish secret-free immutable failure evidence outside the rolled-back transaction."""

    failure_kind = failure_kind or _failure_kind(error)
    summary = _safe_failure_detail(error)
    attempt = len(prepared.ledger.load_events()) + 1
    configuration = {
        "failure_kind": failure_kind,
        "failure_summary_sha256": sha256_bytes(summary.encode("utf-8")),
        "persistence_input_sha256": prepared.persistence_input_sha256,
        "attempt": attempt,
    }
    fingerprint = stage_input_fingerprint(
        stage="persistence_failure",
        producer_version=WEATHER_PERSISTENCE_VERSION,
        inputs=(prepared.feature_manifest_reference,),
        configuration=configuration,
    )
    directory = prepared.store.begin_stage(
        "persistence_failure", WEATHER_PERSISTENCE_VERSION, fingerprint
    )
    failure_reference = prepared.store.write_stage_model(
        directory,
        "persistence-failure.json",
        "weather_persistence_failure",
        WeatherPersistenceFailure(
            run_key=prepared.store.run_key,
            failure_kind=failure_kind,
            error_summary=summary,
            feature_manifest=prepared.feature_manifest_reference,
            persistence_input_sha256=prepared.persistence_input_sha256,
            occurred_at_utc=occurred_at_utc,
        ),
    )
    return prepared.store.write_stage_manifest(
        directory,
        StageManifest(
            run_key=prepared.store.run_key,
            stage="persistence_failure",
            producer_version=WEATHER_PERSISTENCE_VERSION,
            input_fingerprint_sha256=fingerprint,
            inputs=(prepared.feature_manifest_reference,),
            outputs=(failure_reference,),
            configuration=configuration,
            disposition="complete",
            started_at_utc=occurred_at_utc,
            completed_at_utc=occurred_at_utc,
        ),
    )


def _record_prepared_failure(
    prepared: PreparedWeatherPersistence, error: Exception, *, failure_kind: str | None = None
) -> None:
    """Best-effort state evidence; never conceal the triggering persistence failure."""

    try:
        events = prepared.ledger.load_events()
        if events and events[-1].stage == "persisted" and events[-1].disposition == "persisted":
            return
        occurred_at_utc = _now_utc()
        kind = failure_kind or _failure_kind(error)
        failure_evidence = _publish_failure_evidence(
            prepared,
            error,
            occurred_at_utc=occurred_at_utc,
            failure_kind=kind,
        )
        prepared.ledger.append(
            invocation_mode="resume",
            stage="persisted",
            disposition="failed",
            occurred_at_utc=occurred_at_utc,
            evidence=failure_evidence,
            detail=f"persistence_{kind}_failure",
        )
    except (ArtifactError, OSError, StateError, ValueError):
        return


def _record_preparation_failure(run_key: str, root: Path, error: Exception) -> None:
    """Record a policy/artifact preparation failure when a valid ledger permits it."""

    try:
        store = WeatherArtifactStore(run_key, project_root=root)
        ledger = RunStateLedger(store)
        events = ledger.load_events()
        if not events or (
            events[-1].stage == "persisted" and events[-1].disposition == "persisted"
        ):
            return
        occurred_at_utc = _now_utc()
        summary = _safe_failure_detail(error)
        configuration = {
            "failure_kind": "prepare",
            "failure_summary_sha256": sha256_bytes(summary.encode("utf-8")),
            "attempt": len(events) + 1,
        }
        fingerprint = stage_input_fingerprint(
            stage="persistence_failure",
            producer_version=WEATHER_PERSISTENCE_VERSION,
            inputs=(),
            configuration=configuration,
        )
        directory = store.begin_stage(
            "persistence_failure", WEATHER_PERSISTENCE_VERSION, fingerprint
        )
        failure_reference = store.write_stage_model(
            directory,
            "persistence-failure.json",
            "weather_persistence_failure",
            WeatherPersistenceFailure(
                run_key=run_key,
                failure_kind="prepare",
                error_summary=summary,
                occurred_at_utc=occurred_at_utc,
            ),
        )
        evidence = store.write_stage_manifest(
            directory,
            StageManifest(
                run_key=run_key,
                stage="persistence_failure",
                producer_version=WEATHER_PERSISTENCE_VERSION,
                input_fingerprint_sha256=fingerprint,
                inputs=(),
                outputs=(failure_reference,),
                configuration=configuration,
                disposition="complete",
                started_at_utc=occurred_at_utc,
                completed_at_utc=occurred_at_utc,
            ),
        )
        ledger.append(
            invocation_mode="resume",
            stage="persisted",
            disposition="failed",
            occurred_at_utc=occurred_at_utc,
            evidence=evidence,
            detail="persistence_prepare_failure",
        )
    except (ArtifactError, OSError, StateError, ValueError):
        return


def persist_weather_run(
    run_key: str,
    usage_policy_path: Path | None,
    *,
    database_url: str | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Persist a fully verified weather run in one transaction, or revalidate an exact replay."""

    root = (project_root or Path.cwd()).resolve()
    try:
        prepared = prepare_weather_persistence(run_key, usage_policy_path, project_root=root)
    except WeatherPersistenceError as error:
        _record_preparation_failure(run_key, root, error)
        raise
    resolved_url = configured_database_url(database_url)
    try:
        connection = open_writable_database(resolved_url, root)
    except DatabaseConfigurationError as error:
        configuration_error = WeatherPersistenceError(str(error))
        _record_prepared_failure(prepared, configuration_error, failure_kind="schema_preflight")
        raise configuration_error from error
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN IMMEDIATE")
        _require_schema(connection)
        existing = _existing_run(connection, run_key)
        if existing is not None:
            _verify_source(connection, prepared)
            counts, persisted_graph_sha256 = _verify_existing_run(connection, prepared, existing)
            connection.rollback()
            events = prepared.ledger.load_events()
            terminal = events[-1].stage == "persisted" and events[-1].disposition == "persisted"
            disposition = "revalidated_no_op" if terminal else "recovered_committed_write"
        else:
            _insert_graph(connection, prepared)
            inserted = _existing_run(connection, run_key)
            if inserted is None:
                raise WeatherPersistenceError(
                    "Inserted weather run cannot be reloaded for verification."
                )
            counts, persisted_graph_sha256 = _verify_existing_run(connection, prepared, inserted)
            connection.commit()
            disposition = "inserted"
    except Exception as error:
        if connection.in_transaction:
            connection.rollback()
        _record_prepared_failure(prepared, error)
        if isinstance(error, WeatherPersistenceError):
            raise
        if isinstance(error, sqlite3.Error):
            raise WeatherPersistenceError(
                "Weather SQLite transaction failed and was rolled back."
            ) from error
        raise WeatherPersistenceError("Weather persistence did not complete.") from error
    finally:
        connection.close()

    completed_at_utc = _now_utc()
    try:
        receipt = _publish_receipt(
            prepared,
            database_identity=_database_identity(resolved_url, root),
            disposition=disposition,
            table_counts=counts,
            persisted_graph_sha256=persisted_graph_sha256,
            completed_at_utc=completed_at_utc,
        )
        events = prepared.ledger.load_events()
        if not (events[-1].stage == "persisted" and events[-1].disposition == "persisted"):
            prepared.ledger.append(
                invocation_mode="resume",
                stage="persisted",
                disposition="persisted",
                occurred_at_utc=completed_at_utc,
                evidence=receipt,
            )
    except Exception as error:
        _record_prepared_failure(prepared, error, failure_kind="receipt")
        if isinstance(error, WeatherPersistenceError):
            raise
        raise WeatherPersistenceError(
            "Weather database commit succeeded but receipt/state publication did not complete."
        ) from error
    return {
        "status": disposition,
        "run_key": run_key,
        "persistence_input_sha256": prepared.persistence_input_sha256,
        "receipt": receipt.relative_path,
        "table_counts": counts,
    }
