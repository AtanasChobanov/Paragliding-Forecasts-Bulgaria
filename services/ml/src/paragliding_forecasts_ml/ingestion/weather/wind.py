"""Canonical source-neutral wind vector calculations."""

from __future__ import annotations

from math import hypot, isfinite


class WindCalculationError(ValueError):
    """Wind-vector inputs cannot safely produce a finite derived value."""


def component_wind_speed(u_m_s: float, v_m_s: float) -> float:
    """Return scalar wind speed from finite eastward and northward components."""

    if not isfinite(u_m_s) or not isfinite(v_m_s):
        raise WindCalculationError("Wind components must be finite.")
    return hypot(u_m_s, v_m_s)
