"""Synthetic cloudbase physics; no retained user data, transport or SQLite writes."""

from __future__ import annotations

from dataclasses import replace

import pytest

from paragliding_forecasts_ml.ingestion.weather.features.thermodynamics import (
    PressureProfilePoint,
    ThermodynamicError,
    mixed_layer_lcl_agl_m,
)
from paragliding_forecasts_ml.predictions.cloudbase.physics import (
    buoyancy_flux,
    condensations,
    parcel,
    pressure_height,
)
from paragliding_forecasts_ml.predictions.cloudbase.policy import POLICY


@pytest.fixture
def column(cloudbase_column):
    return cloudbase_column


def test_policy_is_explicit_and_immutable():
    assert POLICY.as_dict()["height_margin_m"] == 250
    assert replace(POLICY, height_margin_m=500).height_margin_m == 500
    assert POLICY.height_margin_m == 250


def test_central_lcl_matches_existing_romps_method(column):
    expected = mixed_layer_lcl_agl_m(
        surface_pressure_pa=column.surface_pressure_pa,
        surface_temperature_k=column.temperature_2m_k,
        surface_specific_humidity_kg_per_kg=column.specific_humidity_2m_kg_kg,
        profile=tuple(
            PressureProfilePoint(p.pressure_pa, p.temperature_k, p.specific_humidity_kg_kg)
            for p in column.profile
        ),
    )
    assert parcel(column, 10000).lcl_agl_m == expected


def test_missing_source_layer_boundary_is_not_extrapolated(column):
    shallow = column.model_copy(update={"profile": column.profile[:1]})
    with pytest.raises(ThermodynamicError):
        parcel(shallow, 10000)


def test_levels_below_site_are_used_for_model_parcel(column):
    full = parcel(column, 10000)
    truncated = parcel(
        column.model_copy(
            update={"profile": tuple(p for p in column.profile if p.height_msl_m >= 1500)}
        ),
        10000,
    )
    assert abs(full.lcl_agl_m - truncated.lcl_agl_m) > 1


def test_temperature_perturbation_does_not_mutate_environment(column):
    baseline = parcel(column, 10000)
    warmer = parcel(column, 10000, 1)
    assert warmer.lcl_agl_m > baseline.lcl_agl_m
    assert warmer.specific_humidity == baseline.specific_humidity
    assert column.temperature_2m_k == 300


def test_pressure_height_is_bounded_and_keeps_model_reference(column):
    assert pressure_height(column, 95000) == 0
    assert pressure_height(column, 85000) == 1000
    assert 1000 < pressure_height(column, 82500) < 1500
    with pytest.raises(ThermodynamicError):
        pressure_height(column, 40000)


def test_ccl_uses_mean_moisture_and_returns_finite_native_bracket(column):
    result = condensations(column, parcel(column, 10000).specific_humidity)
    assert len(result) == 1
    assert 50000 < result[0].pressure_pa < 95000
    assert 0 < result[0].height_model_agl_m < 5100
    assert result[0].convective_temperature_k > 250


def test_ccl_no_intersection_is_censored_not_clear_sky(column):
    assert condensations(column, 0.00001) == ()


def test_buoyancy_uses_matching_intervals_and_model_heights(column):
    value, reason = buoyancy_flux(column)
    assert value > 0 and reason is None
    bad = column.model_copy(update={"latent_interval": None})
    assert buoyancy_flux(bad) == (None, "buoyancy_flux_interval_mismatch")
    missing = column.model_copy(update={"sensible_heat_flux_w_m2": None})
    assert buoyancy_flux(missing) == (None, "buoyancy_input_missing")


def test_invalid_order_and_unavailable_hour_rejected(column):
    with pytest.raises(ThermodynamicError):
        parcel(column.model_copy(update={"profile": column.profile[::-1]}), 10000)
    with pytest.raises(ThermodynamicError):
        parcel(column.model_copy(update={"input_issues": ("unavailable:source_late",)}), 10000)
