from __future__ import annotations

from math import hypot

import pytest

from paragliding_forecasts_ml.ingestion.weather.wind import (
    WindCalculationError,
    component_wind_speed,
)


def test_component_wind_speed_uses_hypot_for_the_retained_rounding_edge_case() -> None:
    u_value = -0.9561042182562771
    v_value = 1.3604827612750012

    expected = hypot(u_value, v_value)
    legacy = (u_value**2 + v_value**2) ** 0.5

    assert component_wind_speed(u_value, v_value) == expected
    assert expected != legacy


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_component_wind_speed_rejects_non_finite_components(value: float) -> None:
    with pytest.raises(WindCalculationError, match="finite"):
        component_wind_speed(value, 1.0)
