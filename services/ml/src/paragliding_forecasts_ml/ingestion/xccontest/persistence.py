"""Transactional persistence of verified XCContest validation snapshots."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paragliding_forecasts_ml.storage.sqlite import (
    DatabaseConfigurationError,
    configured_database_url,
    open_writable_database,
)

from .models import SOURCE_CODE
from .site_mapping import _safe_run_directory, repository_root, utc_now
from .versions import (
    COLLECTOR_VERSION,
    PARSER_VERSION,
    PERSISTENCE_VERSION,
    VALIDATION_OUTPUT_DIRECTORY,
    VALIDATION_VERSION,
)

SHA = re.compile(r"[0-9a-f]{64}\Z")
UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
UUID4 = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
POLICY_KEYS = {
    "permission_basis",
    "permission_reference",
    "model_training_allowed",
    "operational_use_allowed",
}
BASES = {
    "written_permission",
    "source_terms",
    "owner_export",
    "official_api_terms",
    "pilot_provided",
}
ROUTES = {
    "free_flight",
    "free_triangle",
    "fai_triangle",
    "closed_free_triangle",
    "closed_fai_triangle",
    "other",
    "unknown",
}
KEY_TYPES = {"source_takeoff_id", "source_site_token", "normalized_name", "source_point"}


class PersistenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class Prepared:
    report: dict[str, Any]
    records: tuple[dict[str, Any], ...]
    manifest: dict[str, Any]
    report_path: Path
    accepted_path: Path
    report_sha: str
    accepted_sha: str


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_object(path: Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PersistenceError(f"{name} is not readable JSON.") from error
    if not isinstance(value, dict):
        raise PersistenceError(f"{name} must be a JSON object.")
    return value


def local_path(value: object, root: Path, name: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise PersistenceError(f"{name} must be a repository-relative POSIX path.")
    path = (root / Path(value)).resolve()
    if Path(value).is_absolute() or ".." in Path(value).parts or not path.is_file():
        raise PersistenceError(f"{name} is unsafe or missing.")
    try:
        path.relative_to(root)
    except ValueError as error:
        raise PersistenceError(f"{name} escapes the repository.") from error
    return path


def sha(value: object, name: str) -> str:
    if not isinstance(value, str) or SHA.fullmatch(value) is None:
        raise PersistenceError(f"{name} must be lowercase SHA-256.")
    return value


def timestamp(value: object, name: str) -> str:
    if not isinstance(value, str) or UTC.fullmatch(value) is None:
        raise PersistenceError(f"{name} must be UTC.")
    return value


def load_policy(path: Path) -> tuple[str, str, bool, bool]:
    policy = json_object(path, "Import policy")
    if set(policy) != POLICY_KEYS:
        raise PersistenceError("Import policy must contain exactly four permission fields.")
    basis, ref, training, operational = (
        policy["permission_basis"],
        policy["permission_reference"],
        policy["model_training_allowed"],
        policy["operational_use_allowed"],
    )
    if (
        not isinstance(basis, str)
        or basis not in BASES
        or not isinstance(ref, str)
        or not ref.strip()
    ):
        raise PersistenceError("Import policy has invalid permission metadata.")
    if type(training) is not bool or type(operational) is not bool:
        raise PersistenceError("Import policy usage flags must be JSON booleans.")
    return basis, ref.strip(), training, operational


def validate_record(row: dict[str, Any]) -> None:
    if (
        row.get("source") != SOURCE_CODE
        or row.get("validation_status") != "accepted"
        or row.get("validator_version") != VALIDATION_VERSION
    ):
        raise PersistenceError("Accepted flight has incompatible validation metadata.")
    if not isinstance(row.get("source_flight_id"), str) or not row["source_flight_id"].isdigit():
        raise PersistenceError("Accepted flight has invalid source ID.")
    if not isinstance(row.get("source_flight_url"), str) or not row["source_flight_url"].startswith(
        "https://www.xcontest.org/"
    ):
        raise PersistenceError("Accepted flight has invalid source URL.")
    if row.get("route_type") not in ROUTES or row.get("mapping_key_type") not in KEY_TYPES:
        raise PersistenceError("Accepted flight has invalid route or mapping type.")
    if not isinstance(row.get("source_site_mapping_id"), int) or not isinstance(
        row.get("site_id"), int
    ):
        raise PersistenceError("Accepted flight has invalid mapping evidence.")
    if (
        type(row.get("scored_distance_km")) not in (int, float)
        or not 100 <= float(row["scored_distance_km"]) <= 2000
    ):
        raise PersistenceError("Accepted flight has invalid distance.")
    if row.get("duration_seconds") is not None and (
        type(row["duration_seconds"]) is not int or not 1 <= row["duration_seconds"] <= 86400
    ):
        raise PersistenceError("Accepted flight has invalid duration.")
    timestamp(row.get("takeoff_at_utc"), "Accepted takeoff timestamp")
    timestamp(row.get("validated_at_utc"), "Accepted validation timestamp")


def prepare(run_key: str, snapshot: str, root: Path) -> Prepared:
    if UUID4.fullmatch(run_key) is None:
        raise PersistenceError("run_key must be lowercase UUID v4.")
    snapshot = sha(snapshot, "validation_snapshot")
    folder = _safe_run_directory(run_key, root) / VALIDATION_OUTPUT_DIRECTORY / snapshot
    report_path = folder / "validation-report.json"
    report = json_object(report_path, "Validation report")
    if (
        report.get("source") != SOURCE_CODE
        or report.get("run_key") != run_key
        or report.get("validator_version") != VALIDATION_VERSION
        or report.get("parser_version") != PARSER_VERSION
        or report.get("mapping_snapshot_sha256") != snapshot
    ):
        raise PersistenceError("Validation report does not match requested snapshot.")
    paths = {}
    for path_key, hash_key in (
        ("accepted_flights_path", "accepted_flights_sha256"),
        ("site_quarantine_path", "site_quarantine_sha256"),
        ("parser_normalized_path", "parser_normalized_sha256"),
        ("parser_report_path", "parser_report_sha256"),
        ("raw_manifest_path", "raw_manifest_sha256"),
    ):
        path = local_path(report.get(path_key), root, path_key)
        if digest(path) != sha(report.get(hash_key), hash_key):
            raise PersistenceError(f"{path_key} SHA-256 does not match report.")
        paths[path_key] = path
    manifest = json_object(paths["raw_manifest_path"], "Raw manifest")
    if (
        manifest.get("source") != SOURCE_CODE
        or manifest.get("run_key") != run_key
        or manifest.get("status") not in {"complete", "incomplete"}
    ):
        raise PersistenceError("Raw manifest is incompatible.")
    if not isinstance(manifest.get("source_url"), str) or not manifest["source_url"].startswith(
        "https://www.xcontest.org/"
    ):
        raise PersistenceError("Raw manifest source URL is invalid.")
    timestamp(manifest.get("started_at_utc"), "Raw manifest started_at_utc")
    try:
        records = tuple(
            json.loads(line)
            for line in paths["accepted_flights_path"].read_text(encoding="utf-8").splitlines()
        )
    except json.JSONDecodeError as error:
        raise PersistenceError("Accepted flights JSONL is invalid.") from error
    counters = (
        "records_seen",
        "records_accepted",
        "records_rejected",
        "records_quarantined",
        "records_deduplicated",
    )
    if (
        any(type(report.get(key)) is not int or report[key] < 0 for key in counters)
        or report["records_accepted"] != len(records)
        or report["records_seen"] != sum(report[key] for key in counters[1:])
    ):
        raise PersistenceError("Validation counters do not reconcile.")
    seen: set[str] = set()
    for row in records:
        if not isinstance(row, dict):
            raise PersistenceError("Accepted flights JSONL row must be an object.")
        validate_record(row)
        if row["source_flight_id"] in seen:
            raise PersistenceError("Accepted flights contain duplicate source IDs.")
        seen.add(row["source_flight_id"])
    return Prepared(
        report,
        records,
        manifest,
        report_path,
        paths["accepted_flights_path"],
        digest(report_path),
        digest(paths["accepted_flights_path"]),
    )


def mapping_hash(connection: sqlite3.Connection, source_id: int) -> str:
    rows = connection.execute(
        "SELECT id, site_id, key_type, key_value, point_latitude_deg, point_longitude_deg, status, verification_reference, verified_at_utc FROM source_site_mappings WHERE source_id = ? ORDER BY id",
        (source_id,),
    ).fetchall()
    payload = [
        {
            "id": int(r[0]),
            "site_id": int(r[1]),
            "key_type": str(r[2]),
            "key_value": r[3],
            "point_latitude_deg": r[4],
            "point_longitude_deg": r[5],
            "status": str(r[6]),
            "verification_reference": r[7],
            "verified_at_utc": r[8],
        }
        for r in rows
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def persist_import(
    run_key: str,
    validation_snapshot: str,
    policy_path: Path,
    *,
    database_url: str | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    root = (project_root or repository_root()).resolve()
    prepared = prepare(run_key, validation_snapshot, root)
    basis, ref, training, operational = load_policy(policy_path)
    try:
        connection = open_writable_database(configured_database_url(database_url), root)
    except DatabaseConfigurationError as error:
        raise PersistenceError("Could not open migrated database for writing.") from error
    try:
        connection.execute("BEGIN IMMEDIATE")
        source = connection.execute(
            "SELECT id FROM flight_sources WHERE code = ?", (SOURCE_CODE,)
        ).fetchone()
        if source is None:
            raise PersistenceError("Database does not contain XCContest source.")
        source_id = int(source[0])
        if mapping_hash(connection, source_id) != validation_snapshot:
            raise PersistenceError("Approved mapping snapshot changed; re-run validation.")
        if connection.execute(
            "SELECT 1 FROM ingestion_runs WHERE run_key = ?", (run_key,)
        ).fetchone():
            raise PersistenceError("Run already exists; T-014 owns retry policy.")
        for row in prepared.records:
            mapping = connection.execute(
                "SELECT source_id, site_id, status FROM source_site_mappings WHERE id = ?",
                (row["source_site_mapping_id"],),
            ).fetchone()
            if mapping is None or tuple(mapping) != (source_id, row["site_id"], "approved"):
                raise PersistenceError(
                    "Accepted flight mapping is no longer approved XCContest evidence."
                )
        now = utc_now()
        pipeline = (
            f"{COLLECTOR_VERSION}|{PARSER_VERSION}|{VALIDATION_VERSION}|{PERSISTENCE_VERSION}"
        )
        notes = json.dumps(
            {
                "accepted_flights_path": prepared.accepted_path.relative_to(root).as_posix(),
                "accepted_flights_sha256": prepared.accepted_sha,
                "mapping_snapshot_sha256": validation_snapshot,
                "validation_report_path": prepared.report_path.relative_to(root).as_posix(),
                "validation_report_sha256": prepared.report_sha,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        cur = connection.execute(
            "INSERT INTO ingestion_runs (run_key,source_id,ingestion_method,status,source_url,permission_basis,permission_reference,model_training_allowed,operational_use_allowed,raw_manifest_path,raw_manifest_sha256,pipeline_version,started_at_utc,completed_at_utc,records_seen,records_accepted,records_rejected,records_quarantined,records_deduplicated,notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_key,
                source_id,
                "browser_ui",
                "succeeded",
                prepared.manifest["source_url"],
                basis,
                ref,
                int(training),
                int(operational),
                prepared.report["raw_manifest_path"],
                prepared.report["raw_manifest_sha256"],
                pipeline,
                prepared.manifest["started_at_utc"],
                now,
                *[
                    prepared.report[key]
                    for key in (
                        "records_seen",
                        "records_accepted",
                        "records_rejected",
                        "records_quarantined",
                        "records_deduplicated",
                    )
                ],
                notes,
            ),
        )
        run_id = int(cur.lastrowid)
        rows = [
            (
                source_id,
                row["source_flight_id"],
                row["source_flight_url"],
                row["source_site_mapping_id"],
                row["takeoff_at_utc"],
                row["duration_seconds"],
                row["scored_distance_km"],
                row["route_type"],
                "metadata",
                f"metadata-only; validator={VALIDATION_VERSION}; mapping_snapshot_sha256={validation_snapshot}; mapping_key_type={row['mapping_key_type']}",
                row["validated_at_utc"],
                run_id,
                run_id,
                now,
                now,
            )
            for row in prepared.records
        ]
        connection.executemany(
            "INSERT INTO flight_records (source_id,source_flight_id,source_flight_url,source_site_mapping_id,takeoff_at_utc,duration_seconds,scored_distance_km,route_type,validation_level,validation_notes,validated_at_utc,created_by_ingestion_run_id,last_validated_by_ingestion_run_id,created_at_utc,updated_at_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        connection.commit()
    except (PersistenceError, sqlite3.Error) as error:
        connection.rollback()
        if isinstance(error, PersistenceError):
            raise
        raise PersistenceError(
            "SQLite transaction did not complete; no flights were persisted."
        ) from error
    finally:
        connection.close()
    return {
        "ingestion_run_id": run_id,
        "run_key": run_key,
        "status": "succeeded",
        "records_seen": prepared.report["records_seen"],
        "records_accepted": prepared.report["records_accepted"],
        "records_rejected": prepared.report["records_rejected"],
        "records_quarantined": prepared.report["records_quarantined"],
        "records_deduplicated": prepared.report["records_deduplicated"],
        "validation_snapshot_sha256": validation_snapshot,
        "accepted_flights_sha256": prepared.accepted_sha,
        "pipeline_version": pipeline,
    }
