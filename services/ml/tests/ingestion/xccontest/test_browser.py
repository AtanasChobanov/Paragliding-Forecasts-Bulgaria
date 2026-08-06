from __future__ import annotations

from paragliding_forecasts_ml.ingestion.xccontest.browser import PlaywrightFlightListDriver
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
