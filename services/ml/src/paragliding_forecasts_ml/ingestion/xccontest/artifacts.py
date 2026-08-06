"""Ignored raw-artifact and interim-state handling for the collector."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .models import (
    COLLECTOR_VERSION,
    MIN_DISTANCE_KM,
    RAW_MANIFEST_SCHEMA_VERSION,
    SOURCE_CODE,
    SOURCE_LIST_URL,
    ArtifactEntry,
    FlightListScope,
    PageObservation,
    SeasonCollectionStatus,
)


def repository_root() -> Path:
    """Locate the repository from the installed source-tree package layout."""

    return Path(__file__).resolve().parents[6]


def safe_failure_summary(error: Exception) -> str:
    """Keep a compact operational error without persisting source content."""

    message = " ".join(str(error).splitlines()).strip()
    error_type = type(error).__name__
    if not message:
        return error_type
    return f"{error_type}: {message[:300]}"


def scope_metadata(scope: FlightListScope) -> dict[str, str | None]:
    """Serialize a collector scope without embedding source rows in run state."""

    return {
        "category": scope.category.key,
        "category_filter": scope.category.filter_value,
        "date_filter": scope.date_filter,
        "sort_key": scope.sort_key,
        "sort_direction": scope.sort_direction,
    }


class RawArtifactStore:
    """Writes immutable flight-list fragments and mutable local run state."""

    def __init__(
        self,
        *,
        project_root: Path | None = None,
        run_key: str | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._project_root = project_root or repository_root()
        self._clock = clock or (lambda: datetime.now(UTC))
        self.run_key = run_key or str(uuid4())
        self.started_at_utc = self._now()
        self.completed_at_utc: datetime | None = None
        self.raw_dir = self._project_root / "data" / "raw" / "xccontest" / self.run_key
        self.interim_dir = self._project_root / "data" / "interim" / "xccontest" / self.run_key
        self.raw_dir.mkdir(parents=True, exist_ok=False)
        self.interim_dir.mkdir(parents=True, exist_ok=False)
        self._entries: list[ArtifactEntry] = []
        self._row_observations_seen = 0
        self._source_flight_ids: set[str] = set()

    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def entries(self) -> tuple[ArtifactEntry, ...]:
        return tuple(self._entries)

    @property
    def row_observations_seen(self) -> int:
        return self._row_observations_seen

    @property
    def distinct_source_flights_seen(self) -> int:
        return len(self._source_flight_ids)

    @property
    def repeated_source_flight_observations(self) -> int:
        return self._row_observations_seen - self.distinct_source_flights_seen

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("Artifact clock must return a timezone-aware datetime.")
        return value.astimezone(UTC).replace(microsecond=0)

    def write_page(self, page: PageObservation) -> ArtifactEntry:
        """Save the unmodified rendered ``#flights`` fragment exactly once."""

        scope = page.scope
        artifact_path = self.raw_dir / (
            f"season-{page.season}-category-{scope.category.key}-date-{scope.date_key}"
            f"-sort-{scope.sort_key}-{scope.sort_direction}.html"
        )
        if artifact_path.exists():
            raise FileExistsError(f"Refusing to overwrite immutable artifact: {artifact_path}")

        encoded_fragment = page.fragment_html.encode("utf-8")
        with artifact_path.open("xb") as artifact_file:
            artifact_file.write(encoded_fragment)

        entry = ArtifactEntry(
            relative_path=artifact_path.relative_to(self._project_root).as_posix(),
            sha256=hashlib.sha256(encoded_fragment).hexdigest(),
            season=page.season,
            category=scope.category.key,
            date_filter=scope.date_filter,
            sort_key=scope.sort_key,
            sort_direction=scope.sort_direction,
            retrieved_at_utc=self._now(),
            first_flight_id=page.first_flight_id,
            last_flight_id=page.last_flight_id,
            first_distance_km=page.first_distance_km,
            last_distance_km=page.last_distance_km,
            row_observation_count=len(page.rows),
            qualifying_row_observation_count=sum(
                row.distance_km >= MIN_DISTANCE_KM for row in page.rows
            ),
        )
        self._entries.append(entry)
        self._row_observations_seen += len(page.rows)
        self._source_flight_ids.update(row.source_flight_id for row in page.rows)
        return entry

    def write_checkpoint(
        self,
        *,
        season: int,
        status: str,
        scope: FlightListScope,
        unresolved_scopes: tuple[FlightListScope, ...] = (),
    ) -> Path:
        """Record local progress without modifying raw artifacts."""

        checkpoint_path = self.interim_dir / "checkpoint.json"
        checkpoint_path.write_text(
            json.dumps(
                {
                    "run_key": self.run_key,
                    "season": season,
                    "status": status,
                    "scope": scope_metadata(scope),
                    "unresolved_scopes": [scope_metadata(item) for item in unresolved_scopes],
                    "artifacts_written": len(self._entries),
                    "row_observations_seen": self.row_observations_seen,
                    "distinct_source_flights_seen": self.distinct_source_flights_seen,
                    "repeated_source_flight_observations": (
                        self.repeated_source_flight_observations
                    ),
                    "updated_at_utc": self._now().isoformat().replace("+00:00", "Z"),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return checkpoint_path

    def write_failure_report(self, *, error: str) -> Path:
        """Store collector state only; never include page HTML or credentials."""

        report_path = self.interim_dir / "collection-report.json"
        failed_at_utc = self._now()
        report_path.write_text(
            json.dumps(
                {
                    "run_key": self.run_key,
                    "status": "failed",
                    "error": error,
                    "artifacts_written": len(self._entries),
                    "row_observations_seen": self.row_observations_seen,
                    "distinct_source_flights_seen": self.distinct_source_flights_seen,
                    "repeated_source_flight_observations": (
                        self.repeated_source_flight_observations
                    ),
                    "started_at_utc": self.started_at_utc.isoformat().replace("+00:00", "Z"),
                    "failed_at_utc": failed_at_utc.isoformat().replace("+00:00", "Z"),
                    "updated_at_utc": failed_at_utc.isoformat().replace("+00:00", "Z"),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return report_path

    def finalize_manifest(
        self,
        *,
        completed_seasons: tuple[int, ...],
        season_statuses: tuple[SeasonCollectionStatus, ...],
    ) -> Path:
        """Write the run manifest once after every requested season completes."""

        manifest_path = self.raw_dir / "manifest.json"
        if manifest_path.exists():
            raise FileExistsError(f"Refusing to overwrite immutable manifest: {manifest_path}")

        self.completed_at_utc = self._now()
        run_status = (
            "incomplete"
            if any(status.unresolved_scopes for status in season_statuses)
            else "complete"
        )
        manifest = {
            "manifest_schema_version": RAW_MANIFEST_SCHEMA_VERSION,
            "collector_version": COLLECTOR_VERSION,
            "source": SOURCE_CODE,
            "source_url": SOURCE_LIST_URL,
            "run_key": self.run_key,
            "status": run_status,
            "started_at_utc": self.started_at_utc.isoformat().replace("+00:00", "Z"),
            "completed_at_utc": self.completed_at_utc.isoformat().replace("+00:00", "Z"),
            "scope": {
                "country": "BG",
                "primary_glider_category": "FAI3",
                "minimum_scored_distance_km": 100,
                "completed_seasons": list(completed_seasons),
            },
            "season_statuses": [
                {
                    "season": status.season,
                    "status": status.status,
                    "unresolved_scopes": [
                        scope_metadata(scope) for scope in status.unresolved_scopes
                    ],
                }
                for status in season_statuses
            ],
            "observation_counts": {
                "views_written": len(self._entries),
                "row_observations_seen": self.row_observations_seen,
                "distinct_source_flights_seen": self.distinct_source_flights_seen,
                "repeated_source_flight_observations": (self.repeated_source_flight_observations),
            },
            "artifacts": [
                {
                    "path": entry.relative_path,
                    "sha256": entry.sha256,
                    "season": entry.season,
                    "category": entry.category,
                    "date_filter": entry.date_filter,
                    "sort_key": entry.sort_key,
                    "sort_direction": entry.sort_direction,
                    "retrieved_at_utc": entry.retrieved_at_utc.isoformat().replace("+00:00", "Z"),
                    "first_flight_id": entry.first_flight_id,
                    "last_flight_id": entry.last_flight_id,
                    "first_distance_km": entry.first_distance_km,
                    "last_distance_km": entry.last_distance_km,
                    "row_observation_count": entry.row_observation_count,
                    "qualifying_row_observation_count": (entry.qualifying_row_observation_count),
                }
                for entry in self._entries
            ],
        }
        with manifest_path.open("x", encoding="utf-8", newline="\n") as manifest_file:
            json.dump(manifest, manifest_file, ensure_ascii=False, indent=2)
            manifest_file.write("\n")
        return manifest_path
