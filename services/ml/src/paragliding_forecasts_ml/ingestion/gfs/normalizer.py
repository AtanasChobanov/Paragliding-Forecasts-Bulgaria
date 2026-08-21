"""T-017 canonical normalization for immutable GFS parser output."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from typing import Literal

import numpy as np
from pydantic import Field

from ..atmosphere.contracts import ArtifactReference, AtmosphericContract, StageManifest
from ..weather.artifacts import WeatherArtifactStore, stage_input_fingerprint
from .parser import (
    GfsNativeGridMessage,
    load_array,
    load_batch,
)

GFS_NORMALIZER_VERSION = "gfs-normalizer/1"


class GfsCanonicalGridMessage(AtmosphericContract):
    """One canonical grid grain prior to deterministic S05 site sampling."""

    field_code: str
    grain: Literal["surface", "pressure_level", "convection", "interval"]
    source_selector_keys: tuple[str, ...] = Field(min_length=1)
    canonical_unit: str
    values: ArtifactReference
    quality_state: Literal["real", "derived", "missing", "sentinel_missing", "invalid_payload"]
    valid_at_utc: str
    pressure_pa: float | None = Field(default=None, gt=0)
    dimension: str | None = None
    interval_start_utc: str | None = None
    interval_end_utc: str | None = None
    statistic_type: Literal["instantaneous", "interval_average", "accumulation"] | None = None
    native_sign_convention: str | None = None
    normalization_method: str | None = None
    normalization_version: str | None = None
    derivation_method: str | None = None
    derivation_version: str | None = None


class GfsCanonicalGridBatch(AtmosphericContract):
    """Separate canonical surface and pressure-level output grains for S05."""

    gfs_canonical_grid_batch_schema_version: Literal[1] = 1
    run_key: str
    parser_stage_manifest: ArtifactReference
    normalizer_version: str = GFS_NORMALIZER_VERSION
    surface_grains: tuple[GfsCanonicalGridMessage, ...]
    pressure_level_grains: tuple[GfsCanonicalGridMessage, ...]
    source_unsupported_selectors: tuple[str, ...]


_DIRECT: dict[str, tuple[str, str, str | None]] = {
    "tmp_2m": ("air_temperature_k", "surface", None),
    "dpt_2m": ("dew_point_temperature_k", "surface", None),
    "rh_2m": ("relative_humidity_percent", "surface", None),
    "ugrd_10m": ("wind_u_m_s", "surface", None),
    "vgrd_10m": ("wind_v_m_s", "surface", None),
    "pres_surface": ("air_pressure_pa", "surface", "surface"),
    "prmsl": ("air_pressure_pa", "surface", "mean_sea_level"),
    "hpbl": ("provider_boundary_layer_height_agl_m", "surface", None),
    "tcdc": ("cloud_cover_percent", "surface", "total"),
    "lcdc": ("cloud_cover_percent", "surface", "low"),
    "mcdc": ("cloud_cover_percent", "surface", "mid"),
    "hcdc": ("cloud_cover_percent", "surface", "high"),
    "pwat": ("total_column_water_vapour_kg_m2", "surface", None),
}

_PRESSURE_FIELDS = {
    "hgt": "geopotential_height_msl_m",
    "tmp": "air_temperature_k",
    "rh": "relative_humidity_percent",
    "ugrd": "wind_u_m_s",
    "vgrd": "wind_v_m_s",
    "vvel": "vertical_velocity_pa_s",
}


def normalize(
    store: WeatherArtifactStore, parser_stage_manifest: ArtifactReference, *, occurred_at_utc: str
) -> ArtifactReference:
    """Normalize a complete parser stage without rereading any remote source."""

    batch = load_batch(store, parser_stage_manifest)
    fingerprint = stage_input_fingerprint(
        stage="normalizer",
        producer_version=GFS_NORMALIZER_VERSION,
        inputs=(parser_stage_manifest,),
        configuration={"catalogue": "t017-spike-v1", "normalization": GFS_NORMALIZER_VERSION},
    )
    directory = store.begin_stage("normalizer", GFS_NORMALIZER_VERSION, fingerprint)
    surface: list[GfsCanonicalGridMessage] = []
    pressure: list[GfsCanonicalGridMessage] = []
    messages = {message.selector_key: message for message in batch.messages}
    for message in batch.messages:
        if message.selector_key in _DIRECT:
            surface.append(_direct(store, directory, message, *_DIRECT[message.selector_key]))
        elif _is_pressure(message.selector_key):
            pressure.append(_pressure(store, directory, message))
        elif message.selector_key.startswith(("cape_", "cin_")):
            surface.append(_convection(store, directory, message))
        elif message.selector_key == "apcp":
            surface.append(
                _interval(store, directory, message, "precipitation_amount_mm", "accumulation")
            )
        elif message.selector_key == "dswrf":
            surface.append(
                _interval(store, directory, message, "shortwave_radiation_w_m2", "interval_average")
            )
    surface.extend(_wind_derivations(store, directory, messages, pressure=False))
    pressure.extend(_wind_derivations(store, directory, messages, pressure=True))
    unsupported = tuple(sorted({"gust_surface", "orog"} & set(messages)))
    output = GfsCanonicalGridBatch(
        run_key=batch.run_key,
        parser_stage_manifest=parser_stage_manifest,
        surface_grains=tuple(surface),
        pressure_level_grains=tuple(pressure),
        source_unsupported_selectors=unsupported,
    )
    output_reference = store.write_stage_model(
        directory,
        "canonical-grid-batch.json",
        "gfs_canonical_grid_batch",
        output,
        record_count=len(surface) + len(pressure),
    )
    outputs = tuple([item.values for item in (*surface, *pressure)] + [output_reference])
    return store.write_stage_manifest(
        directory,
        StageManifest(
            run_key=batch.run_key,
            stage="normalizer",
            producer_version=GFS_NORMALIZER_VERSION,
            input_fingerprint_sha256=fingerprint,
            inputs=(parser_stage_manifest,),
            outputs=outputs,
            configuration={"catalogue": "t017-spike-v1", "normalization": GFS_NORMALIZER_VERSION},
            disposition="complete",
            started_at_utc=occurred_at_utc,
            completed_at_utc=occurred_at_utc,
        ),
    )


def _direct(
    store: WeatherArtifactStore,
    directory,
    message: GfsNativeGridMessage,
    field_code: str,
    grain: str,
    dimension: str | None,
) -> GfsCanonicalGridMessage:
    values = load_array(store, message.values)
    reference = _write_array(store, directory, f"canonical-{message.selector_key}", values)
    return _message(
        message,
        field_code=field_code,
        grain=grain,
        values=reference,
        dimension=dimension,
        normalization_method="gfs_native_unit_retained",
    )


def _pressure(
    store: WeatherArtifactStore, directory, message: GfsNativeGridMessage
) -> GfsCanonicalGridMessage:
    name, pressure_hpa = message.selector_key.rsplit("_", maxsplit=1)
    field_code = _PRESSURE_FIELDS[name]
    values = load_array(store, message.values)
    method = "gfs_geopotential_height_gpm_retained" if name == "hgt" else "gfs_native_unit_retained"
    return _message(
        message,
        field_code=field_code,
        grain="pressure_level",
        values=_write_array(store, directory, f"canonical-{message.selector_key}", values),
        pressure_pa=float(pressure_hpa) * 100,
        normalization_method=method,
    )


def _convection(
    store: WeatherArtifactStore, directory, message: GfsNativeGridMessage
) -> GfsCanonicalGridMessage:
    values = load_array(store, message.values)
    is_cin = message.selector_key.startswith("cin_")
    if is_cin:
        values = np.abs(values)
    dimension = "surface" if message.selector_key.endswith("surface") else "180-0_mb_above_ground"
    return _message(
        message,
        field_code=(
            "convective_inhibition_magnitude_j_per_kg"
            if is_cin
            else "convective_available_potential_energy_j_per_kg"
        ),
        grain="convection",
        values=_write_array(store, directory, f"canonical-{message.selector_key}", values),
        dimension=dimension,
        native_sign_convention=("signed_non_positive" if is_cin else None),
        normalization_method=(
            "gfs_cin_absolute_magnitude" if is_cin else "gfs_native_unit_retained"
        ),
    )


def _interval(
    store: WeatherArtifactStore,
    directory,
    message: GfsNativeGridMessage,
    field_code: str,
    statistic_type: Literal["accumulation", "interval_average"],
) -> GfsCanonicalGridMessage:
    values = load_array(store, message.values)
    start = _add_hours(message.reference_at_utc, message.step_start_hours)
    end = _add_hours(message.reference_at_utc, message.step_end_hours)
    method = (
        "gfs_kg_m2_to_mm"
        if field_code == "precipitation_amount_mm"
        else "gfs_interval_average_retained"
    )
    return _message(
        message,
        field_code=field_code,
        grain="interval",
        values=_write_array(store, directory, f"canonical-{message.selector_key}", values),
        interval_start_utc=start,
        interval_end_utc=end,
        statistic_type=statistic_type,
        normalization_method=method,
    )


def _wind_derivations(
    store: WeatherArtifactStore,
    directory,
    messages: dict[str, GfsNativeGridMessage],
    *,
    pressure: bool,
) -> list[GfsCanonicalGridMessage]:
    pairs: list[tuple[GfsNativeGridMessage, GfsNativeGridMessage]] = []
    if pressure:
        for level in (925, 850, 700):
            u, v = messages.get(f"ugrd_{level}"), messages.get(f"vgrd_{level}")
            if u and v:
                pairs.append((u, v))
    else:
        u, v = messages.get("ugrd_10m"), messages.get("vgrd_10m")
        if u and v:
            pairs.append((u, v))
    result: list[GfsCanonicalGridMessage] = []
    for u, v in pairs:
        u_values, v_values = load_array(store, u.values), load_array(store, v.values)
        speed = np.hypot(u_values, v_values)
        direction = (np.degrees(np.arctan2(-u_values, -v_values)) + 360.0) % 360.0
        direction[np.isclose(speed, 0.0, rtol=0.0, atol=0.0)] = np.nan
        grain = "pressure_level" if pressure else "surface"
        pressure_pa = u.level * 100 if pressure else None
        quality = _derived_quality(speed, direction)
        result.append(
            _message(
                u,
                field_code="wind_speed_m_s",
                grain=grain,
                values=_write_array(
                    store, directory, f"derived-{u.selector_key}-wind-speed", speed
                ),
                pressure_pa=pressure_pa,
                quality_state=quality,
                derivation_method="wind_speed_from_u_v",
            )
        )
        result.append(
            _message(
                u,
                field_code="wind_direction_degrees_from_north",
                grain=grain,
                values=_write_array(
                    store, directory, f"derived-{u.selector_key}-wind-direction", direction
                ),
                pressure_pa=pressure_pa,
                quality_state=quality,
                derivation_method="meteorological_wind_direction_from_u_v",
            )
        )
    return result


def _message(
    source: GfsNativeGridMessage,
    *,
    field_code: str,
    grain: str,
    values: ArtifactReference,
    quality_state: Literal["real", "derived", "missing", "sentinel_missing", "invalid_payload"]
    | None = None,
    pressure_pa: float | None = None,
    dimension: str | None = None,
    interval_start_utc: str | None = None,
    interval_end_utc: str | None = None,
    statistic_type: Literal["instantaneous", "interval_average", "accumulation"] | None = None,
    native_sign_convention: str | None = None,
    normalization_method: str | None = None,
    derivation_method: str | None = None,
) -> GfsCanonicalGridMessage:
    return GfsCanonicalGridMessage(
        field_code=field_code,
        grain=grain,
        source_selector_keys=(source.selector_key,),
        canonical_unit=_unit(field_code),
        values=values,
        quality_state=quality_state or source.quality_state,
        valid_at_utc=source.valid_at_utc,
        pressure_pa=pressure_pa,
        dimension=dimension,
        interval_start_utc=interval_start_utc,
        interval_end_utc=interval_end_utc,
        statistic_type=statistic_type,
        native_sign_convention=native_sign_convention,
        normalization_method=normalization_method,
        normalization_version="gfs-normalization/1" if normalization_method else None,
        derivation_method=derivation_method,
        derivation_version="gfs-normalization/1" if derivation_method else None,
    )


def _write_array(
    store: WeatherArtifactStore, directory, artifact_key: str, array: np.ndarray
) -> ArtifactReference:
    buffer = io.BytesIO()
    np.save(buffer, array, allow_pickle=False)
    return store.write_stage_bytes(
        directory,
        f"{artifact_key}.npy",
        artifact_key,
        buffer.getvalue(),
        media_type="application/x-npy",
        record_count=int(array.size),
    )


def _is_pressure(selector_key: str) -> bool:
    return selector_key.rsplit("_", maxsplit=1)[0] in _PRESSURE_FIELDS


def _derived_quality(*arrays: np.ndarray) -> Literal["derived", "sentinel_missing"]:
    return "sentinel_missing" if any(np.isnan(array).any() for array in arrays) else "derived"


def _add_hours(timestamp: str, hours: float) -> str:
    return (
        datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        + timedelta(hours=hours)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def _unit(field_code: str) -> str:
    return {
        "air_temperature_k": "K",
        "dew_point_temperature_k": "K",
        "relative_humidity_percent": "%",
        "air_pressure_pa": "Pa",
        "wind_u_m_s": "m/s",
        "wind_v_m_s": "m/s",
        "wind_speed_m_s": "m/s",
        "wind_direction_degrees_from_north": "degree",
        "geopotential_height_msl_m": "m",
        "vertical_velocity_pa_s": "Pa/s",
        "provider_boundary_layer_height_agl_m": "m",
        "cloud_cover_percent": "%",
        "total_column_water_vapour_kg_m2": "kg/m2",
        "precipitation_amount_mm": "mm",
        "shortwave_radiation_w_m2": "W/m2",
        "convective_available_potential_energy_j_per_kg": "J/kg",
        "convective_inhibition_magnitude_j_per_kg": "J/kg",
    }[field_code]
