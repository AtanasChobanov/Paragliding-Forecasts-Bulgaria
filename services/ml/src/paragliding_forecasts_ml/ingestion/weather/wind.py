"""Canonical source-neutral wind vector calculations."""

from __future__ import annotations

from math import atan2, degrees, hypot, isfinite

CALM_WIND_EPSILON_M_S = 1e-6


class WindCalculationError(ValueError):
    """Wind-vector inputs cannot safely produce a finite derived value."""


def component_wind_speed(u_m_s: float, v_m_s: float) -> float:
    """Return scalar wind speed from finite eastward and northward components."""

    if not isfinite(u_m_s) or not isfinite(v_m_s):
        raise WindCalculationError("Wind components must be finite.")
    return hypot(u_m_s, v_m_s)


def meteorological_direction_from_uv(u_m_s: float, v_m_s: float) -> float | None:
    """Return direction-from degrees, or null when both components are numerical calm."""

    speed = component_wind_speed(u_m_s, v_m_s)
    if speed <= CALM_WIND_EPSILON_M_S:
        return None
    return (degrees(atan2(-u_m_s, -v_m_s)) + 360.0) % 360.0
