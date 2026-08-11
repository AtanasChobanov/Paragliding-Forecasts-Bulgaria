from __future__ import annotations

import pytest

from paragliding_forecasts_ml.ingestion.xccontest.browser import (
    COUNTRY_SELECTOR,
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
    driver = PlaywrightFlightListDriver(
        CollectorConfig(seasons=(2025,), country_codes=("BG",)), sleeper=lambda _: None
    )
    driver._page = page

    driver._wait_for_selected_value('select[name="filter[country]"]', "BG")

    assert page.wait_calls == [
        (
            "([selector, expectedValue]) => document.querySelector(selector)?.value === expectedValue",
            ['select[name="filter[country]"]', "BG"],
        )
    ]


def test_maps_only_collector_control_fields() -> None:
    row = PlaywrightFlightListDriver._row_observation(
        {"id": "5802259", "distance": "400.86", "launchCountry": "BG"}
    )

    assert row.source_flight_id == "5802259"
    assert row.launch_country_code == "BG"
    assert row.distance_km == 400.86


def test_accepts_dates_from_both_calendar_years_of_an_xccontest_season() -> None:
    PlaywrightFlightListDriver._validate_season_dates(
        2025,
        ("2024-10-01", "2024-12-31", "2025-01-01", "2025-09-30"),
    )


@pytest.mark.parametrize("value", ("2024-09-30", "2025-10-01", "not-a-date"))
def test_rejects_dates_outside_or_invalid_for_an_xccontest_season(value: str) -> None:
    with pytest.raises(BrowserCollectionError):
        PlaywrightFlightListDriver._validate_season_dates(2025, (value,))


def test_select_country_uses_the_rendered_country_control(monkeypatch) -> None:
    driver = PlaywrightFlightListDriver(
        CollectorConfig(seasons=(2025,), country_codes=("BG",)), sleeper=lambda _: None
    )
    selected: list[tuple[str, str]] = []
    monkeypatch.setattr(
        driver,
        "_select_option",
        lambda selector, value: selected.append((selector, value)),
    )

    driver.select_country("RS")

    assert selected == [(COUNTRY_SELECTOR, "RS")]


class FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status


class FakeSeasonLocator:
    def __init__(self, selected: list[str]) -> None:
        self._selected = selected

    def select_option(self, value: str) -> None:
        self._selected.append(value)


class FakeSeasonPage:
    def __init__(self, status: int) -> None:
        self.status = status
        self.selected: list[str] = []
        self.goto_calls: list[str] = []

    def goto(self, url: str, *, wait_until: str) -> FakeResponse:
        assert wait_until == "domcontentloaded"
        self.goto_calls.append(url)
        return FakeResponse(self.status)

    def locator(self, selector: str) -> FakeSeasonLocator:
        return FakeSeasonLocator(self.selected)

    def wait_for_load_state(self, state: str) -> None:
        assert state == "domcontentloaded"


def test_paces_navigation_and_season_selection_and_rejects_failed_navigation(monkeypatch) -> None:
    delays: list[float] = []
    driver = PlaywrightFlightListDriver(
        CollectorConfig(seasons=(2025,), country_codes=("BG",)), sleeper=delays.append
    )
    page = FakeSeasonPage(500)
    driver._page = page
    monkeypatch.setattr(driver, "_wait_for_flights_container", lambda: None)

    with pytest.raises(BrowserCollectionError, match="500"):
        driver.prepare_season(2025)

    assert delays == [30]
    assert page.goto_calls == ["https://www.xcontest.org/world/en/flights/"]


def test_paces_navigation_and_season_selection_before_source_changes(monkeypatch) -> None:
    delays: list[float] = []
    driver = PlaywrightFlightListDriver(
        CollectorConfig(seasons=(2025,), country_codes=("BG",)), sleeper=delays.append
    )
    page = FakeSeasonPage(200)
    driver._page = page
    monkeypatch.setattr(driver, "_wait_for_flights_container", lambda: None)
    monkeypatch.setattr(driver, "_season_option_value", lambda _season: "season-2025")

    driver.prepare_season(2025)

    assert delays == [30, 30]
    assert page.selected == ["season-2025"]
