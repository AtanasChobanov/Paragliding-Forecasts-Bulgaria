from __future__ import annotations

import pytest

from paragliding_forecasts_ml.ingestion.xccontest.browser import (
    BrowserCollectionError,
    PlaywrightFlightListDriver,
)
from paragliding_forecasts_ml.ingestion.xccontest.models import CollectorConfig


class FakeFlightsLocator:
    def wait_for(self, *, state: str) -> None:
        assert state == "visible"


class FakePage:
    def __init__(self) -> None:
        self.wait_calls: list[tuple[str, object]] = []

    def locator(self, selector: str):
        assert selector == "#flights"
        return FakeFlightsLocator()

    def wait_for_function(self, expression: str, *, arg: object = None) -> None:
        self.wait_calls.append((expression, arg))

    def wait_for_timeout(self, milliseconds: int) -> None:
        assert milliseconds == 250


def test_passes_wait_for_function_values_by_keyword_argument() -> None:
    page = FakePage()
    driver = PlaywrightFlightListDriver(CollectorConfig(seasons=(2025,)), sleeper=lambda _: None)
    driver._page = page

    driver._wait_for_selected_value('select[name="filter[country]"]', "BG")

    assert page.wait_calls == [
        (
            "([selector, expectedValue]) => document.querySelector(selector)?.value === expectedValue",
            ['select[name="filter[country]"]', "BG"],
        )
    ]


def test_maps_downstream_flight_fields_without_normalizing_source_strings() -> None:
    row = PlaywrightFlightListDriver._row_observation(
        {
            "id": "5802259",
            "distance": "400.86",
            "launchCountry": "BG",
            "flightDate": "02.08.25",
            "takeoffTime": "10:55",
            "utcOffset": "=UTC+03:00",
            "launchName": "?",
            "launchSearchUrl": (
                "https://www.xcontest.org/2025/world/en/flights-search/"
                "?filter[point]=28.074375%2043.74609"
            ),
            "routeType": "free flight",
            "duration": "9 : 05",
            "detailUrl": (
                "https://www.xcontest.org/2025/world/en/flights/detail:adit0/2.08.2025/07:55"
            ),
        }
    )

    assert row.source_flight_id == "5802259"
    assert row.flight_date_raw == "02.08.25"
    assert row.takeoff_time_raw == "10:55"
    assert row.utc_offset_raw == "=UTC+03:00"
    assert row.launch_name_raw == "?"
    assert row.launch_country_code == "BG"
    assert row.launch_search_url is not None
    assert "filter[point]=28.074375%2043.74609" in row.launch_search_url
    assert row.route_type_raw == "free flight"
    assert row.distance_km == 400.86
    assert row.duration_raw == "9 : 05"
    assert row.source_flight_url is not None
    assert row.source_flight_url.endswith("detail:adit0/2.08.2025/07:55")


def test_keeps_optional_fields_missing_for_short_rows() -> None:
    row = PlaywrightFlightListDriver._row_observation(
        {
            "id": "short-row",
            "distance": "100,00",
            "launchCountry": "BG",
        }
    )

    assert row.distance_km == 100.0
    assert row.flight_date_raw is None
    assert row.launch_name_raw is None
    assert row.duration_raw is None
    assert row.source_flight_url is None


def test_accepts_dates_from_both_calendar_years_of_an_xccontest_season() -> None:
    PlaywrightFlightListDriver._validate_season_dates(
        2025,
        ("2024-10-01", "2024-12-31", "2025-01-01", "2025-09-30"),
    )


@pytest.mark.parametrize("value", ("2024-09-30", "2025-10-01", "not-a-date"))
def test_rejects_dates_outside_or_invalid_for_an_xccontest_season(value: str) -> None:
    with pytest.raises(BrowserCollectionError):
        PlaywrightFlightListDriver._validate_season_dates(2025, (value,))
