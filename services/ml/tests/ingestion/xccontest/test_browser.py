from __future__ import annotations

from paragliding_forecasts_ml.ingestion.xccontest.browser import (
    NEXT_PAGE_SELECTOR,
    PlaywrightFlightListDriver,
)
from paragliding_forecasts_ml.ingestion.xccontest.models import CollectorConfig


class FakeFlightsLocator:
    def wait_for(self, *, state: str) -> None:
        assert state == "visible"


class FakeNextLocator:
    def __init__(self) -> None:
        self.clicked = False

    def count(self) -> int:
        return 1

    def get_attribute(self, name: str) -> str:
        assert name == "href"
        return "#flights[start]=100"

    def click(self) -> None:
        self.clicked = True


class FakePage:
    def __init__(self) -> None:
        self.next_locator = FakeNextLocator()
        self.wait_calls: list[tuple[str, object]] = []

    def locator(self, selector: str):
        if selector == "#flights":
            return FakeFlightsLocator()
        assert selector == NEXT_PAGE_SELECTOR
        return self.next_locator

    def wait_for_function(self, expression: str, *, arg: object = None) -> None:
        self.wait_calls.append((expression, arg))

    def wait_for_timeout(self, milliseconds: int) -> None:
        assert milliseconds == 250


def test_passes_wait_for_function_values_by_keyword_argument() -> None:
    page = FakePage()
    driver = PlaywrightFlightListDriver(CollectorConfig(seasons=(2025,)), sleeper=lambda _: None)
    driver._page = page

    driver._wait_for_selected_value('select[name="filter[country]"]', "BG")
    driver.next_page("12345")

    assert page.wait_calls[0][1] == ['select[name="filter[country]"]', "BG"]
    assert page.wait_calls[1][1] == "12345"
    assert page.next_locator.clicked is True
