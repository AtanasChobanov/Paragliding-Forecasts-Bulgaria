"""Collector orchestration for rendered XCContest flight-list artifacts."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from itertools import pairwise
from typing import Protocol

from .artifacts import RawArtifactStore, safe_failure_summary
from .models import (
    ALL_DISTANCE_ACTIVITY_SORTS,
    EXACT_GLIDER_CATEGORIES,
    PRIMARY_GLIDER_CATEGORY,
    RESCUE_SORTS,
    CollectionReport,
    CollectorConfig,
    FlightListScope,
    PageObservation,
    TargetCollectionStatus,
    is_supported_activity_date,
    source_default_scope,
)


class CollectionError(RuntimeError):
    """The collector could not establish a trustworthy source-list boundary."""


class FlightListDriver(Protocol):
    """Small UI-driver contract, deliberately independent of Playwright."""

    def prepare_season(self, season: int) -> None:
        """Select the requested season."""

    def select_country(self, country_code: str) -> None:
        """Select one requested launch-country filter."""

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
        target_statuses: list[TargetCollectionStatus] = []
        self._artifacts.set_collection_context(self._config)
        self._view_count = self._artifacts.view_count
        try:
            for season in self._config.seasons:
                self._driver.prepare_season(season)
                for country_code in self._config.country_codes:
                    self._driver.select_country(country_code)
                    target_statuses.append(self._collect_target(season, country_code))
                completed_seasons.append(season)

            manifest_path = self._artifacts.finalize_manifest(
                requested_seasons=self._config.seasons,
                country_codes=self._config.country_codes,
                completed_seasons=tuple(completed_seasons),
                target_statuses=tuple(target_statuses),
                delay_seconds=self._config.delay_seconds,
                acknowledge_rate_limit_risk=self._config.acknowledge_rate_limit_risk,
            )
            manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            completed_at_utc = self._artifacts.completed_at_utc
            if completed_at_utc is None:
                raise CollectionError("XCContest manifest did not record a completion time.")
            run_status = (
                "incomplete"
                if any(status.unresolved_scopes for status in target_statuses)
                else "complete"
            )
            return CollectionReport(
                run_key=self._artifacts.run_key,
                status=run_status,
                manifest_relative_path=manifest_path.relative_to(
                    self._artifacts.project_root
                ).as_posix(),
                manifest_sha256=manifest_sha256,
                country_codes=self._config.country_codes,
                completed_seasons=tuple(completed_seasons),
                started_at_utc=self._artifacts.started_at_utc,
                completed_at_utc=completed_at_utc,
                completed_target_count=len(target_statuses),
                unresolved_scope_count=sum(
                    len(status.unresolved_scopes) for status in target_statuses
                ),
                artifact_count=len(self._artifacts.entries),
                row_observations_seen=self._artifacts.row_observations_seen,
                distinct_source_flights_seen=self._artifacts.distinct_source_flights_seen,
                repeated_source_flight_observations=(
                    self._artifacts.repeated_source_flight_observations
                ),
                skipped_activity_date_count=sum(
                    len(status.skipped_activity_dates) for status in target_statuses
                ),
            )
        except Exception as error:
            self._artifacts.write_failure_report(error=safe_failure_summary(error))
            raise

    def _collect_target(self, season: int, country_code: str) -> TargetCollectionStatus:
        """Keep threshold evidence first, then collect date-scoped activity evidence."""

        default_scope = source_default_scope(PRIMARY_GLIDER_CATEGORY)
        self._capture_scope(
            season,
            country_code,
            default_scope,
            require_rows=True,
            acquisition_purpose="threshold_100",
        )
        offered_dates = tuple(sorted(self._driver.available_dates(season)))
        activity_dates = tuple(date for date in offered_dates if is_supported_activity_date(date))
        skipped_activity_dates = tuple(
            date for date in offered_dates if not is_supported_activity_date(date)
        )
        threshold_status, threshold_unresolved = self._collect_threshold_target(
            season, country_code, activity_dates
        )
        activity_unresolved = self._collect_activity_target(season, country_code, activity_dates)
        unresolved_scopes = (*threshold_unresolved, *activity_unresolved)
        status = "saturated_unresolved" if unresolved_scopes else threshold_status
        self._artifacts.write_checkpoint(
            season=season,
            country_code=country_code,
            status=status,
            scope=None,
            unresolved_scopes=unresolved_scopes,
        )
        return TargetCollectionStatus(
            season,
            country_code,
            status,
            unresolved_scopes,
            skipped_activity_dates,
        )

    def _collect_threshold_target(
        self, season: int, country_code: str, activity_dates: tuple[str, ...]
    ) -> tuple[str, tuple[FlightListScope, ...]]:
        """Preserve the existing distance-threshold coverage strategy unchanged."""

        primary_scope = FlightListScope(category=PRIMARY_GLIDER_CATEGORY)
        primary_page = self._capture_scope(season, country_code, primary_scope, require_rows=True)
        if not primary_page.is_distance_saturated:
            return "complete_primary", ()

        unresolved_scopes: list[FlightListScope] = []
        for category in EXACT_GLIDER_CATEGORIES:
            category_scope = FlightListScope(category=category)
            category_page = self._capture_scope(
                season, country_code, category_scope, require_rows=False
            )
            if not category_page.is_distance_saturated:
                continue

            for date_filter in activity_dates:
                date_scope = FlightListScope(category=category, date_filter=date_filter)
                date_page = self._capture_scope(
                    season, country_code, date_scope, require_rows=False
                )
                if not date_page.is_distance_saturated:
                    continue

                unresolved_scopes.append(date_scope)
                for rescue_sort in RESCUE_SORTS:
                    self._capture_scope(
                        season,
                        country_code,
                        replace(
                            rescue_sort,
                            category=category,
                            date_filter=date_filter,
                        ),
                        require_rows=False,
                    )

        status = "complete_partitioned" if not unresolved_scopes else "saturated_unresolved"
        return status, tuple(unresolved_scopes)

    def _collect_activity_target(
        self, season: int, country_code: str, activity_dates: tuple[str, ...]
    ) -> tuple[FlightListScope, ...]:
        """Collect source-offered dates after threshold coverage without adding CLI dates."""

        unresolved_scopes: list[FlightListScope] = []
        for date_filter in activity_dates:
            primary_default_page = self._capture_activity_default(
                season,
                country_code,
                category=PRIMARY_GLIDER_CATEGORY,
                date_filter=date_filter,
            )
            if not primary_default_page.has_next_page:
                continue
            for category in EXACT_GLIDER_CATEGORIES:
                category_default_page = self._capture_activity_default(
                    season,
                    country_code,
                    category=category,
                    date_filter=date_filter,
                )
                if not category_default_page.has_next_page:
                    continue
                category_distance_page = self._capture_activity_sorts(
                    season,
                    country_code,
                    category=category,
                    date_filter=date_filter,
                )
                if category_distance_page.is_all_distance_saturated:
                    unresolved_scopes.append(
                        FlightListScope(category=category, date_filter=date_filter)
                    )
        return tuple(unresolved_scopes)

    def _capture_activity_default(
        self,
        season: int,
        country_code: str,
        *,
        category,
        date_filter: str,
    ) -> PageObservation:
        """Capture one unsorted activity view before deciding whether to partition."""

        return self._capture_scope(
            season,
            country_code,
            source_default_scope(category, date_filter=date_filter),
            require_rows=False,
            write_empty=True,
            acquisition_purpose="all_distance_activity",
        )

    def _capture_activity_sorts(
        self,
        season: int,
        country_code: str,
        *,
        category,
        date_filter: str,
    ) -> PageObservation:
        """Use explicit rescue orders only after a category default view is full."""

        distance_page: PageObservation | None = None
        for sort_scope in ALL_DISTANCE_ACTIVITY_SORTS:
            page = self._capture_scope(
                season,
                country_code,
                replace(sort_scope, category=category, date_filter=date_filter),
                require_rows=False,
                write_empty=True,
                acquisition_purpose="all_distance_activity",
            )
            if page.scope.sort_key == "distance" and page.scope.sort_direction == "descending":
                distance_page = page
        if distance_page is None:
            raise CollectionError(
                "XCContest activity strategy did not collect distance descending."
            )
        return distance_page

    def _capture_scope(
        self,
        season: int,
        country_code: str,
        scope: FlightListScope,
        *,
        require_rows: bool,
        write_empty: bool = True,
        acquisition_purpose: str = "threshold_100",
    ) -> PageObservation:
        recovered = self._artifacts.recovered_page(
            season=season,
            country_code=country_code,
            scope=scope,
            acquisition_purpose=acquisition_purpose,
        )
        if recovered is not None:
            return recovered
        if self._view_count >= self._config.max_views:
            raise CollectionError(
                "The configured view cap was reached before XCContest collection completed. "
                "Increase --max-views only after reviewing the source workload."
            )
        self._driver.select_scope(scope)
        page = self._driver.read_page(season, scope)
        self._view_count += 1
        self._validate_page(
            page,
            expected_season=season,
            expected_country_code=country_code,
            expected_scope=scope,
            require_rows=require_rows,
        )
        if page.rows or write_empty:
            self._artifacts.write_page(page, acquisition_purpose=acquisition_purpose)
            self._artifacts.write_checkpoint(
                season=season,
                country_code=country_code,
                status="in_progress",
                scope=scope,
                acquisition_purpose=acquisition_purpose,
            )
        return page

    @staticmethod
    def _validate_page(
        page: PageObservation,
        *,
        expected_season: int,
        expected_country_code: str,
        expected_scope: FlightListScope,
        require_rows: bool,
    ) -> None:
        if page.season != expected_season:
            raise CollectionError("XCContest page was read under an unexpected season.")
        if page.scope != expected_scope:
            raise CollectionError("XCContest page was read under an unexpected selected scope.")
        if require_rows and not page.rows:
            raise CollectionError("XCContest rendered no flight rows for the primary PG scope.")
        if page.country_filter != expected_country_code:
            raise CollectionError(
                "XCContest country control no longer reports the expected country filter."
            )
        if page.glider_category_filter != expected_scope.category.filter_value:
            raise CollectionError(
                "XCContest glider control no longer reports the expected category."
            )
        if page.date_filter != (expected_scope.date_filter or ""):
            raise CollectionError("XCContest date control no longer reports the expected date.")
        if any(row.launch_country_code != expected_country_code for row in page.rows):
            raise CollectionError(
                "XCContest rendered a flight whose launch country is outside the selected country."
            )

        if expected_scope.sort_key == "distance" and expected_scope.sort_direction == "descending":
            distances = tuple(row.distance_km for row in page.rows)
            if any(left < right for left, right in pairwise(distances)):
                raise CollectionError(
                    "XCContest page distances are not sorted in descending order."
                )
