"""Unit/sentinel normalization and the small approved IGRA derivation set."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import cos, exp, isfinite, radians, sin

from .models import (
    CanonicalSounding,
    CanonicalSoundingLevel,
    NativeIgraDerivedSounding,
    NativeIgraSounding,
    ProviderDerivedSoundingLevel,
    ProviderDerivedSoundingParameters,
)
from .versions import NORMALIZER_VERSION


@dataclass(frozen=True)
class IgraNormalizationResult:
    soundings: tuple[CanonicalSounding, ...]
    levels: tuple[CanonicalSoundingLevel, ...]
    provider_parameters: tuple[ProviderDerivedSoundingParameters, ...]
    provider_levels: tuple[ProviderDerivedSoundingLevel, ...]
    report: dict[str, int]


def normalize(
    raw_soundings: tuple[NativeIgraSounding, ...],
    derived_soundings: tuple[NativeIgraDerivedSounding, ...],
    *,
    source_snapshot_id: str,
    inventory_latitude_deg: float | None,
    inventory_longitude_deg: float | None,
) -> IgraNormalizationResult:
    """Normalize every structurally selected record; validation owns dispositions later."""

    soundings: list[CanonicalSounding] = []
    levels: list[CanonicalSoundingLevel] = []
    keys: dict[tuple[str, str, int | None], str] = {}
    for raw in raw_soundings:
        key = _sounding_key(raw.station_id, raw.nominal_date_utc, raw.nominal_hour_utc)
        keys[(raw.station_id, raw.nominal_date_utc, raw.nominal_hour_utc)] = key
        nominal = _nominal_timestamp(raw.nominal_date_utc, raw.nominal_hour_utc)
        release, precision, delta = _release_timestamp(
            raw.nominal_date_utc, raw.release_time_hhmm, nominal
        )
        normalized_levels = tuple(_normalize_level(key, level) for level in raw.levels)
        levels.extend(normalized_levels)
        thermo = any(
            level.temperature_k is not None
            or level.dew_point_k is not None
            or level.relative_humidity_percent is not None
            for level in normalized_levels
        )
        wind = any(
            level.wind_speed_m_s is not None and level.wind_direction_degrees is not None
            for level in normalized_levels
        )
        soundings.append(
            CanonicalSounding(
                sounding_key=key,
                source_snapshot_id=source_snapshot_id,
                record_sha256=raw.record_sha256,
                station_id=raw.station_id,
                nominal_at_utc=nominal,
                nominal_date_utc=raw.nominal_date_utc,
                nominal_hour_utc=raw.nominal_hour_utc,
                release_at_utc=release,
                release_precision=precision,
                release_delta_seconds=delta,
                latitude_deg=_coordinate(raw.latitude_native),
                longitude_deg=_coordinate(raw.longitude_native),
                inventory_latitude_deg=inventory_latitude_deg,
                inventory_longitude_deg=inventory_longitude_deg,
                thermodynamic_usable=thermo,
                wind_usable=wind,
            )
        )
    parameters: list[ProviderDerivedSoundingParameters] = []
    provider_levels: list[ProviderDerivedSoundingLevel] = []
    for derived in derived_soundings:
        key = keys.get(
            (derived.station_id, derived.nominal_date_utc, derived.nominal_hour_utc),
            _sounding_key(derived.station_id, derived.nominal_date_utc, derived.nominal_hour_utc),
        )
        parameters.append(
            ProviderDerivedSoundingParameters(
                sounding_key=key,
                native_record_sha256=derived.record_sha256,
                values=_normalize_derived_parameters(derived.parameters),
                provenance={
                    name: _derived_provenance(value) for name, value in derived.parameters.items()
                },
            )
        )
        for level in derived.levels:
            provider_levels.append(
                ProviderDerivedSoundingLevel(
                    sounding_key=key,
                    ordinal=level.ordinal,
                    values=_normalize_derived_level(level.values),
                    provenance={
                        name: _derived_provenance(value) for name, value in level.values.items()
                    },
                )
            )
    return IgraNormalizationResult(
        soundings=tuple(
            sorted(soundings, key=lambda item: (item.nominal_at_utc or "", item.record_sha256))
        ),
        levels=tuple(sorted(levels, key=lambda item: (item.sounding_key, item.ordinal))),
        provider_parameters=tuple(
            sorted(parameters, key=lambda item: (item.sounding_key, item.native_record_sha256))
        ),
        provider_levels=tuple(
            sorted(provider_levels, key=lambda item: (item.sounding_key, item.ordinal))
        ),
        report={
            "raw_soundings": len(raw_soundings),
            "canonical_soundings": len(soundings),
            "canonical_levels": len(levels),
            "provider_derived_soundings": len(parameters),
            "provider_derived_levels": len(provider_levels),
        },
    )


def _normalize_level(sounding_key: str, level) -> CanonicalSoundingLevel:
    pressure, pressure_prov = _value(level.pressure, "pressure_pa")
    height, height_prov = _value(level.geopotential_height, "geopotential_height_msl_m")
    temperature_native, temperature_prov = _value(level.temperature, "temperature_tenth_c")
    dpdp_native, dpdp_prov = _value(level.dew_point_depression, "dew_point_depression_tenth_c")
    rh_native, rh_prov = _value(level.relative_humidity, "reported_relative_humidity_tenth_percent")
    direction, direction_prov = _value(level.wind_direction, "wind_direction_degrees")
    speed_native, speed_prov = _value(level.wind_speed, "wind_speed_tenth_m_s")
    elapsed, elapsed_prov = _elapsed(level.elapsed_time)
    temperature = temperature_native / 10 + 273.15 if temperature_native is not None else None
    dew_point = (
        temperature - dpdp_native / 10
        if temperature is not None and dpdp_native is not None
        else None
    )
    reported_rh = rh_native / 10 if rh_native is not None else None
    derived_rh = _relative_humidity(temperature, dew_point)
    speed = speed_native / 10 if speed_native is not None else None
    u, v = _wind_components(speed, direction)
    provenance = {
        "pressure_pa": pressure_prov,
        "geopotential_height_msl_m": height_prov,
        "temperature_k": _scaled_provenance(temperature_prov, "raw_temperature_tenth_c_to_k/1"),
        "dew_point_k": _derived_provenance_from(dpdp_prov, "dew_point_from_depression/1"),
        "reported_relative_humidity_percent": _scaled_provenance(rh_prov, "raw_rh_tenth_percent/1"),
        "relative_humidity_percent": _derived_provenance_from(
            dpdp_prov, "magnus_relative_humidity_over_water/1"
        ),
        "wind_direction_degrees": direction_prov,
        "wind_speed_m_s": _scaled_provenance(speed_prov, "wind_speed_tenth_m_s/1"),
        "u_wind_m_s": _derived_provenance_from(speed_prov, "meteorological_direction_to_uv/1"),
        "v_wind_m_s": _derived_provenance_from(speed_prov, "meteorological_direction_to_uv/1"),
        "elapsed_seconds": elapsed_prov,
    }
    return CanonicalSoundingLevel(
        sounding_key=sounding_key,
        ordinal=level.ordinal,
        pressure_pa=pressure,
        geopotential_height_msl_m=float(height) if height is not None else None,
        temperature_k=temperature,
        dew_point_k=dew_point,
        relative_humidity_percent=reported_rh if reported_rh is not None else derived_rh,
        wind_direction_degrees=float(direction) if direction is not None else None,
        wind_speed_m_s=speed,
        u_wind_m_s=u,
        v_wind_m_s=v,
        elapsed_seconds=elapsed,
        provenance=provenance,
    )


def _value(native: int | None, field: str) -> tuple[int | None, dict[str, object]]:
    if native in {-9999, -8888, -99999}:
        return None, {
            "quality_state": "sentinel_missing",
            "missing_reason": "source_removed_by_qa"
            if native == -8888
            else "source_missing_before_qa",
            "native_value": None,
            "native_field": field,
        }
    if native is None:
        return None, {
            "quality_state": "missing",
            "missing_reason": "blank_native",
            "native_field": field,
        }
    return native, {"quality_state": "real", "native_value": native, "native_field": field}


def _elapsed(native: int | None) -> tuple[int | None, dict[str, object]]:
    value, provenance = _value(native, "elapsed_time")
    if value is None:
        return None, provenance
    seconds = value % 100
    if seconds > 59:
        return None, {
            **provenance,
            "quality_state": "invalid_payload",
            "invalid_reason": "etime_seconds",
        }
    return (value // 100) * 60 + seconds, provenance


def _relative_humidity(temperature_k: float | None, dew_point_k: float | None) -> float | None:
    if temperature_k is None or dew_point_k is None:
        return None
    temperature_c = temperature_k - 273.15
    dew_point_c = dew_point_k - 273.15
    value = 100 * exp(
        17.625 * dew_point_c / (243.04 + dew_point_c)
        - 17.625 * temperature_c / (243.04 + temperature_c)
    )
    return value if isfinite(value) else None


def _wind_components(
    speed: float | None, direction: int | None
) -> tuple[float | None, float | None]:
    if speed is None or direction is None:
        return None, None
    radians_from_north = radians(direction)
    return -speed * sin(radians_from_north), -speed * cos(radians_from_north)


def _release_timestamp(
    nominal_date: str, release_hhmm: str | None, nominal: str | None
) -> tuple[str | None, str, int | None]:
    if release_hhmm in {None, "9999"} or nominal is None:
        return None, "missing", None
    hour = int(release_hhmm[0:2])
    minute_digits = release_hhmm[2:4]
    if hour > 23:
        return None, "missing", None
    precision = "hour" if minute_digits == "99" else "minute"
    minute = 0 if precision == "hour" else int(minute_digits)
    if minute > 59:
        return None, "missing", None
    target = datetime.fromisoformat(nominal)
    candidates = [
        datetime.combine(
            target.date() + timedelta(days=offset), datetime.min.time(), tzinfo=UTC
        ).replace(hour=hour, minute=minute)
        for offset in (-1, 0, 1)
    ]
    chosen = min(candidates, key=lambda candidate: abs((candidate - target).total_seconds()))
    return chosen.strftime("%Y-%m-%dT%H:%M:%SZ"), precision, int((chosen - target).total_seconds())


def _nominal_timestamp(nominal_date: str, nominal_hour: int | None) -> str | None:
    return None if nominal_hour is None else f"{nominal_date}T{nominal_hour:02d}:00:00Z"


def _coordinate(native: int | None) -> float | None:
    return None if native in {None, -99999, -9999, -8888} else native / 10000


def _sounding_key(station_id: str, nominal_date: str, nominal_hour: int | None) -> str:
    hour = "missing" if nominal_hour is None else f"{nominal_hour:02d}"
    return f"noaa_igra_bum00015614:{station_id}:{nominal_date}T{hour}:00:00Z"


def _scaled_provenance(provenance: dict[str, object], method: str) -> dict[str, object]:
    return {
        **provenance,
        "normalization_method": method,
        "normalization_version": NORMALIZER_VERSION,
    }


def _derived_provenance_from(provenance: dict[str, object], method: str) -> dict[str, object]:
    if provenance.get("quality_state") != "real":
        return provenance
    return {
        **provenance,
        "quality_state": "derived",
        "derivation_method": method,
        "derivation_version": NORMALIZER_VERSION,
    }


def _derived_provenance(native: int | None) -> dict[str, object]:
    _value_result, provenance = _value(native, "provider_derived")
    return provenance


def _normalize_derived_parameters(values: dict[str, int | None]) -> dict[str, float | int | None]:
    result: dict[str, float | int | None] = {}
    for name, native in values.items():
        value, _ = _value(native, name)
        if value is None:
            result[name] = None
        elif name == "pw":
            result[name] = value / 100
        elif name in {"invtempdif", "li", "si", "ki", "tti"}:
            result[name] = value / 10
        elif name == "cin":
            result["native_cin_j_kg"] = value
            result["cin_magnitude_j_kg"] = abs(value)
        else:
            result[name] = value
    return result


def _normalize_derived_level(values: dict[str, int | None]) -> dict[str, float | int | None]:
    result: dict[str, float | int | None] = {}
    scaled = {
        "temperature",
        "temperature_gradient",
        "potential_temperature",
        "potential_temperature_gradient",
        "virtual_temperature",
        "virtual_potential_temperature",
        "vapor_pressure",
        "saturation_vapor_pressure",
        "reported_relative_humidity",
        "calculated_relative_humidity",
        "relative_humidity_gradient",
        "u_wind",
        "u_wind_gradient",
        "v_wind",
        "v_wind_gradient",
    }
    for name, native in values.items():
        value, _ = _value(native, name)
        result[name] = None if value is None else value / 10 if name in scaled else value
    return result
