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
    EXACT_GLIDER_CATEGORIES,
    PRIMARY_GLIDER_CATEGORY,
    RESCUE_SORTS,
    CollectorConfig,
    FlightListScope,
    PageObservation,
    RowObservation,
)


def scope(
    category=PRIMARY_GLIDER_CATEGORY,
    *,
    date_filter: str | None = None,
    sort_key: str = "distance",
    sort_direction: str = "descending",
) -> FlightListScope:
    return FlightListScope(category, date_filter, sort_key, sort_direction)


def observation(
    selected_scope: FlightListScope,
    distances: Iterable[float],
    *,
    has_next_page: bool = False,
    country_code: str = "BG",
    glider_category_filter: str | None = None,
    date_filter: str | None = None,
    launch_country_code: str | None = None,
) -> PageObservation:
    launch_country_code = launch_country_code or country_code
    rows = tuple(
        RowObservation(
            source_flight_id=(
                f"flight-{country_code}-{selected_scope.category.key}-{selected_scope.date_key}"
                f"-{selected_scope.sort_key}-{selected_scope.sort_direction}-{index}"
            ),
            distance_km=distance,
            launch_country_code=launch_country_code,
        )
        for index, distance in enumerate(distances, start=1)
    )
    return PageObservation(
        season=2025,
        scope=selected_scope,
        country_filter=country_code,
        glider_category_filter=glider_category_filter or selected_scope.category.filter_value,
        date_filter=(selected_scope.date_filter or "") if date_filter is None else date_filter,
        rows=rows,
        fragment_html=(
            f'<section id="flights" data-country="{country_code}" '
            f'data-category="{selected_scope.category.key}" '
            f'data-date="{selected_scope.date_key}" data-sort="{selected_scope.sort_key}"></section>'
        ),
        has_next_page=has_next_page,
    )


class FakeDriver:
    def __init__(
        self,
        pages: dict[tuple[str, FlightListScope], PageObservation],
        dates: tuple[str, ...] = (),
    ) -> None:
        self._pages = pages
        self._dates = dates
        self.prepared_seasons: list[int] = []
        self.selected_countries: list[str] = []
        self.selected_scopes: list[tuple[str, FlightListScope]] = []
        self._country_code: str | None = None

    def prepare_season(self, season: int) -> None:
        self.prepared_seasons.append(season)

    def select_country(self, country_code: str) -> None:
        self._country_code = country_code
        self.selected_countries.append(country_code)

    def select_scope(self, selected_scope: FlightListScope) -> None:
        assert self._country_code is not None
        self.selected_scopes.append((self._country_code, selected_scope))

    def available_dates(self, season: int) -> tuple[str, ...]:
        assert season == 2025
        return self._dates

    def read_page(self, season: int, selected_scope: FlightListScope) -> PageObservation:
        assert season == 2025
        assert self._country_code is not None
        return self._pages[(self._country_code, selected_scope)]


def collector(
    tmp_path,
    pages: dict[tuple[str, FlightListScope], PageObservation],
    *,
    dates: tuple[str, ...] = (),
    country_codes: tuple[str, ...] = ("BG",),
    max_views: int = 2_000,
) -> tuple[FakeDriver, RawArtifactStore, FlightListCollector]:
    driver = FakeDriver(pages, dates)
    artifacts = RawArtifactStore(project_root=tmp_path, run_key="test-run")
    instance = FlightListCollector(
        config=CollectorConfig(seasons=(2025,), country_codes=country_codes, max_views=max_views),
        driver=driver,
        artifacts=artifacts,
    )
    return driver, artifacts, instance


def test_completes_from_primary_pg_view_when_it_reaches_the_threshold(tmp_path) -> None:
    primary = scope()
    driver, artifacts, instance = collector(
        tmp_path,
        {("BG", primary): observation(primary, (158.2, 100.0, 99.9), has_next_page=True)},
    )

    report = instance.collect()

    assert driver.prepared_seasons == [2025]
    assert driver.selected_countries == ["BG"]
    assert driver.selected_scopes == [("BG", primary)]
    assert report.target_statuses[0].status == "complete_primary"
    assert report.target_statuses[0].country_code == "BG"
    assert report.target_statuses[0].unresolved_scopes == ()
    assert len(report.artifacts) == 1
    assert report.status == "complete"
    assert report.completed_target_count == 1
    assert report.manifest_relative_path == "data/raw/xccontest/test-run/manifest.json"
    assert len(report.manifest_sha256) == 64
    assert report.started_at_utc <= report.completed_at_utc
    assert report.row_observations_seen == 3
    assert report.distinct_source_flights_seen == 3
    assert report.repeated_source_flight_observations == 0
    checkpoint = json.loads((artifacts.interim_dir / "checkpoint.json").read_text())
    assert checkpoint["country_code"] == "BG"
    assert checkpoint["status"] == "complete_primary"


def test_saturated_primary_partitions_the_exact_solo_pg_categories(tmp_path) -> None:
    primary = scope()
    category_scopes = tuple(scope(category) for category in EXACT_GLIDER_CATEGORIES)
    pages = {
        ("BG", primary): observation(primary, (151.0, 100.0), has_next_page=True),
        ("BG", category_scopes[0]): observation(category_scopes[0], (220.0,)),
        ("BG", category_scopes[1]): observation(category_scopes[1], (160.0,)),
        ("BG", category_scopes[2]): observation(category_scopes[2], (120.0,)),
        ("BG", category_scopes[3]): observation(category_scopes[3], (99.0,)),
        ("BG", category_scopes[4]): observation(category_scopes[4], ()),
    }
    driver, artifacts, instance = collector(tmp_path, pages, dates=("2025-07-01",))

    report = instance.collect()

    assert driver.selected_scopes == [
        ("BG", primary),
        *(("BG", item) for item in category_scopes),
    ]
    assert report.target_statuses[0].status == "complete_partitioned"
    assert len(report.artifacts) == 5
    assert not any("category-en-a" in entry.relative_path for entry in report.artifacts)
    assert (artifacts.raw_dir / "manifest.json").is_file()


def test_saturated_category_date_runs_every_rescue_sort_and_marks_coverage_unresolved(
    tmp_path,
) -> None:
    primary = scope()
    ccc = scope(EXACT_GLIDER_CATEGORIES[0])
    overflowing_date = scope(EXACT_GLIDER_CATEGORIES[0], date_filter="2025-07-01")
    quiet_date = scope(EXACT_GLIDER_CATEGORIES[0], date_filter="2025-07-02")
    rescue_scopes = tuple(
        scope(
            EXACT_GLIDER_CATEGORIES[0],
            date_filter="2025-07-01",
            sort_key=item.sort_key,
            sort_direction=item.sort_direction,
        )
        for item in RESCUE_SORTS
    )
    other_category_scopes = tuple(scope(category) for category in EXACT_GLIDER_CATEGORIES[1:])
    pages = {
        ("BG", primary): observation(primary, (151.0, 100.0), has_next_page=True),
        ("BG", ccc): observation(ccc, (150.0, 100.0), has_next_page=True),
        ("BG", overflowing_date): observation(overflowing_date, (140.0, 100.0), has_next_page=True),
        ("BG", quiet_date): observation(quiet_date, (130.0, 99.0), has_next_page=True),
        **{
            ("BG", rescue_scope): observation(rescue_scope, (125.0, 101.0), has_next_page=True)
            for rescue_scope in rescue_scopes
        },
        **{
            ("BG", category_scope): observation(category_scope, (120.0,))
            for category_scope in other_category_scopes
        },
    }
    driver, artifacts, instance = collector(
        tmp_path,
        pages,
        dates=("2025-07-01", "2025-07-02"),
    )

    report = instance.collect()

    assert driver.selected_scopes == [
        ("BG", primary),
        ("BG", ccc),
        ("BG", overflowing_date),
        *(("BG", item) for item in rescue_scopes),
        ("BG", quiet_date),
        *(("BG", item) for item in other_category_scopes),
    ]
    assert report.target_statuses[0].status == "saturated_unresolved"
    assert report.target_statuses[0].unresolved_scopes == (overflowing_date,)
    assert len(report.artifacts) == len(driver.selected_scopes)
    manifest = json.loads((artifacts.raw_dir / "manifest.json").read_text())
    assert manifest["target_statuses"][0]["unresolved_scopes"] == [
        {
            "category": "ccc",
            "category_filter": "FAI3-41|50",
            "date_filter": "2025-07-01",
            "sort_key": "distance",
            "sort_direction": "descending",
        }
    ]


def test_rejects_launch_outside_the_selected_country_before_writing_artifact(tmp_path) -> None:
    primary = scope()
    _driver, artifacts, instance = collector(
        tmp_path,
        {("BG", primary): observation(primary, (120.0,), launch_country_code="RS")},
    )

    with pytest.raises(CollectionError, match="outside the selected country"):
        instance.collect()

    assert artifacts.entries == ()
    failure_report = json.loads((artifacts.interim_dir / "collection-report.json").read_text())
    assert failure_report["error"].startswith("CollectionError:")


def test_collects_each_country_sequentially_in_one_run(tmp_path) -> None:
    primary = scope()
    driver, artifacts, instance = collector(
        tmp_path,
        {
            ("BG", primary): observation(primary, (120.0,), country_code="BG"),
            ("RS", primary): observation(primary, (130.0,), country_code="RS"),
        },
        country_codes=("BG", "RS"),
    )

    report = instance.collect()

    assert driver.prepared_seasons == [2025]
    assert driver.selected_countries == ["BG", "RS"]
    assert driver.selected_scopes == [("BG", primary), ("RS", primary)]
    assert report.country_codes == ("BG", "RS")
    assert report.completed_target_count == 2
    assert [(item.season, item.country_code) for item in report.target_statuses] == [
        (2025, "BG"),
        (2025, "RS"),
    ]
    assert {entry.country_code for entry in report.artifacts} == {"BG", "RS"}
    assert all("-country-" in entry.relative_path for entry in report.artifacts)
    manifest = json.loads((artifacts.raw_dir / "manifest.json").read_text())
    assert manifest["scope"]["country_codes"] == ["BG", "RS"]
    assert manifest["scope"]["country_scope_source"] == "all_sites"
    assert [item["country_code"] for item in manifest["target_statuses"]] == ["BG", "RS"]


def test_global_view_cap_applies_across_all_country_targets(tmp_path) -> None:
    primary = scope()
    driver, artifacts, instance = collector(
        tmp_path,
        {
            ("BG", primary): observation(primary, (120.0,), country_code="BG"),
            ("RS", primary): observation(primary, (130.0,), country_code="RS"),
        },
        country_codes=("BG", "RS"),
        max_views=1,
    )

    with pytest.raises(CollectionError, match="view cap"):
        instance.collect()

    assert driver.selected_countries == ["BG", "RS"]
    assert driver.selected_scopes == [("BG", primary)]
    assert len(artifacts.entries) == 1
    assert not (artifacts.raw_dir / "manifest.json").exists()


def test_rejects_a_page_when_the_country_control_does_not_match_the_target(tmp_path) -> None:
    primary = scope()
    _driver, artifacts, instance = collector(
        tmp_path,
        {
            ("BG", primary): observation(
                primary,
                (120.0,),
                country_code="RS",
                launch_country_code="BG",
            )
        },
    )

    with pytest.raises(CollectionError, match="expected country filter"):
        instance.collect()

    assert artifacts.entries == ()
