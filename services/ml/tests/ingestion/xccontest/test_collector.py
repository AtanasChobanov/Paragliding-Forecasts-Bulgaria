from __future__ import annotations

import json
from collections.abc import Iterable

import pytest

from paragliding_forecasts_ml.ingestion.xccontest.artifacts import RawArtifactStore
from paragliding_forecasts_ml.ingestion.xccontest.collector import (
    CollectionError,
    FlightListCollector,
)
from paragliding_forecasts_ml.ingestion.xccontest.models import (
    CollectorConfig,
    PageObservation,
    RowObservation,
)


def observation(
    page_number: int,
    distances: Iterable[float],
    *,
    has_next_page: bool = False,
    country_filter: str = "BG",
    glider_category_filter: str = "FAI3",
    launch_country_code: str = "BG",
) -> PageObservation:
    rows = tuple(
        RowObservation(
            source_flight_id=f"flight-{page_number}-{index}",
            distance_km=distance,
            launch_country_code=launch_country_code,
        )
        for index, distance in enumerate(distances, start=1)
    )
    return PageObservation(
        season=2025,
        page_number=page_number,
        country_filter=country_filter,
        glider_category_filter=glider_category_filter,
        rows=rows,
        fragment_html=f'<section id="flights" data-page="{page_number}"></section>',
        has_next_page=has_next_page,
    )


class FakeDriver:
    def __init__(self, pages: tuple[PageObservation, ...]) -> None:
        self._pages = iter(pages)
        self.prepared_seasons: list[int] = []
        self.next_page_requests: list[str] = []

    def prepare_scope(self, season: int) -> None:
        self.prepared_seasons.append(season)

    def read_page(self, season: int) -> PageObservation:
        assert season == 2025
        return next(self._pages)

    def next_page(self, previous_first_flight_id: str) -> None:
        self.next_page_requests.append(previous_first_flight_id)


def collect(
    tmp_path: pytest.TempPathFactory,
    pages: tuple[PageObservation, ...],
    *,
    max_pages: int = 10,
) -> tuple[FakeDriver, RawArtifactStore, object]:
    driver = FakeDriver(pages)
    artifacts = RawArtifactStore(project_root=tmp_path, run_key="test-run")
    report = FlightListCollector(
        config=CollectorConfig(seasons=(2025,), max_pages=max_pages),
        driver=driver,
        artifacts=artifacts,
    ).collect()
    return driver, artifacts, report


def test_collects_exactly_100_km_page_then_stops_at_first_shorter_row(tmp_path) -> None:
    driver, artifacts, report = collect(
        tmp_path,
        (
            observation(1, (158.2, 100.0), has_next_page=True),
            observation(2, (99.9, 98.1), has_next_page=True),
        ),
    )

    assert driver.prepared_seasons == [2025]
    assert driver.next_page_requests == ["flight-1-1"]
    assert report.completed_seasons == (2025,)
    assert len(report.artifacts) == 2
    assert (artifacts.raw_dir / "season-2025-page-0001.html").is_file()
    assert (artifacts.raw_dir / "season-2025-page-0002.html").is_file()
    checkpoint = json.loads((artifacts.interim_dir / "checkpoint.json").read_text())
    assert checkpoint["status"] == "threshold_reached"


def test_rejects_non_bulgarian_launch_before_writing_artifact(tmp_path) -> None:
    driver = FakeDriver((observation(1, (120.0,), launch_country_code="RS"),))
    artifacts = RawArtifactStore(project_root=tmp_path, run_key="test-run")
    collector = FlightListCollector(
        config=CollectorConfig(seasons=(2025,)),
        driver=driver,
        artifacts=artifacts,
    )

    with pytest.raises(CollectionError, match="outside BG"):
        collector.collect()

    assert artifacts.entries == ()
    failure_report = json.loads((artifacts.interim_dir / "collection-report.json").read_text())
    assert failure_report["error"].startswith("CollectionError:")


def test_fails_at_page_cap_instead_of_silently_truncating(tmp_path) -> None:
    driver = FakeDriver((observation(1, (151.0,), has_next_page=True),))
    artifacts = RawArtifactStore(project_root=tmp_path, run_key="test-run")
    collector = FlightListCollector(
        config=CollectorConfig(seasons=(2025,), max_pages=1),
        driver=driver,
        artifacts=artifacts,
    )

    with pytest.raises(CollectionError, match="page cap"):
        collector.collect()

    assert len(artifacts.entries) == 1
    assert not (artifacts.raw_dir / "manifest.json").exists()


def test_rejects_empty_table_instead_of_reporting_a_completed_collection(tmp_path) -> None:
    driver = FakeDriver((observation(1, ()),))
    artifacts = RawArtifactStore(project_root=tmp_path, run_key="test-run")
    collector = FlightListCollector(
        config=CollectorConfig(seasons=(2025,)),
        driver=driver,
        artifacts=artifacts,
    )

    with pytest.raises(CollectionError, match="no flight rows"):
        collector.collect()

    assert artifacts.entries == ()
    assert not (artifacts.raw_dir / "manifest.json").exists()
