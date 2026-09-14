from __future__ import annotations

import pytest

from paragliding_forecasts_ml.ingestion.weather.features.vertical import (
    VerticalCoverageError,
    VerticalPoint,
    bulk_vector_shear_m_s_per_km,
    endpoint_lapse_rate_k_per_km,
    interpolate_linear,
    meteorological_direction_from_uv,
    scalar_speed_profile,
    trapezoidal_mean,
)


def _points(*pairs: tuple[float, float]) -> tuple[VerticalPoint, ...]:
    return tuple(VerticalPoint(height, value) for height, value in pairs)


def test_linear_interpolation_and_trapezoidal_mean_use_exact_uneven_height_segments() -> None:
    points = _points((2, 10), (500, 20), (1500, 40), (3000, 70))

    assert interpolate_linear(points, 1000) == pytest.approx(30)
    assert trapezoidal_mean(points, 2, 1500) == pytest.approx((15 * 498 + 30 * 1000) / 1498)
    assert trapezoidal_mean(points, 500, 3000) == pytest.approx((30 * 1000 + 55 * 1500) / 2500)


def test_vertical_calculations_fail_closed_without_full_bracketing_or_unique_heights() -> None:
    points = _points((2, 290), (1500, 280))

    with pytest.raises(VerticalCoverageError, match="not bracketed"):
        interpolate_linear(points, 1501)
    with pytest.raises(VerticalCoverageError, match="strictly increasing"):
        trapezoidal_mean(_points((2, 290), (2, 289), (1500, 280)), 2, 1500)


def test_lapse_and_endpoint_vector_shear_follow_the_approved_formulas() -> None:
    temperatures = _points((2, 290), (1500, 280))
    u = _points((10, 1), (1500, 4))
    v = _points((10, 2), (1500, 6))

    assert endpoint_lapse_rate_k_per_km(temperatures, 2, 1500) == pytest.approx(1000 * 10 / 1498)
    assert bulk_vector_shear_m_s_per_km(u, v, 10, 1500) == pytest.approx(1000 * 5 / 1490)


def test_scalar_speed_is_integrated_before_vector_direction_and_calm_is_null() -> None:
    u = _points((10, 3), (1500, -3))
    v = _points((10, 4), (1500, 4))

    speeds = scalar_speed_profile(u, v)

    assert [point.value for point in speeds] == pytest.approx([5, 5])
    assert meteorological_direction_from_uv(-1, 0) == pytest.approx(90)
    assert meteorological_direction_from_uv(0, 0) is None
    with pytest.raises(VerticalCoverageError, match="identical AGL heights"):
        scalar_speed_profile(u, _points((11, 4), (1500, 4)))
