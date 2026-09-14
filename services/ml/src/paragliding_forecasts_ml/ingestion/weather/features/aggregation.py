"""DST-aware strict day-window aggregation for S07 canonical evidence."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from math import isfinite
from zoneinfo import ZoneInfo

SOFIA_TIME_ZONE = "Europe/Sofia"
SOFIA_WINDOW_VERSION = "sofia-flying-window/1"
_WINDOW_START_HOUR = 10
_WINDOW_END_HOUR = 20


@dataclass(frozen=True)
class FlyingWindow:
    """The fixed local instantaneous and half-open interval coverage contract."""

    local_date: date
    expected_instants_utc: tuple[str, ...]
    interval_start_utc: str
    interval_end_utc: str


@dataclass(frozen=True)
class TimedValue:
    """One canonical instantaneous scalar at an exact UTC valid time."""

    valid_at_utc: str
    value: float | None


@dataclass(frozen=True)
class IntervalValue:
    """One canonical amount or interval-average scalar on a half-open UTC interval."""

    interval_start_utc: str
    interval_end_utc: str
    value: float | None


@dataclass(frozen=True)
class AggregationResult:
    """A finite value or exact machine-readable missing reason, never a partial aggregate."""

    value: float | None
    missing_reason: str | None = None

    @property
    def is_complete(self) -> bool:
        return self.value is not None and self.missing_reason is None


def sofia_flying_window(local_date: date) -> FlyingWindow:
    """Return exactly eleven local 10:00--20:00 instants and [10:00,20:00) coverage."""

    zone = ZoneInfo(SOFIA_TIME_ZONE)
    instants = tuple(
        _format_utc(datetime.combine(local_date, time(hour), tzinfo=zone).astimezone(UTC))
        for hour in range(_WINDOW_START_HOUR, _WINDOW_END_HOUR + 1)
    )
    return FlyingWindow(
        local_date=local_date,
        expected_instants_utc=instants,
        interval_start_utc=instants[0],
        interval_end_utc=_format_utc(
            datetime.combine(local_date, time(_WINDOW_END_HOUR), tzinfo=zone).astimezone(UTC)
        ),
    )


def strict_hourly_reduction(
    observations: Sequence[TimedValue],
    window: FlyingWindow,
    reducer: Callable[[tuple[float, ...]], float],
) -> AggregationResult:
    """Reduce only one complete, unique set of the eleven expected instants."""

    expected = set(window.expected_instants_utc)
    actual = [item.valid_at_utc for item in observations]
    if len(actual) != len(set(actual)):
        return AggregationResult(None, "duplicate_hour")
    if set(actual) - expected:
        return AggregationResult(None, "hour_outside_flying_window")
    if set(actual) != expected:
        return AggregationResult(None, "missing_hour")
    values: list[float] = []
    by_time = {item.valid_at_utc: item.value for item in observations}
    for instant in window.expected_instants_utc:
        value = by_time[instant]
        if value is None:
            return AggregationResult(None, "hour_value_missing")
        if not isfinite(value):
            return AggregationResult(None, "hour_value_non_finite")
        values.append(value)
    result = reducer(tuple(values))
    if not isfinite(result):
        return AggregationResult(None, "aggregate_non_finite")
    return AggregationResult(result)


def interval_total(intervals: Sequence[IntervalValue], window: FlyingWindow) -> AggregationResult:
    """Sum canonical amounts only after exact half-open window coverage is proved."""

    covered, reason = _complete_intervals(intervals, window)
    if reason is not None:
        return AggregationResult(None, reason)
    return AggregationResult(sum(item.value for item in covered if item.value is not None))


def interval_weighted_mean(
    intervals: Sequence[IntervalValue], window: FlyingWindow
) -> AggregationResult:
    """Duration-weight interval-average values after exact half-open coverage is proved."""

    covered, reason = _complete_intervals(intervals, window)
    if reason is not None:
        return AggregationResult(None, reason)
    durations = tuple(_duration_seconds(item) for item in covered)
    denominator = sum(durations)
    if denominator <= 0:
        return AggregationResult(None, "invalid_interval_duration")
    numerator = sum(
        value.value * duration
        for value, duration in zip(covered, durations, strict=True)
        if value.value is not None
    )
    return AggregationResult(numerator / denominator)


def interval_maximum(intervals: Sequence[IntervalValue], window: FlyingWindow) -> AggregationResult:
    """Return the greatest validated interval-average value, not an unobserved point peak."""

    covered, reason = _complete_intervals(intervals, window)
    if reason is not None:
        return AggregationResult(None, reason)
    return AggregationResult(max(item.value for item in covered if item.value is not None))


def hourly_amount_maximum(
    intervals: Sequence[IntervalValue], window: FlyingWindow
) -> AggregationResult:
    """Return an amount maximum only when every validated interval is exactly one hour."""

    covered, reason = _complete_intervals(intervals, window)
    if reason is not None:
        return AggregationResult(None, reason)
    if any(_duration_seconds(item) != 3600 for item in covered):
        return AggregationResult(None, "hourly_amount_not_resolved")
    return AggregationResult(max(item.value for item in covered if item.value is not None))


def _complete_intervals(
    intervals: Sequence[IntervalValue], window: FlyingWindow
) -> tuple[tuple[IntervalValue, ...], str | None]:
    if not intervals:
        return (), "interval_coverage_missing"
    identities = tuple((item.interval_start_utc, item.interval_end_utc) for item in intervals)
    if len(identities) != len(set(identities)):
        return (), "duplicate_interval"
    parsed: list[tuple[datetime, datetime, IntervalValue]] = []
    for item in intervals:
        try:
            start = _parse_utc(item.interval_start_utc)
            end = _parse_utc(item.interval_end_utc)
        except ValueError:
            return (), "invalid_interval_timestamp"
        if start >= end:
            return (), "invalid_interval_duration"
        if start < _parse_utc(window.interval_start_utc) or end > _parse_utc(
            window.interval_end_utc
        ):
            return (), "interval_outside_flying_window"
        if item.value is None:
            return (), "interval_value_missing"
        if not isfinite(item.value):
            return (), "interval_value_non_finite"
        parsed.append((start, end, item))
    parsed.sort(key=lambda item: (item[0], item[1]))
    window_start = _parse_utc(window.interval_start_utc)
    window_end = _parse_utc(window.interval_end_utc)
    if parsed[0][0] != window_start:
        return (), "interval_coverage_gap"
    previous_end = window_start
    for start, end, _item in parsed:
        if start < previous_end:
            return (), "interval_overlap"
        if start > previous_end:
            return (), "interval_coverage_gap"
        previous_end = end
    if previous_end != window_end:
        return (), "interval_coverage_gap"
    return tuple(item for _start, _end, item in parsed), None


def _duration_seconds(interval: IntervalValue) -> float:
    return (
        _parse_utc(interval.interval_end_utc) - _parse_utc(interval.interval_start_utc)
    ).total_seconds()


def _parse_utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _format_utc(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")
