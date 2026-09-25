"""Versioned XCContest raw-manifest validation for offline parsing."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import MIN_DISTANCE_KM, SOURCE_CODE, SOURCE_LIST_URL
from .selectors import DISTANCE_SELECTOR
from .versions import RAW_MANIFEST_SCHEMA_VERSION

COUNTRY_CODE_PATTERN = re.compile(r"^[A-Z]{2}$")
FLIGHT_ROW_ID_PATTERN = re.compile(r"^flight-([0-9]+)$")
SUPPORTED_MANIFEST_SCHEMA_VERSIONS = (1, 2, 3, RAW_MANIFEST_SCHEMA_VERSION)


class ManifestValidationError(ValueError):
    """A raw manifest or one of its immutable artifacts is inconsistent."""


@dataclass(frozen=True)
class ManifestContract:
    """Validated compatibility metadata used while parsing artifact rows."""

    schema_version: int
    collector_version: str | None
    status: str | None
    country_codes: tuple[str, ...]
    seasons: tuple[int, ...]
    expected_observation_counts: dict[str, int] | None

    def verify_artifact_rows(self, artifact: dict[str, Any], rows: list[Any]) -> tuple[str, ...]:
        """Verify v2 per-artifact counters against the exact saved DOM."""

        source_flight_ids: list[str] = []
        qualifying_rows = 0
        for row in rows:
            match = FLIGHT_ROW_ID_PATTERN.fullmatch(row.attributes.get("id", ""))
            if match is None:
                raise ManifestValidationError("Raw artifact contains a non-numeric flight row id.")
            source_flight_ids.append(match.group(1))
            distance_node = row.css_first(DISTANCE_SELECTOR)
            if distance_node is None:
                raise ManifestValidationError("Raw artifact row is missing its scored distance.")
            try:
                distance = float(" ".join(distance_node.text().split()).replace(",", "."))
            except ValueError as error:
                raise ManifestValidationError(
                    "Raw artifact row has a non-numeric scored distance."
                ) from error
            qualifying_rows += distance >= MIN_DISTANCE_KM

        if self.schema_version >= 2:
            if len(rows) != artifact["row_observation_count"]:
                raise ManifestValidationError(
                    f"Manifest v2 row count does not match artifact: {artifact['path']}"
                )
            expected_qualifying = (
                artifact["at_or_above_100km_row_observation_count"]
                if self.schema_version >= 4
                else artifact["qualifying_row_observation_count"]
            )
            if qualifying_rows != expected_qualifying:
                raise ManifestValidationError(
                    f"Manifest v2 qualifying count does not match artifact: {artifact['path']}"
                )
            if self.schema_version >= 4:
                if source_flight_ids != artifact["source_flight_ids"]:
                    raise ManifestValidationError(
                        f"Manifest v4 source IDs do not match artifact: {artifact['path']}"
                    )
                if len(rows) - qualifying_rows != artifact["below_100km_row_observation_count"]:
                    raise ManifestValidationError(
                        f"Manifest v4 below-threshold count does not match artifact: {artifact['path']}"
                    )
        return tuple(source_flight_ids)

    def verify_run_rows(self, source_flight_ids: list[str]) -> None:
        """Verify v2 run-wide observation, distinct-ID, and repeat counters."""

        if self.expected_observation_counts is None:
            return
        counts = self.expected_observation_counts
        observed = len(source_flight_ids)
        distinct = len(set(source_flight_ids))
        repeated = observed - distinct
        if (
            observed != counts["row_observations_seen"]
            or distinct != counts["distinct_source_flights_seen"]
            or repeated != counts["repeated_source_flight_observations"]
        ):
            raise ManifestValidationError(
                "Manifest v2 run observation counters do not match the saved artifacts."
            )

    def report_fields(self) -> dict[str, Any]:
        return {
            "raw_collector_version": self.collector_version,
            "raw_manifest_status": self.status,
            "raw_country_codes": list(self.country_codes),
            "raw_seasons": list(self.seasons),
            "raw_manifest_observation_counts_verified": self.schema_version >= 2,
        }


def _unique_values(value: Any, field_name: str, validator: Any) -> tuple[Any, ...]:
    if not isinstance(value, list) or not value or any(not validator(item) for item in value):
        raise ManifestValidationError(f"Raw manifest {field_name} is invalid.")
    if len(set(value)) != len(value):
        raise ManifestValidationError(f"Raw manifest {field_name} must not contain duplicates.")
    return tuple(value)


def _validate_v3_source_pacing(manifest: dict[str, Any]) -> None:
    pacing = manifest.get("source_pacing")
    if not isinstance(pacing, dict):
        raise ManifestValidationError("Manifest v3 source_pacing must be an object.")
    delay = pacing.get("delay_seconds")
    acknowledged = pacing.get("below_recommended_delay_acknowledged")
    if (
        not isinstance(delay, (int, float))
        or isinstance(delay, bool)
        or delay < 3
        or pacing.get("recommended_delay_seconds") != 30
        or type(acknowledged) is not bool
    ):
        raise ManifestValidationError("Manifest v3 source pacing is invalid.")
    if delay < 30 and not acknowledged:
        raise ManifestValidationError(
            "Manifest v3 below-recommended source pacing requires acknowledgement."
        )


def _validate_v2_or_v3_scope_and_targets(
    manifest: dict[str, Any],
) -> tuple[tuple[str, ...], tuple[int, ...]]:
    if manifest.get("source_url") != SOURCE_LIST_URL:
        raise ManifestValidationError("Manifest v2 source URL is unsupported.")
    if not isinstance(manifest.get("collector_version"), str) or not manifest["collector_version"]:
        raise ManifestValidationError("Manifest v2 must identify its collector version.")
    if manifest.get("status") != "complete":
        raise ManifestValidationError(
            "Manifest v2 must have complete collection status before parsing."
        )
    scope = manifest.get("scope")
    if not isinstance(scope, dict):
        raise ManifestValidationError("Manifest v2 scope must be an object.")
    countries = _unique_values(
        scope.get("country_codes"),
        "scope.country_codes",
        lambda item: isinstance(item, str) and COUNTRY_CODE_PATTERN.fullmatch(item) is not None,
    )
    requested_seasons = _unique_values(
        scope.get("requested_seasons"),
        "scope.requested_seasons",
        lambda item: isinstance(item, int) and 2000 <= item <= 2100,
    )
    completed_seasons = _unique_values(
        scope.get("completed_seasons"),
        "scope.completed_seasons",
        lambda item: isinstance(item, int) and 2000 <= item <= 2100,
    )
    if set(requested_seasons) != set(completed_seasons):
        raise ManifestValidationError(
            "Manifest v2 must complete every requested season before parsing."
        )
    if scope.get("country_scope_source") != "all_sites":
        raise ManifestValidationError("Manifest v2 country scope source must be all_sites.")
    if scope.get("primary_glider_category") != "FAI3":
        raise ManifestValidationError("Manifest v2 primary glider category must be FAI3.")
    if scope.get("minimum_scored_distance_km") != MIN_DISTANCE_KM:
        raise ManifestValidationError("Manifest v2 minimum scored distance must be 100 km.")

    expected_targets = {(season, country) for season in requested_seasons for country in countries}
    targets = manifest.get("target_statuses")
    if not isinstance(targets, list):
        raise ManifestValidationError("Manifest v2 target_statuses must be an array.")
    actual_targets: set[tuple[int, str]] = set()
    for target in targets:
        if (
            not isinstance(target, dict)
            or target.get("status") not in {"complete_primary", "complete_partitioned"}
            or target.get("unresolved_scopes") != []
        ):
            raise ManifestValidationError("Manifest v2 target status is not complete.")
        actual_targets.add((target.get("season"), target.get("country_code")))
    if actual_targets != expected_targets or len(targets) != len(expected_targets):
        raise ManifestValidationError(
            "Manifest v2 target statuses do not cover the requested scope exactly."
        )
    return countries, requested_seasons


def _validate_v2_or_v3_artifacts_and_counts(
    manifest: dict[str, Any],
    artifacts: list[dict[str, Any]],
    country_codes: tuple[str, ...],
    seasons: tuple[int, ...],
) -> dict[str, int]:
    total_rows = 0
    for artifact in artifacts:
        if (
            artifact.get("season") not in seasons
            or artifact.get("country_code") not in country_codes
        ):
            raise ManifestValidationError(
                "Manifest v2 artifact falls outside its declared country/season scope."
            )
        row_count = artifact.get("row_observation_count")
        qualifying_count = artifact.get("qualifying_row_observation_count")
        if (
            not isinstance(row_count, int)
            or row_count < 1
            or not isinstance(qualifying_count, int)
            or not 0 <= qualifying_count <= row_count
        ):
            raise ManifestValidationError("Manifest v2 artifact observation counters are invalid.")
        total_rows += row_count

    counts = manifest.get("observation_counts")
    required_count_fields = (
        "views_written",
        "row_observations_seen",
        "distinct_source_flights_seen",
        "repeated_source_flight_observations",
    )
    if not isinstance(counts, dict) or any(
        not isinstance(counts.get(field), int) or counts[field] < 0
        for field in required_count_fields
    ):
        raise ManifestValidationError("Manifest v2 observation_counts is invalid.")
    if counts["views_written"] != len(artifacts) or counts["row_observations_seen"] != total_rows:
        raise ManifestValidationError(
            "Manifest v2 run observation counters do not match its artifacts."
        )
    if (
        counts["distinct_source_flights_seen"] + counts["repeated_source_flight_observations"]
        != total_rows
    ):
        raise ManifestValidationError("Manifest v2 distinct/repeated counters are inconsistent.")
    return {field: counts[field] for field in required_count_fields}


def _validate_v4_scope_and_targets(
    manifest: dict[str, Any],
) -> tuple[tuple[str, ...], tuple[int, ...]]:
    if manifest.get("source_url") != SOURCE_LIST_URL:
        raise ManifestValidationError("Manifest v4 source URL is unsupported.")
    if not isinstance(manifest.get("collector_version"), str) or not manifest["collector_version"]:
        raise ManifestValidationError("Manifest v4 must identify its collector version.")
    if manifest.get("status") not in {"complete", "incomplete"}:
        raise ManifestValidationError("Manifest v4 collection status is invalid.")
    scope = manifest.get("scope")
    if not isinstance(scope, dict):
        raise ManifestValidationError("Manifest v4 scope must be an object.")
    countries = _unique_values(
        scope.get("country_codes"),
        "scope.country_codes",
        lambda item: isinstance(item, str) and COUNTRY_CODE_PATTERN.fullmatch(item) is not None,
    )
    seasons = _unique_values(
        scope.get("requested_seasons"),
        "scope.requested_seasons",
        lambda item: isinstance(item, int) and 2000 <= item <= 2100,
    )
    completed = _unique_values(
        scope.get("completed_seasons"),
        "scope.completed_seasons",
        lambda item: isinstance(item, int) and 2000 <= item <= 2100,
    )
    if set(seasons) != set(completed):
        raise ManifestValidationError(
            "Manifest v4 must complete every requested season before parsing."
        )
    if (
        scope.get("country_scope_source") != "all_sites"
        or scope.get("primary_glider_category") != "FAI3"
        or scope.get("minimum_observed_scored_distance_km") != 0
        or scope.get("threshold_coverage_distance_km") != MIN_DISTANCE_KM
    ):
        raise ManifestValidationError("Manifest v4 scope contract is invalid.")
    expected_targets = {(season, country) for season in seasons for country in countries}
    targets = manifest.get("target_statuses")
    if not isinstance(targets, list) or len(targets) != len(expected_targets):
        raise ManifestValidationError("Manifest v4 target statuses are invalid.")
    actual_targets: set[tuple[int, str]] = set()
    for target in targets:
        if (
            not isinstance(target, dict)
            or target.get("status")
            not in {"complete_primary", "complete_partitioned", "saturated_unresolved"}
            or not isinstance(target.get("unresolved_scopes"), list)
        ):
            raise ManifestValidationError("Manifest v4 target status is invalid.")
        actual_targets.add((target.get("season"), target.get("country_code")))
    if actual_targets != expected_targets:
        raise ManifestValidationError(
            "Manifest v4 target statuses do not cover the requested scope exactly."
        )
    return countries, seasons


def _validate_v4_artifacts_and_counts(
    manifest: dict[str, Any],
    artifacts: list[dict[str, Any]],
    country_codes: tuple[str, ...],
    seasons: tuple[int, ...],
) -> dict[str, int]:
    total_rows = below = above = 0
    for artifact in artifacts:
        if (
            artifact.get("season") not in seasons
            or artifact.get("country_code") not in country_codes
            or artifact.get("acquisition_purpose") not in {"threshold_100", "all_distance_activity"}
        ):
            raise ManifestValidationError("Manifest v4 artifact falls outside its declared scope.")
        mode = artifact.get("sort_mode")
        key, direction = artifact.get("sort_key"), artifact.get("sort_direction")
        valid_sort = (
            key is None and direction is None
            if mode == "source_default"
            else mode == "explicit"
            and key in {"distance", "pilot", "points", "duration"}
            and direction in {"ascending", "descending"}
        )
        ids = artifact.get("source_flight_ids")
        row_count = artifact.get("row_observation_count")
        artifact_below = artifact.get("below_100km_row_observation_count")
        artifact_above = artifact.get("at_or_above_100km_row_observation_count")
        if (
            not valid_sort
            or not isinstance(ids, list)
            or not all(isinstance(item, str) and item.isdigit() for item in ids)
            or not isinstance(row_count, int)
            or row_count != len(ids)
            or not isinstance(artifact_below, int)
            or not isinstance(artifact_above, int)
            or artifact_below < 0
            or artifact_above < 0
            or artifact_below + artifact_above != row_count
            or type(artifact.get("has_next_page")) is not bool
        ):
            raise ManifestValidationError("Manifest v4 artifact contract is invalid.")
        total_rows += row_count
        below += artifact_below
        above += artifact_above
    counts = manifest.get("observation_counts")
    fields = (
        "views_written",
        "row_observations_seen",
        "distinct_source_flights_seen",
        "repeated_source_flight_observations",
        "below_100km_row_observations",
        "at_or_above_100km_row_observations",
    )
    if not isinstance(counts, dict) or any(
        not isinstance(counts.get(field), int) or counts[field] < 0 for field in fields
    ):
        raise ManifestValidationError("Manifest v4 observation counts are invalid.")
    if (
        counts["views_written"] != len(artifacts)
        or counts["row_observations_seen"] != total_rows
        or counts["below_100km_row_observations"] != below
        or counts["at_or_above_100km_row_observations"] != above
        or counts["distinct_source_flights_seen"] + counts["repeated_source_flight_observations"]
        != total_rows
    ):
        raise ManifestValidationError("Manifest v4 observation counts do not match its artifacts.")
    statuses = manifest.get("activity_scope_statuses")
    if not isinstance(statuses, list) or any(
        not isinstance(item, dict)
        or item.get("status") not in {"complete", "partial_saturated", "empty", "failed"}
        or type(item.get("source_default_captured")) is not bool
        for item in statuses
    ):
        raise ManifestValidationError("Manifest v4 activity scope statuses are invalid.")
    return {field: counts[field] for field in fields[:4]}


def load_manifest(
    run_key: str, project_root: Path
) -> tuple[Path, dict[str, Any], list[dict[str, Any]], ManifestContract]:
    """Load legacy/v1 or v2 metadata and verify every immutable artifact hash."""

    raw_run_dir = project_root / "data" / "raw" / SOURCE_CODE / run_key
    manifest_path = raw_run_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ManifestValidationError(f"Raw manifest does not exist: {manifest_path}") from error
    except json.JSONDecodeError as error:
        raise ManifestValidationError("Raw manifest is not valid JSON.") from error
    if not isinstance(manifest, dict) or manifest.get("source") != SOURCE_CODE:
        raise ManifestValidationError("Raw manifest must identify XCContest as its source.")
    if manifest.get("run_key") != run_key:
        raise ManifestValidationError("Raw manifest run_key does not match the requested run.")
    schema_version = manifest.get("manifest_schema_version", 1)
    if schema_version not in SUPPORTED_MANIFEST_SCHEMA_VERSIONS:
        raise ManifestValidationError("Raw manifest schema version is unsupported.")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ManifestValidationError("Raw manifest must contain at least one artifact.")

    if schema_version == 4:
        countries, seasons = _validate_v4_scope_and_targets(manifest)
        expected_counts = _validate_v4_artifacts_and_counts(manifest, artifacts, countries, seasons)
        _validate_v3_source_pacing(manifest)
        collector_version = manifest["collector_version"]
        status = manifest["status"]
        legacy_country = None
    elif schema_version >= 2:
        countries, seasons = _validate_v2_or_v3_scope_and_targets(manifest)
        expected_counts = _validate_v2_or_v3_artifacts_and_counts(
            manifest, artifacts, countries, seasons
        )
        if schema_version == 3:
            _validate_v3_source_pacing(manifest)
        collector_version = manifest["collector_version"]
        status = manifest["status"]
        legacy_country = None
    else:
        scope = manifest.get("scope")
        legacy_country = scope.get("country") if isinstance(scope, dict) else None
        if (
            not isinstance(legacy_country, str)
            or COUNTRY_CODE_PATTERN.fullmatch(legacy_country) is None
        ):
            raise ManifestValidationError(
                "Legacy raw manifest must provide one uppercase ISO2 country."
            )
        countries = (legacy_country,)
        artifact_seasons = [artifact.get("season") for artifact in artifacts]
        if any(
            not isinstance(season, int) or not 2000 <= season <= 2100 for season in artifact_seasons
        ):
            raise ManifestValidationError("Legacy raw manifest artifact season is invalid.")
        seasons = tuple(sorted(set(artifact_seasons)))
        expected_counts = None
        collector_version = manifest.get("collector_version")
        status = manifest.get("status")

    validated: list[dict[str, Any]] = []
    raw_root = (project_root / "data" / "raw").resolve()
    required = ("path", "sha256", "season", "category")
    for artifact in artifacts:
        if not isinstance(artifact, dict) or any(not artifact.get(key) for key in required):
            raise ManifestValidationError("Raw manifest artifact is missing required metadata.")
        if schema_version < 4 and (
            not artifact.get("sort_key") or not artifact.get("sort_direction")
        ):
            raise ManifestValidationError(
                "Raw manifest artifact is missing required sort metadata."
            )
        artifact_path = (project_root / artifact["path"]).resolve()
        try:
            artifact_path.relative_to(raw_run_dir.resolve())
            artifact_path.relative_to(raw_root)
        except ValueError as error:
            raise ManifestValidationError(
                "Raw manifest artifact path escapes its run directory."
            ) from error
        if not artifact_path.is_file():
            raise ManifestValidationError(
                f"Raw manifest artifact does not exist: {artifact['path']}"
            )
        if hashlib.sha256(artifact_path.read_bytes()).hexdigest() != artifact["sha256"]:
            raise ManifestValidationError(
                f"Raw artifact SHA-256 does not match manifest: {artifact['path']}"
            )
        country = artifact.get("country_code") if schema_version >= 2 else legacy_country
        validated.append({**artifact, "manifest_country_code": country})

    contract = ManifestContract(
        schema_version=schema_version,
        collector_version=collector_version,
        status=status,
        country_codes=countries,
        seasons=seasons,
        expected_observation_counts=expected_counts,
    )
    return manifest_path, manifest, validated, contract
