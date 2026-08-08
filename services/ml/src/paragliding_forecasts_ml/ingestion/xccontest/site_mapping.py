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
class MappingCatalog:
    source_id: int
    sites: tuple[Site, ...]
    mappings: tuple[SourceSiteMapping, ...]

    @property
    def sites_by_id(self) -> dict[int, Site]:
        return {site.id: site for site in self.sites}


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
    connection = open_read_only_database(url, root)
    try:
        source = connection.execute(
            "SELECT id FROM flight_sources WHERE code = ?", (SOURCE_CODE,)
        ).fetchone()
        if source is None:
            raise SiteMappingError("Migrated database does not contain the XCContest source.")
        site_rows = connection.execute(
            """SELECT id, slug, name, country_code_iso2, site_type, latitude_deg, longitude_deg,
                      catchment_radius_km
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
    payload = [
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
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _proposal_key(record: dict[str, Any]) -> tuple[str, object]:
    evidence = candidate_evidence(record)
    for key_type in ("source_takeoff_id", "source_site_token", "normalized_name", "source_point"):
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
    """Create grouped, human-reviewable proposals without changing SQLite."""

    root = (project_root or repository_root()).resolve()
    records, report, normalized_path, report_path = load_parser_records(run_key, root)
    catalog = load_mapping_catalog(database_url, project_root=root)
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        if record.get("parser_status") != "normalized":
            continue
        try:
            if any(mapping.status == "approved" for mapping in matching_mappings(record, catalog)):
                continue
            key_type, key_value = _proposal_key(record)
        except SiteMappingError:
            continue
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
            },
        )
        group["candidate_count"] += 1
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
    if output_directory.exists():
        raise FileExistsError(f"Refusing to overwrite mapping proposal output: {output_directory}")
    output_directory.mkdir(parents=True, exist_ok=False)
    proposals_path = output_directory / "mapping-proposals.jsonl"
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
                    if key not in {"source_display_names", "seasons"}
                },
                "source_display_names": sorted(group["source_display_names"]),
                "seasons": sorted(group["seasons"]),
                "recommendation": reason,
            }
        )
    proposal_records.sort(key=lambda item: (item["key_type"], str(item["key_value"])))
    with proposals_path.open("x", encoding="utf-8", newline="\n") as output:
        for proposal in proposal_records:
            output.write(json.dumps(proposal, ensure_ascii=False, sort_keys=True))
            output.write("\n")
    report_payload = {
        "mapping_version": MAPPING_VERSION,
        "run_key": run_key,
        "source": SOURCE_CODE,
        "parser_normalized_path": normalized_path.relative_to(root).as_posix(),
        "parser_report_path": report_path.relative_to(root).as_posix(),
        "parser_normalized_candidates": report["normalized_candidates"],
        "proposal_count": len(proposal_records),
        "mapping_snapshot_sha256": mapping_snapshot_sha256(catalog),
    }
    report_path = output_directory / "proposal-report.json"
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


def apply_mapping_decisions(
    review_path: Path,
    *,
    database_url: str | None = None,
    project_root: Path | None = None,
) -> dict[str, int]:
    """Apply a fully reviewed local JSONL file in one SQLite transaction."""

    decisions = _load_decisions(review_path)
    root = project_root or repository_root()
    connection = open_writable_database(configured_database_url(database_url), root)
    inserted = promoted = unchanged = rejected = 0
    try:
        connection.execute("BEGIN IMMEDIATE")
        source_row = connection.execute(
            "SELECT id FROM flight_sources WHERE code = ?", (SOURCE_CODE,)
        ).fetchone()
        if source_row is None:
            raise SiteMappingError("Migrated database does not contain the XCContest source.")
        source_id = int(source_row[0])
        for decision in decisions:
            action = _decision_value(decision, "decision")
            if action == "rejected":
                rejected += 1
                continue
            if action not in {"provisional", "approved"}:
                raise SiteMappingError(
                    "Mapping decision must be approved, provisional, or rejected."
                )
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
                           AND point_latitude_deg = ? AND point_longitude_deg = ?
                           AND status <> 'retired'""",
                    (source_id, latitude, longitude),
                ).fetchone()
                key_value = None
            else:
                key_value = _decision_value(decision, "key_value")
                existing = connection.execute(
                    """SELECT id, site_id, status FROM source_site_mappings
                         WHERE source_id = ? AND key_type = ? AND key_value = ?
                           AND status <> 'retired'""",
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
                                  notes = COALESCE(?, notes)
                            WHERE id = ?""",
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
    except (sqlite3.Error, DatabaseConfigurationError) as error:
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
    }
