"""Mixed-parcel liquid LCL and MetPy CCL on one explicit model column."""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from itertools import pairwise

import metpy.calc as mpcalc
import numpy as np
from metpy.units import units

from ...ingestion.weather.features.thermodynamics import (
    CONSTANTS,
    HeightProfilePoint,
    PressureProfilePoint,
    ThermodynamicError,
    _normalized_pressure_profile,
    _pressure_layer_knots,
    _pressure_weighted_trapezoid,
    liquid_relative_humidity,
    romps_liquid_lcl_agl_m,
    thermal_strength_from_surface_fluxes,
)
from .models import HourlyInput


@dataclass(frozen=True)
class Parcel:
    temperature_k: float
    specific_humidity: float
    lcl_agl_m: float


@dataclass(frozen=True)
class Condensation:
    pressure_pa: float
    height_model_agl_m: float
    convective_temperature_k: float


def validate_column(hour: HourlyInput) -> None:
    surface = (hour.surface_pressure_pa, hour.temperature_2m_k, hour.specific_humidity_2m_kg_kg)
    if any(value is None for value in surface) or hour.model_elevation_msl_m is None:
        raise ThermodynamicError("surface_or_model_terrain_missing")
    if any(issue.startswith(("unavailable:", "profile_missing:")) for issue in hour.input_issues):
        raise ThermodynamicError("required_source_input_unavailable")
    previous_p = hour.surface_pressure_pa
    previous_z = hour.model_elevation_msl_m
    for point in hour.profile:
        if point.pressure_pa >= previous_p or point.height_msl_m <= previous_z:
            raise ThermodynamicError("model_profile_order_invalid")
        previous_p, previous_z = point.pressure_pa, point.height_msl_m
    if not hour.profile:
        raise ThermodynamicError("model_profile_missing")


def parcel(hour: HourlyInput, depth_pa: float, offset_k: float = 0.0) -> Parcel:
    """Use the existing theta/q quadrature; perturb only the parcel, not environment."""
    validate_column(hour)
    assert hour.surface_pressure_pa is not None and hour.temperature_2m_k is not None
    assert hour.specific_humidity_2m_kg_kg is not None
    ps = hour.surface_pressure_pa
    profile = _normalized_pressure_profile(
        (
            PressureProfilePoint(ps, hour.temperature_2m_k, hour.specific_humidity_2m_kg_kg),
            *(
                PressureProfilePoint(p.pressure_pa, p.temperature_k, p.specific_humidity_kg_kg)
                for p in hour.profile
            ),
        )
    )
    knots = _pressure_layer_knots(profile, ps - depth_pa, ps)
    pressures = tuple(p.pressure_pa for p in knots)
    theta = _pressure_weighted_trapezoid(
        pressures,
        tuple(p.temperature_k * (100_000 / p.pressure_pa) ** CONSTANTS.kappa for p in knots),
    )
    q = _pressure_weighted_trapezoid(pressures, tuple(p.specific_humidity_kg_per_kg for p in knots))
    temperature = theta * (ps / 100_000) ** CONSTANTS.kappa + offset_k
    rh = liquid_relative_humidity(ps, temperature, q)
    return Parcel(temperature, q, romps_liquid_lcl_agl_m(ps, temperature, rh))


def pressure_height(hour: HourlyInput, pressure_pa: float) -> float:
    """Height above model ground, bounded by the source profile, linear in ln(p)."""
    assert hour.surface_pressure_pa is not None and hour.model_elevation_msl_m is not None
    points = (
        (hour.surface_pressure_pa, 0.0),
        *((p.pressure_pa, p.height_msl_m - hour.model_elevation_msl_m) for p in hour.profile),
    )
    for p, z in points:
        if math.isclose(p, pressure_pa, rel_tol=0, abs_tol=1e-6):
            return z
    for (p1, z1), (p2, z2) in pairwise(points):
        if p1 > pressure_pa > p2:
            return z1 + math.log(pressure_pa / p1) / math.log(p2 / p1) * (z2 - z1)
    raise ThermodynamicError("condensation_pressure_outside_profile")


def condensations(hour: HourlyInput, moisture: float) -> tuple[Condensation, ...]:
    """CCL uses exactly the chosen mean q, avoiding a second, implicit mixing rule."""
    assert hour.surface_pressure_pa is not None and hour.temperature_2m_k is not None
    pressure = np.array([hour.surface_pressure_pa, *(p.pressure_pa for p in hour.profile)])
    temperature = np.array([hour.temperature_2m_k, *(p.temperature_k for p in hour.profile)])
    dewpoint = mpcalc.dewpoint_from_specific_humidity(pressure * units.Pa, moisture)
    with warnings.catch_warnings():
        # No intersection is a censored diagnostic, never evidence of clear sky.
        warnings.filterwarnings("ignore", message=".*intersection.*", category=UserWarning)
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        pc, _tc, convective = mpcalc.ccl(
            pressure * units.Pa,
            temperature * units.K,
            dewpoint,
            mixed_layer_depth=None,
            which="all",
        )
    pressures = np.atleast_1d(pc.to("Pa").magnitude)
    temperatures = np.atleast_1d(convective.to("K").magnitude)
    result: list[Condensation] = []
    for p, t in sorted(zip(pressures, temperatures, strict=True), reverse=True):
        if not math.isfinite(float(p)) or not math.isfinite(float(t)):
            continue
        if any(abs(float(p) - previous.pressure_pa) <= 1.0 for previous in result):
            continue
        result.append(Condensation(float(p), pressure_height(hour, float(p)), float(t)))
    return tuple(result)


def buoyancy_flux(hour: HourlyInput) -> tuple[float | None, str | None]:
    required = (
        hour.surface_pressure_pa,
        hour.temperature_2m_k,
        hour.specific_humidity_2m_kg_kg,
        hour.pbl_model_agl_m,
        hour.sensible_heat_flux_w_m2,
        hour.latent_heat_flux_w_m2,
    )
    if any(value is None for value in required):
        return None, "buoyancy_input_missing"
    if (
        hour.sensible_interval is None
        or hour.sensible_interval != hour.latent_interval
        or hour.sensible_interval[1] != hour.valid_at_utc
        or hour.sensible_interval[0] >= hour.sensible_interval[1]
    ):
        return None, "buoyancy_flux_interval_mismatch"
    assert hour.model_elevation_msl_m is not None
    try:
        result = thermal_strength_from_surface_fluxes(
            surface_pressure_pa=required[0],
            surface_temperature_k=required[1],
            surface_specific_humidity_kg_per_kg=required[2],
            provider_boundary_layer_height_agl_m=required[3],
            sensible_heat_flux_upward_w_m2=required[4],
            latent_heat_flux_upward_w_m2=required[5],
            profile=tuple(
                HeightProfilePoint(
                    p.height_msl_m - hour.model_elevation_msl_m,
                    p.pressure_pa,
                    p.temperature_k,
                    p.specific_humidity_kg_kg,
                )
                for p in hour.profile
            ),
        )
    except ThermodynamicError as error:
        return None, str(error)
    # The helper also returns w*; it is intentionally not a product output here.
    return result.surface_buoyancy_flux_kinematic_m2_s3, None
