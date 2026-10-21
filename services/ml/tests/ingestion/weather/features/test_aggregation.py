from __future__ import annotations

from datetime import date, timedelta

import pytest

from paragliding_forecasts_ml.ingestion.weather.features.aggregation import (
    IntervalValue,
    TimedValue,
    hourly_amount_maximum,
    interval_maximum,
    interval_total,
    interval_weighted_mean,
    sofia_flying_window,
    strict_hourly_reduction,
)


def _hours(window, value: float = 1.0) -> tuple[TimedValue, ...]:
    return tuple(TimedValue(instant, value) for instant in window.expected_instants_utc)


def _intervals(
    window, durations_and_values: tuple[tuple[int, float], ...]
) -> tuple[IntervalValue, ...]:
    start = window.interval_start_utc
    items: list[IntervalValue] = []
    for seconds, value in durations_and_values:
        end = (_parse(start) + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
        items.append(IntervalValue(start, end, value))
        start = end
    return tuple(items)


def _parse(value: str):
    from datetime import UTC, datetime

    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def test_sofia_window_has_exactly_eleven_instants_and_respects_summer_and_winter_offsets() -> None:
    summer = sofia_flying_window(date(2026, 7, 1))
    winter = sofia_flying_window(date(2026, 1, 1))

    assert len(summer.expected_instants_utc) == 11
    assert summer.expected_instants_utc[0] == "2026-07-01T07:00:00Z"
    assert summer.expected_instants_utc[-1] == "2026-07-01T17:00:00Z"
    assert winter.expected_instants_utc[0] == "2026-01-01T08:00:00Z"
    assert winter.interval_end_utc == "2026-01-01T18:00:00Z"


@pytest.mark.parametrize(
    ("local_date", "first_utc", "last_utc"),
    (
        (date(2026, 3, 28), "2026-03-28T08:00:00Z", "2026-03-28T18:00:00Z"),
        (date(2026, 3, 29), "2026-03-29T07:00:00Z", "2026-03-29T17:00:00Z"),
        (date(2026, 10, 24), "2026-10-24T07:00:00Z", "2026-10-24T17:00:00Z"),
        (date(2026, 10, 25), "2026-10-25T08:00:00Z", "2026-10-25T18:00:00Z"),
    ),
)
def test_sofia_window_keeps_eleven_instants_and_ten_interval_hours_across_dst(
    local_date: date, first_utc: str, last_utc: str
) -> None:
    window = sofia_flying_window(local_date)

    assert window.expected_instants_utc == tuple(
        (_parse(first_utc) + timedelta(hours=hour)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for hour in range(11)
    )
    assert window.interval_start_utc == first_utc
    assert window.interval_end_utc == last_utc
    assert (_parse(last_utc) - _parse(first_utc)).total_seconds() == 10 * 3600


def test_hourly_reduction_requires_every_unique_expected_instant() -> None:
    window = sofia_flying_window(date(2026, 7, 1))

    assert (
        strict_hourly_reduction(
            _hours(window, 2), window, lambda values: sum(values) / len(values)
        ).value
        == 2
    )
    assert (
        strict_hourly_reduction(_hours(window)[:-1], window, max).missing_reason == "missing_hour"
    )
    assert (
        strict_hourly_reduction(
            (*_hours(window), TimedValue("2026-07-01T06:00:00Z", 1)), window, max
        ).missing_reason
        == "hour_outside_flying_window"
    )
    assert (
        strict_hourly_reduction((*_hours(window), _hours(window)[0]), window, max).missing_reason
        == "duplicate_hour"
    )


@pytest.mark.parametrize(
    ("replacement", "expected_reason"),
    (
        (None, "hour_value_missing"),
        (float("nan"), "hour_value_non_finite"),
        (float("inf"), "hour_value_non_finite"),
        (-float("inf"), "hour_value_non_finite"),
    ),
)
def test_hourly_reduction_rejects_missing_and_non_finite_values(
    replacement: float | None, expected_reason: str
) -> None:
    window = sofia_flying_window(date(2026, 7, 1))
    observations = (
        *_hours(window, 0)[:5],
        TimedValue(window.expected_instants_utc[5], replacement),
        *_hours(window, 0)[6:],
    )

    result = strict_hourly_reduction(observations, window, sum)

    assert result.value is None
    assert result.missing_reason == expected_reason


def test_hourly_zero_is_available_and_reducer_overflow_is_missing() -> None:
    window = sofia_flying_window(date(2026, 7, 1))

    assert strict_hourly_reduction(_hours(window, 0), window, min).value == 0
    overflow = strict_hourly_reduction(_hours(window, 1e308), window, sum)
    assert overflow.value is None
    assert overflow.missing_reason == "aggregate_non_finite"


def test_interval_reductions_require_exact_contiguous_half_open_coverage() -> None:
    window = sofia_flying_window(date(2026, 7, 1))
    hourly = _intervals(window, tuple((3600, float(hour)) for hour in range(1, 11)))

    assert interval_total(hourly, window).value == 55
    assert hourly_amount_maximum(hourly, window).value == 10
    assert interval_maximum(hourly, window).value == 10
    assert interval_weighted_mean(hourly, window).value == pytest.approx(5.5)
    assert interval_total(hourly[:-1], window).missing_reason == "interval_coverage_gap"
    assert interval_total((*hourly, hourly[0]), window).missing_reason == "duplicate_interval"
    overlapping_first = IntervalValue(
        hourly[0].interval_start_utc,
        (_parse(hourly[0].interval_end_utc) + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        1,
    )
    assert (
        interval_total((overlapping_first, *hourly[1:]), window).missing_reason
        == "interval_overlap"
    )


def test_interval_reductions_exclude_preceding_hour_and_keep_non_hourly_total_separate() -> None:
    window = sofia_flying_window(date(2026, 7, 1))
    half_windows = _intervals(window, ((7200, 2), (7200, 4), (7200, 6), (7200, 8), (7200, 10)))
    preceding = IntervalValue("2026-07-01T06:00:00Z", window.interval_start_utc, 99)

    assert interval_total(half_windows, window).value == 30
    assert interval_weighted_mean(half_windows, window).value == pytest.approx(6)
    assert (
        hourly_amount_maximum(half_windows, window).missing_reason == "hourly_amount_not_resolved"
    )
    assert (
        interval_total((*half_windows, preceding), window).missing_reason
        == "interval_outside_flying_window"
    )


def test_interval_mean_weights_duration_and_amount_maximum_requires_hourly_resolution() -> None:
    window = sofia_flying_window(date(2026, 7, 1))
    radiation = _intervals(window, ((2 * 3600, 100.0), (8 * 3600, 200.0)))
    rainfall = _intervals(window, tuple((3600, float(hour)) for hour in range(1, 11)))

    assert interval_weighted_mean(radiation, window).value == 180.0
    assert interval_maximum(radiation, window).value == 200.0
    assert interval_total(rainfall, window).value == 55.0
    assert hourly_amount_maximum(rainfall, window).value == 10.0
    assert hourly_amount_maximum(radiation, window).missing_reason == "hourly_amount_not_resolved"


@pytest.mark.parametrize(
    ("interval", "expected_reason"),
    (
        (
            IntervalValue("2026-07-01T07:00:00Z", "2026-07-01T07:00:00Z", 1),
            "invalid_interval_duration",
        ),
        (IntervalValue("2026-07-01T07:00:00Z", "invalid", 1), "invalid_interval_timestamp"),
        (
            IntervalValue("2026-07-01T07:00:00Z", "2026-07-01T08:00:00Z", None),
            "interval_value_missing",
        ),
        (
            IntervalValue("2026-07-01T07:00:00Z", "2026-07-01T08:00:00Z", float("nan")),
            "interval_value_non_finite",
        ),
        (
            IntervalValue("2026-07-01T06:00:00Z", "2026-07-01T08:00:00Z", 1),
            "interval_outside_flying_window",
        ),
    ),
)
def test_interval_reducers_fail_closed_on_invalid_evidence(
    interval: IntervalValue, expected_reason: str
) -> None:
    window = sofia_flying_window(date(2026, 7, 1))
    hourly = _intervals(window, tuple((3600, 0.0) for _ in range(10)))

    result = interval_total((interval, *hourly[1:]), window)

    assert result.value is None
    assert result.missing_reason == expected_reason


def test_interval_reducers_reject_internal_gap_and_overlap_without_partial_values() -> None:
    window = sofia_flying_window(date(2026, 7, 1))
    hourly = _intervals(window, tuple((3600, 1.0) for _ in range(10)))
    gap = IntervalValue("2026-07-01T09:30:00Z", "2026-07-01T10:00:00Z", 1.0)
    overlap = IntervalValue("2026-07-01T08:30:00Z", "2026-07-01T10:00:00Z", 1.0)

    for reducer in (interval_total, interval_weighted_mean, interval_maximum):
        assert (
            reducer((*hourly[:2], gap, *hourly[3:]), window).missing_reason
            == "interval_coverage_gap"
        )
        assert (
            reducer((*hourly[:2], overlap, *hourly[3:]), window).missing_reason
            == "interval_overlap"
        )
