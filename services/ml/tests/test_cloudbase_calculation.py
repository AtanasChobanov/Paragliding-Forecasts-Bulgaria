from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from paragliding_forecasts_ml.ingestion.weather.features.aggregation import sofia_flying_window
from paragliding_forecasts_ml.predictions.cloudbase import calculation
from paragliding_forecasts_ml.predictions.cloudbase.models import Height
from paragliding_forecasts_ml.predictions.cloudbase.physics import Condensation


@pytest.fixture
def column(cloudbase_column):
    return cloudbase_column


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, "cumulus"),
        ({"height_gap": 249.9}, "indeterminate"),
        ({"temperature_margin": 0.999}, "indeterminate"),
        ({"b0": 0}, "indeterminate"),
        ({"b0": None}, "indeterminate"),
        ({"rh": 0.99}, "other_cloud"),
        ({"low_cloud": 80}, "other_cloud"),
        ({"low_cloud": None}, "indeterminate"),
        ({"low_cloud": -1}, "indeterminate"),
        ({"ccl_count": 0}, "indeterminate"),
        ({"ccl_count": 2}, "indeterminate"),
        ({"base_in_profile": False}, "indeterminate"),
        ({"height_gap": -250, "temperature_margin": -1, "b0": None, "low_cloud": 20}, "blue"),
        ({"height_gap": -250, "temperature_margin": -1, "low_cloud": 20.1}, "indeterminate"),
        ({"height_gap": -250, "temperature_margin": 1}, "indeterminate"),
    ],
)
def test_policy_boundaries_and_missingness(overrides, expected):
    args = {
        "rh": 0.6,
        "low_cloud": 10,
        "height_gap": 250,
        "temperature_margin": 1,
        "b0": 0.001,
        "ccl_count": 1,
    }
    args.update(overrides)
    assert calculation.formation(**args)[0] == expected


def test_hour_uses_model_terrain_and_preserves_signed_site_agl(column, monkeypatch):
    monkeypatch.setattr(calculation, "condensations", lambda *_: (Condensation(80000, 1500, 298),))
    value = calculation.calculate_hour(column)
    assert value.regime == "cumulus"
    assert value.estimated_cloudbase == value.potential_base
    assert value.potential_base.msl_m == 500 + value.potential_base.model_agl_m
    assert value.potential_base.site_agl_m == value.potential_base.msl_m - 1500
    assert value.confidence == "low"
    higher = calculation.calculate_hour(column.model_copy(update={"site_elevation_msl_m": 5000}))
    assert higher.potential_base.site_agl_m < 0
    assert "potential_base_below_site" in higher.limitations
    assert higher.potential_base.msl_m == value.potential_base.msl_m


def test_multiple_ccl_and_missing_flux_keep_potential_not_predicted_base(column, monkeypatch):
    monkeypatch.setattr(
        calculation,
        "condensations",
        lambda *_: (Condensation(80000, 1500, 298), Condensation(70000, 2600, 299)),
    )
    result = calculation.calculate_hour(column)
    assert result.regime == "indeterminate" and result.potential_base is not None
    assert result.estimated_cloudbase is None
    monkeypatch.setattr(calculation, "condensations", lambda *_: (Condensation(80000, 1500, 298),))
    result = calculation.calculate_hour(column.model_copy(update={"sensible_heat_flux_w_m2": None}))
    assert (
        result.regime == "indeterminate"
        and "positive_heating_not_established" in result.reason_codes
    )


def test_missing_hour_never_becomes_blue(column):
    result = calculation.calculate_hour(column.model_copy(update={"temperature_2m_k": None}))
    assert result.regime == "missing" and result.potential_base is None


def test_impossible_result_contract_is_rejected(column):
    result = calculation.calculate_hour(column)
    with pytest.raises(ValidationError):
        type(result).model_validate(
            {
                **result.model_dump(),
                "regime": "blue",
                "estimated_cloudbase": Height(msl_m=2000, model_agl_m=1500, site_agl_m=500),
            }
        )


def hours_for_day(column, regimes):
    times = sofia_flying_window(date.fromisoformat(column.target_local_date)).expected_instants_utc
    rows = []
    for valid, regime in zip(times, regimes, strict=True):
        row = calculation.calculate_hour(column.model_copy(update={"valid_at_utc": valid}))
        value = Height(msl_m=2300, model_agl_m=1800, site_agl_m=800)
        rows.append(
            type(row).model_validate(
                {
                    **row.model_dump(),
                    "regime": regime,
                    "data_status": "missing" if regime == "missing" else "baseline",
                    "potential_base": None if regime == "missing" else value,
                    "estimated_cloudbase": value if regime == "cumulus" else None,
                    "confidence": None if regime == "missing" else "low",
                }
            )
        )
    return rows


@pytest.mark.parametrize(
    ("regime", "state"),
    [
        ("blue", "blue"),
        ("missing", "missing"),
        ("other_cloud", "other_cloud"),
        ("indeterminate", "indeterminate"),
    ],
)
def test_all_day_states(column, regime, state):
    daily = calculation.aggregate_day(hours_for_day(column, [regime] * 11))
    assert daily.summary_state == state and daily.max_cloudbase is None
    assert daily.present_hours == (0 if regime == "missing" else 11)


def test_one_cumulus_hour_and_ten_blue_is_numeric_maximum(column):
    rows = hours_for_day(column, ["blue"] * 5 + ["cumulus"] + ["blue"] * 5)
    daily = calculation.aggregate_day(rows)
    assert daily.max_at_utc == rows[5].valid_at_utc
    assert daily.max_cloudbase == rows[5].estimated_cloudbase
    assert daily.coverage_complete and daily.summary_state == "cloudbase_available"


def test_missing_and_indeterminate_hours_qualify_numeric_maximum(column):
    rows = hours_for_day(column, ["cumulus", "missing", "indeterminate"] + ["blue"] * 8)
    daily = calculation.aggregate_day(rows)
    assert daily.max_cloudbase is not None and not daily.coverage_complete
    assert daily.present_hours == 10 and daily.classified_hours == 9


def test_equal_maximum_uses_earliest_hour_and_not_potential_only(column):
    rows = hours_for_day(column, ["blue"] + ["cumulus"] * 10)
    rows[0] = rows[0].model_copy(
        update={"potential_base": Height(msl_m=9000, model_agl_m=8500, site_agl_m=7500)}
    )
    assert calculation.aggregate_day(rows[::-1]).max_at_utc == rows[1].valid_at_utc


def test_mixed_day_without_base_is_not_all_blue(column):
    rows = hours_for_day(column, ["blue"] * 10 + ["indeterminate"])
    assert calculation.aggregate_day(rows).summary_state == "indeterminate"


def test_daily_wire_contract_rejects_false_all_day_and_coverage_claims(column):
    daily = calculation.aggregate_day(hours_for_day(column, ["cumulus", "missing"] + ["blue"] * 9))
    for changes in (
        {"coverage_complete": True},
        {"max_at_utc": None},
        {"summary_state": "blue"},
        {"present_hours": 11},
    ):
        with pytest.raises(ValidationError):
            type(daily).model_validate({**daily.model_dump(), **changes})


def test_duplicate_missing_and_mixed_identity_hours_are_rejected(column):
    rows = hours_for_day(column, ["blue"] * 11)
    for bad in (rows[:-1], [rows[0]] * 11, [rows[0].model_copy(update={"site_id": 2}), *rows[1:]]):
        with pytest.raises(ValueError):
            calculation.aggregate_day(bad)


@pytest.mark.parametrize(
    ("day", "first"),
    [("2024-03-31", "2024-03-31T07:00:00Z"), ("2024-10-27", "2024-10-27T08:00:00Z")],
)
def test_window_and_local_times_across_dst(column, day, first):
    rows = hours_for_day(column.model_copy(update={"target_local_date": day}), ["blue"] * 11)
    assert rows[0].valid_at_utc == first
    assert "T10:00:00" in rows[0].valid_at_local
    assert calculation.aggregate_day(rows).expected_hours == 11
