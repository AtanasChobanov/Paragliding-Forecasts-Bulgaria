"""Versioned physical helpers for S08 mixed-layer and thermal features."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from math import exp, isfinite, log

from scipy.special import lambertw

ROMPS_LIQUID_LCL_VERSION = "romps-liquid-lcl/1"
SURFACE_VIRTUAL_POTENTIAL_TEMPERATURE_FLUX_VERSION = "surface-virtual-potential-temperature-flux/1"
SURFACE_BUOYANCY_FLUX_VERSION = "surface-buoyancy-flux/1"
DEARDORFF_CONVECTIVE_VELOCITY_VERSION = "deardorff-convective-velocity/1"


@dataclass(frozen=True)
class ThermodynamicConstants:
    """Pinned SI constants used by all S08 thermodynamic derivations."""

    gravitational_acceleration_m_s2: float = 9.81
    dry_air_gas_constant_j_kg_k: float = 287.04
    water_vapour_gas_constant_j_kg_k: float = 461.0
    dry_air_specific_heat_j_kg_k: float = 1004.04
    latent_heat_vaporization_j_kg: float = 2.5e6
    reference_pressure_pa: float = 100000.0
    triple_point_temperature_k: float = 273.16
    triple_point_pressure_pa: float = 611.65
    vaporization_energy_j_kg: float = 2.3740e6
    dry_air_cv_j_kg_k: float = 719.0
    water_vapour_cv_j_kg_k: float = 1418.0
    liquid_water_cv_j_kg_k: float = 4119.0

    @property
    def kappa(self) -> float:
        return self.dry_air_gas_constant_j_kg_k / self.dry_air_specific_heat_j_kg_k


CONSTANTS = ThermodynamicConstants()


class ThermodynamicError(ValueError):
    """A requested feature has incomplete or physically invalid inputs."""


@dataclass(frozen=True)
class PressureProfilePoint:
    pressure_pa: float
    temperature_k: float
    specific_humidity_kg_per_kg: float


@dataclass(frozen=True)
class HeightProfilePoint:
    height_agl_m: float
    pressure_pa: float
    temperature_k: float
    specific_humidity_kg_per_kg: float


@dataclass(frozen=True)
class ThermalStrengthResult:
    surface_buoyancy_flux_kinematic_m2_s3: float
    convective_velocity_scale_m_s: float


def mixed_layer_lcl_agl_m(
    *,
    surface_pressure_pa: float,
    surface_temperature_k: float,
    surface_specific_humidity_kg_per_kg: float,
    profile: tuple[PressureProfilePoint, ...],
) -> float:
    """Calculate the lowest-100-hPa mixed-parcel liquid LCL above ground.

    The two pressure boundaries are interpolated in ln(p), and temperature is
    converted to potential temperature before pressure-weighted mixing. The
    returned parcel LCL is the exact liquid-water expression from Romps (2017).
    """

    _require_surface_state(
        surface_pressure_pa, surface_temperature_k, surface_specific_humidity_kg_per_kg
    )
    lower_pressure = surface_pressure_pa - 10_000.0
    if lower_pressure <= 0.0:
        raise ThermodynamicError("mixed_layer_pressure_invalid")
    accepted_profile = tuple(point for point in profile if point.pressure_pa < surface_pressure_pa)
    normalized = _normalized_pressure_profile(
        (
            PressureProfilePoint(
                surface_pressure_pa,
                surface_temperature_k,
                surface_specific_humidity_kg_per_kg,
            ),
            *accepted_profile,
        )
    )
    knots = _pressure_layer_knots(normalized, lower_pressure, surface_pressure_pa)
    potential_temperature = tuple(
        point.temperature_k
        * (CONSTANTS.reference_pressure_pa / point.pressure_pa) ** CONSTANTS.kappa
        for point in knots
    )
    mixed_theta = _pressure_weighted_trapezoid(
        tuple(point.pressure_pa for point in knots), potential_temperature
    )
    mixed_q = _pressure_weighted_trapezoid(
        tuple(point.pressure_pa for point in knots),
        tuple(point.specific_humidity_kg_per_kg for point in knots),
    )
    parcel_temperature = (
        mixed_theta * (surface_pressure_pa / CONSTANTS.reference_pressure_pa) ** CONSTANTS.kappa
    )
    relative_humidity = liquid_relative_humidity(surface_pressure_pa, parcel_temperature, mixed_q)
    return romps_liquid_lcl_agl_m(surface_pressure_pa, parcel_temperature, relative_humidity)


def liquid_relative_humidity(
    pressure_pa: float, temperature_k: float, specific_humidity_kg_per_kg: float
) -> float:
    """Return liquid-water relative humidity from specific humidity and pressure."""

    _require_surface_state(pressure_pa, temperature_k, specific_humidity_kg_per_kg)
    epsilon = CONSTANTS.dry_air_gas_constant_j_kg_k / CONSTANTS.water_vapour_gas_constant_j_kg_k
    vapor_pressure = (
        specific_humidity_kg_per_kg
        * pressure_pa
        / (epsilon + (1.0 - epsilon) * specific_humidity_kg_per_kg)
    )
    saturation = _saturation_vapour_pressure_liquid(temperature_k)
    if not isfinite(vapor_pressure) or vapor_pressure < 0.0 or vapor_pressure >= pressure_pa:
        raise ThermodynamicError("parcel_vapour_pressure_invalid")
    relative_humidity = vapor_pressure / saturation
    if not isfinite(relative_humidity) or relative_humidity < 0.0:
        raise ThermodynamicError("parcel_relative_humidity_invalid")
    return relative_humidity


def romps_liquid_lcl_agl_m(pressure_pa: float, temperature_k: float, rhl: float) -> float:
    """Evaluate Romps (2017) Eq. 22 for a liquid-water LCL on W-1."""

    if not isfinite(rhl) or rhl < 0.0:
        raise ThermodynamicError("parcel_relative_humidity_invalid")
    _require_surface_state(pressure_pa, temperature_k, 0.0)
    if rhl >= 1.0:
        return 0.0
    if rhl == 0.0:
        return (
            CONSTANTS.dry_air_specific_heat_j_kg_k
            * temperature_k
            / CONSTANTS.gravitational_acceleration_m_s2
        )
    pv = rhl * _saturation_vapour_pressure_liquid(temperature_k)
    if not isfinite(pv) or pv <= 0.0 or pv >= pressure_pa:
        raise ThermodynamicError("parcel_vapour_pressure_invalid")
    qv = (
        CONSTANTS.dry_air_gas_constant_j_kg_k
        * pv
        / (
            CONSTANTS.water_vapour_gas_constant_j_kg_k * pressure_pa
            + (CONSTANTS.dry_air_gas_constant_j_kg_k - CONSTANTS.water_vapour_gas_constant_j_kg_k)
            * pv
        )
    )
    cpa = CONSTANTS.dry_air_cv_j_kg_k + CONSTANTS.dry_air_gas_constant_j_kg_k
    cpv = CONSTANTS.water_vapour_cv_j_kg_k + CONSTANTS.water_vapour_gas_constant_j_kg_k
    rgasm = (
        1.0 - qv
    ) * CONSTANTS.dry_air_gas_constant_j_kg_k + qv * CONSTANTS.water_vapour_gas_constant_j_kg_k
    cpm = (1.0 - qv) * cpa + qv * cpv
    energy = (
        CONSTANTS.vaporization_energy_j_kg
        - (CONSTANTS.water_vapour_cv_j_kg_k - CONSTANTS.liquid_water_cv_j_kg_k)
        * CONSTANTS.triple_point_temperature_k
    )
    a_l = (
        -(cpv - CONSTANTS.liquid_water_cv_j_kg_k) / CONSTANTS.water_vapour_gas_constant_j_kg_k
        + cpm / rgasm
    )
    b_l = -energy / (CONSTANTS.water_vapour_gas_constant_j_kg_k * temperature_k)
    c_l = (
        pv
        / _saturation_vapour_pressure_liquid(temperature_k)
        * exp(-energy / (CONSTANTS.water_vapour_gas_constant_j_kg_k * temperature_k))
    )
    argument = b_l / a_l * c_l ** (1.0 / a_l)
    solution = lambertw(argument, -1)
    if abs(float(solution.imag)) > 1e-10 or not isfinite(float(solution.real)):
        raise ThermodynamicError("lcl_solver_non_real")
    lcl = (
        cpm
        * temperature_k
        / CONSTANTS.gravitational_acceleration_m_s2
        * (1.0 - b_l / (a_l * float(solution.real)))
    )
    if not isfinite(lcl) or lcl < 0.0:
        raise ThermodynamicError("lcl_height_invalid")
    return lcl


def thermal_strength_from_surface_fluxes(
    *,
    surface_pressure_pa: float,
    surface_temperature_k: float,
    surface_specific_humidity_kg_per_kg: float,
    sensible_heat_flux_upward_w_m2: float,
    latent_heat_flux_upward_w_m2: float,
    provider_boundary_layer_height_agl_m: float,
    profile: tuple[HeightProfilePoint, ...],
) -> ThermalStrengthResult:
    """Return signed B0 and positive-part Deardorff w* for one exact interval."""

    _require_surface_state(
        surface_pressure_pa, surface_temperature_k, surface_specific_humidity_kg_per_kg
    )
    if (
        not isfinite(provider_boundary_layer_height_agl_m)
        or provider_boundary_layer_height_agl_m <= 2.0
    ):
        raise ThermodynamicError("provider_boundary_layer_height_invalid")
    if not isfinite(sensible_heat_flux_upward_w_m2) or not isfinite(latent_heat_flux_upward_w_m2):
        raise ThermodynamicError("surface_heat_flux_invalid")
    mean_theta_v = _height_weighted_mean_virtual_potential_temperature(
        surface_pressure_pa=surface_pressure_pa,
        surface_temperature_k=surface_temperature_k,
        surface_specific_humidity_kg_per_kg=surface_specific_humidity_kg_per_kg,
        profile=profile,
        upper_height_agl_m=provider_boundary_layer_height_agl_m,
    )
    virtual_temperature = surface_temperature_k * (1.0 + 0.61 * surface_specific_humidity_kg_per_kg)
    density = surface_pressure_pa / (CONSTANTS.dry_air_gas_constant_j_kg_k * virtual_temperature)
    if not isfinite(density) or density <= 0.0:
        raise ThermodynamicError("surface_density_invalid")
    w_theta_v = (CONSTANTS.reference_pressure_pa / surface_pressure_pa) ** CONSTANTS.kappa * (
        (1.0 + 0.61 * surface_specific_humidity_kg_per_kg)
        * sensible_heat_flux_upward_w_m2
        / (density * CONSTANTS.dry_air_specific_heat_j_kg_k)
        + 0.61
        * surface_temperature_k
        * latent_heat_flux_upward_w_m2
        / (density * CONSTANTS.latent_heat_vaporization_j_kg)
    )
    buoyancy_flux = CONSTANTS.gravitational_acceleration_m_s2 / mean_theta_v * w_theta_v
    if not isfinite(buoyancy_flux):
        raise ThermodynamicError("surface_buoyancy_flux_invalid")
    convective_velocity = max(buoyancy_flux, 0.0) * provider_boundary_layer_height_agl_m
    convective_velocity = convective_velocity ** (1.0 / 3.0)
    if not isfinite(convective_velocity) or convective_velocity < 0.0:
        raise ThermodynamicError("convective_velocity_invalid")
    return ThermalStrengthResult(buoyancy_flux, convective_velocity)


def _normalized_pressure_profile(
    profile: tuple[PressureProfilePoint, ...],
) -> tuple[PressureProfilePoint, ...]:
    if len(profile) < 2:
        raise ThermodynamicError("mixed_layer_profile_insufficient")
    points = tuple(sorted(profile, key=lambda point: point.pressure_pa, reverse=True))
    if len({point.pressure_pa for point in points}) != len(points):
        raise ThermodynamicError("mixed_layer_profile_duplicate_pressure")
    for point in points:
        _require_surface_state(
            point.pressure_pa, point.temperature_k, point.specific_humidity_kg_per_kg
        )
    return points


def _pressure_layer_knots(
    profile: tuple[PressureProfilePoint, ...], lower_pressure: float, upper_pressure: float
) -> tuple[PressureProfilePoint, ...]:
    if profile[0].pressure_pa < upper_pressure or profile[-1].pressure_pa > lower_pressure:
        raise ThermodynamicError("mixed_layer_pressure_boundary_not_bracketed")
    points = [
        _interpolate_pressure(profile, upper_pressure),
        *(point for point in profile if lower_pressure < point.pressure_pa < upper_pressure),
        _interpolate_pressure(profile, lower_pressure),
    ]
    return tuple(sorted(points, key=lambda point: point.pressure_pa, reverse=True))


def _interpolate_pressure(
    profile: tuple[PressureProfilePoint, ...], target_pressure: float
) -> PressureProfilePoint:
    for point in profile:
        if point.pressure_pa == target_pressure:
            return point
    for higher, lower in pairwise(profile):
        if higher.pressure_pa > target_pressure > lower.pressure_pa:
            fraction = (log(target_pressure) - log(higher.pressure_pa)) / (
                log(lower.pressure_pa) - log(higher.pressure_pa)
            )
            return PressureProfilePoint(
                pressure_pa=target_pressure,
                temperature_k=higher.temperature_k
                + fraction * (lower.temperature_k - higher.temperature_k),
                specific_humidity_kg_per_kg=higher.specific_humidity_kg_per_kg
                + fraction
                * (lower.specific_humidity_kg_per_kg - higher.specific_humidity_kg_per_kg),
            )
    raise ThermodynamicError("mixed_layer_pressure_boundary_not_bracketed")


def _pressure_weighted_trapezoid(
    pressures_pa: tuple[float, ...], values: tuple[float, ...]
) -> float:
    numerator = 0.0
    denominator = 0.0
    for (upper, lower), (upper_value, lower_value) in zip(
        pairwise(pressures_pa), pairwise(values), strict=True
    ):
        weight = upper - lower
        numerator += weight * (upper_value + lower_value) / 2.0
        denominator += weight
    if denominator <= 0.0 or not isfinite(numerator):
        raise ThermodynamicError("mixed_layer_integration_invalid")
    return numerator / denominator


def _height_weighted_mean_virtual_potential_temperature(
    *,
    surface_pressure_pa: float,
    surface_temperature_k: float,
    surface_specific_humidity_kg_per_kg: float,
    profile: tuple[HeightProfilePoint, ...],
    upper_height_agl_m: float,
) -> float:
    points = (
        HeightProfilePoint(
            2.0,
            surface_pressure_pa,
            surface_temperature_k,
            surface_specific_humidity_kg_per_kg,
        ),
        *tuple(sorted(profile, key=lambda point: point.height_agl_m)),
    )
    if len({point.height_agl_m for point in points}) != len(points):
        raise ThermodynamicError("thermal_profile_duplicate_height")
    for point in points:
        if point.height_agl_m < 2.0:
            raise ThermodynamicError("thermal_profile_below_surface")
        _require_surface_state(
            point.pressure_pa, point.temperature_k, point.specific_humidity_kg_per_kg
        )
    if points[-1].height_agl_m < upper_height_agl_m:
        raise ThermodynamicError("provider_boundary_layer_not_bracketed")
    bounded = [point for point in points if point.height_agl_m < upper_height_agl_m]
    bounded.append(_interpolate_height(points, upper_height_agl_m))
    numerator = 0.0
    denominator = 0.0
    for lower, upper in pairwise(bounded):
        distance = upper.height_agl_m - lower.height_agl_m
        if distance <= 0.0:
            raise ThermodynamicError("thermal_profile_height_invalid")
        lower_theta_v = _virtual_potential_temperature(lower)
        upper_theta_v = _virtual_potential_temperature(upper)
        numerator += distance * (lower_theta_v + upper_theta_v) / 2.0
        denominator += distance
    if denominator <= 0.0 or not isfinite(numerator):
        raise ThermodynamicError("thermal_profile_integration_invalid")
    return numerator / denominator


def _interpolate_height(
    profile: tuple[HeightProfilePoint, ...], target_height: float
) -> HeightProfilePoint:
    for point in profile:
        if point.height_agl_m == target_height:
            return point
    for lower, upper in pairwise(profile):
        if lower.height_agl_m < target_height < upper.height_agl_m:
            fraction = (target_height - lower.height_agl_m) / (
                upper.height_agl_m - lower.height_agl_m
            )
            return HeightProfilePoint(
                height_agl_m=target_height,
                pressure_pa=lower.pressure_pa + fraction * (upper.pressure_pa - lower.pressure_pa),
                temperature_k=lower.temperature_k
                + fraction * (upper.temperature_k - lower.temperature_k),
                specific_humidity_kg_per_kg=lower.specific_humidity_kg_per_kg
                + fraction
                * (upper.specific_humidity_kg_per_kg - lower.specific_humidity_kg_per_kg),
            )
    raise ThermodynamicError("provider_boundary_layer_not_bracketed")


def _virtual_potential_temperature(point: HeightProfilePoint) -> float:
    return (
        point.temperature_k
        * (CONSTANTS.reference_pressure_pa / point.pressure_pa) ** CONSTANTS.kappa
        * (1.0 + 0.61 * point.specific_humidity_kg_per_kg)
    )


def _require_surface_state(
    pressure_pa: float, temperature_k: float, specific_humidity: float
) -> None:
    if (
        not isfinite(pressure_pa)
        or not isfinite(temperature_k)
        or not isfinite(specific_humidity)
        or pressure_pa <= 0.0
        or temperature_k <= 0.0
        or specific_humidity < 0.0
        or specific_humidity >= 1.0
    ):
        raise ThermodynamicError("thermodynamic_input_invalid")


def _saturation_vapour_pressure_liquid(temperature_k: float) -> float:
    cpv = CONSTANTS.water_vapour_cv_j_kg_k + CONSTANTS.water_vapour_gas_constant_j_kg_k
    return (
        CONSTANTS.triple_point_pressure_pa
        * (temperature_k / CONSTANTS.triple_point_temperature_k)
        ** ((cpv - CONSTANTS.liquid_water_cv_j_kg_k) / CONSTANTS.water_vapour_gas_constant_j_kg_k)
        * exp(
            (
                CONSTANTS.vaporization_energy_j_kg
                - (CONSTANTS.water_vapour_cv_j_kg_k - CONSTANTS.liquid_water_cv_j_kg_k)
                * CONSTANTS.triple_point_temperature_k
            )
            / CONSTANTS.water_vapour_gas_constant_j_kg_k
            * (1.0 / CONSTANTS.triple_point_temperature_k - 1.0 / temperature_k)
        )
    )
