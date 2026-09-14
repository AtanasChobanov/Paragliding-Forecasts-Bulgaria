"""Durable orchestration for the XCContest ingestion stages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...storage.sqlite import (
    DatabaseConfigurationError,
    configured_database_url,
    load_site_country_codes,
    open_read_only_database,
)
from .collection_runner import CollectionExecutionError, collect_run
from .models import CollectionReport, CollectorConfig
from .parser import ParseError, parse_run
from .persistence import PersistenceError, load_policy, persist_import
from .site_mapping import (
    SiteMappingError,
    _proposal_id,
    _proposal_key,
    _safe_run_directory,
    load_mapping_catalog,
    load_parser_records,
    mapping_snapshot_sha256,
    read_jsonl,
    repository_root,
    write_mapping_proposals,
)
from .validator import ValidationError, validate_run
from .versions import MAPPING_OUTPUT_DIRECTORY, PARSER_OUTPUT_DIRECTORY, VALIDATION_OUTPUT_DIRECTORY

MAPPING_REVIEW_REASONS = frozenset(
    {
        "unknown_mapping",
        "mapping_not_approved",
        "ambiguous_mapping",
        "mapping_country_mismatch",
    }
)


class PipelineError(RuntimeError):
    """A pipeline stage could not safely continue."""


def _json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise PipelineError(f"{label} does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise PipelineError(f"{label} is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise PipelineError(f"{label} must be a JSON object: {path}")
    return value


def _preflight(policy_path: Path, database_url: str | None) -> tuple[str, tuple[str, ...]]:
    """Validate local prerequisites before a fresh run reaches the source."""

    try:
        load_policy(policy_path)
        resolved_url = configured_database_url(database_url)
        countries = load_site_country_codes(resolved_url)
        connection = open_read_only_database(resolved_url)
    except (DatabaseConfigurationError, PersistenceError) as error:
        raise PipelineError(f"XCContest pipeline preflight failed: {error}") from error
    try:
        required_tables = {
            "flight_sources",
            "sites",
            "source_site_mappings",
            "flight_ingestion_runs",
            "flight_records",
        }
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        available = {str(row[0]) for row in rows}
        missing = sorted(required_tables - available)
        if missing:
            raise PipelineError(
                "XCContest pipeline requires a migrated database; missing tables: "
                + ", ".join(missing)
            )
        if (
            connection.execute("SELECT 1 FROM flight_sources WHERE code = 'xccontest'").fetchone()
            is None
        ):
            raise PipelineError("Migrated database does not contain the XCContest source.")
    except DatabaseConfigurationError:
        raise
    except Exception as error:
        if isinstance(error, PipelineError):
            raise
        raise PipelineError(
            "XCContest pipeline could not inspect the migrated database."
        ) from error
    finally:
        connection.close()
    return resolved_url, countries


def _existing_or_parsed(run_key: str, root: Path) -> dict[str, Any]:
    parser_dir = _safe_run_directory(run_key, root) / PARSER_OUTPUT_DIRECTORY
    if parser_dir.is_dir():
        try:
            _, report, _, _ = load_parser_records(run_key, root)
        except SiteMappingError as error:
            raise PipelineError(f"Existing parser staging is not reusable: {error}") from error
        return report
    try:
        return parse_run(run_key).report
    except (ParseError, FileExistsError) as error:
        raise PipelineError(f"XCContest parser did not complete: {error}") from error


def _existing_or_proposed(run_key: str, root: Path, database_url: str | None) -> dict[str, Any]:
    output_dir = _safe_run_directory(run_key, root) / MAPPING_OUTPUT_DIRECTORY
    if output_dir.is_dir():
        report = _json_object(output_dir / "proposal-report.json", "Mapping proposal report")
        if report.get("run_key") != run_key:
            raise PipelineError("Existing mapping proposal report belongs to another run.")
        return report
    try:
        return write_mapping_proposals(run_key, database_url=database_url)
    except (SiteMappingError, FileExistsError) as error:
        raise PipelineError(f"XCContest mapping proposal did not complete: {error}") from error


def _existing_or_validated(run_key: str, root: Path, database_url: str | None) -> dict[str, Any]:
    try:
        catalog = load_mapping_catalog(database_url, project_root=root)
        snapshot = mapping_snapshot_sha256(catalog)
    except SiteMappingError as error:
        raise PipelineError(
            f"XCContest validation could not read approved mappings: {error}"
        ) from error
    output_dir = _safe_run_directory(run_key, root) / VALIDATION_OUTPUT_DIRECTORY / snapshot
    if output_dir.is_dir():
        report = _json_object(output_dir / "validation-report.json", "Validation report")
        if report.get("run_key") != run_key or report.get("mapping_snapshot_sha256") != snapshot:
            raise PipelineError(
                "Existing validation output does not match the current mapping snapshot."
            )
        return report
    try:
        return validate_run(run_key, database_url=database_url).report
    except (ValidationError, FileExistsError) as error:
        raise PipelineError(f"XCContest validation did not complete: {error}") from error


def _rejected_review_proposal_ids(run_key: str, root: Path) -> frozenset[str]:
    """Load rejections that are tied to this run's immutable proposal artifact."""

    mapping_directory = _safe_run_directory(run_key, root) / MAPPING_OUTPUT_DIRECTORY
    decisions_path = mapping_directory / "mapping-decisions.jsonl"
    if not decisions_path.is_file():
        return frozenset()
    try:
        proposals = read_jsonl(mapping_directory / "mapping-proposals.jsonl")
        decisions = read_jsonl(decisions_path)
    except SiteMappingError as error:
        raise PipelineError(f"Mapping review artifacts are not reusable: {error}") from error
    proposal_by_id: dict[str, dict[str, Any]] = {}
    for proposal in proposals:
        proposal_id = proposal.get("proposal_id")
        if not isinstance(proposal_id, str) or not proposal_id:
            raise PipelineError("Mapping proposal artifact contains an invalid proposal_id.")
        if proposal_id in proposal_by_id:
            raise PipelineError("Mapping proposal artifact contains duplicate proposal_ids.")
        proposal_by_id[proposal_id] = proposal
    rejected: set[str] = set()
    seen: set[str] = set()
    for decision in decisions:
        proposal_id = decision.get("proposal_id")
        if not isinstance(proposal_id, str) or proposal_id not in proposal_by_id:
            raise PipelineError("Mapping decision does not belong to this run's proposal artifact.")
        if proposal_id in seen:
            raise PipelineError("Mapping decisions contain duplicate proposal_ids.")
        seen.add(proposal_id)
        proposal = proposal_by_id[proposal_id]
        if any(
            decision.get(field) != proposal.get(field)
            for field in (
                "source",
                "key_type",
                "key_value",
                "point_latitude_deg",
                "point_longitude_deg",
            )
        ):
            raise PipelineError("Mapping decision evidence does not match its immutable proposal.")
        action = decision.get("decision")
        if action not in {"approved", "provisional", "rejected"}:
            raise PipelineError("Mapping decision must be approved, provisional, or rejected.")
        if action == "rejected":
            rejected.add(proposal_id)
    return frozenset(rejected)


def _actionable_quarantines(report: dict[str, Any], run_key: str, root: Path) -> tuple[int, int]:
    """Return unresolved and explicitly rejected mapping quarantine counts."""

    path_value = report.get("site_quarantine_path")
    if not isinstance(path_value, str):
        raise PipelineError("Validation report does not identify its quarantine output.")
    quarantine_path = root / path_value
    try:
        records = read_jsonl(quarantine_path)
    except SiteMappingError as error:
        raise PipelineError(f"Validation quarantine output is not reusable: {error}") from error
    rejected_proposals = _rejected_review_proposal_ids(run_key, root)
    unresolved = reviewed_rejected = 0
    for record in records:
        if record.get("reason") not in MAPPING_REVIEW_REASONS:
            continue
        candidate = record.get("candidate")
        if not isinstance(candidate, dict):
            raise PipelineError("Mapping-actionable quarantine record has no candidate evidence.")
        try:
            key_type, key_value = _proposal_key(candidate)
        except SiteMappingError as error:
            raise PipelineError(
                "Mapping-actionable quarantine record has unusable proposal evidence."
            ) from error
        proposal_id = _proposal_id(key_type, key_value)
        if proposal_id in rejected_proposals:
            reviewed_rejected += 1
        else:
            unresolved += 1
    return unresolved, reviewed_rejected


def _paused_result(
    *,
    status: str,
    run_key: str,
    parser_report: dict[str, Any],
    proposal_report: dict[str, Any],
    validation_report: dict[str, Any],
    actionable_quarantine_count: int,
    reviewed_rejected_mapping_quarantine_count: int = 0,
) -> dict[str, Any]:
    return {
        "status": status,
        "run_key": run_key,
        "parser": parser_report,
        "mapping_proposals": proposal_report,
        "validation": validation_report,
        "actionable_mapping_quarantine_count": actionable_quarantine_count,
        "reviewed_rejected_mapping_quarantine_count": reviewed_rejected_mapping_quarantine_count,
        "next_step": "Review/apply mapping decisions, then run xccontest-ingest resume --run-key <uuid>.",
    }


def resume_run(
    run_key: str,
    policy_path: Path,
    *,
    database_url: str | None = None,
    persist_approved_only: bool = False,
) -> dict[str, Any]:
    """Resume offline stages from durable evidence without contacting XCContest."""

    resolved_url, _ = _preflight(policy_path, database_url)
    root = repository_root()
    parser_report = _existing_or_parsed(run_key, root)
    proposal_report = _existing_or_proposed(run_key, root, resolved_url)
    validation_report = _existing_or_validated(run_key, root, resolved_url)
    actionable, reviewed_rejected = _actionable_quarantines(validation_report, run_key, root)
    if actionable and not persist_approved_only:
        return _paused_result(
            status="awaiting_mapping_review",
            run_key=run_key,
            parser_report=parser_report,
            proposal_report=proposal_report,
            validation_report=validation_report,
            actionable_quarantine_count=actionable,
            reviewed_rejected_mapping_quarantine_count=reviewed_rejected,
        )
    if validation_report.get("records_accepted") == 0:
        return _paused_result(
            status="no_accepted_records",
            run_key=run_key,
            parser_report=parser_report,
            proposal_report=proposal_report,
            validation_report=validation_report,
            actionable_quarantine_count=actionable,
            reviewed_rejected_mapping_quarantine_count=reviewed_rejected,
        )
    snapshot = validation_report.get("mapping_snapshot_sha256")
    if not isinstance(snapshot, str):
        raise PipelineError("Validation report does not identify its mapping snapshot.")
    try:
        persistence_report = persist_import(
            run_key,
            snapshot,
            policy_path,
            database_url=resolved_url,
            mapping_review_complete=not actionable,
        )
    except PersistenceError as error:
        raise PipelineError(f"XCContest persistence did not complete: {error}") from error
    status = persistence_report.get("status")
    if status not in {"succeeded", "awaiting_reconciliation_review"}:
        raise PipelineError("XCContest persistence returned an unsupported status.")
    result = {
        "status": status,
        "run_key": run_key,
        "parser": parser_report,
        "mapping_proposals": proposal_report,
        "validation": validation_report,
        "actionable_mapping_quarantine_count": actionable,
        "reviewed_rejected_mapping_quarantine_count": reviewed_rejected,
        "persistence": persistence_report,
    }
    if status == "awaiting_reconciliation_review":
        result["next_step"] = (
            "Review reconciliation decisions, then run xccontest-ingest resume --run-key <uuid>."
        )
    return result


def fresh_run(
    config: CollectorConfig,
    policy_path: Path,
    *,
    database_url: str | None = None,
    persist_approved_only: bool = False,
) -> dict[str, Any]:
    """Collect a new raw run, then execute its offline stages through the review gate."""

    resolved_url, countries = _preflight(policy_path, database_url)
    if config.country_codes != countries:
        raise PipelineError(
            "Fresh pipeline country scope does not match the preflight database scope."
        )
    try:
        collection_report = collect_run(config)
    except CollectionExecutionError as error:
        raise PipelineError(str(error)) from error
    if collection_report.status != "complete":
        return {
            "status": "incomplete_coverage",
            "run_key": collection_report.run_key,
            "collector": _collection_summary(collection_report),
            "next_step": "Review the immutable manifest coverage before running offline stages.",
        }
    result = resume_run(
        collection_report.run_key,
        policy_path,
        database_url=resolved_url,
        persist_approved_only=persist_approved_only,
    )
    return {"collector": _collection_summary(collection_report), **result}


def _collection_summary(report: CollectionReport) -> dict[str, Any]:
    return {
        "status": report.status,
        "manifest_relative_path": report.manifest_relative_path,
        "manifest_sha256": report.manifest_sha256,
        "country_codes": list(report.country_codes),
        "completed_seasons": list(report.completed_seasons),
        "artifact_count": report.artifact_count,
        "row_observations_seen": report.row_observations_seen,
        "distinct_source_flights_seen": report.distinct_source_flights_seen,
        "repeated_source_flight_observations": report.repeated_source_flight_observations,
    }
