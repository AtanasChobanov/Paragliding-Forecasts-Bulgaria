"""The authorized, visible-UI XCContest browser adapter."""

from __future__ import annotations

from collections.abc import Callable
from itertools import pairwise
from typing import Self

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from .models import COUNTRY_CODE, CollectorConfig, FlightListScope, PageObservation, RowObservation

ROOT_URL = "https://www.xcontest.org/world/en/flights/"
SEASON_SELECTOR = 'div.under-bar select[onchange*="document.location.replace"]'
COUNTRY_SELECTOR = 'select[name="filter[country]"]'
GLIDER_SELECTOR = 'select[name="filter[detail_glider_catg]"]'
DATE_SELECTOR = 'select[name="filter[date]"]'
ROW_SELECTOR = "#flights table.XClist tbody tr[id^='flight-']"
SORT_SELECTOR_TEMPLATE = "#flights table.XClist thead a[href*='flights[sort]={sort_key}']"


class BrowserCollectionError(RuntimeError):
    """The source UI could not prove the collector's expected state."""


class PlaywrightFlightListDriver:
    """Interact only through the XCContest-rendered controls and DOM."""

    def __init__(self, config: CollectorConfig, *, sleeper: Callable[[float], None]) -> None:
        self._config = config
        self._sleeper = sleeper
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def __enter__(self) -> Self:
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=not self._config.headed,
            slow_mo=self._config.slow_mo_ms,
        )
        self._context = self._browser.new_context()
        self._page = self._context.new_page()
        self._page.set_default_timeout(self._config.timeout_seconds * 1000)
        return self

    def __exit__(self, *_: object) -> None:
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    @property
    def _active_page(self) -> Page:
        if self._page is None:
            raise BrowserCollectionError("Browser driver was used before it was started.")
        return self._page

    def prepare_season(self, season: int) -> None:
        """Select the season and BG through their rendered controls."""

        page = self._active_page
        page.goto(ROOT_URL, wait_until="domcontentloaded")
        self._wait_for_flights_container()

        season_option = self._season_option_value(season)
        page.locator(SEASON_SELECTOR).select_option(season_option)
        page.wait_for_load_state("domcontentloaded")
        self._wait_for_flights_container()

        self._select_option(COUNTRY_SELECTOR, COUNTRY_CODE)

    def select_scope(self, scope: FlightListScope) -> None:
        """Change only rendered category, date and table-order controls."""

        self._select_option(GLIDER_SELECTOR, scope.category.filter_value)
        self._select_option(DATE_SELECTOR, scope.date_filter or "")
        self._ensure_sort(scope.sort_key, scope.sort_direction)

    def available_dates(self, season: int) -> tuple[str, ...]:
        """Read source-offered ISO dates; never invent a calendar or URL filter."""

        options = self._active_page.locator(DATE_SELECTOR).evaluate_all(
            """selects => Array.from(selects[0].options).map(option => option.value)"""
        )
        dates = tuple(value for value in options if value)
        if any(not value.startswith(f"{season}-") for value in dates):
            raise BrowserCollectionError(
                "XCContest date selector exposed a date outside the selected season."
            )
        if len(set(dates)) != len(dates):
            raise BrowserCollectionError("XCContest date selector exposed duplicate date values.")
        return dates

    def read_page(self, season: int, scope: FlightListScope) -> PageObservation:
        """Read control fields and retain only the rendered list fragment."""

        page = self._active_page
        self._wait_for_flights_container()
        fragment_html = page.locator("#flights").evaluate("element => element.outerHTML")
        raw_rows = page.locator(ROW_SELECTOR).evaluate_all(
            """rows => rows.map(row => {
                const distance = row.querySelector('td.km strong')?.textContent?.trim() ?? '';
                const launchLink = row.querySelector('a.lau');
                const launchCell = launchLink?.closest('td');
                const launchCountry = launchCell?.querySelector('.cic')?.textContent?.trim() ?? '';
                return { id: row.id.replace(/^flight-/, ''), distance, launchCountry };
            })"""
        )
        rows = tuple(
            RowObservation(
                source_flight_id=str(row["id"]),
                distance_km=float(str(row["distance"]).replace(",", ".")),
                launch_country_code=str(row["launchCountry"]),
            )
            for row in raw_rows
        )
        next_link = page.locator(".XCpager a[title='next page']")
        next_href = next_link.get_attribute("href") if next_link.count() else None
        return PageObservation(
            season=season,
            scope=scope,
            country_filter=page.locator(COUNTRY_SELECTOR).input_value(),
            glider_category_filter=page.locator(GLIDER_SELECTOR).input_value(),
            date_filter=page.locator(DATE_SELECTOR).input_value(),
            rows=rows,
            fragment_html=fragment_html,
            has_next_page=bool(next_href and next_href != "#"),
        )

    def _season_option_value(self, season: int) -> str:
        options = self._active_page.locator(SEASON_SELECTOR).evaluate_all(
            "selects => Array.from(selects[0].options).map(option => ({ text: option.textContent.trim(), value: option.value }))"
        )
        expected_text = f"World XContest {season}"
        for option in options:
            if str(option["text"]).endswith(expected_text):
                return str(option["value"])
        raise BrowserCollectionError(
            f"XCContest did not offer season {season} in its season selector."
        )

    def _select_option(self, selector: str, value: str) -> None:
        page = self._active_page
        if page.locator(selector).input_value() == value:
            return
        previous_fragment = page.locator("#flights").evaluate("element => element.outerHTML")
        self._pace_source_transition()
        page.locator(selector).select_option(value)
        self._wait_for_selected_value(selector, value, previous_fragment)

    def _ensure_sort(self, sort_key: str, sort_direction: str) -> None:
        page = self._active_page
        selector = SORT_SELECTOR_TEMPLATE.format(sort_key=sort_key)
        sort_link = page.locator(selector)
        expected_class = "down" if sort_direction == "descending" else "up"
        for _ in range(3):
            class_names = sort_link.evaluate("element => Array.from(element.classList)")
            if expected_class in class_names:
                if sort_key == "distance" and sort_direction == "descending":
                    self._assert_distance_descending()
                return
            previous_fragment = page.locator("#flights").evaluate("element => element.outerHTML")
            self._pace_source_transition()
            sort_link.click()
            page.wait_for_function(
                """([selector, className, previousHtml]) => {
                    const link = document.querySelector(selector);
                    const flights = document.querySelector("#flights");
                    return link?.classList.contains(className) && flights?.outerHTML !== previousHtml;
                }""",
                arg=[selector, expected_class, previous_fragment],
            )
            self._wait_for_flights_container()
        raise BrowserCollectionError(
            f"XCContest {sort_key} column did not produce {sort_direction} order."
        )

    def _assert_distance_descending(self) -> None:
        raw_distances = self._active_page.locator(ROW_SELECTOR).evaluate_all(
            "rows => rows.map(row => row.querySelector('td.km strong')?.textContent?.trim() ?? '')"
        )
        distances = tuple(float(str(value).replace(",", ".")) for value in raw_distances)
        if any(left < right for left, right in pairwise(distances)):
            raise BrowserCollectionError(
                "XCContest length column did not produce descending distances."
            )

    def _wait_for_flights_container(self) -> None:
        self._active_page.locator("#flights").wait_for(state="visible")
        self._active_page.wait_for_timeout(250)

    def _wait_for_selected_value(
        self,
        selector: str,
        expected_value: str,
        previous_fragment: str | None = None,
    ) -> None:
        if previous_fragment is None:
            self._active_page.wait_for_function(
                "([selector, expectedValue]) => document.querySelector(selector)?.value === expectedValue",
                arg=[selector, expected_value],
            )
        else:
            self._active_page.wait_for_function(
                """([selector, expectedValue, previousHtml]) => {
                    const flights = document.querySelector("#flights");
                    return document.querySelector(selector)?.value === expectedValue
                        && flights?.outerHTML !== previousHtml;
                }""",
                arg=[selector, expected_value, previous_fragment],
            )
        self._wait_for_flights_container()

    def _pace_source_transition(self) -> None:
        self._sleeper(self._config.delay_seconds)
