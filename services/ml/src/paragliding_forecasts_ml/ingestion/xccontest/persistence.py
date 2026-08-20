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
from .reconciliation import (
    ReconciliationAction,
    ReconciliationError,
    build_quality_notes,
    canonical_flight,
    compare_flight,
    decisions_sha256,
    load_review_decisions,
    plan_sha256,
    proposal_for,
    write_or_load_proposals,
)
from .site_mapping import _safe_run_directory, repository_root, utc_now
from .versions import (
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
        or not isinstance(manifest.get("collector_version"), str)
        or not manifest["collector_version"]
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


def _incoming_record(row: dict[str, Any]) -> dict[str, Any]:
    """Add persistence-owned validation values to a validated staging row."""

    return {**row, "track_url": row.get("track_url"), "validation_level": "metadata"}


def _existing_flight(
    connection: sqlite3.Connection, source_id: int, source_flight_id: str
) -> dict[str, Any] | None:
    row = connection.execute(
        """SELECT fr.id, fr.source_flight_url, fr.source_site_mapping_id, fr.takeoff_at_utc,
                  fr.duration_seconds, fr.scored_distance_km, fr.route_type, fr.track_url,
                  fr.validation_level, ssm.key_type AS mapping_key_type
             FROM flight_records AS fr
             INNER JOIN source_site_mappings AS ssm ON ssm.id = fr.source_site_mapping_id
            WHERE fr.source_id = ? AND fr.source_flight_id = ?""",
        (source_id, source_flight_id),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": int(row[0]),
        "source_flight_url": str(row[1]),
        "source_site_mapping_id": int(row[2]),
        "takeoff_at_utc": str(row[3]),
        "duration_seconds": row[4],
        "scored_distance_km": row[5],
        "route_type": str(row[6]),
        "track_url": row[7],
        "validation_level": str(row[8]),
        "mapping_key_type": str(row[9]),
    }


def _load_run_notes(value: object) -> dict[str, Any]:
    """Upgrade existing unversioned JSON provenance lazily, without losing it."""

    if not isinstance(value, str) or not value:
        return {"schema_version": 2, "persistence_events": []}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {"schema_version": 2, "legacy_notes": value, "persistence_events": []}
    if (
        isinstance(parsed, dict)
        and parsed.get("schema_version") == 2
        and isinstance(parsed.get("persistence_events"), list)
    ):
        return parsed
    return {"schema_version": 2, "legacy_provenance": parsed, "persistence_events": []}


def _event_sha256(
    *,
    run_key: str,
    validation_snapshot: str,
    prepared: Prepared,
    mapping_review_complete: bool,
) -> str:
    """Identify one applied validation snapshot, independently of its prior DB state."""

    value = {
        "schema_version": 1,
        "run_key": run_key,
        "validation_snapshot_sha256": validation_snapshot,
        "validation_report_sha256": prepared.report_sha,
        "accepted_flights_sha256": prepared.accepted_sha,
        "mapping_review_complete": mapping_review_complete,
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _run_event(
    *,
    event_sha256: str,
    validation_snapshot: str,
    prepared: Prepared,
    root: Path,
    plan: str,
    mapping_review_complete: bool,
    decisions_digest: str | None,
    counts: dict[str, int],
    now: str,
) -> dict[str, Any]:
    return {
        "event_sha256": event_sha256,
        "event_type": "reconciliation_applied",
        "applied_at_utc": now,
        "validation_snapshot_sha256": validation_snapshot,
        "validation_report_path": prepared.report_path.relative_to(root).as_posix(),
        "validation_report_sha256": prepared.report_sha,
        "accepted_flights_path": prepared.accepted_path.relative_to(root).as_posix(),
        "accepted_flights_sha256": prepared.accepted_sha,
        "reconciliation_plan_sha256": plan,
        "reconciliation_decisions_sha256": decisions_digest,
        "mapping_review_complete": mapping_review_complete,
        "counts": counts,
    }


def _existing_run(
    connection: sqlite3.Connection, run_key: str
) -> tuple[int, int, str, str, str, str, str, int, int, str] | None:
    row = connection.execute(
        """SELECT id, source_id, source_url, permission_basis, permission_reference,
                  raw_manifest_path, raw_manifest_sha256, model_training_allowed,
                  operational_use_allowed, notes
             FROM flight_ingestion_runs WHERE run_key = ?""",
        (run_key,),
    ).fetchone()
    if row is None:
        return None
    return (
        int(row[0]),
        int(row[1]),
        str(row[2]),
        str(row[3]),
        str(row[4]),
        str(row[5]),
        str(row[6]),
        int(row[7]),
        int(row[8]),
        str(row[9]) if row[9] is not None else "",
    )


def persist_import(
    run_key: str,
    validation_snapshot: str,
    policy_path: Path,
    *,
    database_url: str | None = None,
    project_root: Path | None = None,
    mapping_review_complete: bool = True,
) -> dict[str, Any]:
    """Persist or reconcile one integrity-verified XCContest validation snapshot offline."""

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
        for row in prepared.records:
            mapping = connection.execute(
                "SELECT source_id, site_id, status FROM source_site_mappings WHERE id = ?",
                (row["source_site_mapping_id"],),
            ).fetchone()
            if mapping is None or tuple(mapping) != (source_id, row["site_id"], "approved"):
                raise PersistenceError(
                    "Accepted flight mapping is no longer approved XCContest evidence."
                )

        pipeline = (
            f"{prepared.manifest['collector_version']}|{PARSER_VERSION}|{VALIDATION_VERSION}|"
            f"{PERSISTENCE_VERSION}"
        )
        existing_run = _existing_run(connection, run_key)
        event_sha = _event_sha256(
            run_key=run_key,
            validation_snapshot=validation_snapshot,
            prepared=prepared,
            mapping_review_complete=mapping_review_complete,
        )
        if existing_run is not None:
            (
                run_id,
                existing_source_id,
                existing_source_url,
                existing_basis,
                existing_reference,
                existing_manifest_path,
                existing_manifest_sha,
                existing_training,
                existing_operational,
                existing_notes,
            ) = existing_run
            if (
                existing_source_id != source_id
                or existing_source_url != prepared.manifest["source_url"]
                or existing_basis != basis
                or existing_reference != ref
                or existing_manifest_path != prepared.report["raw_manifest_path"]
                or existing_manifest_sha != prepared.report["raw_manifest_sha256"]
                or existing_training != int(training)
                or existing_operational != int(operational)
            ):
                raise PersistenceError(
                    "Existing run_key has incompatible source, manifest, or permission provenance."
                )
            existing_run_notes = _load_run_notes(existing_notes)
            events = existing_run_notes["persistence_events"]
            if any(
                isinstance(event, dict) and event.get("event_sha256") == event_sha
                for event in events
            ):
                connection.rollback()
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
                    "reconciliation": {
                        "status": "no_op",
                        "event_sha256": event_sha,
                        "mapping_review_complete": mapping_review_complete,
                    },
                }
        else:
            run_id = None
            existing_run_notes = {"schema_version": 2, "persistence_events": []}

        incoming_by_id = {
            row["source_flight_id"]: _incoming_record(row) for row in prepared.records
        }
        existing_by_id = {
            source_flight_id: _existing_flight(connection, source_id, source_flight_id)
            for source_flight_id in incoming_by_id
        }
        actions = tuple(
            compare_flight(
                source_flight_id,
                existing_by_id[source_flight_id],
                incoming_by_id[source_flight_id],
            )
            for source_flight_id in sorted(incoming_by_id, key=int)
        )
        reconciliation_plan = plan_sha256(
            run_key, validation_snapshot, prepared.accepted_sha, actions
        )
        conflicts = tuple(action for action in actions if action.requires_review)
        decisions: dict[str, dict[str, Any]] = {}
        decisions_digest: str | None = None
        if conflicts:
            artifacts = write_or_load_proposals(
                root,
                run_key=run_key,
                validation_snapshot_sha256=validation_snapshot,
                accepted_flights_sha256=prepared.accepted_sha,
                actions=actions,
            )
            decisions = load_review_decisions(artifacts)
            if decisions is None:
                connection.rollback()
                return {
                    "run_key": run_key,
                    "status": "awaiting_reconciliation_review",
                    "records_seen": prepared.report["records_seen"],
                    "records_accepted": prepared.report["records_accepted"],
                    "validation_snapshot_sha256": validation_snapshot,
                    "accepted_flights_sha256": prepared.accepted_sha,
                    "reconciliation": {
                        "plan_sha256": artifacts.plan_sha256,
                        "proposal_count": len(artifacts.proposals),
                        "proposals_path": artifacts.proposals_path.relative_to(root).as_posix(),
                        "proposals_sha256": artifacts.proposals_sha256,
                        "report_path": artifacts.report_path.relative_to(root).as_posix(),
                        "decisions_path": artifacts.decisions_path.relative_to(root).as_posix(),
                        "next_step": (
                            "Copy reconciliation-proposals.jsonl to reconciliation-decisions.jsonl, "
                            "add one reviewed decision per proposal, then run xccontest-ingest resume."
                        ),
                    },
                }
            decisions_digest = decisions_sha256(artifacts)

        resolved: list[
            tuple[
                dict[str, Any],
                ReconciliationAction,
                dict[str, Any],
                str,
                str | None,
                str,
                int | None,
            ]
        ] = []
        for action in actions:
            incoming = incoming_by_id[action.source_flight_id]
            existing = existing_by_id[action.source_flight_id]
            final_values = action.incoming
            outcome = action.outcome
            decision_reference: str | None = None
            if action.requires_review:
                proposal = proposal_for(
                    action,
                    run_key=run_key,
                    validation_snapshot_sha256=validation_snapshot,
                    accepted_flights_sha256=prepared.accepted_sha,
                )
                decision = decisions[proposal["proposal_id"]]
                decision_reference = decision["verification_reference"]
                if decision["decision"] == "keep_existing":
                    if action.existing is None or existing is None:
                        raise PersistenceError("Conflict review cannot retain a missing flight.")
                    final_values = action.existing
                    outcome = "reviewed_keep_existing"
                else:
                    outcome = "reviewed_accept_incoming"
            elif action.existing is not None:
                final_values = {**action.existing, **action.updates}
            mapping_key_type = (
                existing["mapping_key_type"]
                if existing is not None
                and int(final_values["source_site_mapping_id"])
                == int(existing["source_site_mapping_id"])
                else incoming["mapping_key_type"]
            )
            resolved.append(
                (
                    incoming,
                    action,
                    final_values,
                    outcome,
                    decision_reference,
                    mapping_key_type,
                    int(existing["id"]) if existing is not None else None,
                )
            )

        counts = {
            "inserted": 0,
            "revalidated_unchanged": 0,
            "enriched": 0,
            "preserved_existing": 0,
            "reviewed_keep_existing": 0,
            "reviewed_accept_incoming": 0,
        }
        for _incoming, _action, _final, outcome, _reference, _mapping_type, _id in resolved:
            counts[outcome] += 1
        now = utc_now()
        event = _run_event(
            event_sha256=event_sha,
            validation_snapshot=validation_snapshot,
            prepared=prepared,
            root=root,
            plan=reconciliation_plan,
            mapping_review_complete=mapping_review_complete,
            decisions_digest=decisions_digest,
            counts=counts,
            now=now,
        )
        existing_run_notes["persistence_events"].append(event)
        notes = json.dumps(existing_run_notes, sort_keys=True, separators=(",", ":"))
        if run_id is None:
            cursor = connection.execute(
                "INSERT INTO flight_ingestion_runs (run_key,source_id,ingestion_method,status,source_url,permission_basis,permission_reference,model_training_allowed,operational_use_allowed,raw_manifest_path,raw_manifest_sha256,pipeline_version,started_at_utc,completed_at_utc,records_seen,records_accepted,records_rejected,records_quarantined,records_deduplicated,notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
            run_id = int(cursor.lastrowid)
        else:
            connection.execute(
                "UPDATE flight_ingestion_runs SET status = 'succeeded', completed_at_utc = ?, pipeline_version = ?, records_seen = ?, records_accepted = ?, records_rejected = ?, records_quarantined = ?, records_deduplicated = ?, notes = ? WHERE id = ?",
                (
                    now,
                    pipeline,
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
                    run_id,
                ),
            )

        for (
            incoming,
            action,
            final_values,
            outcome,
            decision_reference,
            mapping_key_type,
            existing_flight_id,
        ) in resolved:
            quality_notes = build_quality_notes(
                canonical=final_values,
                mapping_key_type=mapping_key_type,
                validation_snapshot_sha256=validation_snapshot,
                accepted_flights_sha256=prepared.accepted_sha,
                artifact_references=incoming["artifact_references"],
                parser_version=PARSER_VERSION,
                validator_version=VALIDATION_VERSION,
                persistence_version=PERSISTENCE_VERSION,
                outcome=outcome,
                event_sha256=event_sha,
                decision_reference=decision_reference,
            )
            values = canonical_flight(final_values)
            if existing_flight_id is None:
                connection.execute(
                    "INSERT INTO flight_records (source_id,source_flight_id,source_flight_url,source_site_mapping_id,takeoff_at_utc,duration_seconds,scored_distance_km,route_type,track_url,validation_level,validation_notes,validated_at_utc,created_by_ingestion_run_id,last_validated_by_ingestion_run_id,created_at_utc,updated_at_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        source_id,
                        action.source_flight_id,
                        values["source_flight_url"],
                        values["source_site_mapping_id"],
                        values["takeoff_at_utc"],
                        values["duration_seconds"],
                        float(values["scored_distance_km"]),
                        values["route_type"],
                        values["track_url"],
                        values["validation_level"],
                        quality_notes,
                        incoming["validated_at_utc"],
                        run_id,
                        run_id,
                        now,
                        now,
                    ),
                )
            else:
                connection.execute(
                    "UPDATE flight_records SET source_flight_url = ?, source_site_mapping_id = ?, takeoff_at_utc = ?, duration_seconds = ?, scored_distance_km = ?, route_type = ?, track_url = ?, validation_level = ?, validation_notes = ?, validated_at_utc = ?, last_validated_by_ingestion_run_id = ?, updated_at_utc = ? WHERE id = ?",
                    (
                        values["source_flight_url"],
                        values["source_site_mapping_id"],
                        values["takeoff_at_utc"],
                        values["duration_seconds"],
                        float(values["scored_distance_km"]),
                        values["route_type"],
                        values["track_url"],
                        values["validation_level"],
                        quality_notes,
                        incoming["validated_at_utc"],
                        run_id,
                        now,
                        existing_flight_id,
                    ),
                )
        connection.commit()
    except (PersistenceError, ReconciliationError, sqlite3.Error) as error:
        connection.rollback()
        if isinstance(error, PersistenceError):
            raise
        if isinstance(error, ReconciliationError):
            raise PersistenceError(str(error)) from error
        raise PersistenceError("SQLite reconciliation transaction did not complete.") from error
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
        "reconciliation": {
            "status": "applied",
            "event_sha256": event_sha,
            "plan_sha256": reconciliation_plan,
            "mapping_review_complete": mapping_review_complete,
            "counts": counts,
        },
    }
