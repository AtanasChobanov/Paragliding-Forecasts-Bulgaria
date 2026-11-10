"""Daily policy thresholds, input alignment and partial evidence."""

import json
from datetime import date

import pytest
from pydantic import ValidationError

from paragliding_forecasts_ml.ingestion.weather.features.aggregation import sofia_flying_window
from paragliding_forecasts_ml.ingestion.weather.serialization import sha256_bytes
from paragliding_forecasts_ml.predictions.overdevelopment.models import (
    FIELD_UNITS,
    ForecastDay,
    Observation,
    observation_layout,
)
from paragliding_forecasts_ml.predictions.overdevelopment.policy import Policy, load_policy
from paragliding_forecasts_ml.predictions.overdevelopment.scoring import _score_level, evaluate_day

RUN_KEY = "11111111-1111-4111-8111-111111111111"
POLICY, POLICY_BYTES = load_policy()


def forecast(overrides=None, **defaults):
    window = sofia_flying_window(date(2024, 6, 2))
    observations = []
    for timestamp, key, end in observation_layout(window):
        index = window.expected_instants_utc.index(timestamp)
        value = (overrides or {}).get((key, index), defaults.get(key, 0.0))
        observations.append(
            Observation(
                key=key,
                valid_at_utc=timestamp,
                interval_end_utc=end,
                unit=FIELD_UNITS[key],
                value=value,
                quality="missing" if value is None else "real",
                missing_reason="field_absent" if value is None else None,
            )
        )
    return ForecastDay(
        run_key=RUN_KEY,
        site_id=1,
        site_slug="synthetic",
        point_footprint_key="a" * 64,
        target_local_date="2024-06-02",
        source_product_key="synthetic",
        issue_local_date="2024-06-01",
        cycle_reference_utc="2024-06-01T06:00:00Z",
        horizon_days=1,
        window_start_utc=window.interval_start_utc,
        window_end_utc=window.interval_end_utc,
        hourly_source_ready_at_utc=("2024-06-01T13:00:00Z",) * 11,
        source_ready_at_utc="2024-06-01T13:00:00Z",
        observations=tuple(observations),
    )


def assess(day):
    return evaluate_day(day, POLICY, sha256_bytes(POLICY_BYTES))


@pytest.mark.parametrize(
    ("score", "level"),
    [(0, "low"), (24.999, "low"), (25, "medium"), (64.999, "medium"), (65, "high")],
)
def test_category_boundaries(score, level):
    assert _score_level(score, POLICY) == level


def test_cloud_and_instability_are_independent_daily_contributions():
    assert assess(forecast())["reasons"][0]["code"] == "weak_modelled_signals"
    cloud = assess(forecast(low_cloud=90, humidity=90))
    assert cloud["risk_level"] == "medium"
    assert cloud["score"] == pytest.approx(26.25)
    assert assess(forecast(cape=1000, cin=25))["score"] == pytest.approx(26.25)
    assert assess(forecast(cape=1000, cin=100))["score"] == pytest.approx(10.5)
    assert assess(forecast(cape=501, cin=25))["score"] - assess(forecast(cape=499, cin=25))[
        "score"
    ] == pytest.approx(0.07)


def test_unrelated_hours_cannot_trigger_convective_override():
    day = forecast({("cape", 2): 1200, ("cin", 2): 30, ("rain", 7): 1.2})
    result = assess(day)
    assert result["risk_level"] == "medium"
    assert result["score"] == pytest.approx(47.961666666666666)
    assert result["overrides"] == []
    assert [reason["code"] for reason in result["reasons"]] == ["instability", "precipitation"]


def test_high_by_score_and_sum_of_maximum_contributions():
    day = forecast({("rain", 1): 0.9}, cape=1250, cin=25, low_cloud=100, humidity=100)
    result = assess(day)
    assert result["risk_level"] == "high"
    assert result["overrides"] == []
    assert (
        assess(forecast(rain=2.5, cape=1250, cin=25, low_cloud=100, humidity=100))["score"] == 100
    )


@pytest.mark.parametrize(
    ("overrides", "defaults", "code"),
    [
        ({("rain", 9): 2.5}, {}, "high_precipitation"),
        ({}, {"rain": 0.5}, "high_precipitation"),
        ({("cape", 2): 1000, ("cin", 2): 50, ("rain", 2): 1.0}, {}, "strong_convective_signal"),
        ({("wind", 10): 10.0001}, {}, "strong_near_surface_wind"),
    ],
)
def test_override_boundaries(overrides, defaults, code):
    result = assess(forecast(overrides, **defaults))
    assert result["risk_level"] == "high"
    assert result["overrides"][0]["code"] == code
    assert result["reasons"][0]["code"] == code


def test_just_below_rain_boundaries_and_exact_wind_limit():
    result = assess(forecast({("rain", 0): 2.499, ("rain", 1): 2.499}, wind=10))
    assert result["overrides"] == []
    assert result["risk_level"] == "medium"


@pytest.mark.parametrize(("key", "value"), [("cape", 999.99), ("cin", 50.01), ("rain", 0.99)])
def test_convective_override_requires_each_threshold(key, value):
    values = {("cape", 2): 1000, ("cin", 2): 50, ("rain", 2): 1.0}
    values[key, 2] = value
    assert assess(forecast(values))["overrides"] == []


def test_partial_evidence_and_conditional_cin():
    result = assess(forecast({("cape", 1): 250, ("cin", 1): None}))
    assert result["risk_level"] == "low"
    assert result["coverage"]["complete"]
    assert result["coverage"]["gaps"][0]["required"] is False
    result = assess(forecast({("cape", 1): 251, ("cin", 1): None}))
    assert result["risk_level"] is result["score"] is result["confidence"] is None
    assert result["data_status"] == "missing"
    result = assess(forecast({("rain", 0): None}, rain=0.6))
    assert result["risk_level"] == "high"
    assert result["confidence"] == "low"
    assert result["score"] is result["contributions"] is None
    assert not result["coverage"]["complete"]
    assert result["overrides"][0]["evidence"][0]["lower_bound"]
    assert "at least" in result["reasons"][0]["message"]


def test_all_overrides_have_stable_order_and_earliest_peak():
    result = assess(forecast({("rain", 2): 2.5, ("rain", 3): 2.5}, cape=1000, cin=50, wind=11))
    assert [reason["code"] for reason in result["reasons"]] == [
        "high_precipitation",
        "strong_convective_signal",
        "strong_near_surface_wind",
    ]
    assert len(result["overrides"][0]["evidence"]) == 3
    assert result["reasons"][0]["evidence"]["valid_at_utc"] == "2024-06-02T09:00:00Z"
    assert result["reasons"][2]["evidence"]["valid_at_utc"] == "2024-06-02T07:00:00Z"


@pytest.mark.parametrize(
    "change",
    [
        {"rain_peak": {"lower": 2, "upper": 2}},
        {"low_cloud": {"lower": 50, "upper": 101}},
        {"rain_weight": 36},
        {"medium_threshold": 65},
        {"high_threshold": 101},
        {"cin_discount": 1.01},
        {"override_convective_cape_j_per_kg": 250},
        {"override_wind_m_s": float("inf")},
        {"unknown": 1},
    ],
)
def test_policy_rejects_invalid_configuration(change):
    with pytest.raises(ValidationError):
        Policy.model_validate_json(json.dumps(json.loads(POLICY_BYTES) | change))
