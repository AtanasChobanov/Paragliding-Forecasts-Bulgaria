"""Reviewed XCContest source-evidence to canonical-site mapping workflow."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from paragliding_forecasts_ml.storage.sqlite import (
    DatabaseConfigurationError,
    configured_database_url,
    open_read_only_database,
    open_writable_database,
)

from .models import SOURCE_CODE
from .versions import MAPPING_OUTPUT_DIRECTORY, MAPPING_VERSION, PARSER_OUTPUT_DIRECTORY


class SiteMappingError(RuntimeError):
    """A mapping proposal, review decision, or SQLite catalog is unsafe."""


@dataclass(frozen=True)
class Site:
    id: int
    slug: str
    name: str
    country_code_iso2: str
    site_type: str
    latitude_deg: float
    longitude_deg: float
    catchment_radius_km: float | None
    is_active: bool


@dataclass(frozen=True)
class SourceSiteMapping:
    id: int
    source_id: int
    site_id: int
    key_type: str
    key_value: str | None
    source_display_name: str | None
    point_latitude_deg: float | None
    point_longitude_deg: float | None
    status: str
    verification_reference: str | None
    verified_at_utc: str | None
    notes: str | None


@dataclass(frozen=True)
class SourceSiteExclusion:
    id: int
    source_id: int
    key_type: str
    key_value: str
    origin_run_key: str
    origin_proposal_id: str
    notes: str | None
    status: str
    created_at_utc: str
    retired_at_utc: str | None
    retirement_reason: str | None


@dataclass(frozen=True)
class MappingCatalog:
    source_id: int
    sites: tuple[Site, ...]
    mappings: tuple[SourceSiteMapping, ...]
    exclusions: tuple[SourceSiteExclusion, ...]

    @property
    def sites_by_id(self) -> dict[int, Site]:
        return {site.id: site for site in self.sites}


@dataclass(frozen=True)
class CatchmentResolution:
    """Deterministic geographic relation between a source point and project sites."""

    point: tuple[float, float] | None
    matches: tuple[dict[str, object], ...]

    @property
    def disposition(self) -> str | None:
        if self.point is None:
            return None
        if not self.matches:
            return "outside_configured_catchments"
        if len(self.matches) == 1:
            return "inside_unique_catchment"
        return "ambiguous_catchment"


def repository_root() -> Path:
    """Locate the repository from the installed source-tree package layout."""

    return Path(__file__).resolve().parents[6]


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def normalized_name(value: str | None) -> str | None:
    """Produce a deterministic reviewed-alias key without transliteration."""

    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    return " ".join(unicodedata.normalize("NFKC", cleaned).casefold().split())


def _round_coordinate(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    rounded = round(float(value), 6)
    return rounded if math.isfinite(rounded) else None


def _point_evidence(record: dict[str, Any]) -> tuple[float, float] | None:
    latitude = _round_coordinate(record.get("launch_latitude_deg"))
    longitude = _round_coordinate(record.get("launch_longitude_deg"))
    if latitude is None and longitude is None:
        return None
    if latitude is None or longitude is None:
        raise SiteMappingError("Launch point evidence must provide both latitude and longitude.")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise SiteMappingError("Launch point evidence is outside valid coordinate ranges.")
    return latitude, longitude


def source_site_token(launch_search_url: object) -> str | None:
    """Extract the current XCContest opaque site token without decoding it."""

    if not isinstance(launch_search_url, str):
        return None
    parts = urlsplit(launch_search_url)
    if parts.scheme != "https" or parts.hostname != "www.xcontest.org":
        raise SiteMappingError("Launch search URL is not an HTTPS XCContest URL.")
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    pairs.extend(
        pair
        for segment in parts.fragment.split("@")
        for pair in parse_qsl(segment, keep_blank_values=True)
    )
    values = [value.strip() for key, value in pairs if key == "filter[site]" and value.strip()]
    if len(values) > 1:
        raise SiteMappingError("Launch search URL has multiple source-site tokens.")
    return values[0] if values else None


def candidate_evidence(record: dict[str, Any]) -> dict[str, object]:
    """Return source-specific evidence keys in the accepted matching order."""

    evidence: dict[str, object] = {}
    takeoff_id = _clean_text(record.get("launch_takeoff_id"))
    if takeoff_id is not None:
        evidence["source_takeoff_id"] = takeoff_id
    token = source_site_token(record.get("launch_search_url"))
    if token is not None:
        evidence["source_site_token"] = token
    name = normalized_name(_clean_text(record.get("launch_name_raw")))
    if name is not None:
        evidence["normalized_name"] = name
    point = _point_evidence(record)
    if point is not None:
        evidence["source_point"] = point
    return evidence


def haversine_distance_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Return great-circle distance using the mean Earth radius in kilometres."""

    radius_km = 6371.0088
    latitude_delta = math.radians(latitude_b - latitude_a)
    longitude_delta = math.radians(longitude_b - longitude_a)
    value = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(math.radians(latitude_a))
        * math.cos(math.radians(latitude_b))
        * math.sin(longitude_delta / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def catchment_suggestions(
    record: dict[str, Any], sites: tuple[Site, ...]
) -> list[dict[str, object]]:
    """Return every same-country configured catchment containing the launch point."""

    point = _point_evidence(record)
    country = _clean_text(record.get("launch_country_code_iso2"))
    if point is None or country is None:
        return []
    latitude, longitude = point
    suggestions: list[dict[str, object]] = []
    for site in sites:
        if site.country_code_iso2 != country or site.catchment_radius_km is None:
            continue
        distance = haversine_distance_km(latitude, longitude, site.latitude_deg, site.longitude_deg)
        if distance <= site.catchment_radius_km:
            suggestions.append(
                {
                    "site_id": site.id,
                    "site_slug": site.slug,
                    "distance_km": round(distance, 3),
                    "catchment_radius_km": site.catchment_radius_km,
                    "reason": "inside_configured_catchment",
                }
            )
    return sorted(suggestions, key=lambda item: (item["distance_km"], item["site_id"]))


def catchment_resolution(record: dict[str, Any], sites: tuple[Site, ...]) -> CatchmentResolution:
    """Classify a valid source point against every configured project catchment."""

    point = _point_evidence(record)
    if point is None:
        return CatchmentResolution(point=None, matches=())
    latitude, longitude = point
    matches: list[dict[str, object]] = []
    for site in sites:
        if site.catchment_radius_km is None:
            continue
        distance = haversine_distance_km(latitude, longitude, site.latitude_deg, site.longitude_deg)
        if distance <= site.catchment_radius_km:
            matches.append(
                {
                    "site_id": site.id,
                    "site_slug": site.slug,
                    "distance_km": round(distance, 3),
                    "catchment_radius_km": site.catchment_radius_km,
                    "reason": "inside_configured_catchment",
                }
            )
    return CatchmentResolution(
        point=point,
        matches=tuple(sorted(matches, key=lambda item: (item["distance_km"], item["site_id"]))),
    )


def _safe_run_directory(run_key: str, root: Path) -> Path:
    if not run_key or Path(run_key).name != run_key:
        raise SiteMappingError("Run key must be one path segment.")
    directory = (root / "data" / "interim" / SOURCE_CODE / run_key).resolve()
    expected_parent = (root / "data" / "interim" / SOURCE_CODE).resolve()
    try:
        directory.relative_to(expected_parent)
    except ValueError as error:
        raise SiteMappingError("Run key resolves outside XCContest interim data.") from error
    return directory


def parser_staging_paths(run_key: str, root: Path) -> tuple[Path, Path]:
    run_directory = _safe_run_directory(run_key, root)
    output_directory = run_directory / PARSER_OUTPUT_DIRECTORY
    normalized_path = output_directory / "normalized-flights.jsonl"
    report_path = output_directory / "parse-report.json"
    if not normalized_path.is_file() or not report_path.is_file():
        raise SiteMappingError("Parser staging output is missing for the requested run.")
    return normalized_path, report_path


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise SiteMappingError(f"Invalid JSONL at {path}:{line_number}.") from error
        if not isinstance(record, dict):
            raise SiteMappingError(f"JSONL record at {path}:{line_number} must be an object.")
        records.append(record)
    return records


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            output.write("\n")


def load_parser_records(
    run_key: str, root: Path
) -> tuple[list[dict[str, Any]], dict[str, Any], Path, Path]:
    normalized_path, report_path = parser_staging_paths(run_key, root)
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SiteMappingError("Parser report is not valid JSON.") from error
    if (
        not isinstance(report, dict)
        or report.get("source") != SOURCE_CODE
        or report.get("run_key") != run_key
    ):
        raise SiteMappingError("Parser report does not belong to the requested XCContest run.")
    records = read_jsonl(normalized_path)
    expected = report.get("normalized_candidates")
    if not isinstance(expected, int) or expected != len(records):
        raise SiteMappingError(
            "Parser report normalized candidate count does not match JSONL output."
        )
    return records, report, normalized_path, report_path


def load_mapping_catalog(
    database_url: str | None = None,
    *,
    project_root: Path | None = None,
) -> MappingCatalog:
    """Load the source, canonical sites, and every mapping status read-only."""

    url = configured_database_url(database_url)
    root = project_root or repository_root()
    try:
        connection = open_read_only_database(url, root)
    except DatabaseConfigurationError as error:
        raise SiteMappingError("Could not open the configured mapping database.") from error
    try:
        source = connection.execute(
            "SELECT id FROM flight_sources WHERE code = ?", (SOURCE_CODE,)
        ).fetchone()
        if source is None:
            raise SiteMappingError("Migrated database does not contain the XCContest source.")
        site_rows = connection.execute(
            """SELECT id, slug, name, country_code_iso2, site_type, latitude_deg, longitude_deg,
                      catchment_radius_km, is_active
                 FROM sites ORDER BY id"""
        ).fetchall()
        mapping_rows = connection.execute(
            """SELECT id, source_id, site_id, key_type, key_value, source_display_name,
                      point_latitude_deg, point_longitude_deg, status, verification_reference,
                      verified_at_utc, notes
                 FROM source_site_mappings
                WHERE source_id = ? ORDER BY id""",
            (source[0],),
        ).fetchall()
        exclusion_rows = connection.execute(
            """SELECT id, source_id, key_type, key_value, origin_run_key, origin_proposal_id,
                      notes, status, created_at_utc, retired_at_utc, retirement_reason
                 FROM source_site_exclusions
                WHERE source_id = ? ORDER BY id""",
            (source[0],),
        ).fetchall()
    except sqlite3.Error as error:
        raise SiteMappingError(
            "Database does not satisfy the T-012 site-mapping contract."
        ) from error
    finally:
        connection.close()
    return MappingCatalog(
        source_id=int(source[0]),
        sites=tuple(
            Site(
                id=int(row[0]),
                slug=str(row[1]),
                name=str(row[2]),
                country_code_iso2=str(row[3]),
                site_type=str(row[4]),
                latitude_deg=float(row[5]),
                longitude_deg=float(row[6]),
                catchment_radius_km=None if row[7] is None else float(row[7]),
                is_active=bool(row[8]),
            )
            for row in site_rows
        ),
        mappings=tuple(
            SourceSiteMapping(
                id=int(row[0]),
                source_id=int(row[1]),
                site_id=int(row[2]),
                key_type=str(row[3]),
                key_value=None if row[4] is None else str(row[4]),
                source_display_name=None if row[5] is None else str(row[5]),
                point_latitude_deg=None if row[6] is None else float(row[6]),
                point_longitude_deg=None if row[7] is None else float(row[7]),
                status=str(row[8]),
                verification_reference=None if row[9] is None else str(row[9]),
                verified_at_utc=None if row[10] is None else str(row[10]),
                notes=None if row[11] is None else str(row[11]),
            )
            for row in mapping_rows
        ),
        exclusions=tuple(
            SourceSiteExclusion(
                id=int(row[0]),
                source_id=int(row[1]),
                key_type=str(row[2]),
                key_value=str(row[3]),
                origin_run_key=str(row[4]),
                origin_proposal_id=str(row[5]),
                notes=None if row[6] is None else str(row[6]),
                status=str(row[7]),
                created_at_utc=str(row[8]),
                retired_at_utc=None if row[9] is None else str(row[9]),
                retirement_reason=None if row[10] is None else str(row[10]),
            )
            for row in exclusion_rows
        ),
    )


def matching_mappings(record: dict[str, Any], catalog: MappingCatalog) -> list[SourceSiteMapping]:
    evidence = candidate_evidence(record)
    matches: list[SourceSiteMapping] = []
    for mapping in catalog.mappings:
        value = evidence.get(mapping.key_type)
        if mapping.key_type == "source_point":
            if not isinstance(value, tuple):
                continue
            latitude, longitude = value
            if (
                _round_coordinate(mapping.point_latitude_deg) == latitude
                and _round_coordinate(mapping.point_longitude_deg) == longitude
            ):
                matches.append(mapping)
        elif isinstance(value, str) and mapping.key_value == value:
            matches.append(mapping)
    return matches


def mapping_snapshot_sha256(catalog: MappingCatalog) -> str:
    """Hash active mapping state, exclusions, and catchment scope for output reuse."""

    payload = {
        "source_id": catalog.source_id,
        "sites": [
            {
                "id": site.id,
                "slug": site.slug,
                "country_code_iso2": site.country_code_iso2,
                "latitude_deg": site.latitude_deg,
                "longitude_deg": site.longitude_deg,
                "catchment_radius_km": site.catchment_radius_km,
                "is_active": site.is_active,
            }
            for site in catalog.sites
        ],
        "mappings": [
            {
                "id": mapping.id,
                "site_id": mapping.site_id,
                "key_type": mapping.key_type,
                "key_value": mapping.key_value,
                "point_latitude_deg": mapping.point_latitude_deg,
                "point_longitude_deg": mapping.point_longitude_deg,
                "status": mapping.status,
                "verification_reference": mapping.verification_reference,
                "verified_at_utc": mapping.verified_at_utc,
            }
            for mapping in catalog.mappings
        ],
        "active_exclusions": [
            {
                "id": exclusion.id,
                "key_type": exclusion.key_type,
                "key_value": exclusion.key_value,
                "origin_run_key": exclusion.origin_run_key,
                "origin_proposal_id": exclusion.origin_proposal_id,
                "created_at_utc": exclusion.created_at_utc,
            }
            for exclusion in catalog.exclusions
            if exclusion.status == "active"
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def matching_exclusions(
    record: dict[str, Any], catalog: MappingCatalog
) -> list[SourceSiteExclusion]:
    """Return exact active stable-key exclusions; names and points never match."""

    evidence = candidate_evidence(record)
    return [
        exclusion
        for exclusion in catalog.exclusions
        if exclusion.status == "active"
        and isinstance(evidence.get(exclusion.key_type), str)
        and evidence[exclusion.key_type] == exclusion.key_value
    ]


def exclusion_resolution(
    record: dict[str, Any], catalog: MappingCatalog
) -> tuple[SourceSiteExclusion | None, bool]:
    """Return a safely reusable exclusion or whether fresh evidence conflicts with one."""

    exclusions = matching_exclusions(record, catalog)
    if not exclusions:
        return None, False
    active_mappings = [
        mapping
        for mapping in matching_mappings(record, catalog)
        if mapping.status in {"approved", "provisional"}
    ]
    geographic = catchment_resolution(record, catalog.sites)
    if active_mappings or geographic.disposition in {
        "inside_unique_catchment",
        "ambiguous_catchment",
    }:
        return None, True
    return min(exclusions, key=lambda item: item.id), False


def _proposal_key(record: dict[str, Any]) -> tuple[str, object]:
    evidence = candidate_evidence(record)
    for key_type in ("source_takeoff_id", "source_site_token", "source_point", "normalized_name"):
        if key_type in evidence:
            return key_type, evidence[key_type]
    raise SiteMappingError("Candidate has no usable launch evidence for a mapping proposal.")


def _proposal_id(key_type: str, key_value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            {"source": SOURCE_CODE, "key_type": key_type, "key_value": key_value}, sort_keys=True
        ).encode()
    ).hexdigest()


def write_mapping_proposals(
    run_key: str,
    *,
    database_url: str | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Create v4 human-review proposals without modifying SQLite."""

    root = (project_root or repository_root()).resolve()
    records, parser_report, normalized_path, parser_report_path = load_parser_records(run_key, root)
    catalog = load_mapping_catalog(database_url, project_root=root)
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    automatically_rejected_candidate_count = 0
    persisted_exclusion_candidate_count = 0
    for record in records:
        if record.get("parser_status") != "normalized":
            continue
        try:
            evidence = candidate_evidence(record)
            active = [
                mapping
                for mapping in matching_mappings(record, catalog)
                if mapping.status in {"approved", "provisional"}
            ]
            geographic = catchment_resolution(record, catalog.sites)
            exclusion, exclusion_conflict = exclusion_resolution(record, catalog)
        except SiteMappingError:
            continue
        if active and not exclusion_conflict:
            target_site_ids = {mapping.site_id for mapping in active}
            geographic_site_id = (
                int(geographic.matches[0]["site_id"])
                if geographic.disposition == "inside_unique_catchment"
                else None
            )
            if len(target_site_ids) == 1 and not (
                geographic.disposition == "outside_configured_catchments"
                or (geographic_site_id is not None and geographic_site_id not in target_site_ids)
            ):
                continue
        if (
            geographic.disposition == "outside_configured_catchments"
            and not active
            and not exclusion_conflict
        ):
            if exclusion is not None:
                persisted_exclusion_candidate_count += 1
            else:
                automatically_rejected_candidate_count += 1
            continue
        proposal_keys = [
            (key_type, evidence[key_type])
            for key_type in ("source_takeoff_id", "source_site_token")
            if key_type in evidence
        ]
        if not proposal_keys:
            proposal_keys = [_proposal_key(record)]
        for key_type, key_value in proposal_keys:
            exact_exclusion = next(
                (
                    item
                    for item in matching_exclusions(record, catalog)
                    if item.key_type == key_type and item.key_value == key_value
                ),
                None,
            )
            if exact_exclusion is not None and not exclusion_conflict:
                persisted_exclusion_candidate_count += 1
                continue
            review_reason = (
                "mapping_exclusion_conflict"
                if exclusion_conflict
                else "mapping_coordinate_conflict"
                if active
                else None
            )
            key_json = json.dumps(key_value, sort_keys=True)
            group = groups.setdefault(
                (key_type, key_json),
                {
                    "proposal_id": _proposal_id(key_type, key_value),
                    "source": SOURCE_CODE,
                    "key_type": key_type,
                    "key_value": key_value if isinstance(key_value, str) else None,
                    "point_latitude_deg": key_value[0] if isinstance(key_value, tuple) else None,
                    "point_longitude_deg": key_value[1] if isinstance(key_value, tuple) else None,
                    "source_display_names": set(),
                    "candidate_count": 0,
                    "sample_source_flight_ids": [],
                    "seasons": set(),
                    "catchment_suggestions": [],
                    "review_reasons": set(),
                    "matching_mapping_ids": set(),
                    "matching_exclusion_ids": set(),
                },
            )
            group["candidate_count"] += 1
            if review_reason is not None:
                group["review_reasons"].add(review_reason)
                group["matching_mapping_ids"].update(mapping.id for mapping in active)
                group["matching_exclusion_ids"].update(
                    item.id for item in matching_exclusions(record, catalog)
                )
            display_name = _clean_text(record.get("launch_name_raw"))
            if display_name is not None:
                group["source_display_names"].add(display_name)
            flight_id = _clean_text(record.get("source_flight_id"))
            if flight_id is not None and len(group["sample_source_flight_ids"]) < 10:
                group["sample_source_flight_ids"].append(flight_id)
            for reference in record.get("artifact_references", []):
                if isinstance(reference, dict) and isinstance(reference.get("season"), int):
                    group["seasons"].add(reference["season"])
            for suggestion in catchment_suggestions(record, catalog.sites):
                if suggestion not in group["catchment_suggestions"]:
                    group["catchment_suggestions"].append(suggestion)
    output_directory = _safe_run_directory(run_key, root) / MAPPING_OUTPUT_DIRECTORY
    proposals_path = output_directory / "mapping-proposals.jsonl"
    report_path = output_directory / "proposal-report.json"
    if proposals_path.exists() or report_path.exists():
        raise FileExistsError(f"Refusing to overwrite mapping proposal output: {output_directory}")
    output_directory.mkdir(parents=True, exist_ok=True)
    proposal_records: list[dict[str, Any]] = []
    for group in groups.values():
        suggestion_count = len(group["catchment_suggestions"])
        reason = (
            "inside_unique_catchment"
            if suggestion_count == 1
            else "ambiguous_catchment"
            if suggestion_count > 1
            else "review_required"
        )
        proposal_records.append(
            {
                **{
                    key: value
                    for key, value in group.items()
                    if key
                    not in {
                        "source_display_names",
                        "seasons",
                        "review_reasons",
                        "matching_mapping_ids",
                        "matching_exclusion_ids",
                    }
                },
                "source_display_names": sorted(group["source_display_names"]),
                "seasons": sorted(group["seasons"]),
                "review_reasons": sorted(group["review_reasons"]),
                "matching_mapping_ids": sorted(group["matching_mapping_ids"]),
                "matching_exclusion_ids": sorted(group["matching_exclusion_ids"]),
                "recommendation": (
                    "mapping_exclusion_conflict"
                    if "mapping_exclusion_conflict" in group["review_reasons"]
                    else "mapping_coordinate_conflict"
                    if "mapping_coordinate_conflict" in group["review_reasons"]
                    else reason
                ),
            }
        )
    proposal_records.sort(key=lambda item: (item["key_type"], str(item["key_value"])))
    _write_jsonl(proposals_path, proposal_records)
    report_payload = {
        "mapping_version": MAPPING_VERSION,
        "run_key": run_key,
        "source": SOURCE_CODE,
        "parser_normalized_path": normalized_path.relative_to(root).as_posix(),
        "parser_report_path": parser_report_path.relative_to(root).as_posix(),
        "parser_normalized_candidates": parser_report["normalized_candidates"],
        "proposal_count": len(proposal_records),
        "automatically_rejected_candidate_count": automatically_rejected_candidate_count,
        "persisted_exclusion_candidate_count": persisted_exclusion_candidate_count,
        "mapping_snapshot_sha256": mapping_snapshot_sha256(catalog),
    }
    report_path.write_text(
        json.dumps(report_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "output_dir": output_directory,
        "proposals_path": proposals_path,
        "report_path": report_path,
        **report_payload,
    }


def _decision_value(decision: dict[str, Any], name: str) -> str:
    value = _clean_text(decision.get(name))
    if value is None:
        raise SiteMappingError(f"Mapping decision requires {name}.")
    return value


def _decision_point(decision: dict[str, Any]) -> tuple[float, float]:
    latitude = _round_coordinate(decision.get("point_latitude_deg"))
    longitude = _round_coordinate(decision.get("point_longitude_deg"))
    if latitude is None or longitude is None:
        raise SiteMappingError("Source-point mapping decision requires both point coordinates.")
    return latitude, longitude


def _load_decisions(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise SiteMappingError(f"Mapping review file does not exist: {path}")
    return read_jsonl(path)


def _automatic_mapping_decisions(
    records: list[dict[str, Any]], catalog: MappingCatalog
) -> list[dict[str, Any]]:
    """Derive approved mappings only from unambiguous, in-country coordinates."""

    snapshot = mapping_snapshot_sha256(catalog)
    candidates: list[tuple[dict[str, Any], Site, dict[str, object], dict[str, object]]] = []
    key_targets: dict[tuple[str, object], set[int]] = {}
    for record in records:
        if record.get("parser_status") != "normalized":
            continue
        try:
            evidence = candidate_evidence(record)
            resolution = catchment_resolution(record, catalog.sites)
        except SiteMappingError:
            continue
        if resolution.disposition != "inside_unique_catchment":
            continue
        match = resolution.matches[0]
        site = catalog.sites_by_id[int(match["site_id"])]
        if _clean_text(record.get("launch_country_code_iso2")) != site.country_code_iso2:
            continue
        active = [
            mapping
            for mapping in matching_mappings(record, catalog)
            if mapping.status in {"approved", "provisional"}
        ]
        if any(mapping.site_id != site.id for mapping in active):
            continue
        mapping_keys: dict[str, object] = {
            key_type: evidence[key_type]
            for key_type in ("source_point", "source_takeoff_id", "source_site_token")
            if key_type in evidence
        }
        if not mapping_keys:
            continue
        for key_type, key_value in mapping_keys.items():
            key_targets.setdefault((key_type, key_value), set()).add(site.id)
        candidates.append((record, site, match, mapping_keys))

    conflicting_keys = {key for key, site_ids in key_targets.items() if len(site_ids) > 1}
    decisions: dict[tuple[str, object], dict[str, Any]] = {}
    for record, site, match, mapping_keys in candidates:
        if any(
            (key_type, key_value) in conflicting_keys
            for key_type, key_value in mapping_keys.items()
        ):
            continue
        display_name = _clean_text(record.get("launch_name_raw"))
        point = mapping_keys.get("source_point")
        assert isinstance(point, tuple)
        reference = (
            "automatic-unique-catchment:v1; "
            f"catalog:{snapshot}; site:{site.slug}; "
            f"point:{point[0]:.6f},{point[1]:.6f}; "
            f"distance-km:{float(match['distance_km']):.3f}; "
            f"radius-km:{float(match['catchment_radius_km']):.3f}"
        )
        notes = "Automatically approved from one configured geographic catchment."
        for key_type, key_value in mapping_keys.items():
            identity = (key_type, key_value)
            decision: dict[str, Any] = {
                "decision": "approved",
                "key_type": key_type,
                "site_slug": site.slug,
                "source_display_name": display_name,
                "verification_reference": reference,
                "notes": notes,
            }
            if key_type == "source_point":
                assert isinstance(key_value, tuple)
                decision["key_value"] = None
                decision["point_latitude_deg"] = key_value[0]
                decision["point_longitude_deg"] = key_value[1]
            else:
                assert isinstance(key_value, str)
                decision["key_value"] = key_value
                decision["point_latitude_deg"] = None
                decision["point_longitude_deg"] = None
            existing = decisions.get(identity)
            if existing is None:
                decisions[identity] = decision
            elif existing["site_slug"] != site.slug:
                raise SiteMappingError("Automatic mapping evidence resolves to different sites.")
    return [decisions[key] for key in sorted(decisions, key=lambda item: (item[0], str(item[1])))]


def auto_apply_coordinate_mappings(
    run_key: str,
    *,
    database_url: str | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Persist deterministic coordinate-backed mappings and retain their decision evidence."""

    root = (project_root or repository_root()).resolve()
    records, parser_report, normalized_path, parser_report_path = load_parser_records(run_key, root)
    output_directory = _safe_run_directory(run_key, root) / MAPPING_OUTPUT_DIRECTORY
    decisions_path = output_directory / "automatic-mapping-decisions.jsonl"
    report_path = output_directory / "automatic-mapping-report.json"
    proposals_path = output_directory / "mapping-proposals.jsonl"
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if not isinstance(report, dict) or report.get("run_key") != run_key:
            raise SiteMappingError("Automatic mapping report belongs to another run.")
        return report
    if proposals_path.exists():
        raise SiteMappingError(
            "Automatic mappings must be applied before human proposals are written."
        )
    catalog = load_mapping_catalog(database_url, project_root=root)
    if decisions_path.is_file():
        decisions = read_jsonl(decisions_path)
    else:
        decisions = _automatic_mapping_decisions(records, catalog)
        output_directory.mkdir(parents=True, exist_ok=True)
        _write_jsonl(decisions_path, decisions)
    applied = apply_mapping_decisions(decisions_path, database_url=database_url, project_root=root)
    updated_catalog = load_mapping_catalog(database_url, project_root=root)
    report = {
        "mapping_version": MAPPING_VERSION,
        "run_key": run_key,
        "source": SOURCE_CODE,
        "parser_normalized_path": normalized_path.relative_to(root).as_posix(),
        "parser_report_path": parser_report_path.relative_to(root).as_posix(),
        "parser_normalized_candidates": parser_report["normalized_candidates"],
        "pre_auto_mapping_snapshot_sha256": mapping_snapshot_sha256(catalog),
        "mapping_snapshot_sha256": mapping_snapshot_sha256(updated_catalog),
        "automatic_decisions_path": decisions_path.relative_to(root).as_posix(),
        "automatic_decisions_sha256": hashlib.sha256(decisions_path.read_bytes()).hexdigest(),
        "automatic_decision_count": len(decisions),
        "applied": applied,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def _reviewed_proposals(review_path: Path) -> tuple[str, dict[str, dict[str, Any]]] | None:
    """Load the immutable v4 proposal artifact beside a human decision file."""

    proposals_path = review_path.parent / "mapping-proposals.jsonl"
    report_path = review_path.parent / "proposal-report.json"
    if not proposals_path.is_file() or not report_path.is_file():
        return None
    report = json.loads(report_path.read_text(encoding="utf-8"))
    run_key = report.get("run_key") if isinstance(report, dict) else None
    if not isinstance(run_key, str) or not run_key:
        raise SiteMappingError("Mapping proposal report does not contain its run key.")
    proposals: dict[str, dict[str, Any]] = {}
    for proposal in read_jsonl(proposals_path):
        proposal_id = proposal.get("proposal_id")
        if not isinstance(proposal_id, str) or not proposal_id or proposal_id in proposals:
            raise SiteMappingError(
                "Mapping proposal artifact contains an invalid or duplicate proposal_id."
            )
        proposals[proposal_id] = proposal
    return run_key, proposals


def _eligible_rejection(
    decision: dict[str, Any], context: tuple[str, dict[str, dict[str, Any]]] | None
) -> tuple[str, dict[str, Any]] | None:
    """Validate a minimal human rejection against its immutable proposal."""

    if context is None:
        raise SiteMappingError("Rejected mapping decisions require sibling v4 proposal artifacts.")
    run_key, proposals = context
    proposal_id = decision.get("proposal_id")
    if not isinstance(proposal_id, str) or proposal_id not in proposals:
        raise SiteMappingError(
            "Rejected mapping decision does not belong to its proposal artifact."
        )
    proposal = proposals[proposal_id]
    for field in ("source", "key_type", "key_value", "point_latitude_deg", "point_longitude_deg"):
        if decision.get(field) != proposal.get(field):
            raise SiteMappingError(
                "Rejected mapping decision evidence does not match its immutable proposal."
            )
    if proposal.get("source") != SOURCE_CODE:
        raise SiteMappingError("Rejected mapping proposal has the wrong source.")
    if proposal.get("key_type") not in {"source_site_token", "source_takeoff_id"}:
        return None
    key_value = proposal.get("key_value")
    if not isinstance(key_value, str) or _clean_text(key_value) is None:
        raise SiteMappingError("Rejected stable-key proposal has no exact key value.")
    return run_key, proposal


def apply_mapping_decisions(
    review_path: Path,
    *,
    database_url: str | None = None,
    project_root: Path | None = None,
) -> dict[str, int]:
    """Apply reviewed decisions atomically, persisting only eligible rejections."""

    decisions = _load_decisions(review_path)
    context = _reviewed_proposals(review_path)
    parsed_rejections: list[tuple[str, dict[str, Any]] | None] = []
    for decision in decisions:
        action = _decision_value(decision, "decision")
        if action not in {"provisional", "approved", "rejected"}:
            raise SiteMappingError("Mapping decision must be approved, provisional, or rejected.")
        parsed_rejections.append(
            _eligible_rejection(decision, context) if action == "rejected" else None
        )
    root = project_root or repository_root()
    try:
        connection = open_writable_database(configured_database_url(database_url), root)
    except DatabaseConfigurationError as error:
        raise SiteMappingError("Could not open the configured mapping database.") from error
    inserted = promoted = unchanged = rejected = exclusions_inserted = exclusions_unchanged = 0
    rejected_not_persisted = 0
    try:
        connection.execute("BEGIN IMMEDIATE")
        source_row = connection.execute(
            "SELECT id FROM flight_sources WHERE code = ?", (SOURCE_CODE,)
        ).fetchone()
        if source_row is None:
            raise SiteMappingError("Migrated database does not contain the XCContest source.")
        source_id = int(source_row[0])
        for decision, rejection in zip(decisions, parsed_rejections, strict=True):
            action = _decision_value(decision, "decision")
            if action == "rejected":
                rejected += 1
                if rejection is None:
                    rejected_not_persisted += 1
                    continue
                origin_run_key, proposal = rejection
                key_type = str(proposal["key_type"])
                key_value = str(proposal["key_value"])
                positive = connection.execute(
                    """SELECT id FROM source_site_mappings
                       WHERE source_id = ? AND key_type = ? AND key_value = ?
                         AND status IN ('approved', 'provisional')""",
                    (source_id, key_type, key_value),
                ).fetchone()
                if positive is not None:
                    raise SiteMappingError(
                        "Active positive mapping conflicts with rejected stable key."
                    )
                existing_exclusion = connection.execute(
                    """SELECT id FROM source_site_exclusions
                       WHERE source_id = ? AND key_type = ? AND key_value = ? AND status = 'active'""",
                    (source_id, key_type, key_value),
                ).fetchone()
                if existing_exclusion is not None:
                    exclusions_unchanged += 1
                    continue
                connection.execute(
                    """INSERT INTO source_site_exclusions (
                           source_id, key_type, key_value, origin_run_key, origin_proposal_id,
                           notes, status, created_at_utc, retired_at_utc, retirement_reason
                       ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, NULL, NULL)""",
                    (
                        source_id,
                        key_type,
                        key_value,
                        origin_run_key,
                        str(proposal["proposal_id"]),
                        _clean_text(decision.get("notes")),
                        utc_now(),
                    ),
                )
                exclusions_inserted += 1
                continue
            key_type = _decision_value(decision, "key_type")
            if key_type not in {
                "source_takeoff_id",
                "source_site_token",
                "normalized_name",
                "source_point",
            }:
                raise SiteMappingError("Mapping decision has an unsupported key_type.")
            site_slug = _decision_value(decision, "site_slug")
            site_row = connection.execute(
                "SELECT id FROM sites WHERE slug = ?", (site_slug,)
            ).fetchone()
            if site_row is None:
                raise SiteMappingError(
                    f"Mapping decision references unknown site slug: {site_slug}"
                )
            site_id = int(site_row[0])
            display_name = _clean_text(decision.get("source_display_name"))
            notes = _clean_text(decision.get("notes"))
            verification_reference = _clean_text(decision.get("verification_reference"))
            verified_at = _clean_text(decision.get("verified_at_utc")) or utc_now()
            if action == "approved" and verification_reference is None:
                raise SiteMappingError("Approved mapping decision requires verification_reference.")
            if key_type == "source_point":
                latitude, longitude = _decision_point(decision)
                existing = connection.execute(
                    """SELECT id, site_id, status FROM source_site_mappings
                       WHERE source_id = ? AND key_type = 'source_point'
                         AND point_latitude_deg = ? AND point_longitude_deg = ? AND status <> 'retired'""",
                    (source_id, latitude, longitude),
                ).fetchone()
                key_value = None
            else:
                key_value = _decision_value(decision, "key_value")
                exclusion = connection.execute(
                    """SELECT id FROM source_site_exclusions
                       WHERE source_id = ? AND key_type = ? AND key_value = ? AND status = 'active'""",
                    (source_id, key_type, key_value),
                ).fetchone()
                if exclusion is not None:
                    raise SiteMappingError(
                        "Active rejected stable key conflicts with positive mapping."
                    )
                existing = connection.execute(
                    """SELECT id, site_id, status FROM source_site_mappings
                       WHERE source_id = ? AND key_type = ? AND key_value = ? AND status <> 'retired'""",
                    (source_id, key_type, key_value),
                ).fetchone()
                latitude = longitude = None
            if existing is not None:
                if int(existing[1]) != site_id:
                    raise SiteMappingError(
                        "Active mapping evidence already belongs to a different site."
                    )
                if str(existing[2]) == "provisional" and action == "approved":
                    connection.execute(
                        """UPDATE source_site_mappings
                           SET status = 'approved', verification_reference = ?, verified_at_utc = ?,
                               notes = COALESCE(?, notes) WHERE id = ?""",
                        (verification_reference, verified_at, notes, int(existing[0])),
                    )
                    promoted += 1
                else:
                    unchanged += 1
                continue
            connection.execute(
                """INSERT INTO source_site_mappings (
                       source_id, site_id, key_type, key_value, source_display_name,
                       point_latitude_deg, point_longitude_deg, status, verification_reference,
                       verified_at_utc, notes
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    source_id,
                    site_id,
                    key_type,
                    key_value,
                    display_name,
                    latitude,
                    longitude,
                    action,
                    verification_reference if action == "approved" else None,
                    verified_at if action == "approved" else None,
                    notes,
                ),
            )
            inserted += 1
        connection.commit()
    except sqlite3.Error as error:
        connection.rollback()
        raise SiteMappingError("Could not apply reviewed source-site mappings.") from error
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return {
        "records_seen": len(decisions),
        "inserted": inserted,
        "promoted": promoted,
        "unchanged": unchanged,
        "rejected": rejected,
        "exclusions_inserted": exclusions_inserted,
        "exclusions_unchanged": exclusions_unchanged,
        "rejected_not_persisted": rejected_not_persisted,
    }


def retire_site_exclusion(
    exclusion_id: int,
    retirement_reason: str,
    *,
    database_url: str | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Explicitly retire one active stable-key exclusion without deleting its audit trail."""

    reason = _clean_text(retirement_reason)
    if exclusion_id <= 0 or reason is None:
        raise SiteMappingError("Exclusion retirement requires a positive id and non-empty reason.")
    root = project_root or repository_root()
    try:
        connection = open_writable_database(configured_database_url(database_url), root)
    except DatabaseConfigurationError as error:
        raise SiteMappingError("Could not open the configured mapping database.") from error
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id, status FROM source_site_exclusions WHERE id = ?", (exclusion_id,)
        ).fetchone()
        if row is None:
            raise SiteMappingError("Source-site exclusion does not exist.")
        if str(row[1]) != "active":
            raise SiteMappingError("Source-site exclusion is already retired.")
        retired_at = utc_now()
        connection.execute(
            """UPDATE source_site_exclusions
               SET status = 'retired', retired_at_utc = ?, retirement_reason = ? WHERE id = ?""",
            (retired_at, reason, exclusion_id),
        )
        connection.commit()
    except sqlite3.Error as error:
        connection.rollback()
        raise SiteMappingError("Could not retire source-site exclusion.") from error
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return {"exclusion_id": exclusion_id, "status": "retired", "retired_at_utc": retired_at}
