"""Read-only, bounded verification of retained model-column inputs.

This boundary deliberately verifies compact decoded values, not deleted raw GRIB
payloads. It never resumes ingestion, appends ledger events or changes SQLite.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import UTC, date, datetime, time
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from ...ingestion.atmosphere.contracts import (
    ArtifactReference,
    StageManifest,
    validate_utc_timestamp,
)
from ...ingestion.gfs.compact import load_matrix_slice, strict_compact_bilinear_value
from ...ingestion.gfs.models import GFS_SOURCE_ID
from ...ingestion.gfs.normalizer import GfsCompactCanonicalGridBatch
from ...ingestion.gfs.profile import GFS_FEATURE_PROFILE_PRESSURES_HPA
from ...ingestion.weather.artifacts import WeatherArtifactStore
from ...ingestion.weather.features.aggregation import sofia_flying_window
from ...ingestion.weather.grid import site_config_fingerprint
from ...ingestion.weather.persistence_models import WeatherPersistenceReceipt
from ...ingestion.weather.spatial import CanonicalSiteSampleBatch
from ...ingestion.weather.state import RunStateLedger
from ...storage.sqlite import configured_database_url, open_read_only_database
from .models import HourlyInput, ProfileLevel


class CloudbaseInputError(ValueError):
    """A retained forecast cannot be trusted or selected without ambiguity."""


def utc(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_identity(run: dict) -> tuple[str, int, str]:
    """Pin DEC-066 issue identity without selecting a newer, leaked forecast."""
    reference = datetime.fromisoformat(validate_utc_timestamp(run["reference_at_utc"]))
    target = date.fromisoformat(run["target_local_date"])
    horizon = (target - reference.date()).days
    if (
        run["status"] != "succeeded"
        or run["source_code"] != GFS_SOURCE_ID
        or run["source_kind"] != "forecast"
        or reference.utcoffset() != UTC.utcoffset(reference)
        or reference.time().replace(tzinfo=None) != time(6)
        or horizon not in (1, 2, 3)
    ):
        raise CloudbaseInputError("Expected a succeeded GFS 06Z D+1/D+2/D+3 forecast run.")
    cutoff = datetime.combine(reference.date(), time(16), tzinfo=ZoneInfo("Europe/Sofia"))
    return utc(reference), horizon, utc(cutoff)


class RetainedReader:
    def __init__(self, root: Path, run: dict):
        self.run = run
        self.store = WeatherArtifactStore(run["run_key"], project_root=root)
        self.snapshot = RunStateLedger(self.store).load_state()
        self.references: dict[str, dict] = {}

    def read(self, reference: ArtifactReference) -> bytes:
        # All interim evidence must belong to this run; raw manifests use raw_dir.
        expected = (
            self.store.raw_dir
            if reference.artifact_key == "raw_manifest"
            else self.store.interim_dir
        )
        path = self.store.verify_reference(reference, expected_root=expected)
        self.references[reference.relative_path] = reference.model_dump(mode="json")
        return path.read_bytes()

    def event_reference(self, name: str) -> ArtifactReference:
        event = self.snapshot.effective_event(name)
        if event is None or event.evidence is None:
            raise CloudbaseInputError(f"Required effective weather event is absent: {name}")
        return event.evidence

    def stage(self, name: str, expected_stage: str) -> StageManifest:
        result = StageManifest.model_validate_json(
            self.read(self.event_reference(name)), strict=True
        )
        if (
            result.stage != expected_stage
            or result.disposition != "complete"
            or result.run_key != self.run["run_key"]
        ):
            raise CloudbaseInputError(f"Invalid effective {name} stage.")
        return result

    def batch_output(self, stage: StageManifest, key: str) -> bytes:
        candidates = [reference for reference in stage.outputs if reference.artifact_key == key]
        if len(candidates) != 1:
            raise CloudbaseInputError(f"Expected one retained output: {key}")
        return self.read(candidates[0])

    def load(self) -> tuple[GfsCompactCanonicalGridBatch, CanonicalSiteSampleBatch]:
        raw = self.event_reference("raw_complete")
        if raw.sha256 != self.run["raw_manifest_sha256"]:
            raise CloudbaseInputError("SQLite and retained raw-manifest identity disagree.")
        self.read(raw)  # Metadata only; never dereference raw payloads.
        metadata = self.store.read_raw_manifest(raw)
        if metadata.source_id != GFS_SOURCE_ID or metadata.status != "complete":
            raise CloudbaseInputError("Raw metadata is not a complete GFS source.")
        persistence = self.stage("persisted", "persistence")
        receipt = WeatherPersistenceReceipt.model_validate_json(
            self.batch_output(persistence, "weather_persistence_receipt"), strict=True
        )
        if (
            receipt.run_key != self.run["run_key"]
            or receipt.source_id != GFS_SOURCE_ID
            or receipt.target_local_date != self.run["target_local_date"]
            or receipt.feature_manifest.sha256 != self.run["feature_manifest_sha256"]
            or receipt.persistence_input_sha256 != self.run["persistence_input_sha256"]
        ):
            raise CloudbaseInputError("SQLite and retained persistence receipt disagree.")
        normalizer = self.stage("normalized", "normalizer")
        batch = GfsCompactCanonicalGridBatch.model_validate_json(
            self.batch_output(normalizer, "gfs_compact_canonical_grid_batch"), strict=True
        )
        if batch.run_key != self.run[
            "run_key"
        ] or batch.parser_stage_manifest != self.event_reference("parsed"):
            raise CloudbaseInputError("Canonical batch mixes run/parser lineage.")
        parser = self.stage("parsed", "parser")
        if raw not in parser.inputs:
            raise CloudbaseInputError("Parser does not consume the effective raw metadata.")
        if batch.parser_stage_manifest not in normalizer.inputs:
            raise CloudbaseInputError("Normalizer does not consume the effective parser.")
        if batch.reused_parser_values_matrix not in parser.outputs:
            raise CloudbaseInputError("Compact matrix is not an effective parser output.")
        spatial = self.stage("spatially_aligned", "spatial")
        samples = CanonicalSiteSampleBatch.model_validate_json(
            self.batch_output(spatial, "canonical_site_sample_batch"), strict=True
        )
        if (
            samples.run_key != self.run["run_key"]
            or samples.normalizer_stage_manifest != self.event_reference("normalized")
            or samples.normalizer_stage_manifest not in spatial.inputs
            or samples.site_config_sha256 != site_config_fingerprint(samples.site_configs)
            or samples.grid_geometry_sha256 != batch.grid.descriptor.native_geometry.geometry_sha256
        ):
            raise CloudbaseInputError(
                "Sampling metadata disagrees with the effective model column."
            )
        for reference in (batch.reused_parser_values_matrix, batch.derived_values_matrix):
            if reference is not None:
                self.store.verify_reference(reference, expected_root=self.store.interim_dir)
                self.references[reference.relative_path] = reference.model_dump(mode="json")
        # Record the accepted validation/feature anchors without recursive raw verification.
        validation = self.stage("validated", "validator")
        feature = self.stage("features_built", "feature_builder")
        if (
            self.event_reference("spatially_aligned") not in validation.inputs
            or self.event_reference("validated") not in feature.inputs
            or receipt.feature_manifest != self.event_reference("features_built")
            or receipt.feature_manifest not in persistence.inputs
        ):
            raise CloudbaseInputError("Accepted validation/feature lineage disagrees.")
        return batch, samples

    def value(self, batch, reference, footprint) -> float | None:
        array = load_matrix_slice(
            self.store, reference, expected_selection_sha256=batch.grid.descriptor.selection_sha256
        )
        result = strict_compact_bilinear_value(array, batch.grid.descriptor, footprint)
        return float(result) if result is not None and math.isfinite(result) else None

    def grain_value(self, batch, grain, footprint) -> float | None:
        if grain is None or grain.quality_state not in {"real", "derived"}:
            return None
        return self.value(batch, grain.values, footprint)

    def hours(self, points: list[dict]) -> list[HourlyInput]:
        reference, horizon, cutoff = run_identity(self.run)
        batch, samples = self.load()
        if len({s.site_id for s in samples.site_configs}) != len(samples.site_configs):
            raise CloudbaseInputError("Duplicate retained site configuration.")
        footprints = {f.site_id: f for f in samples.point_footprints}
        if len(footprints) != len(samples.site_configs):
            raise CloudbaseInputError("Ambiguous or incomplete point footprints.")
        point_index = {(p["site_id"], p["valid_at_utc"]): p for p in points}
        if len(point_index) != len(points):
            raise CloudbaseInputError("Duplicate persisted point sample.")
        surface: dict[tuple, object] = {}
        levels: dict[tuple, object] = {}
        for grain in (*batch.surface_grains, *batch.pressure_level_grains):
            if grain.reference_at_utc != reference:
                raise CloudbaseInputError("Canonical fields mix forecast cycles.")
            expected_lead = (
                datetime.fromisoformat(grain.valid_at_utc) - datetime.fromisoformat(reference)
            ).total_seconds() / 3600
            if grain.lead_hours != expected_lead:
                raise CloudbaseInputError("Canonical field lead disagrees with its valid time.")
            expected_unit = {
                "air_pressure_pa": "Pa",
                "air_temperature_k": "K",
                "specific_humidity_kg_per_kg": "kg/kg",
                "geopotential_height_msl_m": "m",
                "provider_boundary_layer_height_agl_m": "m",
                "cloud_cover_percent": "%",
                "surface_sensible_heat_flux_upward_w_m2": "W/m2",
                "surface_latent_heat_flux_upward_w_m2": "W/m2",
            }.get(grain.field_code)
            if expected_unit is not None and grain.canonical_unit != expected_unit:
                raise CloudbaseInputError("Canonical source units disagree with the calculation.")
            key = (grain.valid_at_utc, grain.field_code, grain.dimension, grain.pressure_pa)
            index = levels if grain.pressure_pa is not None else surface
            if key in index:
                raise CloudbaseInputError("Duplicate canonical source field.")
            index[key] = grain
        rows = []
        window = sofia_flying_window(date.fromisoformat(self.run["target_local_date"]))
        for site in sorted(samples.site_configs, key=lambda s: s.site_id):
            footprint = footprints[site.site_id]
            if footprint.purpose != "point" or footprint.sampling_method != "bilinear":
                raise CloudbaseInputError(
                    "Model column requires the retained bilinear point footprint."
                )
            weights = [node.interpolation_weight for node in footprint.nodes]
            if any(w is None or w < 0 for w in weights) or not math.isclose(
                sum(weights), 1, abs_tol=1e-9
            ):
                raise CloudbaseInputError("Invalid retained point weights.")
            for valid in window.expected_instants_utc:
                issues: list[str] = []
                point = point_index.get((site.site_id, valid))
                ready = None if point is None else point["required_inputs_last_modified_at_utc"]
                if ready is not None:
                    validate_utc_timestamp(ready)
                if ready is None or ready > cutoff:
                    issues.append("unavailable:source_not_ready_by_cutoff")
                if point is not None and (
                    point["reference_at_utc"] != reference
                    or point["lead_hours"]
                    != (
                        datetime.fromisoformat(valid) - datetime.fromisoformat(reference)
                    ).total_seconds()
                    / 3600
                ):
                    raise CloudbaseInputError("Persisted hour mixes cycle or lead identity.")

                def scalar(code, dimension=None, valid=valid, footprint=footprint):
                    grain = surface.get((valid, code, dimension, None))
                    return self.grain_value(batch, grain, footprint)

                terrain = self.value(batch, batch.grid.model_elevation_msl_m, footprint)
                ps = scalar("air_pressure_pa", "surface")
                profile = []
                if ps is not None and terrain is not None:
                    for hpa in GFS_FEATURE_PROFILE_PRESSURES_HPA:
                        pressure = hpa * 100.0
                        if pressure >= ps:
                            continue
                        values = []
                        for code in (
                            "geopotential_height_msl_m",
                            "air_temperature_k",
                            "specific_humidity_kg_per_kg",
                        ):
                            grain = levels.get((valid, code, None, pressure))
                            values.append(self.grain_value(batch, grain, footprint))
                        z, t, q = values
                        if z is not None and z <= terrain:
                            continue
                        if any(v is None for v in values) or t <= 0 or not 0 <= q < 1:
                            issues.append(f"profile_missing:{hpa}")
                            continue
                        profile.append(
                            ProfileLevel(
                                pressure_pa=pressure,
                                height_msl_m=z,
                                temperature_k=t,
                                specific_humidity_kg_kg=q,
                            )
                        )

                def interval(code, valid=valid):
                    grain = surface.get((valid, code, None, None))
                    if (
                        grain is None
                        or grain.interval_start_utc is None
                        or grain.interval_end_utc is None
                    ):
                        return None
                    return (grain.interval_start_utc, grain.interval_end_utc)

                rows.append(
                    HourlyInput(
                        run_key=self.run["run_key"],
                        site_id=site.site_id,
                        site_slug=site.site_slug,
                        target_local_date=self.run["target_local_date"],
                        valid_at_utc=valid,
                        reference_at_utc=reference,
                        issue_cutoff_utc=cutoff,
                        source_ready_at_utc=ready,
                        horizon_days=horizon,
                        site_elevation_msl_m=site.reference_elevation_msl_m,
                        model_elevation_msl_m=terrain,
                        surface_pressure_pa=ps,
                        temperature_2m_k=scalar("air_temperature_k", "2m_above_ground"),
                        specific_humidity_2m_kg_kg=scalar(
                            "specific_humidity_kg_per_kg", "2m_above_ground"
                        ),
                        pbl_model_agl_m=scalar("provider_boundary_layer_height_agl_m"),
                        low_cloud_percent=scalar("cloud_cover_percent", "low"),
                        total_cloud_percent=scalar("cloud_cover_percent", "total"),
                        sensible_heat_flux_w_m2=scalar("surface_sensible_heat_flux_upward_w_m2"),
                        latent_heat_flux_w_m2=scalar("surface_latent_heat_flux_upward_w_m2"),
                        sensible_interval=interval("surface_sensible_heat_flux_upward_w_m2"),
                        latent_interval=interval("surface_latent_heat_flux_upward_w_m2"),
                        stored_lcl_model_agl_m=None
                        if point is None
                        else point["mixed_layer_lcl_agl_m"],
                        profile=tuple(profile),
                        input_issues=tuple(issues),
                    )
                )
        return rows


def read_inputs(
    run_key: str, *, project_root: Path, database_url: str | None = None
) -> tuple[list[HourlyInput], dict]:
    if str(UUID(run_key)) != run_key:
        raise CloudbaseInputError("run-key must be a lowercase UUID.")
    connection = open_read_only_database(configured_database_url(database_url), project_root)
    connection.row_factory = sqlite3.Row
    try:
        records = connection.execute(
            """SELECT r.*, p.reference_at_utc, s.code AS source_code, s.source_kind
               FROM weather_ingestion_runs r
               JOIN weather_product_runs p ON p.id=r.product_run_id
               JOIN weather_sources s ON s.id=p.source_id WHERE r.run_key=?""",
            (run_key,),
        ).fetchall()
        if len(records) != 1:
            raise CloudbaseInputError("Expected one persisted weather run.")
        run = dict(records[0])
        run_identity(run)
        points = [
            dict(p)
            for p in connection.execute(
                """SELECT f.site_id, v.valid_at_utc, v.lead_hours,
                      v.required_inputs_last_modified_at_utc, p.reference_at_utc,
                      x.mixed_layer_lcl_agl_m
               FROM weather_point_samples x
               JOIN weather_sampling_footprints f ON f.id=x.point_footprint_id
               JOIN weather_product_valid_times v ON v.id=x.product_valid_time_id
               JOIN weather_product_runs p ON p.id=v.product_run_id
               WHERE x.ingestion_run_id=? AND f.purpose='point'
               ORDER BY f.site_id,v.valid_at_utc""",
                (run["id"],),
            )
        ]
        reader = RetainedReader(project_root, run)
        hours = reader.hours(points)
        evidence = {
            "run_key": run_key,
            "source_id": run["source_code"],
            "reference_at_utc": run["reference_at_utc"],
            "target_local_date": run["target_local_date"],
            "verification_scope": "retained_compact_values_and_metadata_not_raw_grib",
            "references": [reader.references[p] for p in sorted(reader.references)],
        }
        return hours, evidence
    finally:
        connection.close()
