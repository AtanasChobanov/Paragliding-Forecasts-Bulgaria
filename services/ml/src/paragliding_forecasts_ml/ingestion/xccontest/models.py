"""Value objects used by the XCContest collector boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

SOURCE_CODE = "xccontest"
SOURCE_LIST_URL = "https://www.xcontest.org/world/en/flights/"
MIN_DISTANCE_KM = 100.0
DEFAULT_DELAY_SECONDS = 3.0
DEFAULT_MAX_VIEWS = 2_000


@dataclass(frozen=True)
class GliderCategory:
    """One visible XCContest category option that belongs to the solo-PG scope."""

    key: str
    filter_value: str


PRIMARY_GLIDER_CATEGORY = GliderCategory(key="pg", filter_value="FAI3")
EXACT_GLIDER_CATEGORIES = (
    GliderCategory(key="ccc", filter_value="FAI3-41|50"),
    GliderCategory(key="en-d", filter_value="FAI3-40|40"),
    GliderCategory(key="en-c", filter_value="FAI3-30|39"),
    GliderCategory(key="en-b", filter_value="FAI3-20|29"),
    GliderCategory(key="en-a", filter_value="FAI3-10|19"),
)


@dataclass(frozen=True)
class FlightListScope:
    """A single visible-table view selected through XCContest controls."""

    category: GliderCategory
    date_filter: str | None = None
    sort_key: str = "distance"
    sort_direction: str = "descending"

    def __post_init__(self) -> None:
        if self.sort_key not in {"distance", "pilot", "points", "duration"}:
            raise ValueError(f"Unsupported XCContest sort key: {self.sort_key}.")
        if self.sort_direction not in {"ascending", "descending"}:
            raise ValueError("XCContest sort direction must be ascending or descending.")

    @property
    def date_key(self) -> str:
        return self.date_filter or "all"


RESCUE_SORTS = tuple(
    FlightListScope(
        category=PRIMARY_GLIDER_CATEGORY,
        sort_key=sort_key,
        sort_direction=direction,
    )
    for sort_key in ("pilot", "points", "duration")
    for direction in ("descending", "ascending")
)


@dataclass(frozen=True)
class CollectorConfig:
    """Explicit, deliberately narrow source scope for one collection run."""

    seasons: tuple[int, ...]
    country_codes: tuple[str, ...]
    headed: bool = False
    slow_mo_ms: int = 0
    timeout_seconds: int = 30
    max_views: int = DEFAULT_MAX_VIEWS
    delay_seconds: float = DEFAULT_DELAY_SECONDS

    def __post_init__(self) -> None:
        if not self.seasons:
            raise ValueError("At least one XCContest season is required.")
        if len(set(self.seasons)) != len(self.seasons):
            raise ValueError("Each XCContest season may be requested only once.")
        if any(season < 2000 or season > 2100 for season in self.seasons):
            raise ValueError("XCContest seasons must be four-digit years.")
        if not self.country_codes:
            raise ValueError("At least one XCContest country code is required.")
        if len(set(self.country_codes)) != len(self.country_codes):
            raise ValueError("Each XCContest country code may be requested only once.")
        if any(
            len(country_code) != 2
            or any(character < "A" or character > "Z" for character in country_code)
            for country_code in self.country_codes
        ):
            raise ValueError("XCContest country codes must be uppercase ISO2 values.")
        if self.slow_mo_ms < 0:
            raise ValueError("slow_mo_ms must be zero or greater.")
        if self.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be at least one.")
        if self.max_views < 1:
            raise ValueError("max_views must be at least one.")
        if self.delay_seconds < DEFAULT_DELAY_SECONDS:
            raise ValueError(f"delay_seconds must be at least {DEFAULT_DELAY_SECONDS:g}.")


@dataclass(frozen=True)
class RowObservation:
    """Minimal collector-control evidence; the exact HTML is the parser input."""

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
    scope: FlightListScope
    country_filter: str
    glider_category_filter: str
    date_filter: str
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

    @property
    def is_distance_saturated(self) -> bool:
        """True only when distance order proves qualifying rows may be on page two."""

        return bool(
            self.scope.sort_key == "distance"
            and self.scope.sort_direction == "descending"
            and self.has_next_page
            and self.last_distance_km is not None
            and self.last_distance_km >= MIN_DISTANCE_KM
        )


@dataclass(frozen=True)
class ArtifactEntry:
    """One immutable rendered list fragment recorded in the final manifest."""

    relative_path: str
    sha256: str
    season: int
    country_code: str
    category: str
    date_filter: str | None
    sort_key: str
    sort_direction: str
    retrieved_at_utc: datetime
    first_flight_id: str | None
    last_flight_id: str | None
    first_distance_km: float | None
    last_distance_km: float | None
    row_observation_count: int
    qualifying_row_observation_count: int


@dataclass(frozen=True)
class TargetCollectionStatus:
    """Coverage result for one season/country target without parser-level deduplication."""

    season: int
    country_code: str
    status: str
    unresolved_scopes: tuple[FlightListScope, ...]


@dataclass(frozen=True)
class CollectionReport:
    """Compact command result; the immutable manifest owns collector detail."""

    run_key: str
    status: str
    manifest_relative_path: str
    manifest_sha256: str
    country_codes: tuple[str, ...]
    completed_seasons: tuple[int, ...]
    started_at_utc: datetime
    completed_at_utc: datetime
    completed_target_count: int
    unresolved_scope_count: int
    artifact_count: int
    row_observations_seen: int
    distinct_source_flights_seen: int
    repeated_source_flight_observations: int
