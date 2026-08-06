"""Collector orchestration for rendered XCContest flight-list artifacts."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from itertools import pairwise
from typing import Protocol

from .artifacts import RawArtifactStore, safe_failure_summary
from .models import (
    COUNTRY_CODE,
    EXACT_GLIDER_CATEGORIES,
    PRIMARY_GLIDER_CATEGORY,
    RESCUE_SORTS,
    CollectionReport,
    CollectorConfig,
    FlightListScope,
    PageObservation,
    SeasonCollectionStatus,
)


class CollectionError(RuntimeError):
    """The collector could not establish a trustworthy source-list boundary."""


class FlightListDriver(Protocol):
    """Small UI-driver contract, deliberately independent of Playwright."""

    def prepare_season(self, season: int) -> None:
        """Select the requested season and Bulgarian launch-country filter."""

    def select_scope(self, scope: FlightListScope) -> None:
        """Select the category, optional date, and requested visible sort."""

    def available_dates(self, season: int) -> tuple[str, ...]:
        """Return selectable dates from the rendered XCContest date control."""

    def read_page(self, season: int, scope: FlightListScope) -> PageObservation:
        """Return the current rendered list state."""


class FlightListCollector:
    """Capture first-page views through progressively narrower visible controls."""

    def __init__(
        self,
        *,
        config: CollectorConfig,
        driver: FlightListDriver,
        artifacts: RawArtifactStore,
    ) -> None:
        self._config = config
        self._driver = driver
        self._artifacts = artifacts
        self._view_count = 0

    def collect(self) -> CollectionReport:
        """Collect requested seasons without using XCContest pagination controls."""

        completed_seasons: list[int] = []
        season_statuses: list[SeasonCollectionStatus] = []
        try:
            for season in self._config.seasons:
                season_statuses.append(self._collect_season(season))
                completed_seasons.append(season)

            manifest_path = self._artifacts.finalize_manifest(
                completed_seasons=tuple(completed_seasons),
                season_statuses=tuple(season_statuses),
            )
            manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            completed_at_utc = self._artifacts.completed_at_utc
            if completed_at_utc is None:
                raise CollectionError("XCContest manifest did not record a completion time.")
            run_status = (
                "incomplete"
                if any(status.unresolved_scopes for status in season_statuses)
                else "complete"
            )
            return CollectionReport(
                run_key=self._artifacts.run_key,
                artifact_root=self._artifacts.raw_dir,
                completed_seasons=tuple(completed_seasons),
                season_statuses=tuple(season_statuses),
                artifacts=self._artifacts.entries,
                manifest_path=manifest_path,
                manifest_relative_path=manifest_path.relative_to(
                    self._artifacts.project_root
                ).as_posix(),
                manifest_sha256=manifest_sha256,
                status=run_status,
                started_at_utc=self._artifacts.started_at_utc,
                completed_at_utc=completed_at_utc,
                row_observations_seen=self._artifacts.row_observations_seen,
                distinct_source_flights_seen=self._artifacts.distinct_source_flights_seen,
                repeated_source_flight_observations=(
                    self._artifacts.repeated_source_flight_observations
                ),
            )
        except Exception as error:
            self._artifacts.write_failure_report(error=safe_failure_summary(error))
            raise

    def _collect_season(self, season: int) -> SeasonCollectionStatus:
        self._driver.prepare_season(season)
        primary_scope = FlightListScope(category=PRIMARY_GLIDER_CATEGORY)
        primary_page = self._capture_scope(season, primary_scope, require_rows=True)
        if not primary_page.is_distance_saturated:
            self._artifacts.write_checkpoint(
                season=season,
                status="complete_primary",
                scope=primary_scope,
            )
            return SeasonCollectionStatus(season, "complete_primary", ())

        dates = self._driver.available_dates(season)
        if not dates:
            raise CollectionError(
                "XCContest did not expose any selectable dates for a saturated season."
            )

        unresolved_scopes: list[FlightListScope] = []
        for category in EXACT_GLIDER_CATEGORIES:
            category_scope = FlightListScope(category=category)
            category_page = self._capture_scope(season, category_scope, require_rows=False)
            if not category_page.is_distance_saturated:
                continue

            for date_filter in dates:
                date_scope = FlightListScope(category=category, date_filter=date_filter)
                date_page = self._capture_scope(season, date_scope, require_rows=False)
                if not date_page.is_distance_saturated:
                    continue

                unresolved_scopes.append(date_scope)
                for rescue_sort in RESCUE_SORTS:
                    self._capture_scope(
                        season,
                        replace(
                            rescue_sort,
                            category=category,
                            date_filter=date_filter,
                        ),
                        require_rows=False,
                    )

        status = "complete_partitioned" if not unresolved_scopes else "saturated_unresolved"
        self._artifacts.write_checkpoint(
            season=season,
            status=status,
            scope=primary_scope,
            unresolved_scopes=tuple(unresolved_scopes),
        )
        return SeasonCollectionStatus(season, status, tuple(unresolved_scopes))

    def _capture_scope(
        self,
        season: int,
        scope: FlightListScope,
        *,
        require_rows: bool,
    ) -> PageObservation:
        if self._view_count >= self._config.max_views:
            raise CollectionError(
                "The configured view cap was reached before XCContest collection completed. "
                "Increase --max-views only after reviewing the source workload."
            )
        self._driver.select_scope(scope)
        page = self._driver.read_page(season, scope)
        self._view_count += 1
        self._validate_page(
            page, expected_season=season, expected_scope=scope, require_rows=require_rows
        )
        if page.rows:
            self._artifacts.write_page(page)
        return page

    @staticmethod
    def _validate_page(
        page: PageObservation,
        *,
        expected_season: int,
        expected_scope: FlightListScope,
        require_rows: bool,
    ) -> None:
        if page.season != expected_season:
            raise CollectionError("XCContest page was read under an unexpected season.")
        if page.scope != expected_scope:
            raise CollectionError("XCContest page was read under an unexpected selected scope.")
        if require_rows and not page.rows:
            raise CollectionError("XCContest rendered no flight rows for the primary PG scope.")
        if page.country_filter != COUNTRY_CODE:
            raise CollectionError("XCContest country control no longer reports the BG filter.")
        if page.glider_category_filter != expected_scope.category.filter_value:
            raise CollectionError(
                "XCContest glider control no longer reports the expected category."
            )
        if page.date_filter != (expected_scope.date_filter or ""):
            raise CollectionError("XCContest date control no longer reports the expected date.")
        if any(row.launch_country_code != COUNTRY_CODE for row in page.rows):
            raise CollectionError("XCContest rendered a flight whose launch country is outside BG.")

        if expected_scope.sort_key == "distance" and expected_scope.sort_direction == "descending":
            distances = tuple(row.distance_km for row in page.rows)
            if any(left < right for left, right in pairwise(distances)):
                raise CollectionError(
                    "XCContest page distances are not sorted in descending order."
                )
