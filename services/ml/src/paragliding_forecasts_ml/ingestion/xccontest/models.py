"""Value objects used by the XCContest collector boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

COUNTRY_CODE = "BG"
GLIDER_CATEGORY = "FAI3"
MIN_DISTANCE_KM = 100.0
DEFAULT_DELAY_SECONDS = 3.0
DEFAULT_MAX_PAGES = 10


@dataclass(frozen=True)
class CollectorConfig:
    """Explicit, deliberately narrow source scope for one collection run."""

    seasons: tuple[int, ...]
    headed: bool = False
    slow_mo_ms: int = 0
    timeout_seconds: int = 30
    max_pages: int = DEFAULT_MAX_PAGES
    delay_seconds: float = DEFAULT_DELAY_SECONDS

    def __post_init__(self) -> None:
        if not self.seasons:
            raise ValueError("At least one XCContest season is required.")
        if len(set(self.seasons)) != len(self.seasons):
            raise ValueError("Each XCContest season may be requested only once.")
        if any(season < 2000 or season > 2100 for season in self.seasons):
            raise ValueError("XCContest seasons must be four-digit years.")
        if self.slow_mo_ms < 0:
            raise ValueError("slow_mo_ms must be zero or greater.")
        if self.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be at least one.")
        if self.max_pages < 1:
            raise ValueError("max_pages must be at least one.")
        if self.delay_seconds < DEFAULT_DELAY_SECONDS:
            raise ValueError(f"delay_seconds must be at least {DEFAULT_DELAY_SECONDS:g}.")


@dataclass(frozen=True)
class RowObservation:
    """Minimal data needed to control collection, not a parsed flight record."""

    source_flight_id: str
    distance_km: float
    launch_country_code: str

    def __post_init__(self) -> None:
        if not self.source_flight_id:
            raise ValueError("XCContest row must expose a source flight ID.")
        if self.distance_km < 0:
            raise ValueError("XCContest distance cannot be negative.")


@dataclass(frozen=True)
class PageObservation:
    """A rendered list state captured after the browser has settled."""

    season: int
    page_number: int
    country_filter: str
    glider_category_filter: str
    rows: tuple[RowObservation, ...]
    fragment_html: str
    has_next_page: bool

    @property
    def first_flight_id(self) -> str | None:
        return self.rows[0].source_flight_id if self.rows else None

    @property
    def last_flight_id(self) -> str | None:
        return self.rows[-1].source_flight_id if self.rows else None

    @property
    def first_distance_km(self) -> float | None:
        return self.rows[0].distance_km if self.rows else None

    @property
    def last_distance_km(self) -> float | None:
        return self.rows[-1].distance_km if self.rows else None


@dataclass(frozen=True)
class ArtifactEntry:
    """One immutable rendered list fragment recorded in the final manifest."""

    relative_path: str
    sha256: str
    season: int
    page_number: int
    retrieved_at_utc: datetime
    first_flight_id: str | None
    last_flight_id: str | None
    first_distance_km: float | None
    last_distance_km: float | None


@dataclass(frozen=True)
class CollectionReport:
    """Collector-only result; parser and persistence own later pipeline states."""

    run_key: str
    artifact_root: Path
    completed_seasons: tuple[int, ...]
    artifacts: tuple[ArtifactEntry, ...]
    manifest_path: Path
