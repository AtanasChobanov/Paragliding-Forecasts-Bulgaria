from __future__ import annotations

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from paragliding_forecasts_ml.ingestion.xccontest.browser import (
    COUNTRY_SELECTOR,
    ROW_SELECTOR,
    BrowserCollectionError,
    PlaywrightFlightListDriver,
)
from paragliding_forecasts_ml.ingestion.xccontest.models import (
    PRIMARY_GLIDER_CATEGORY,
    CollectorConfig,
    FlightListScope,
    source_default_scope,
)


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


def test_selected_value_wait_accepts_a_new_document_with_identical_results() -> None:
    page = FakePage()
    driver = PlaywrightFlightListDriver(
        CollectorConfig(seasons=(2025,), country_codes=("BG",)), sleeper=lambda _: None
    )
    driver._page = page

    driver._wait_for_selected_value(
        'select[name="filter[date]"]',
        "2025-03-16",
        '<section id="flights"></section>',
        previous_url="https://www.xcontest.org/2025/world/en/flights/",
    )

    expression, arguments = page.wait_calls[0]
    assert "window.location.href !== previousUrl" in expression
    assert "xccontestCollectorTransition" in expression
    assert arguments == [
        'select[name="filter[date]"]',
        "2025-03-16",
        '<section id="flights"></section>',
        "https://www.xcontest.org/2025/world/en/flights/",
    ]


class TimeoutPage(FakePage):
    def wait_for_function(self, expression: str, *, arg: object = None) -> None:
        raise PlaywrightTimeoutError("timed out")


def test_selected_value_timeout_names_the_unsettled_control() -> None:
    driver = PlaywrightFlightListDriver(
        CollectorConfig(seasons=(2025,), country_codes=("BG",)), sleeper=lambda _: None
    )
    driver._page = TimeoutPage()

    with pytest.raises(
        BrowserCollectionError,
        match=r'control select\[name="filter\[date\]"\] did not settle on \'2025-03-16\'',
    ):
        driver._wait_for_selected_value('select[name="filter[date]"]', "2025-03-16")


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


def test_read_page_captures_fragment_controls_and_rows_in_one_browser_callback() -> None:
    class SnapshotLocator:
        def wait_for(self, *, state: str) -> None:
            assert state == "visible"

        def evaluate(self, expression: str, selectors: dict[str, str]) -> dict[str, object]:
            assert "fragmentHtml: flights.outerHTML" in expression
            assert selectors["row"] == ROW_SELECTOR.removeprefix("#flights ")
            assert selectors["date"] == 'select[name="filter[date]"]'
            return {
                "fragmentHtml": '<div id="flights">same snapshot</div>',
                "countryFilter": "BG",
                "gliderCategoryFilter": "FAI3",
                "dateFilter": "2022-05-13",
                "hasNextPage": False,
                "rows": [{"id": "3134454", "distance": "100.0", "launchCountry": "BG"}],
            }

    class SnapshotPage:
        def wait_for_function(self, expression: str, *, arg: object = None) -> None:
            assert "option[selected]" in expression
            assert arg == ['select[name="filter[date]"]', "2022-05-13"]

        def locator(self, selector: str) -> SnapshotLocator:
            assert selector == "#flights"
            return SnapshotLocator()

        def wait_for_timeout(self, milliseconds: int) -> None:
            assert milliseconds == 250

    driver = PlaywrightFlightListDriver(
        CollectorConfig(seasons=(2022,), country_codes=("BG",)), sleeper=lambda _: None
    )
    driver._page = SnapshotPage()

    page = driver.read_page(
        2022, source_default_scope(PRIMARY_GLIDER_CATEGORY, date_filter="2022-05-13")
    )

    assert page.fragment_html == '<div id="flights">same snapshot</div>'
    assert page.date_filter == "2022-05-13"
    assert [row.source_flight_id for row in page.rows] == ["3134454"]


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


def test_source_default_scope_changes_filters_in_place_without_sorting(monkeypatch) -> None:
    driver = PlaywrightFlightListDriver(
        CollectorConfig(seasons=(2025,), country_codes=("BG",)), sleeper=lambda _: None
    )
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        driver,
        "_select_option",
        lambda selector, value: calls.append(("select", selector, value)),
    )
    monkeypatch.setattr(
        driver,
        "_ensure_sort",
        lambda *_: pytest.fail("source_default must not click a sortable column"),
    )

    driver.select_scope(source_default_scope(PRIMARY_GLIDER_CATEGORY, date_filter="2025-07-01"))

    assert calls == [
        ("select", 'select[name="filter[detail_glider_catg]"]', "FAI3"),
        ("select", 'select[name="filter[date]"]', "2025-07-01"),
    ]


def test_explicit_scope_does_not_reset_and_applies_its_sort(monkeypatch) -> None:
    driver = PlaywrightFlightListDriver(
        CollectorConfig(seasons=(2025,), country_codes=("BG",)), sleeper=lambda _: None
    )
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        driver,
        "_select_option",
        lambda selector, value: calls.append(("select", selector, value)),
    )
    monkeypatch.setattr(
        driver,
        "_ensure_sort",
        lambda key, direction: calls.append(("sort", key, direction)),
    )

    driver.select_scope(FlightListScope(PRIMARY_GLIDER_CATEGORY))

    assert calls[-1] == ("sort", "distance", "descending")


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
