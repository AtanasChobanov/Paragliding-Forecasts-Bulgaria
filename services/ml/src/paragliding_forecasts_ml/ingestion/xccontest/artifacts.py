"""Ignored raw-artifact and resumable interim-state handling for the collector."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .models import (
    ACTIVITY_DATE_END_MONTH_DAY,
    ACTIVITY_DATE_POLICY,
    ACTIVITY_DATE_START_MONTH_DAY,
    SOURCE_CODE,
    SOURCE_LIST_URL,
    THRESHOLD_COVERAGE_DISTANCE_KM,
    ArtifactEntry,
    CollectorConfig,
    FlightListScope,
    PageObservation,
    RowObservation,
    TargetCollectionStatus,
)
from .versions import COLLECTOR_VERSION, RAW_MANIFEST_SCHEMA_VERSION

CHECKPOINT_SCHEMA_VERSION = 2
_ACQUISITION_PURPOSES = frozenset({"threshold_100", "all_distance_activity"})


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
        "sort_mode": scope.sort_mode,
        "sort_key": scope.sort_key,
        "sort_direction": scope.sort_direction,
    }


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _entry_json(entry: ArtifactEntry) -> dict[str, object]:
    return {
        **asdict(entry),
        "retrieved_at_utc": _timestamp(entry.retrieved_at_utc),
        "source_flight_ids": list(entry.source_flight_ids),
    }


def _entry_from_json(value: object) -> ArtifactEntry:
    if not isinstance(value, dict):
        raise TypeError("XCContest checkpoint contains an invalid artifact entry.")
    try:
        retrieved_at = datetime.fromisoformat(str(value["retrieved_at_utc"]))
        source_flight_ids = value["source_flight_ids"]
        if not isinstance(source_flight_ids, list) or not all(
            isinstance(item, str) and item for item in source_flight_ids
        ):
            raise ValueError("XCContest checkpoint artifact source-flight IDs are invalid.")
        entry = ArtifactEntry(
            relative_path=str(value["relative_path"]),
            sha256=str(value["sha256"]),
            season=int(value["season"]),
            country_code=str(value["country_code"]),
            category=str(value["category"]),
            date_filter=value.get("date_filter"),
            acquisition_purpose=str(value["acquisition_purpose"]),
            sort_mode=str(value["sort_mode"]),
            sort_key=value.get("sort_key"),
            sort_direction=value.get("sort_direction"),
            retrieved_at_utc=retrieved_at,
            first_flight_id=value.get("first_flight_id"),
            last_flight_id=value.get("last_flight_id"),
            first_distance_km=value.get("first_distance_km"),
            last_distance_km=value.get("last_distance_km"),
            has_next_page=bool(value["has_next_page"]),
            source_flight_ids=tuple(source_flight_ids),
            row_observation_count=int(value["row_observation_count"]),
            qualifying_row_observation_count=int(value["qualifying_row_observation_count"]),
            below_threshold_row_observation_count=int(
                value["below_threshold_row_observation_count"]
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("XCContest checkpoint artifact entry is malformed.") from error
    if entry.acquisition_purpose not in _ACQUISITION_PURPOSES:
        raise ValueError("XCContest checkpoint artifact has an unsupported acquisition purpose.")
    if entry.sort_mode == "source_default":
        if entry.sort_key is not None or entry.sort_direction is not None:
            raise ValueError("XCContest checkpoint source-default artifact has a sort.")
    elif entry.sort_mode != "explicit" or entry.sort_key is None or entry.sort_direction is None:
        raise ValueError("XCContest checkpoint explicit artifact sort is invalid.")
    if entry.row_observation_count != len(entry.source_flight_ids):
        raise ValueError("XCContest checkpoint artifact row and ID counts disagree.")
    if not 0 <= entry.qualifying_row_observation_count <= entry.row_observation_count:
        raise ValueError("XCContest checkpoint artifact threshold count is invalid.")
    if (
        entry.below_threshold_row_observation_count + entry.qualifying_row_observation_count
        != entry.row_observation_count
    ):
        raise ValueError("XCContest checkpoint artifact distance counts disagree.")
    return entry


class RawArtifactStore:
    """Writes immutable list fragments and verifiable state for interrupted collection."""

    def __init__(
        self,
        *,
        project_root: Path | None = None,
        run_key: str | None = None,
        clock: Callable[[], datetime] | None = None,
        resume: bool = False,
    ) -> None:
        self._project_root = project_root or repository_root()
        self._clock = clock or (lambda: datetime.now(UTC))
        self.run_key = run_key or str(uuid4())
        self.raw_dir = self._project_root / "data" / "raw" / "xccontest" / self.run_key
        self.interim_dir = self._project_root / "data" / "interim" / "xccontest" / self.run_key
        self.completed_at_utc: datetime | None = None
        self._collection_context: dict[str, object] | None = None
        if resume:
            self._restore_checkpoint()
        else:
            self.started_at_utc = self._now()
            self.raw_dir.mkdir(parents=True, exist_ok=False)
            self.interim_dir.mkdir(parents=True, exist_ok=False)
            self._entries: list[ArtifactEntry] = []
            self._source_flight_ids: set[str] = set()

    @classmethod
    def resume(cls, run_key: str, *, project_root: Path | None = None) -> RawArtifactStore:
        """Open an interrupted run only after every completed artifact re-verifies."""

        return cls(project_root=project_root, run_key=run_key, resume=True)

    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def entries(self) -> tuple[ArtifactEntry, ...]:
        return tuple(self._entries)

    @property
    def row_observations_seen(self) -> int:
        return sum(entry.row_observation_count for entry in self._entries)

    @property
    def distinct_source_flights_seen(self) -> int:
        return len(self._source_flight_ids)

    @property
    def repeated_source_flight_observations(self) -> int:
        return self.row_observations_seen - self.distinct_source_flights_seen

    @property
    def view_count(self) -> int:
        return len(self._entries)

    @property
    def collection_context(self) -> dict[str, object]:
        if self._collection_context is None:
            raise TypeError("XCContest checkpoint has no collector configuration.")
        return self._collection_context.copy()

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("Artifact clock must return a timezone-aware datetime.")
        return value.astimezone(UTC).replace(microsecond=0)

    def set_collection_context(self, config: CollectorConfig) -> None:
        """Persist only the public season scope and pacing required for safe resume."""

        context = {
            "seasons": list(config.seasons),
            "country_codes": list(config.country_codes),
            "max_views": config.max_views,
            "delay_seconds": config.delay_seconds,
            "acknowledge_rate_limit_risk": config.acknowledge_rate_limit_risk,
            "timeout_seconds": config.timeout_seconds,
            "slow_mo_ms": config.slow_mo_ms,
            "headed": config.headed,
        }
        if self._collection_context is not None and context != self._collection_context:
            raise ValueError(
                "XCContest resumed collector configuration differs from its checkpoint."
            )
        self._collection_context = context

    def write_page(
        self, page: PageObservation, *, acquisition_purpose: str = "threshold_100"
    ) -> ArtifactEntry:
        """Save one exact rendered fragment and its completeness-relevant observations."""

        if acquisition_purpose not in _ACQUISITION_PURPOSES:
            raise ValueError("XCContest artifact has an unsupported acquisition purpose.")
        scope = page.scope
        artifact_path = self.raw_dir / (
            f"season-{page.season}-country-{page.country_filter}-purpose-"
            f"{acquisition_purpose.replace('_', '-')}"
            f"-category-{scope.category.key}-date-{scope.date_key}"
            f"-sort-{scope.artifact_sort_token}.html"
        )
        if artifact_path.exists():
            raise FileExistsError(f"Refusing to overwrite immutable artifact: {artifact_path}")

        encoded_fragment = page.fragment_html.encode("utf-8")
        with artifact_path.open("xb") as artifact_file:
            artifact_file.write(encoded_fragment)

        source_flight_ids = tuple(row.source_flight_id for row in page.rows)
        qualifying_count = sum(
            row.distance_km >= THRESHOLD_COVERAGE_DISTANCE_KM for row in page.rows
        )
        entry = ArtifactEntry(
            relative_path=artifact_path.relative_to(self._project_root).as_posix(),
            sha256=hashlib.sha256(encoded_fragment).hexdigest(),
            season=page.season,
            country_code=page.country_filter,
            category=scope.category.key,
            date_filter=scope.date_filter,
            acquisition_purpose=acquisition_purpose,
            sort_mode=scope.sort_mode,
            sort_key=scope.sort_key,
            sort_direction=scope.sort_direction,
            retrieved_at_utc=self._now(),
            first_flight_id=page.first_flight_id,
            last_flight_id=page.last_flight_id,
            first_distance_km=page.first_distance_km,
            last_distance_km=page.last_distance_km,
            has_next_page=page.has_next_page,
            source_flight_ids=source_flight_ids,
            row_observation_count=len(page.rows),
            qualifying_row_observation_count=qualifying_count,
            below_threshold_row_observation_count=len(page.rows) - qualifying_count,
        )
        self._entries.append(entry)
        self._source_flight_ids.update(source_flight_ids)
        return entry

    def recovered_page(
        self,
        *,
        season: int,
        country_code: str,
        scope: FlightListScope,
        acquisition_purpose: str,
    ) -> PageObservation | None:
        """Return prior verified control evidence so a resume never refetches its view."""

        for entry in self._entries:
            if (
                entry.season == season
                and entry.country_code == country_code
                and entry.category == scope.category.key
                and entry.date_filter == scope.date_filter
                and entry.acquisition_purpose == acquisition_purpose
                and entry.sort_mode == scope.sort_mode
                and entry.sort_key == scope.sort_key
                and entry.sort_direction == scope.sort_direction
            ):
                rows: tuple[RowObservation, ...]
                if not entry.source_flight_ids:
                    rows = ()
                else:
                    distances = [entry.first_distance_km]
                    if len(entry.source_flight_ids) > 1:
                        distances.append(entry.last_distance_km)
                    rows = tuple(
                        RowObservation(
                            source_flight_id=source_id,
                            distance_km=float(distance if distance is not None else 0),
                            launch_country_code=country_code,
                        )
                        for source_id, distance in zip(
                            (entry.source_flight_ids[0], entry.source_flight_ids[-1]),
                            distances,
                            strict=False,
                        )
                    )
                return PageObservation(
                    season=season,
                    scope=scope,
                    country_filter=country_code,
                    glider_category_filter=scope.category.filter_value,
                    date_filter=scope.date_filter or "",
                    rows=rows,
                    fragment_html="",
                    has_next_page=entry.has_next_page,
                )
        return None

    def write_checkpoint(
        self,
        *,
        season: int,
        country_code: str,
        status: str,
        scope: FlightListScope | None = None,
        acquisition_purpose: str | None = None,
        unresolved_scopes: tuple[FlightListScope, ...] = (),
    ) -> Path:
        """Record every verified scope and hash before the next source transition."""

        if self._collection_context is None:
            raise ValueError("XCContest checkpoint requires a collector configuration.")
        last = self._entries[-1] if self._entries else None
        if last is None and scope is None:
            raise ValueError("XCContest checkpoint has no completed scope.")
        last_scope = (
            scope_metadata(scope)
            if scope is not None
            else {
                "category": last.category,
                "category_filter": None,
                "date_filter": last.date_filter,
                "sort_mode": last.sort_mode,
                "sort_key": last.sort_key,
                "sort_direction": last.sort_direction,
            }
        )
        checkpoint_path = self.interim_dir / "checkpoint.json"
        checkpoint_path.write_text(
            json.dumps(
                {
                    "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
                    "run_key": self.run_key,
                    "collector_version": COLLECTOR_VERSION,
                    "started_at_utc": _timestamp(self.started_at_utc),
                    "collector_config": self._collection_context,
                    "season": season,
                    "country_code": country_code,
                    "status": status,
                    "last_completed_scope": {
                        **last_scope,
                        "acquisition_purpose": acquisition_purpose
                        or (last.acquisition_purpose if last is not None else None),
                    },
                    "unresolved_scopes": [scope_metadata(item) for item in unresolved_scopes],
                    "completed_artifacts": [_entry_json(entry) for entry in self._entries],
                    "artifacts_written": len(self._entries),
                    "row_observations_seen": self.row_observations_seen,
                    "distinct_source_flights_seen": self.distinct_source_flights_seen,
                    "repeated_source_flight_observations": self.repeated_source_flight_observations,
                    "updated_at_utc": _timestamp(self._now()),
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
                    "repeated_source_flight_observations": self.repeated_source_flight_observations,
                    "started_at_utc": _timestamp(self.started_at_utc),
                    "failed_at_utc": _timestamp(failed_at_utc),
                    "updated_at_utc": _timestamp(failed_at_utc),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return report_path

    def _activity_scope_statuses(self) -> list[dict[str, object]]:
        grouped: dict[tuple[int, str, str, str | None], list[ArtifactEntry]] = {}
        for entry in self._entries:
            if entry.acquisition_purpose != "all_distance_activity":
                continue
            grouped.setdefault(
                (entry.season, entry.country_code, entry.category, entry.date_filter), []
            ).append(entry)
        statuses: list[dict[str, object]] = []
        for (season, country, category, date_filter), entries in sorted(grouped.items()):
            ids = [source_id for entry in entries for source_id in entry.source_flight_ids]
            distance_descending = next(
                (
                    entry
                    for entry in entries
                    if entry.sort_mode == "explicit"
                    and entry.sort_key == "distance"
                    and entry.sort_direction == "descending"
                ),
                None,
            )
            if not ids:
                state, reason = "empty", None
            elif distance_descending is not None and distance_descending.has_next_page:
                state, reason = "partial_saturated", "distance_descending_has_next_page"
            else:
                state, reason = "complete", None
            statuses.append(
                {
                    "season": season,
                    "country_code": country,
                    "category": category,
                    "date_filter": date_filter,
                    "source_default_captured": any(
                        entry.sort_mode == "source_default" for entry in entries
                    ),
                    "explicit_sorts": [
                        entry.sort_key + ":" + entry.sort_direction
                        for entry in entries
                        if entry.sort_mode == "explicit"
                        and entry.sort_key is not None
                        and entry.sort_direction is not None
                    ],
                    "distance_descending_has_next_page": (
                        distance_descending.has_next_page
                        if distance_descending is not None
                        else None
                    ),
                    "row_observations_seen": sum(entry.row_observation_count for entry in entries),
                    "distinct_source_flights_seen": len(set(ids)),
                    "duplicate_observations": len(ids) - len(set(ids)),
                    "status": state,
                    "reason": reason,
                }
            )
        return statuses

    def finalize_manifest(
        self,
        *,
        requested_seasons: tuple[int, ...],
        country_codes: tuple[str, ...],
        completed_seasons: tuple[int, ...],
        target_statuses: tuple[TargetCollectionStatus, ...],
        delay_seconds: float,
        acknowledge_rate_limit_risk: bool,
    ) -> Path:
        """Write immutable manifest v4 after every requested season completes."""

        manifest_path = self.raw_dir / "manifest.json"
        if manifest_path.exists():
            raise FileExistsError(f"Refusing to overwrite immutable manifest: {manifest_path}")

        self.completed_at_utc = self._now()
        run_status = (
            "incomplete"
            if any(status.unresolved_scopes for status in target_statuses)
            else "complete"
        )
        activity_scope_statuses = self._activity_scope_statuses()
        manifest = {
            "manifest_schema_version": RAW_MANIFEST_SCHEMA_VERSION,
            "collector_version": COLLECTOR_VERSION,
            "source": SOURCE_CODE,
            "source_url": SOURCE_LIST_URL,
            "run_key": self.run_key,
            "status": run_status,
            "started_at_utc": _timestamp(self.started_at_utc),
            "completed_at_utc": _timestamp(self.completed_at_utc),
            "source_pacing": {
                "delay_seconds": delay_seconds,
                "recommended_delay_seconds": 30,
                "below_recommended_delay_acknowledged": acknowledge_rate_limit_risk,
            },
            "scope": {
                "country_codes": list(country_codes),
                "country_scope_source": "all_sites",
                "requested_seasons": list(requested_seasons),
                "primary_glider_category": "FAI3",
                "minimum_observed_scored_distance_km": 0,
                "threshold_coverage_distance_km": THRESHOLD_COVERAGE_DISTANCE_KM,
                "activity_date_policy": {
                    "name": ACTIVITY_DATE_POLICY,
                    "included_from_month_day": ACTIVITY_DATE_START_MONTH_DAY,
                    "included_through_month_day": ACTIVITY_DATE_END_MONTH_DAY,
                },
                "completed_seasons": list(completed_seasons),
            },
            "target_statuses": [
                {
                    "season": status.season,
                    "country_code": status.country_code,
                    "status": status.status,
                    "unresolved_scopes": [
                        scope_metadata(scope) for scope in status.unresolved_scopes
                    ],
                    "skipped_activity_dates": list(status.skipped_activity_dates),
                }
                for status in target_statuses
            ],
            "activity_scope_statuses": activity_scope_statuses,
            "observation_counts": {
                "views_written": len(self._entries),
                "row_observations_seen": self.row_observations_seen,
                "distinct_source_flights_seen": self.distinct_source_flights_seen,
                "repeated_source_flight_observations": self.repeated_source_flight_observations,
                "below_100km_row_observations": sum(
                    entry.below_threshold_row_observation_count for entry in self._entries
                ),
                "at_or_above_100km_row_observations": sum(
                    entry.qualifying_row_observation_count for entry in self._entries
                ),
            },
            "artifacts": [
                {
                    "path": entry.relative_path,
                    "sha256": entry.sha256,
                    "season": entry.season,
                    "country_code": entry.country_code,
                    "acquisition_purpose": entry.acquisition_purpose,
                    "category": entry.category,
                    "date_filter": entry.date_filter,
                    "sort_mode": entry.sort_mode,
                    "sort_key": entry.sort_key,
                    "sort_direction": entry.sort_direction,
                    "retrieved_at_utc": _timestamp(entry.retrieved_at_utc),
                    "first_flight_id": entry.first_flight_id,
                    "last_flight_id": entry.last_flight_id,
                    "first_distance_km": entry.first_distance_km,
                    "last_distance_km": entry.last_distance_km,
                    "has_next_page": entry.has_next_page,
                    "source_flight_ids": list(entry.source_flight_ids),
                    "row_observation_count": entry.row_observation_count,
                    "below_100km_row_observation_count": entry.below_threshold_row_observation_count,
                    "at_or_above_100km_row_observation_count": entry.qualifying_row_observation_count,
                }
                for entry in self._entries
            ],
        }
        with manifest_path.open("x", encoding="utf-8", newline="\n") as manifest_file:
            json.dump(manifest, manifest_file, ensure_ascii=False, indent=2)
            manifest_file.write("\n")
        return manifest_path

    def _restore_checkpoint(self) -> None:
        checkpoint_path = self.interim_dir / "checkpoint.json"
        try:
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as error:
            raise ValueError("XCContest resume requires a valid checkpoint.json.") from error
        if (
            not isinstance(checkpoint, dict)
            or checkpoint.get("checkpoint_schema_version") != CHECKPOINT_SCHEMA_VERSION
            or checkpoint.get("run_key") != self.run_key
            or checkpoint.get("collector_version") != COLLECTOR_VERSION
        ):
            raise ValueError("XCContest checkpoint is not compatible with the active collector.")
        context = checkpoint.get("collector_config")
        if not isinstance(context, dict):
            raise TypeError("XCContest checkpoint has no collector configuration.")
        try:
            started_at = datetime.fromisoformat(str(checkpoint["started_at_utc"]))
            entries = [_entry_from_json(value) for value in checkpoint["completed_artifacts"]]
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("XCContest checkpoint is malformed.") from error
        if (
            not self.raw_dir.is_dir()
            or not self.interim_dir.is_dir()
            or (self.raw_dir / "manifest.json").exists()
        ):
            raise ValueError("XCContest checkpoint cannot resume a missing or finalized raw run.")
        for entry in entries:
            artifact_path = self._project_root / entry.relative_path
            if (
                not artifact_path.is_file()
                or hashlib.sha256(artifact_path.read_bytes()).hexdigest() != entry.sha256
            ):
                raise ValueError("XCContest checkpoint artifact verification failed.")
        self.started_at_utc = started_at.astimezone(UTC).replace(microsecond=0)
        self._collection_context = context
        self._entries = entries
        self._source_flight_ids = {
            source_flight_id for entry in entries for source_flight_id in entry.source_flight_ids
        }
