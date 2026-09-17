from datetime import UTC, datetime

from paragliding_forecasts_ml.ingestion.igra.inventory import parse_selection, resolve_archive_mode


def test_range_selection_is_sorted_and_inclusive() -> None:
    dates, hours = parse_selection(
        dates=(),
        start_date="2025-08-02",
        end_date="2025-08-03",
        nominal_hours=(12, 6),
    )
    assert dates == ("2025-08-02", "2025-08-03")
    assert hours == (6, 12)


def test_auto_historical_selection_uses_period_of_record() -> None:
    assert (
        resolve_archive_mode("auto", ("2025-08-02",), now=datetime(2026, 9, 15, tzinfo=UTC))
        == "period-of-record"
    )
