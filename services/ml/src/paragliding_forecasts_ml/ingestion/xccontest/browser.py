"""The authorized, visible-UI XCContest browser adapter."""

from __future__ import annotations

from collections.abc import Callable
from itertools import pairwise
from typing import Self

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError,
    sync_playwright,
)

from .models import COUNTRY_CODE, GLIDER_CATEGORY, CollectorConfig, PageObservation, RowObservation

ROOT_URL = "https://www.xcontest.org/world/en/flights/"
SEASON_SELECTOR = "div.under-bar select"
COUNTRY_SELECTOR = 'select[name="filter[country]"]'
GLIDER_SELECTOR = 'select[name="filter[detail_glider_catg]"]'
DISTANCE_SORT_SELECTOR = 'a[href*="flights[sort]=distance"]'
ROW_SELECTOR = "#flights table.XClist tbody tr[id^='flight-']"
NEXT_PAGE_SELECTOR = ".XCpager a[title='next page']"


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

    def prepare_scope(self, season: int) -> None:
        """Select season, Bulgarian launch country, PG, and descending length."""

        page = self._active_page
        page.goto(ROOT_URL, wait_until="domcontentloaded")
        self._wait_for_flights_container()

        season_option = self._season_option_value(season)
        page.locator(SEASON_SELECTOR).select_option(season_option)
        page.wait_for_load_state("domcontentloaded")
        self._wait_for_flights_container()

        self._pace_source_transition()
        page.locator(COUNTRY_SELECTOR).select_option(COUNTRY_CODE)
        self._wait_for_selected_value(COUNTRY_SELECTOR, COUNTRY_CODE)

        self._pace_source_transition()
        page.locator(GLIDER_SELECTOR).select_option(GLIDER_CATEGORY)
        self._wait_for_selected_value(GLIDER_SELECTOR, GLIDER_CATEGORY)

        self._sort_distance_descending()

    def read_page(self, season: int) -> PageObservation:
        """Read collector control fields and retain only the rendered list fragment."""

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
        page_marker = page.locator("#flights .XCpager > strong")
        page_number = int(page_marker.text_content() or "1") if page_marker.count() else 1
        next_link = page.locator(NEXT_PAGE_SELECTOR)
        next_href = next_link.get_attribute("href") if next_link.count() else None
        return PageObservation(
            season=season,
            page_number=page_number,
            country_filter=page.locator(COUNTRY_SELECTOR).input_value(),
            glider_category_filter=page.locator(GLIDER_SELECTOR).input_value(),
            rows=rows,
            fragment_html=fragment_html,
            has_next_page=bool(next_href and next_href != "#"),
        )

    def next_page(self, previous_first_flight_id: str) -> None:
        """Follow the source-provided next control and prove that the table advanced."""

        page = self._active_page
        next_link = page.locator(NEXT_PAGE_SELECTOR)
        if not next_link.count() or next_link.get_attribute("href") in {None, "#"}:
            raise BrowserCollectionError("XCContest did not expose a usable next-page control.")
        self._pace_source_transition()
        next_link.click()
        try:
            page.wait_for_function(
                """previousId => {
                    const first = document.querySelector("#flights table.XClist tbody tr[id^='flight-']");
                    return first !== null && first.id.replace(/^flight-/, '') !== previousId;
                }""",
                previous_first_flight_id,
            )
        except TimeoutError as error:
            raise BrowserCollectionError(
                "XCContest next-page action did not change the first flight row."
            ) from error

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

    def _sort_distance_descending(self) -> None:
        page = self._active_page
        for _ in range(2):
            self._pace_source_transition()
            page.locator(DISTANCE_SORT_SELECTOR).click()
            page.wait_for_timeout(500)
            observation = self.read_page_for_sort_check()
            if self._is_non_increasing(observation):
                return
        raise BrowserCollectionError(
            "XCContest length column did not produce descending distances."
        )

    def read_page_for_sort_check(self) -> tuple[float, ...]:
        raw_distances = self._active_page.locator(ROW_SELECTOR).evaluate_all(
            "rows => rows.map(row => row.querySelector('td.km strong')?.textContent?.trim() ?? '')"
        )
        return tuple(float(str(value).replace(",", ".")) for value in raw_distances)

    @staticmethod
    def _is_non_increasing(distances: tuple[float, ...]) -> bool:
        return all(left >= right for left, right in pairwise(distances))

    def _wait_for_flights_container(self) -> None:
        self._active_page.locator("#flights").wait_for(state="visible")
        self._active_page.wait_for_timeout(250)

    def _wait_for_selected_value(self, selector: str, expected_value: str) -> None:
        self._active_page.wait_for_function(
            "([selector, expectedValue]) => document.querySelector(selector)?.value === expectedValue",
            [selector, expected_value],
        )
        self._wait_for_flights_container()

    def _pace_source_transition(self) -> None:
        self._sleeper(self._config.delay_seconds)
