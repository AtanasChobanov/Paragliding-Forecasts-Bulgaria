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
