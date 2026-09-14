"""Exact vertical calculations for the S07 source-neutral feature builder."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from math import atan2, degrees, hypot, isfinite

CALM_WIND_EPSILON_M_S = 1e-6


class VerticalCoverageError(ValueError):
    """A requested AGL result is not fully bracketed by finite source evidence."""


@dataclass(frozen=True)
class VerticalPoint:
    """One finite canonical scalar at a site-AGL height in metres."""

    height_agl_m: float
    value: float


def interpolate_linear(points: Sequence[VerticalPoint], target_height_agl_m: float) -> float:
    """Return an exact linear-in-height value without extrapolation."""

    profile = _validated_profile(points)
    _require_finite(target_height_agl_m, "Target height")
    if (
        target_height_agl_m < profile[0].height_agl_m
        or target_height_agl_m > profile[-1].height_agl_m
    ):
        raise VerticalCoverageError("Target height is not bracketed by the vertical profile.")
    for point in profile:
        if point.height_agl_m == target_height_agl_m:
            return point.value
    for lower, upper in pairwise(profile):
        if lower.height_agl_m < target_height_agl_m < upper.height_agl_m:
            ratio = (target_height_agl_m - lower.height_agl_m) / (
                upper.height_agl_m - lower.height_agl_m
            )
            return lower.value + ratio * (upper.value - lower.value)
    raise VerticalCoverageError("Target height is not bracketed by a profile segment.")


def bounded_profile(
    points: Sequence[VerticalPoint], lower_agl_m: float, upper_agl_m: float
) -> tuple[VerticalPoint, ...]:
    """Add exact boundary points and retain all strictly interior source points."""

    _require_valid_bounds(lower_agl_m, upper_agl_m)
    profile = _validated_profile(points)
    lower = VerticalPoint(lower_agl_m, interpolate_linear(profile, lower_agl_m))
    upper = VerticalPoint(upper_agl_m, interpolate_linear(profile, upper_agl_m))
    interior = tuple(point for point in profile if lower_agl_m < point.height_agl_m < upper_agl_m)
    return (lower, *interior, upper)


def trapezoidal_mean(
    points: Sequence[VerticalPoint], lower_agl_m: float, upper_agl_m: float
) -> float:
    """Return the exact piecewise-linear height mean across a fully covered layer."""

    profile = bounded_profile(points, lower_agl_m, upper_agl_m)
    integral = sum(
        0.5 * (lower.value + upper.value) * (upper.height_agl_m - lower.height_agl_m)
        for lower, upper in pairwise(profile)
    )
    return integral / (upper_agl_m - lower_agl_m)


def endpoint_lapse_rate_k_per_km(
    temperature_points: Sequence[VerticalPoint], lower_agl_m: float, upper_agl_m: float
) -> float:
    """Return positive-for-cooling-with-height environmental lapse rate."""

    _require_valid_bounds(lower_agl_m, upper_agl_m)
    lower_temperature = interpolate_linear(temperature_points, lower_agl_m)
    upper_temperature = interpolate_linear(temperature_points, upper_agl_m)
    return 1000.0 * (lower_temperature - upper_temperature) / (upper_agl_m - lower_agl_m)


def bulk_vector_shear_m_s_per_km(
    u_points: Sequence[VerticalPoint],
    v_points: Sequence[VerticalPoint],
    lower_agl_m: float,
    upper_agl_m: float,
) -> float:
    """Return endpoint bulk vector shear for one fully bracketed AGL layer."""

    _require_valid_bounds(lower_agl_m, upper_agl_m)
    delta_u = interpolate_linear(u_points, upper_agl_m) - interpolate_linear(u_points, lower_agl_m)
    delta_v = interpolate_linear(v_points, upper_agl_m) - interpolate_linear(v_points, lower_agl_m)
    return 1000.0 * hypot(delta_u, delta_v) / (upper_agl_m - lower_agl_m)


def scalar_speed_profile(
    u_points: Sequence[VerticalPoint], v_points: Sequence[VerticalPoint]
) -> tuple[VerticalPoint, ...]:
    """Derive scalar speed at each shared height before any layer integration."""

    u_profile = _validated_profile(u_points)
    v_profile = _validated_profile(v_points)
    if tuple(point.height_agl_m for point in u_profile) != tuple(
        point.height_agl_m for point in v_profile
    ):
        raise VerticalCoverageError("U and V profiles must share identical AGL heights.")
    return tuple(
        VerticalPoint(u_point.height_agl_m, hypot(u_point.value, v_point.value))
        for u_point, v_point in zip(u_profile, v_profile, strict=True)
    )


def meteorological_direction_from_uv(u_m_s: float, v_m_s: float) -> float | None:
    """Return meteorological direction-from degrees, or null for numerical calm."""

    _require_finite(u_m_s, "Wind U")
    _require_finite(v_m_s, "Wind V")
    if hypot(u_m_s, v_m_s) <= CALM_WIND_EPSILON_M_S:
        return None
    return (degrees(atan2(-u_m_s, -v_m_s)) + 360.0) % 360.0


def _validated_profile(points: Sequence[VerticalPoint]) -> tuple[VerticalPoint, ...]:
    profile = tuple(points)
    if len(profile) < 2:
        raise VerticalCoverageError("A vertical calculation requires at least two profile points.")
    previous_height: float | None = None
    for point in profile:
        _require_finite(point.height_agl_m, "Profile height")
        _require_finite(point.value, "Profile value")
        if previous_height is not None and point.height_agl_m <= previous_height:
            raise VerticalCoverageError("Profile heights must be strictly increasing and unique.")
        previous_height = point.height_agl_m
    return profile


def _require_valid_bounds(lower_agl_m: float, upper_agl_m: float) -> None:
    _require_finite(lower_agl_m, "Lower layer bound")
    _require_finite(upper_agl_m, "Upper layer bound")
    if lower_agl_m >= upper_agl_m:
        raise VerticalCoverageError("Layer bounds must be finite and strictly increasing.")


def _require_finite(value: float, label: str) -> None:
    if not isfinite(value):
        raise VerticalCoverageError(f"{label} must be finite.")
