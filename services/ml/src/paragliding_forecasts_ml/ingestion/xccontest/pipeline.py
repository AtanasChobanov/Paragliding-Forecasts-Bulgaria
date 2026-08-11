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
    _safe_run_directory,
    load_mapping_catalog,
    load_parser_records,
    mapping_snapshot_sha256,
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
            "ingestion_runs",
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


def _actionable_quarantines(report: dict[str, Any], root: Path) -> int:
    path_value = report.get("site_quarantine_path")
    if not isinstance(path_value, str):
        raise PipelineError("Validation report does not identify its quarantine output.")
    quarantine_path = root / path_value
    try:
        records = [
            json.loads(line) for line in quarantine_path.read_text(encoding="utf-8").splitlines()
        ]
    except FileNotFoundError as error:
        raise PipelineError("Validation quarantine output does not exist.") from error
    except json.JSONDecodeError as error:
        raise PipelineError("Validation quarantine output is not valid JSONL.") from error
    return sum(
        isinstance(record, dict) and record.get("reason") in MAPPING_REVIEW_REASONS
        for record in records
    )


def _paused_result(
    *,
    status: str,
    run_key: str,
    parser_report: dict[str, Any],
    proposal_report: dict[str, Any],
    validation_report: dict[str, Any],
    actionable_quarantine_count: int,
) -> dict[str, Any]:
    return {
        "status": status,
        "run_key": run_key,
        "parser": parser_report,
        "mapping_proposals": proposal_report,
        "validation": validation_report,
        "actionable_mapping_quarantine_count": actionable_quarantine_count,
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
    actionable = _actionable_quarantines(validation_report, root)
    if actionable and not persist_approved_only:
        return _paused_result(
            status="awaiting_mapping_review",
            run_key=run_key,
            parser_report=parser_report,
            proposal_report=proposal_report,
            validation_report=validation_report,
            actionable_quarantine_count=actionable,
        )
    if validation_report.get("records_accepted") == 0:
        return _paused_result(
            status="no_accepted_records",
            run_key=run_key,
            parser_report=parser_report,
            proposal_report=proposal_report,
            validation_report=validation_report,
            actionable_quarantine_count=actionable,
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
        )
    except PersistenceError as error:
        raise PipelineError(f"XCContest persistence did not complete: {error}") from error
    return {
        "status": "succeeded",
        "run_key": run_key,
        "parser": parser_report,
        "mapping_proposals": proposal_report,
        "validation": validation_report,
        "actionable_mapping_quarantine_count": actionable,
        "persistence": persistence_report,
    }


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
