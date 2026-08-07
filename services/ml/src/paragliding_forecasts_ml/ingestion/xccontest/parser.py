"""Offline parsing and normalization for immutable XCContest list artifacts."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit, urlunsplit

from selectolax.parser import HTMLParser

from .manifest import ManifestValidationError, load_manifest
from .models import MIN_DISTANCE_KM, SOURCE_CODE
from .selectors import (
    DETAIL_LINK_SELECTOR,
    DISTANCE_SELECTOR,
    DURATION_SELECTOR,
    LAUNCH_COUNTRY_SELECTOR,
    LAUNCH_LINK_SELECTOR,
    ROUTE_SELECTOR,
    ROW_SELECTOR,
    TAKEOFF_CELL_SELECTOR,
)

PARSER_VERSION = "xccontest-parser/2"
PARSER_OUTPUT_DIRECTORY = "parser-v2"
MAX_DISTANCE_KM = 2_000.0
FLIGHT_ID_PATTERN = re.compile(r"^flight-([0-9]+)$")
DATE_PATTERN = re.compile(r"^(\d{2})\.(\d{2})\.(\d{2})$")
TIME_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})$")
UTC_OFFSET_PATTERN = re.compile(r"^=?UTC([+-])(\d{2}):(\d{2})$")
NUMBER_PATTERN = re.compile(r"^\d+(?:[.,]\d+)?$")
DURATION_PATTERN = re.compile(r"^(\d+)(?:\s*:\s*(\d{1,2}))?$")
COUNTRY_CODE_PATTERN = re.compile(r"^[A-Z]{2}$")
ROUTE_TYPES = {
    "free flight": "free_flight",
    "free triangle": "free_triangle",
    "fai triangle": "fai_triangle",
    "closed free triangle": "closed_free_triangle",
    "closed fai triangle": "closed_fai_triangle",
}


class ParseError(ValueError):
    """A raw manifest or row cannot produce a safe normalized candidate."""


@dataclass(frozen=True)
class ParsedRun:
    """Locations and counters produced by one offline parser execution."""

    output_dir: Path
    normalized_path: Path
    rejections_path: Path
    report_path: Path
    report: dict[str, Any]


def repository_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.split()) or None


def _required_text(value: str | None, field_name: str) -> str:
    cleaned = _clean_text(value)
    if cleaned is None:
        raise ParseError(f"Missing {field_name}.")
    return cleaned


def _artifact_reference(artifact: dict[str, Any], row_index: int) -> dict[str, Any]:
    return {
        "artifact_path": artifact["path"],
        "artifact_sha256": artifact["sha256"],
        "season": artifact["season"],
        "country_code": artifact.get("country_code") or artifact["manifest_country_code"],
        "category": artifact["category"],
        "date_filter": artifact.get("date_filter"),
        "sort_key": artifact["sort_key"],
        "sort_direction": artifact["sort_direction"],
        "row_index": row_index,
    }


def _source_flight_id(row: Any) -> str:
    match = FLIGHT_ID_PATTERN.fullmatch(row.attributes.get("id", ""))
    if match is None:
        raise ParseError("XCContest row id must have the form flight-<numeric-id>.")
    return match.group(1)


def _cell(row: Any, selector: str, field_name: str) -> Any:
    cell = row.css_first(selector)
    if cell is None:
        raise ParseError(f"Missing {field_name}.")
    return cell


def _parse_takeoff_at_utc(takeoff_cell: Any, season: int) -> str:
    raw_text = _required_text(takeoff_cell.text(), "takeoff date/time/UTC offset")
    date_match = re.search(r"\b\d{2}\.\d{2}\.\d{2}\b", raw_text)
    time_match = re.search(r"\b\d{1,2}:\d{2}\b", raw_text)
    offset_match = re.search(r"=?UTC[+-]\d{2}:\d{2}", raw_text)
    if date_match is None or time_match is None or offset_match is None:
        raise ParseError("Takeoff cell must contain date, time, and UTC offset.")
    date_parts = DATE_PATTERN.match(date_match.group())
    time_parts = TIME_PATTERN.match(time_match.group())
    offset_parts = UTC_OFFSET_PATTERN.match(offset_match.group())
    assert date_parts is not None and time_parts is not None and offset_parts is not None
    day, month, short_year = (int(value) for value in date_parts.groups())
    hour, minute = (int(value) for value in time_parts.groups())
    sign, offset_hours, offset_minutes = offset_parts.groups()
    offset = timedelta(hours=int(offset_hours), minutes=int(offset_minutes))
    if sign == "-":
        offset = -offset
    if abs(offset) > timedelta(hours=14):
        raise ParseError("UTC offset is outside the supported range.")
    candidates: list[datetime] = []
    for year in (season - 1, season):
        if year % 100 != short_year:
            continue
        try:
            local_time = datetime(year, month, day, hour, minute, tzinfo=timezone(offset))
        except ValueError as error:
            raise ParseError("Takeoff date/time is invalid.") from error
        if (
            datetime(season - 1, 10, 1, tzinfo=timezone(offset))
            <= local_time
            <= datetime(season, 9, 30, 23, 59, tzinfo=timezone(offset))
        ):
            candidates.append(local_time)
    if len(candidates) != 1:
        raise ParseError("Takeoff date does not belong to the artifact XCContest season.")
    return candidates[0].astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_distance(row: Any) -> float:
    value = _required_text(
        _cell(row, DISTANCE_SELECTOR, "scored distance").text(), "scored distance"
    )
    if NUMBER_PATTERN.fullmatch(value) is None:
        raise ParseError("Scored distance must be a decimal number in kilometres.")
    distance = float(value.replace(",", "."))
    if not MIN_DISTANCE_KM <= distance <= MAX_DISTANCE_KM:
        raise ParseError(
            f"Scored distance must be between {MIN_DISTANCE_KM:g} and {MAX_DISTANCE_KM:g} km."
        )
    return distance


def _parse_duration_seconds(row: Any) -> int:
    value = _required_text(_cell(row, DURATION_SELECTOR, "duration").text(), "duration")
    match = DURATION_PATTERN.fullmatch(value)
    if match is None:
        raise ParseError("Duration must use XCContest hour or hour:minute notation.")
    hours, minutes = int(match.group(1)), int(match.group(2) or 0)
    if minutes > 59:
        raise ParseError("Duration minutes must be below 60.")
    duration_seconds = hours * 3600 + minutes * 60
    if not 1 <= duration_seconds <= 86_400:
        raise ParseError("Duration must be between one second and 24 hours.")
    return duration_seconds


def _canonical_detail_url(row: Any) -> str:
    link = _cell(row, DETAIL_LINK_SELECTOR, "canonical detail URL")
    raw_url = _required_text(link.attributes.get("href"), "canonical detail URL")
    parts = urlsplit(raw_url)
    if (
        parts.scheme != "https"
        or parts.hostname != "www.xcontest.org"
        or parts.port is not None
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or not re.match(r"^/(?:\d{4}/)?world/en/flights/detail:[^/]+/[^/]+/[^/]+$", parts.path)
    ):
        raise ParseError("Canonical detail URL is not a supported XCContest detail URL.")
    return urlunsplit(("https", "www.xcontest.org", parts.path, "", ""))


def _launch_evidence(row: Any) -> dict[str, Any]:
    launch_link = _cell(row, LAUNCH_LINK_SELECTOR, "launch evidence")
    country_node = (
        launch_link.parent.css_first(LAUNCH_COUNTRY_SELECTOR) if launch_link.parent else None
    )
    country_code = _required_text(
        country_node.text() if country_node is not None else None, "launch country code"
    )
    if COUNTRY_CODE_PATTERN.fullmatch(country_code) is None:
        raise ParseError("Launch country code must be an uppercase ISO2 value.")
    launch_search_url = _required_text(launch_link.attributes.get("href"), "launch search URL")
    parts = urlsplit(launch_search_url)
    if parts.scheme != "https" or parts.hostname != "www.xcontest.org":
        raise ParseError("Launch search URL is not an HTTPS XCContest URL.")
    point_values = parse_qs(parts.query, keep_blank_values=True).get("filter[point]", [])
    if len(point_values) > 1:
        raise ParseError("Launch search URL has multiple point tokens.")
    point_token = _clean_text(point_values[0]) if point_values else None
    longitude_deg: float | None = None
    latitude_deg: float | None = None
    if point_token is not None:
        coordinates = point_token.split(" ")
        if len(coordinates) != 2:
            raise ParseError("Launch point token must contain longitude and latitude.")
        try:
            longitude_deg, latitude_deg = (float(value) for value in coordinates)
        except ValueError as error:
            raise ParseError("Launch point token must contain numeric coordinates.") from error
        if not -180 <= longitude_deg <= 180 or not -90 <= latitude_deg <= 90:
            raise ParseError("Launch point token coordinates are outside valid ranges.")
    return {
        "launch_name_raw": _clean_text(launch_link.attributes.get("title")),
        "launch_country_code_iso2": country_code,
        "launch_point_token": point_token,
        "launch_longitude_deg": longitude_deg,
        "launch_latitude_deg": latitude_deg,
        "launch_search_url": launch_search_url,
    }


def _route_evidence(row: Any) -> tuple[str, str | None]:
    route_node = row.css_first(ROUTE_SELECTOR)
    route_raw = _clean_text(route_node.attributes.get("title") if route_node else None)
    if route_raw is None:
        return "unknown", None
    return ROUTE_TYPES.get(route_raw.casefold(), "other"), route_raw


def _normalize_row(row: Any, artifact: dict[str, Any], row_index: int) -> dict[str, Any]:
    route_type, route_type_raw = _route_evidence(row)
    return {
        "source": SOURCE_CODE,
        "source_flight_id": _source_flight_id(row),
        "source_flight_url": _canonical_detail_url(row),
        "takeoff_at_utc": _parse_takeoff_at_utc(
            _cell(row, TAKEOFF_CELL_SELECTOR, "takeoff"), artifact["season"]
        ),
        "scored_distance_km": _parse_distance(row),
        "duration_seconds": _parse_duration_seconds(row),
        "route_type": route_type,
        "route_type_raw": route_type_raw,
        **_launch_evidence(row),
        "artifact_references": [_artifact_reference(artifact, row_index)],
    }


def _core_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in candidate.items() if key != "artifact_references"}


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            output.write("\n")


def parse_run(run_key: str, *, project_root: Path | None = None) -> ParsedRun:
    """Parse one immutable raw run into deduplicated local staging outputs."""

    root = (project_root or repository_root()).resolve()
    try:
        manifest_path, _manifest, artifacts, manifest_contract = load_manifest(run_key, root)
    except ManifestValidationError as error:
        raise ParseError(str(error)) from error
    candidates_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rejections: list[dict[str, Any]] = []
    observations_seen = threshold_exclusions = 0
    raw_source_flight_ids: list[str] = []
    for artifact in artifacts:
        document = HTMLParser((root / artifact["path"]).read_text(encoding="utf-8"))
        rows = document.css(ROW_SELECTOR)
        try:
            raw_source_flight_ids.extend(manifest_contract.verify_artifact_rows(artifact, rows))
        except ManifestValidationError as error:
            raise ParseError(str(error)) from error
        for row_index, row in enumerate(rows, start=1):
            observations_seen += 1
            source_flight_id: str | None = None
            try:
                source_flight_id = _source_flight_id(row)
                candidate = _normalize_row(row, artifact, row_index)
            except ParseError as error:
                if "Scored distance must be between" in str(error):
                    threshold_exclusions += 1
                rejections.append(
                    {
                        "source": SOURCE_CODE,
                        "source_flight_id": source_flight_id,
                        "reason": str(error),
                        "artifact_reference": _artifact_reference(artifact, row_index),
                    }
                )
                continue
            candidates_by_id[source_flight_id].append(candidate)

    try:
        manifest_contract.verify_run_rows(raw_source_flight_ids)
    except ManifestValidationError as error:
        raise ParseError(str(error)) from error

    normalized: list[dict[str, Any]] = []
    duplicate_observations_removed = conflict_candidates = 0
    for source_flight_id in sorted(candidates_by_id, key=int):
        variants = candidates_by_id[source_flight_id]
        duplicate_observations_removed += len(variants) - 1
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for variant in variants:
            groups[json.dumps(_core_candidate(variant), sort_keys=True)].append(variant)
        unique_variants = [group[0] for group in groups.values()]
        if len(unique_variants) == 1:
            normalized.append(
                {
                    **_core_candidate(unique_variants[0]),
                    "parser_status": "normalized",
                    "artifact_references": [
                        reference
                        for variant in variants
                        for reference in variant["artifact_references"]
                    ],
                }
            )
            continue
        conflict_candidates += 1
        first_core = _core_candidate(unique_variants[0])
        normalized.append(
            {
                "source": SOURCE_CODE,
                "source_flight_id": source_flight_id,
                "parser_status": "conflicted",
                "conflicting_fields": sorted(
                    key
                    for key, value in first_core.items()
                    if any(
                        _core_candidate(variant)[key] != value for variant in unique_variants[1:]
                    )
                ),
                "variants": [
                    {
                        **_core_candidate(variant),
                        "artifact_references": [
                            reference
                            for grouped_variant in groups[
                                json.dumps(_core_candidate(variant), sort_keys=True)
                            ]
                            for reference in grouped_variant["artifact_references"]
                        ],
                    }
                    for variant in unique_variants
                ],
            }
        )

    output_dir = root / "data" / "interim" / SOURCE_CODE / run_key / PARSER_OUTPUT_DIRECTORY
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite parser staging output: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=False)
    normalized_path = output_dir / "normalized-flights.jsonl"
    rejections_path = output_dir / "parse-rejections.jsonl"
    report_path = output_dir / "parse-report.json"
    _write_jsonl(normalized_path, normalized)
    _write_jsonl(rejections_path, rejections)
    report = {
        "parser_version": PARSER_VERSION,
        "source": SOURCE_CODE,
        "run_key": run_key,
        "raw_manifest_path": manifest_path.relative_to(root).as_posix(),
        "raw_manifest_schema_version": manifest_contract.schema_version,
        **manifest_contract.report_fields(),
        "artifact_count": len(artifacts),
        "row_observations_seen": observations_seen,
        "normalized_observations": sum(len(items) for items in candidates_by_id.values()),
        "unique_source_flight_ids": len(candidates_by_id),
        "normalized_candidates": len(normalized),
        "duplicate_observations_removed": duplicate_observations_removed,
        "conflict_candidates": conflict_candidates,
        "threshold_exclusions": threshold_exclusions,
        "records_rejected": len(rejections),
    }
    with report_path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(report, output, ensure_ascii=False, indent=2, sort_keys=True)
        output.write("\n")
    return ParsedRun(output_dir, normalized_path, rejections_path, report_path, report)
