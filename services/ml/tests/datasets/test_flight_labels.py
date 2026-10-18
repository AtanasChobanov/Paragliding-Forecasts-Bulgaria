from __future__ import annotations

from datetime import date

import pytest

from paragliding_forecasts_ml.datasets.flight_labels import (
    LabelAuditError,
    build_rows,
    flying_date,
    season_dates,
    source_season,
)


def sites():
    slugs = {
        "sofia-vitosha-kominite",
        "zlatitsa",
        "sopot",
        "nevsha",
        "shumen",
        "pastrina",
        "dobrich-region",
    }
    return [
        {"id": i, "slug": slug, "country_code_iso2": "BG"}
        for i, slug in enumerate(sorted(slugs), 1)
    ]


def coverage():
    return {
        (2025, day.isoformat(), "BG"): {
            "mature": True,
            "activity_state": "complete",
            "activity_reason": "complete_daily_view",
            "mapping_complete": True,
            "threshold_complete": {str(t): True for t in (100, 200, 300)},
        }
        for day in season_dates(2025)
    }


def flight(distance, *, slug="shumen", identity="1", timestamp="2025-06-12T10:00:00Z"):
    return {
        "id": int(identity),
        "source_id": 1,
        "source_flight_id": identity,
        "source_site_mapping_id": 10,
        "evidence_run_key": "run",
        "site_id": next(s["id"] for s in sites() if s["slug"] == slug),
        "takeoff_at_utc": timestamp,
        "scored_distance_km": distance,
    }


def day_rows(flights, evidence=None):
    return {
        r["site_slug"]: r
        for r in build_rows(sites(), flights, evidence or coverage(), (2025,))
        if r["local_date"] == "2025-06-12"
    }


def states(row):
    return [row["labels"][str(t)]["state"] for t in (100, 200, 300)]


def test_shumen_threshold_flights_never_label_nevsha_positive():
    rows = day_rows(
        [flight(110, identity="1"), flight(150, identity="2"), flight(230, identity="3")]
    )
    assert states(rows["shumen"]) == ["positive", "positive", "negative"]
    assert states(rows["nevsha"]) == ["unknown"] * 3
    assert rows["nevsha"]["flight_count"] == 0
    assert rows["nevsha"]["max_distance_km"] is None
    rows = day_rows([flight(150), flight(78, slug="nevsha", identity="2")])
    assert states(rows["nevsha"]) == ["negative"] * 3
    assert rows["nevsha"]["labels"]["100"]["positive_source_flight_ids"] == []


@pytest.mark.parametrize(
    ("distance", "expected"),
    [
        (0, ["unknown"] * 3),
        (0.01, ["negative"] * 3),
        (99.99, ["negative"] * 3),
        (100, ["positive", "negative", "negative"]),
        (199.99, ["positive", "negative", "negative"]),
        (200, ["positive", "positive", "negative"]),
        (299.99, ["positive", "positive", "negative"]),
        (300, ["positive"] * 3),
        (2000, ["positive"] * 3),
    ],
)
def test_inclusive_nested_thresholds_and_zero_activity(distance, expected):
    row = day_rows([flight(distance)])["shumen"]
    assert states(row) == expected
    assert row["flight_count"] == int(distance > 0)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("mature", False, "evidence_not_mature"),
        ("activity_state", "partial", "complete_daily_view"),
        ("mapping_complete", False, "unresolved_mapping"),
        (
            "threshold_complete",
            {str(t): False for t in (100, 200, 300)},
            "incomplete_threshold_evidence",
        ),
    ],
)
def test_incomplete_evidence_keeps_confirmed_positive_but_blocks_negatives(field, value, reason):
    evidence = coverage()
    evidence[(2025, "2025-06-12", "BG")][field] = value
    row = day_rows([flight(150)], evidence)["shumen"]
    assert states(row) == ["positive", "unknown", "unknown"]
    assert row["labels"]["200"]["reason"] == reason


def test_duplicate_source_flights_cannot_inflate_activity():
    with pytest.raises(LabelAuditError, match="Duplicate"):
        day_rows([flight(50), flight(50)])


@pytest.mark.parametrize("distance", [-1, 2000.01, float("nan"), float("inf")])
def test_invalid_distances_fail(distance):
    with pytest.raises(LabelAuditError, match="distance"):
        day_rows([flight(distance)])


def test_sofia_midnight_and_source_season_not_calendar_year():
    assert flying_date("2025-06-11T21:15:00Z") == date(2025, 6, 12)
    assert flying_date("2024-09-30T21:15:00Z") == date(2024, 10, 1)
    assert source_season(date(2024, 10, 1)) == 2025
    assert source_season(date(2025, 9, 30)) == 2025
    assert (
        states(day_rows([flight(100, timestamp="2025-06-11T21:15:00Z")])["shumen"])[0] == "positive"
    )
    with pytest.raises(LabelAuditError, match="timezone"):
        flying_date("2025-06-12T12:00:00")


def test_full_calendar_includes_leap_day_and_deterministic_site_day_identity():
    assert len(list(season_dates(2024))) == 366
    rows = build_rows(sites(), [], coverage(), (2025,))
    assert len(rows) == 7 * 365
    assert len({(r["site_id"], r["local_date"]) for r in rows}) == len(rows)
    assert all(states(r) == ["unknown"] * 3 for r in rows)
    assert rows == build_rows(list(reversed(sites())), [], coverage(), (2025,))


def test_new_database_site_is_enumerated_without_source_code_change():
    catalog = sites() + [{"id": 8, "slug": "new-launch", "country_code_iso2": "BG"}]
    rows = build_rows(catalog, [flight(107.88)], coverage(), (2025,))
    assert len(rows) == 8 * 365
    new = [r for r in rows if r["site_slug"] == "new-launch"]
    assert len(new) == 365 and all(states(r) == ["unknown"] * 3 for r in new)


def test_partial_vector_preserves_the_107km_positive_in_unknown_output():
    evidence = coverage()
    evidence[(2025, "2025-06-12", "BG")].update(
        activity_state="out_of_window",
        activity_reason="outside_activity_window",
        threshold_complete={str(t): False for t in (100, 200, 300)},
    )
    row = day_rows([flight(107.88)], evidence)["shumen"]
    assert states(row) == ["positive", "unknown", "unknown"]
    assert row["all_labels_known"] is False
