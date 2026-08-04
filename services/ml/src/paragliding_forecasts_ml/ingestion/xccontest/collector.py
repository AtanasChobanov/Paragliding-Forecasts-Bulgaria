"""Collector orchestration for rendered XCContest flight-list artifacts."""

from __future__ import annotations

from itertools import pairwise
from typing import Protocol

from .artifacts import RawArtifactStore, safe_failure_summary
from .models import (
    COUNTRY_CODE,
    GLIDER_CATEGORY,
    MIN_DISTANCE_KM,
    CollectionReport,
    CollectorConfig,
    PageObservation,
)


class CollectionError(RuntimeError):
    """The collector could not establish a trustworthy source-list boundary."""


class FlightListDriver(Protocol):
    """Small UI-driver contract, deliberately independent of Playwright."""

    def prepare_scope(self, season: int) -> None:
        """Select the requested season and collector-owned UI filters."""

    def read_page(self, season: int) -> PageObservation:
        """Return the current rendered list state."""

    def next_page(self, previous_first_flight_id: str) -> None:
        """Use the source UI to advance beyond the current rendered list."""


class FlightListCollector:
    """Capture full rendered pages while enforcing the narrowly approved scope."""

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

    def collect(self) -> CollectionReport:
        """Collect configured seasons, stopping each one at the first sub-100 km row."""

        completed_seasons: list[int] = []
        try:
            for season in self._config.seasons:
                self._collect_season(season)
                completed_seasons.append(season)

            manifest_path = self._artifacts.finalize_manifest(
                completed_seasons=tuple(completed_seasons)
            )
            return CollectionReport(
                run_key=self._artifacts.run_key,
                artifact_root=self._artifacts.raw_dir,
                completed_seasons=tuple(completed_seasons),
                artifacts=self._artifacts.entries,
                manifest_path=manifest_path,
            )
        except Exception as error:
            self._artifacts.write_failure_report(error=safe_failure_summary(error))
            raise

    def _collect_season(self, season: int) -> None:
        self._driver.prepare_scope(season)
        previous_last_distance: float | None = None

        for collected_page_count in range(1, self._config.max_pages + 1):
            page = self._driver.read_page(season)
            self._validate_page(
                page,
                expected_season=season,
                expected_page_number=collected_page_count,
                previous_last_distance=previous_last_distance,
            )
            self._artifacts.write_page(page)

            if any(row.distance_km < MIN_DISTANCE_KM for row in page.rows):
                self._artifacts.write_checkpoint(
                    season=season,
                    page_number=page.page_number,
                    status="threshold_reached",
                )
                return

            if not page.has_next_page:
                self._artifacts.write_checkpoint(
                    season=season,
                    page_number=page.page_number,
                    status="source_exhausted",
                )
                return

            if collected_page_count == self._config.max_pages:
                raise CollectionError(
                    "The configured page cap was reached while XCContest still reported "
                    f"flights of at least {MIN_DISTANCE_KM:g} km."
                )

            if page.first_flight_id is None:
                raise CollectionError(
                    "XCContest exposed an empty page with a usable next-page control."
                )
            previous_last_distance = page.last_distance_km
            self._driver.next_page(page.first_flight_id)

        raise AssertionError("The collector page loop must return or raise before it is exhausted.")

    @staticmethod
    def _validate_page(
        page: PageObservation,
        *,
        expected_season: int,
        expected_page_number: int,
        previous_last_distance: float | None,
    ) -> None:
        if page.season != expected_season:
            raise CollectionError("XCContest page was read under an unexpected season.")
        if page.page_number != expected_page_number:
            raise CollectionError(
                "XCContest pagination did not advance to the expected page number."
            )
        if not page.rows:
            raise CollectionError(
                "XCContest rendered no flight rows; refusing an empty collection."
            )

        if page.country_filter != COUNTRY_CODE:
            raise CollectionError("XCContest country control no longer reports the BG filter.")
        if page.glider_category_filter != GLIDER_CATEGORY:
            raise CollectionError("XCContest glider control no longer reports the FAI3 PG filter.")
        if any(row.launch_country_code != COUNTRY_CODE for row in page.rows):
            raise CollectionError("XCContest rendered a flight whose launch country is outside BG.")

        distances = tuple(row.distance_km for row in page.rows)
        if any(left < right for left, right in pairwise(distances)):
            raise CollectionError("XCContest page distances are not sorted in descending order.")
        if (
            previous_last_distance is not None
            and page.first_distance_km is not None
            and previous_last_distance < page.first_distance_km
        ):
            raise CollectionError("XCContest pagination broke descending distance order.")
