"""Deterministic bilinear point and physical-radius sampling for canonical GFS grids."""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
from pydantic import Field

from ..atmosphere.contracts import ArtifactReference, AtmosphericContract, StageManifest
from ..gfs.compact import (
    GridNodeIndex,
    MatrixSliceReference,
    compact_node_value,
    load_matrix_slice,
    strict_compact_bilinear_value,
)
from ..gfs.normalizer import (
    GfsCanonicalGridMessage,
    GfsCompactCanonicalGridBatch,
    load_canonical_batch,
)
from ..gfs.parser import load_array
from .artifacts import WeatherArtifactStore, stage_input_fingerprint
from .grid import (
    GridGeometryError as SpatialSamplingError,
)
from .grid import (
    SamplingFootprint,
    SamplingNode,  # noqa: F401 - legacy import compatibility
    SiteConfigSnapshot,
    _haversine_km,  # noqa: F401 - legacy import compatibility
    bilinear_footprint,
    radius_footprint,
    site_config_fingerprint,
    snapshot_site_configs,
    strict_bilinear_value,
)
from .sampling_policy import SamplingPolicy, load_sampling_policy
from .serialization import canonical_json_bytes, sha256_bytes
from .sites import load_site_sampling_configs
from .wind import component_wind_speed

WEATHER_SPATIAL_VERSION = "weather-spatial/6"


class SampledField(AtmosphericContract):
    field_code: str
    grain: Literal["surface", "convection", "interval", "pressure_level"]
    canonical_unit: str
    canonical_value: float | None
    quality_state: Literal["real", "derived", "missing", "sentinel_missing", "unsupported"]
    dimension: str | None = None
    pressure_pa: float | None = Field(default=None, gt=0)
    interval_start_utc: str | None = None
    interval_end_utc: str | None = None
    statistic_type: str | None = None
    source_selector_keys: tuple[str, ...] = Field(min_length=1)
    source_raw_artifact_keys: tuple[str, ...] = Field(min_length=1)
    source_native_message_references: tuple[str, ...] = Field(min_length=1)
    normalization_method: str | None = None
    normalization_version: str | None = None
    derivation_method: str | None = None
    derivation_version: str | None = None


class SampledProfileLevel(AtmosphericContract):
    pressure_pa: float = Field(gt=0)
    geopotential_height_msl_m: float
    level_height_agl_m: float = Field(ge=0)
    model_level_height_agl_m: float = Field(ge=0)
    fields: tuple[SampledField, ...] = Field(min_length=1)


class TerrainDiagnostic(AtmosphericContract):
    site_elevation_msl_m: float
    model_elevation_msl_m: float
    model_minus_site_elevation_m: float
    absolute_mismatch_m: float = Field(ge=0)
    disposition: Literal["reported"] = "reported"


class PressureLevelExclusion(AtmosphericContract):
    site_id: int = Field(gt=0)
    valid_at_utc: str
    pressure_pa: float = Field(gt=0)
    code: Literal["missing_geopotential_height", "below_site_or_model_terrain"]
    geopotential_height_msl_m: float | None = None
    site_level_height_agl_m: float | None = None
    model_level_height_agl_m: float | None = None


class SiteAlignedSample(AtmosphericContract):
    sample_identity_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    site_id: int = Field(gt=0)
    point_footprint_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    neighbourhood_footprint_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_at_utc: str
    valid_at_utc: str
    valid_local_date: str
    lead_hours: int | None = Field(default=None, ge=0, le=384)
    terrain: TerrainDiagnostic
    fields: tuple[SampledField, ...] = Field(min_length=1)
    profile_levels: tuple[SampledProfileLevel, ...]


class CanonicalSiteSampleBatch(AtmosphericContract):
    canonical_site_sample_batch_schema_version: Literal[3] = 3
    run_key: str
    normalizer_stage_manifest: ArtifactReference
    grid_key: Literal["gfs_0p25_global", "era5_0p25_global"]
    spatial_version: str = WEATHER_SPATIAL_VERSION
    policy_version: str
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    site_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sampling_fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    grid_geometry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    site_configs: tuple[SiteConfigSnapshot, ...] = Field(min_length=1)
    point_footprints: tuple[SamplingFootprint, ...] = Field(min_length=1)
    neighbourhood_footprints: tuple[SamplingFootprint, ...] = Field(min_length=1)
    samples: tuple[SiteAlignedSample, ...] = Field(min_length=1)
    pressure_level_exclusions: tuple[PressureLevelExclusion, ...]


class NeighbourhoodFieldValues(AtmosphericContract):
    field_code: str
    grain: Literal["surface", "pressure_level"]
    dimension: str | None = None
    pressure_pa: float | None = Field(default=None, gt=0)
    canonical_unit: str
    values: tuple[float | None, ...] = Field(min_length=1)
    source_selector_keys: tuple[str, ...] = Field(min_length=1)


class NeighbourhoodNodeRecord(AtmosphericContract):
    site_id: int = Field(gt=0)
    footprint_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    valid_at_utc: str
    fields: tuple[NeighbourhoodFieldValues, ...] = Field(min_length=1)


class NeighbourhoodNodeBatch(AtmosphericContract):
    neighbourhood_node_batch_schema_version: Literal[1] = 1
    run_key: str
    sampling_fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    records: tuple[NeighbourhoodNodeRecord, ...] = Field(min_length=1)


def pressure_level_agl_heights(
    geopotential_height_msl_m: float,
    site_elevation_msl_m: float,
    model_elevation_msl_m: float,
) -> tuple[float, float] | None:
    """Return site/model AGL only when the pressure surface is above both terrains."""

    site_agl = geopotential_height_msl_m - site_elevation_msl_m
    model_agl = geopotential_height_msl_m - model_elevation_msl_m
    return None if site_agl < 0 or model_agl < 0 else (site_agl, model_agl)


def _sampled_field(grain: GfsCanonicalGridMessage, value: float | None) -> SampledField:
    quality: Literal["real", "derived", "missing", "sentinel_missing", "unsupported"]
    if grain.quality_state == "unsupported":
        quality = "unsupported"
        value = None
    elif value is None:
        quality = "sentinel_missing"
    else:
        quality = "derived" if grain.quality_state == "derived" else "real"
    return SampledField(
        field_code=grain.field_code,
        grain=grain.grain,
        canonical_unit=grain.canonical_unit,
        canonical_value=value,
        quality_state=quality,
        dimension=grain.dimension,
        pressure_pa=grain.pressure_pa,
        interval_start_utc=grain.interval_start_utc,
        interval_end_utc=grain.interval_end_utc,
        statistic_type=grain.statistic_type,
        source_selector_keys=grain.source_selector_keys,
        source_raw_artifact_keys=grain.source_raw_artifact_keys,
        source_native_message_references=grain.source_native_message_references,
        normalization_method=grain.normalization_method,
        normalization_version=grain.normalization_version,
        derivation_method=grain.derivation_method,
        derivation_version=grain.derivation_version,
    )


def _derived_wind_fields(
    u_field: SampledField | None,
    v_field: SampledField | None,
    *,
    grain: Literal["surface", "pressure_level"],
    pressure_pa: float | None,
) -> tuple[SampledField, SampledField]:
    sources = tuple(item for item in (u_field, v_field) if item is not None)
    selector_keys = tuple(key for item in sources for key in item.source_selector_keys) or ("u_v",)
    raw_keys = tuple(key for item in sources for key in item.source_raw_artifact_keys) or (
        "missing",
    )
    references = tuple(
        key for item in sources for key in item.source_native_message_references
    ) or ("missing",)
    u_value = None if u_field is None else u_field.canonical_value
    v_value = None if v_field is None else v_field.canonical_value
    speed = None if u_value is None or v_value is None else component_wind_speed(u_value, v_value)
    direction = (
        None
        if speed is None or speed == 0
        else (math.degrees(math.atan2(-u_value, -v_value)) + 360.0) % 360.0
    )
    dimensions = {item.dimension for item in sources}
    if len(dimensions) > 1:
        raise SpatialSamplingError(
            "Derived wind components have incompatible dimension identities."
        )
    common = {
        "grain": grain,
        "pressure_pa": pressure_pa,
        "dimension": next(iter(dimensions)) if dimensions else None,
        "source_selector_keys": selector_keys,
        "source_raw_artifact_keys": raw_keys,
        "source_native_message_references": references,
        "derivation_version": "site-wind-derivation/1",
    }
    return (
        SampledField(
            field_code="wind_speed_m_s",
            canonical_unit="m/s",
            canonical_value=speed,
            quality_state="derived" if speed is not None else "sentinel_missing",
            derivation_method="wind_speed_from_bilinear_u_v",
            **common,
        ),
        SampledField(
            field_code="wind_direction_degrees_from_north",
            canonical_unit="degree",
            canonical_value=direction,
            quality_state="derived" if speed is not None else "sentinel_missing",
            derivation_method="meteorological_direction_from_bilinear_u_v",
            **common,
        ),
    )


def _valid_local_date(valid_at_utc: str, time_zone: str) -> str:
    try:
        zone = ZoneInfo(time_zone)
    except ZoneInfoNotFoundError as error:
        raise SpatialSamplingError(f"Unknown site time zone: {time_zone}") from error
    instant = datetime.strptime(valid_at_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    return instant.astimezone(zone).date().isoformat()


def _field_sort_key(field: SampledField) -> tuple[object, ...]:
    return (
        field.grain,
        field.pressure_pa or 0,
        field.field_code,
        field.dimension or "",
        field.interval_start_utc or "",
    )


def _grain_sort_key(grain: GfsCanonicalGridMessage) -> tuple[object, ...]:
    return (
        grain.grain,
        grain.pressure_pa or 0,
        grain.field_code,
        grain.dimension or "",
        grain.interval_start_utc or "",
    )


def _is_grid_wind_derivation(grain: GfsCanonicalGridMessage) -> bool:
    return (
        grain.field_code
        in {
            "wind_speed_m_s",
            "wind_direction_degrees_from_north",
        }
        and grain.derivation_method is not None
    )


def _neighbourhood_grains(
    grains: Iterable[GfsCanonicalGridMessage], policy: SamplingPolicy
) -> tuple[GfsCanonicalGridMessage, ...]:
    selected: list[GfsCanonicalGridMessage] = []
    for requested in policy.neighbourhood_sampling.fields:
        matches = [
            grain
            for grain in grains
            if grain.field_code == requested.field_code
            and grain.grain == requested.grain
            and grain.dimension == requested.dimension
            and grain.pressure_pa == requested.pressure_pa
            and not _is_grid_wind_derivation(grain)
        ]
        if len(matches) != 1:
            raise SpatialSamplingError(
                f"Neighbourhood field {requested.field_code}/{requested.pressure_pa} "
                "must resolve to exactly one canonical grain per valid time."
            )
        selected.append(matches[0])
    return tuple(selected)


def sample_canonical_sites(
    store: WeatherArtifactStore,
    normalizer_stage_manifest: ArtifactReference,
    *,
    database_url: str,
    occurred_at_utc: str,
    project_root=None,
) -> ArtifactReference:
    batch = load_canonical_batch(store, normalizer_stage_manifest)
    sites = load_site_sampling_configs(
        database_url, project_root or store.project_root, require_elevation=True
    )
    policy, policy_sha256 = load_sampling_policy()
    snapshots = snapshot_site_configs(sites)
    site_config_sha256 = site_config_fingerprint(snapshots)
    compact_descriptor = (
        batch.grid.descriptor if isinstance(batch, GfsCompactCanonicalGridBatch) else None
    )
    if compact_descriptor is not None:
        if (
            compact_descriptor.site_configs != snapshots
            or compact_descriptor.site_config_sha256 != site_config_sha256
            or compact_descriptor.sampling_policy_version != policy.policy_version
            or compact_descriptor.sampling_policy_sha256 != policy_sha256
        ):
            raise SpatialSamplingError(
                "Compact descriptor site/policy identities differ from spatial inputs."
            )
        point_footprints = compact_descriptor.point_footprints
        radius_footprints = compact_descriptor.neighbourhood_footprints
        grid_geometry_sha256 = compact_descriptor.native_geometry.geometry_sha256
        grid_key = compact_descriptor.native_geometry.grid_key
        model_elevation_reference = batch.grid.model_elevation_msl_m
        model_elevation_artifact = model_elevation_reference.artifact
        compact_selection_sha256: str | None = compact_descriptor.selection_sha256
    else:
        point_footprints = tuple(
            bilinear_footprint(
                batch.grid,
                site,
                method_version=policy.point_sampling.method_version,
                earth_radius_km=policy.neighbourhood_sampling.earth_mean_radius_km,
            )
            for site in sites
        )
        radius_footprints = tuple(
            radius_footprint(
                batch.grid,
                site,
                radius_km=policy.neighbourhood_sampling.radius_km,
                method_version=policy.neighbourhood_sampling.method_version,
                earth_radius_km=policy.neighbourhood_sampling.earth_mean_radius_km,
            )
            for site in sites
        )
        grid_geometry_sha256 = batch.grid.geometry_sha256
        grid_key = batch.grid.grid_key
        model_elevation_reference = batch.grid.model_elevation_msl_m
        model_elevation_artifact = model_elevation_reference
        compact_selection_sha256 = None
    configuration = {
        "spatial_version": WEATHER_SPATIAL_VERSION,
        "policy_version": policy.policy_version,
        "policy_sha256": policy_sha256,
        "site_config_sha256": site_config_sha256,
        "grid_geometry_sha256": grid_geometry_sha256,
        "model_elevation_sha256": model_elevation_artifact.sha256,
        "compact_selection_sha256": compact_selection_sha256,
    }
    fingerprint = stage_input_fingerprint(
        stage="spatial",
        producer_version=WEATHER_SPATIAL_VERSION,
        inputs=(normalizer_stage_manifest,),
        configuration=configuration,
    )
    existing = store.existing_stage_manifest("spatial", WEATHER_SPATIAL_VERSION, fingerprint)
    if existing is not None:
        return existing
    directory = store.begin_stage("spatial", WEATHER_SPATIAL_VERSION, fingerprint)
    point_by_site = {item.site_id: item for item in point_footprints}
    radius_by_site = {item.site_id: item for item in radius_footprints}
    array_cache: dict[tuple[str, int], np.ndarray] = {}

    def array(grain: GfsCanonicalGridMessage) -> np.ndarray:
        reference = grain.values
        if isinstance(reference, MatrixSliceReference):
            if compact_descriptor is None:
                raise SpatialSamplingError("Legacy grid cannot use a compact matrix slice.")
            key = (reference.artifact.sha256, reference.matrix_row)
            if key not in array_cache:
                array_cache[key] = load_matrix_slice(
                    store,
                    reference,
                    expected_selection_sha256=compact_descriptor.selection_sha256,
                )
            return array_cache[key]
        key = (reference.sha256, -1)
        if key not in array_cache:
            array_cache[key] = load_array(store, reference)
        return array_cache[key]

    def point_value(values: np.ndarray, footprint: SamplingFootprint) -> float | None:
        if compact_descriptor is not None:
            return strict_compact_bilinear_value(values, compact_descriptor, footprint)
        return strict_bilinear_value(values, batch.grid, footprint)

    if isinstance(model_elevation_reference, MatrixSliceReference):
        if compact_descriptor is None:
            raise SpatialSamplingError("Legacy grid cannot use compact model elevation.")
        model_elevation_values = load_matrix_slice(
            store,
            model_elevation_reference,
            expected_selection_sha256=compact_descriptor.selection_sha256,
        )
    else:
        model_elevation_values = load_array(store, model_elevation_reference)
    samples: list[SiteAlignedSample] = []
    exclusions: list[PressureLevelExclusion] = []
    neighbourhood_records: list[NeighbourhoodNodeRecord] = []
    all_grains = (*batch.surface_grains, *batch.pressure_level_grains)
    valid_times = sorted({grain.valid_at_utc for grain in all_grains})
    for site in sites:
        point = point_by_site[site.site_id]
        radius = radius_by_site[site.site_id]
        model_elevation = point_value(model_elevation_values, point)
        if model_elevation is None or site.reference_elevation_msl_m is None:
            raise SpatialSamplingError(f"Terrain sampling failed for site {site.site_slug}.")
        terrain = TerrainDiagnostic(
            site_elevation_msl_m=site.reference_elevation_msl_m,
            model_elevation_msl_m=model_elevation,
            model_minus_site_elevation_m=model_elevation - site.reference_elevation_msl_m,
            absolute_mismatch_m=abs(model_elevation - site.reference_elevation_msl_m),
        )
        for valid_at_utc in valid_times:
            valid_grains = tuple(
                sorted(
                    (grain for grain in all_grains if grain.valid_at_utc == valid_at_utc),
                    key=_grain_sort_key,
                )
            )
            if not valid_grains:
                continue
            reference_times = {grain.reference_at_utc for grain in valid_grains}
            lead_hours = {grain.lead_hours for grain in valid_grains}
            if len(reference_times) != 1 or len(lead_hours) != 1:
                raise SpatialSamplingError("One valid time mixes reference times or leads.")

            surface_fields = [
                _sampled_field(grain, point_value(array(grain), point))
                for grain in valid_grains
                if grain.grain != "pressure_level" and not _is_grid_wind_derivation(grain)
            ]
            surface_u = next(
                (field for field in surface_fields if field.field_code == "wind_u_m_s"), None
            )
            surface_v = next(
                (field for field in surface_fields if field.field_code == "wind_v_m_s"), None
            )
            surface_fields.extend(
                _derived_wind_fields(surface_u, surface_v, grain="surface", pressure_pa=None)
            )

            profiles: list[SampledProfileLevel] = []
            pressures = sorted(
                {
                    grain.pressure_pa
                    for grain in valid_grains
                    if grain.grain == "pressure_level" and grain.pressure_pa is not None
                },
                reverse=True,
            )
            for pressure_pa in pressures:
                pressure_grains = tuple(
                    grain
                    for grain in valid_grains
                    if grain.grain == "pressure_level"
                    and grain.pressure_pa == pressure_pa
                    and not _is_grid_wind_derivation(grain)
                )
                fields = [
                    _sampled_field(grain, point_value(array(grain), point))
                    for grain in pressure_grains
                ]
                height_field = next(
                    (field for field in fields if field.field_code == "geopotential_height_msl_m"),
                    None,
                )
                height = None if height_field is None else height_field.canonical_value
                if height is None:
                    exclusions.append(
                        PressureLevelExclusion(
                            site_id=site.site_id,
                            valid_at_utc=valid_at_utc,
                            pressure_pa=pressure_pa,
                            code="missing_geopotential_height",
                        )
                    )
                    continue
                agl_heights = pressure_level_agl_heights(
                    height, site.reference_elevation_msl_m, model_elevation
                )
                if agl_heights is None:
                    exclusions.append(
                        PressureLevelExclusion(
                            site_id=site.site_id,
                            valid_at_utc=valid_at_utc,
                            pressure_pa=pressure_pa,
                            code="below_site_or_model_terrain",
                            geopotential_height_msl_m=height,
                            site_level_height_agl_m=(height - site.reference_elevation_msl_m),
                            model_level_height_agl_m=height - model_elevation,
                        )
                    )
                    continue
                site_agl, model_agl = agl_heights
                pressure_u = next(
                    (field for field in fields if field.field_code == "wind_u_m_s"), None
                )
                pressure_v = next(
                    (field for field in fields if field.field_code == "wind_v_m_s"), None
                )
                fields.extend(
                    _derived_wind_fields(
                        pressure_u,
                        pressure_v,
                        grain="pressure_level",
                        pressure_pa=pressure_pa,
                    )
                )
                profiles.append(
                    SampledProfileLevel(
                        pressure_pa=pressure_pa,
                        geopotential_height_msl_m=height,
                        level_height_agl_m=site_agl,
                        model_level_height_agl_m=model_agl,
                        fields=tuple(sorted(fields, key=_field_sort_key)),
                    )
                )

            identity = sha256_bytes(
                canonical_json_bytes(
                    {
                        "run_key": batch.run_key,
                        "site_id": site.site_id,
                        "valid_at_utc": valid_at_utc,
                        "point_footprint_key": point.footprint_key,
                        "policy_sha256": policy_sha256,
                    }
                )
            )
            samples.append(
                SiteAlignedSample(
                    sample_identity_key=identity,
                    site_id=site.site_id,
                    point_footprint_key=point.footprint_key,
                    neighbourhood_footprint_key=radius.footprint_key,
                    reference_at_utc=next(iter(reference_times)),
                    valid_at_utc=valid_at_utc,
                    valid_local_date=_valid_local_date(valid_at_utc, site.site_time_zone),
                    lead_hours=next(iter(lead_hours)),
                    terrain=terrain,
                    fields=tuple(sorted(surface_fields, key=_field_sort_key)),
                    profile_levels=tuple(profiles),
                )
            )

            neighbourhood_fields: list[NeighbourhoodFieldValues] = []
            for grain in _neighbourhood_grains(valid_grains, policy):
                values = np.asarray(array(grain))
                node_values: list[float | None] = []
                for node in radius.nodes:
                    if compact_descriptor is not None:
                        value = compact_node_value(
                            values,
                            compact_descriptor,
                            GridNodeIndex(
                                row_index=node.row_index,
                                column_index=node.column_index,
                            ),
                        )
                    else:
                        value = float(
                            values.reshape(-1)[
                                node.row_index * batch.grid.column_count + node.column_index
                            ]
                        )
                    node_values.append(value if math.isfinite(value) else None)
                neighbourhood_fields.append(
                    NeighbourhoodFieldValues(
                        field_code=grain.field_code,
                        grain=grain.grain,
                        dimension=grain.dimension,
                        pressure_pa=grain.pressure_pa,
                        canonical_unit=grain.canonical_unit,
                        values=tuple(node_values),
                        source_selector_keys=grain.source_selector_keys,
                    )
                )
            neighbourhood_records.append(
                NeighbourhoodNodeRecord(
                    site_id=site.site_id,
                    footprint_key=radius.footprint_key,
                    valid_at_utc=valid_at_utc,
                    fields=tuple(neighbourhood_fields),
                )
            )

    sample_batch = CanonicalSiteSampleBatch(
        run_key=batch.run_key,
        normalizer_stage_manifest=normalizer_stage_manifest,
        grid_key=grid_key,
        policy_version=policy.policy_version,
        policy_sha256=policy_sha256,
        site_config_sha256=site_config_sha256,
        sampling_fingerprint_sha256=fingerprint,
        grid_geometry_sha256=grid_geometry_sha256,
        site_configs=snapshots,
        point_footprints=point_footprints,
        neighbourhood_footprints=radius_footprints,
        samples=tuple(samples),
        pressure_level_exclusions=tuple(exclusions),
    )
    neighbourhood_batch = NeighbourhoodNodeBatch(
        run_key=batch.run_key,
        sampling_fingerprint_sha256=fingerprint,
        records=tuple(neighbourhood_records),
    )
    samples_reference = store.write_stage_model(
        directory,
        "canonical-site-samples.json",
        "canonical_site_sample_batch",
        sample_batch,
        record_count=len(samples),
    )
    neighbourhood_reference = store.write_stage_model(
        directory,
        "neighbourhood-node-samples.json",
        "neighbourhood_node_batch",
        neighbourhood_batch,
        record_count=len(neighbourhood_records),
    )
    return store.write_stage_manifest(
        directory,
        StageManifest(
            run_key=batch.run_key,
            stage="spatial",
            producer_version=WEATHER_SPATIAL_VERSION,
            input_fingerprint_sha256=fingerprint,
            inputs=(normalizer_stage_manifest,),
            outputs=(samples_reference, neighbourhood_reference),
            configuration=configuration,
            disposition="complete",
            started_at_utc=occurred_at_utc,
            completed_at_utc=occurred_at_utc,
        ),
    )
