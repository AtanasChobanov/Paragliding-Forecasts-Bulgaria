"""Approved-only validation of versioned XCContest parser staging outputs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import SOURCE_CODE
from .site_mapping import (
    MappingCatalog,
    SiteMappingError,
    _clean_text,
    _safe_run_directory,
    candidate_evidence,
    catchment_suggestions,
    load_mapping_catalog,
    load_parser_records,
    mapping_snapshot_sha256,
    matching_mappings,
    repository_root,
    utc_now,
)
from .versions import PARSER_VERSION, VALIDATION_OUTPUT_DIRECTORY, VALIDATION_VERSION


class ValidationError(RuntimeError):
    """A parser candidate cannot safely enter validated staging."""


@dataclass(frozen=True)
class ValidatedRun:
    output_dir: Path
    accepted_path: Path
    quarantine_path: Path
    report_path: Path
    report: dict[str, Any]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mapping_resolution(record: dict[str, Any], catalog: MappingCatalog) -> dict[str, Any]:
    try:
        evidence = candidate_evidence(record)
        mappings = matching_mappings(record, catalog)
    except SiteMappingError as error:
        return {"outcome": "quarantined", "reason": str(error), "mapping_ids": []}
    approved = [mapping for mapping in mappings if mapping.status == "approved"]
    provisional = [mapping for mapping in mappings if mapping.status == "provisional"]
    if not approved:
        return {
            "outcome": "quarantined",
            "reason": "mapping_not_approved" if provisional else "unknown_mapping",
            "mapping_ids": [mapping.id for mapping in mappings],
        }
    target_site_ids = {mapping.site_id for mapping in approved}
    if len(target_site_ids) != 1:
        return {
            "outcome": "quarantined",
            "reason": "ambiguous_mapping",
            "mapping_ids": [mapping.id for mapping in approved],
        }
    site = catalog.sites_by_id[target_site_ids.pop()]
    country = _clean_text(record.get("launch_country_code_iso2"))
    if country != site.country_code_iso2:
        return {
            "outcome": "quarantined",
            "reason": "mapping_country_mismatch",
            "mapping_ids": [mapping.id for mapping in approved],
        }
    for key_type in (
        "source_takeoff_id",
        "source_site_token",
        "normalized_name",
        "source_point",
    ):
        if key_type not in evidence:
            continue
        matching = [
            mapping
            for mapping in approved
            if mapping.key_type == key_type and mapping.site_id == site.id
        ]
        if matching:
            mapping = min(matching, key=lambda item: item.id)
            return {
                "outcome": "accepted",
                "mapping_id": mapping.id,
                "mapping_key_type": mapping.key_type,
                "site_id": site.id,
                "site_slug": site.slug,
            }
    raise ValidationError("Approved mapping resolution did not select a matching evidence key.")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            output.write("\n")


def validate_run(
    run_key: str,
    *,
    database_url: str | None = None,
    project_root: Path | None = None,
) -> ValidatedRun:
    """Validate one parser-v2 run against approved source-site mappings only."""

    root = (project_root or repository_root()).resolve()
    try:
        records, parser_report, normalized_path, parser_report_path = load_parser_records(
            run_key, root
        )
        catalog = load_mapping_catalog(database_url, project_root=root)
    except SiteMappingError as error:
        raise ValidationError(str(error)) from error
    if parser_report.get("parser_version") != PARSER_VERSION:
        raise ValidationError("Validator requires the current compatible parser staging version.")
    validation_time = utc_now()
    accepted: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    for record in records:
        source_flight_id = _clean_text(record.get("source_flight_id"))
        if record.get("parser_status") != "normalized":
            quarantined.append(
                {
                    "source": SOURCE_CODE,
                    "source_flight_id": source_flight_id,
                    "validation_status": "quarantined",
                    "reason": "parser_conflicted",
                    "candidate": record,
                }
            )
            continue
        resolution = _mapping_resolution(record, catalog)
        if resolution["outcome"] == "accepted":
            accepted.append(
                {
                    **record,
                    "validation_status": "accepted",
                    "validator_version": VALIDATION_VERSION,
                    "validated_at_utc": validation_time,
                    "source_site_mapping_id": resolution["mapping_id"],
                    "site_id": resolution["site_id"],
                    "site_slug": resolution["site_slug"],
                    "mapping_key_type": resolution["mapping_key_type"],
                }
            )
            continue
        suggestions = catchment_suggestions(record, catalog.sites)
        quarantined.append(
            {
                "source": SOURCE_CODE,
                "source_flight_id": source_flight_id,
                "validation_status": "quarantined",
                "reason": resolution["reason"],
                "matching_mapping_ids": resolution["mapping_ids"],
                "catchment_suggestions": suggestions,
                "candidate": record,
            }
        )
    seen = parser_report.get("row_observations_seen")
    rejected = parser_report.get("records_rejected")
    deduplicated = parser_report.get("duplicate_observations_removed")
    if not all(isinstance(value, int) and value >= 0 for value in (seen, rejected, deduplicated)):
        raise ValidationError("Parser report does not expose non-negative ingestion counters.")
    if seen != len(accepted) + len(quarantined) + rejected + deduplicated:
        raise ValidationError(
            "Validation outcomes do not reconcile with parser observation counters."
        )
    manifest_path = root / str(parser_report.get("raw_manifest_path", ""))
    if not manifest_path.is_file():
        raise ValidationError("Parser report raw manifest path does not identify an existing file.")
    mapping_snapshot = mapping_snapshot_sha256(catalog)
    output_dir = _safe_run_directory(run_key, root) / VALIDATION_OUTPUT_DIRECTORY / mapping_snapshot
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite validation staging output: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=False)
    accepted_path = output_dir / "accepted-flights.jsonl"
    quarantine_path = output_dir / "site-quarantine.jsonl"
    report_path = output_dir / "validation-report.json"
    _write_jsonl(accepted_path, accepted)
    _write_jsonl(quarantine_path, quarantined)

    report = {
        "validator_version": VALIDATION_VERSION,
        "source": SOURCE_CODE,
        "run_key": run_key,
        "validated_at_utc": validation_time,
        "parser_version": parser_report["parser_version"],
        "parser_normalized_path": normalized_path.relative_to(root).as_posix(),
        "parser_normalized_sha256": _sha256(normalized_path),
        "parser_report_path": parser_report_path.relative_to(root).as_posix(),
        "parser_report_sha256": _sha256(parser_report_path),
        "raw_manifest_path": manifest_path.relative_to(root).as_posix(),
        "raw_manifest_sha256": _sha256(manifest_path),
        "mapping_snapshot_sha256": mapping_snapshot,
        "accepted_flights_path": accepted_path.relative_to(root).as_posix(),
        "accepted_flights_sha256": _sha256(accepted_path),
        "site_quarantine_path": quarantine_path.relative_to(root).as_posix(),
        "site_quarantine_sha256": _sha256(quarantine_path),
        "records_seen": seen,
        "records_accepted": len(accepted),
        "records_rejected": rejected,
        "records_quarantined": len(quarantined),
        "records_deduplicated": deduplicated,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return ValidatedRun(output_dir, accepted_path, quarantine_path, report_path, report)
