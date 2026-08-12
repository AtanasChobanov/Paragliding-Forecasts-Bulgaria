"""Deterministic cross-run flight reconciliation and review artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .site_mapping import _safe_run_directory

SHA = re.compile(r"[0-9a-f]{64}\Z")
UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")

RECONCILIATION_SCHEMA_VERSION = 1
QUALITY_NOTES_SCHEMA_VERSION = 1
RECONCILIATION_OUTPUT_DIRECTORY = "reconciliation-v1"

STRICT_FIELDS = (
    "source_flight_url",
    "source_site_mapping_id",
    "takeoff_at_utc",
    "scored_distance_km",
)
OPTIONAL_FIELDS = ("duration_seconds", "route_type", "track_url", "validation_level")
COMPARISON_FIELDS = STRICT_FIELDS + OPTIONAL_FIELDS
VALIDATION_RANK = {"metadata": 0, "track": 1}


class ReconciliationError(RuntimeError):
    """Reconciliation evidence or review decisions are invalid."""


@dataclass(frozen=True)
class ReconciliationAction:
    """One fully classified incoming source-flight observation."""

    source_flight_id: str
    outcome: str
    existing: dict[str, Any] | None
    incoming: dict[str, Any]
    updates: dict[str, Any]
    preserved_fields: tuple[str, ...]
    conflicting_fields: dict[str, dict[str, Any]]

    @property
    def requires_review(self) -> bool:
        return bool(self.conflicting_fields)


@dataclass(frozen=True)
class ReconciliationArtifacts:
    """Paths and hashes for a non-overwriting conflict review plan."""

    directory: Path
    plan_sha256: str
    proposals_path: Path
    proposals_sha256: str
    report_path: Path
    decisions_path: Path
    proposals: tuple[dict[str, Any], ...]


def _canonical_decimal(value: object) -> str:
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ReconciliationError("A scored distance is not a finite decimal.") from error
    if not decimal.is_finite():
        raise ReconciliationError("A scored distance is not a finite decimal.")
    return format(decimal.normalize(), "f")


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ReconciliationError("A reconciled text field must be text or null.")
    value = value.strip()
    return value or None


def canonical_flight(record: dict[str, Any]) -> dict[str, Any]:
    """Return the identity-independent values that define a canonical flight."""

    try:
        duration = record.get("duration_seconds")
        if duration is not None:
            duration = int(duration)
        mapping_id = int(record["source_site_mapping_id"])
        source_flight_url = _optional_text(record["source_flight_url"])
        takeoff_at_utc = record["takeoff_at_utc"]
        route_type = _optional_text(record.get("route_type"))
        validation_level = _optional_text(record.get("validation_level"))
    except (KeyError, TypeError, ValueError) as error:
        raise ReconciliationError("A flight does not expose a usable canonical value.") from error
    if source_flight_url is None or not isinstance(takeoff_at_utc, str) or not takeoff_at_utc:
        raise ReconciliationError("A flight does not expose a usable canonical value.")
    if route_type is None or validation_level not in VALIDATION_RANK:
        raise ReconciliationError("A flight has invalid route or validation evidence.")
    return {
        "source_flight_url": source_flight_url,
        "source_site_mapping_id": mapping_id,
        "takeoff_at_utc": takeoff_at_utc,
        "scored_distance_km": _canonical_decimal(record["scored_distance_km"]),
        "duration_seconds": duration,
        "route_type": route_type,
        "track_url": _optional_text(record.get("track_url")),
        "validation_level": validation_level,
    }


def record_fingerprint(record: dict[str, Any]) -> str:
    """Hash only canonical values so equivalent numeric JSON forms compare equally."""

    return hashlib.sha256(
        json.dumps(canonical_flight(record), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _field_difference(
    existing: dict[str, Any], incoming: dict[str, Any], field: str
) -> dict[str, Any]:
    return {"existing": existing[field], "incoming": incoming[field]}


def compare_flight(
    source_flight_id: str, existing: dict[str, Any] | None, incoming: dict[str, Any]
) -> ReconciliationAction:
    """Classify one incoming record without performing any database write."""

    incoming_values = canonical_flight(incoming)
    if existing is None:
        return ReconciliationAction(
            source_flight_id,
            "inserted",
            None,
            incoming_values,
            incoming_values,
            (),
            {},
        )

    existing_values = canonical_flight(existing)
    conflicts: dict[str, dict[str, Any]] = {}
    updates: dict[str, Any] = {}
    preserved: list[str] = []
    for field in STRICT_FIELDS:
        if existing_values[field] != incoming_values[field]:
            conflicts[field] = _field_difference(existing_values, incoming_values, field)

    existing_duration = existing_values["duration_seconds"]
    incoming_duration = incoming_values["duration_seconds"]
    if existing_duration is None and incoming_duration is not None:
        updates["duration_seconds"] = incoming_duration
    elif existing_duration is not None and incoming_duration is None:
        preserved.append("duration_seconds")
    elif existing_duration != incoming_duration:
        conflicts["duration_seconds"] = _field_difference(
            existing_values, incoming_values, "duration_seconds"
        )

    existing_route = existing_values["route_type"]
    incoming_route = incoming_values["route_type"]
    if existing_route == "unknown" and incoming_route != "unknown":
        updates["route_type"] = incoming_route
    elif existing_route != "unknown" and incoming_route == "unknown":
        preserved.append("route_type")
    elif existing_route != incoming_route:
        conflicts["route_type"] = _field_difference(existing_values, incoming_values, "route_type")

    existing_track = existing_values["track_url"]
    incoming_track = incoming_values["track_url"]
    if existing_track is None and incoming_track is not None:
        updates["track_url"] = incoming_track
    elif existing_track is not None and incoming_track is None:
        preserved.append("track_url")
    elif existing_track != incoming_track:
        conflicts["track_url"] = _field_difference(existing_values, incoming_values, "track_url")

    if (
        VALIDATION_RANK[incoming_values["validation_level"]]
        > VALIDATION_RANK[existing_values["validation_level"]]
    ):
        updates["validation_level"] = incoming_values["validation_level"]
    elif (
        VALIDATION_RANK[incoming_values["validation_level"]]
        < VALIDATION_RANK[existing_values["validation_level"]]
    ):
        preserved.append("validation_level")

    if conflicts:
        outcome = "conflict"
    elif updates:
        outcome = "enriched"
    elif preserved:
        outcome = "preserved_existing"
    else:
        outcome = "revalidated_unchanged"
    return ReconciliationAction(
        source_flight_id,
        outcome,
        existing_values,
        incoming_values,
        updates,
        tuple(preserved),
        conflicts,
    )


def plan_sha256(
    run_key: str,
    validation_snapshot_sha256: str,
    accepted_flights_sha256: str,
    actions: tuple[ReconciliationAction, ...],
) -> str:
    """Identify exactly one reconciliation attempt against current DB evidence."""

    payload = {
        "schema_version": RECONCILIATION_SCHEMA_VERSION,
        "run_key": run_key,
        "validation_snapshot_sha256": validation_snapshot_sha256,
        "accepted_flights_sha256": accepted_flights_sha256,
        "actions": [
            {
                "source_flight_id": action.source_flight_id,
                "outcome": action.outcome,
                "existing_fingerprint": record_fingerprint(action.existing)
                if action.existing is not None
                else None,
                "incoming_fingerprint": record_fingerprint(action.incoming),
                "conflicting_fields": action.conflicting_fields,
            }
            for action in actions
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def proposal_for(
    action: ReconciliationAction,
    *,
    run_key: str,
    validation_snapshot_sha256: str,
    accepted_flights_sha256: str,
) -> dict[str, Any]:
    if not action.requires_review or action.existing is None:
        raise ReconciliationError("Only conflicting existing flights can have a review proposal.")
    evidence = {
        "reconciliation_schema_version": RECONCILIATION_SCHEMA_VERSION,
        "run_key": run_key,
        "source": "xccontest",
        "source_flight_id": action.source_flight_id,
        "validation_snapshot_sha256": validation_snapshot_sha256,
        "accepted_flights_sha256": accepted_flights_sha256,
        "existing_fingerprint": record_fingerprint(action.existing),
        "incoming_fingerprint": record_fingerprint(action.incoming),
    }
    proposal_id = hashlib.sha256(
        json.dumps(
            {**evidence, "conflicting_fields": action.conflicting_fields},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return {
        "proposal_id": proposal_id,
        **evidence,
        "existing": action.existing,
        "incoming": action.incoming,
        "conflicting_fields": action.conflicting_fields,
    }


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_jsonl(path: Path, rows: tuple[dict[str, Any], ...]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def _json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReconciliationError(f"{label} is not readable JSON.") from error
    if not isinstance(value, dict):
        raise ReconciliationError(f"{label} must be a JSON object.")
    return value


def write_or_load_proposals(
    root: Path,
    *,
    run_key: str,
    validation_snapshot_sha256: str,
    accepted_flights_sha256: str,
    actions: tuple[ReconciliationAction, ...],
) -> ReconciliationArtifacts:
    """Create once, then verify and reuse immutable review evidence for conflicts."""

    conflicts = tuple(action for action in actions if action.requires_review)
    if not conflicts:
        raise ReconciliationError("A reconciliation proposal requires at least one conflict.")
    plan = plan_sha256(run_key, validation_snapshot_sha256, accepted_flights_sha256, actions)
    directory = _safe_run_directory(run_key, root) / RECONCILIATION_OUTPUT_DIRECTORY / plan
    proposals_path = directory / "reconciliation-proposals.jsonl"
    report_path = directory / "reconciliation-report.json"
    decisions_path = directory / "reconciliation-decisions.jsonl"
    proposals = tuple(
        proposal_for(
            action,
            run_key=run_key,
            validation_snapshot_sha256=validation_snapshot_sha256,
            accepted_flights_sha256=accepted_flights_sha256,
        )
        for action in conflicts
    )
    if not directory.exists():
        directory.mkdir(parents=True, exist_ok=False)
        _write_jsonl(proposals_path, proposals)
        report = {
            "reconciliation_schema_version": RECONCILIATION_SCHEMA_VERSION,
            "run_key": run_key,
            "plan_sha256": plan,
            "validation_snapshot_sha256": validation_snapshot_sha256,
            "accepted_flights_sha256": accepted_flights_sha256,
            "proposal_count": len(proposals),
            "proposals_path": proposals_path.relative_to(root).as_posix(),
            "proposals_sha256": _digest(proposals_path),
        }
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    report = _json_object(report_path, "Reconciliation report")
    if (
        report.get("reconciliation_schema_version") != RECONCILIATION_SCHEMA_VERSION
        or report.get("run_key") != run_key
        or report.get("plan_sha256") != plan
        or report.get("validation_snapshot_sha256") != validation_snapshot_sha256
        or report.get("accepted_flights_sha256") != accepted_flights_sha256
        or report.get("proposals_path") != proposals_path.relative_to(root).as_posix()
        or report.get("proposals_sha256") != _digest(proposals_path)
        or report.get("proposal_count") != len(proposals)
    ):
        raise ReconciliationError("Existing reconciliation proposal evidence is incompatible.")
    return ReconciliationArtifacts(
        directory,
        plan,
        proposals_path,
        _digest(proposals_path),
        report_path,
        decisions_path,
        proposals,
    )


def _read_jsonl(path: Path, label: str) -> tuple[dict[str, Any], ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ReconciliationError(f"{label} is not readable.") from error
    result: list[dict[str, Any]] = []
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ReconciliationError(f"{label} contains invalid JSONL.") from error
        if not isinstance(value, dict):
            raise ReconciliationError(f"{label} rows must be objects.")
        result.append(value)
    return tuple(result)


def load_review_decisions(artifacts: ReconciliationArtifacts) -> dict[str, dict[str, Any]] | None:
    """Return validated decisions, or ``None`` while human review is still pending."""

    if not artifacts.decisions_path.is_file():
        return None
    decisions = _read_jsonl(artifacts.decisions_path, "Reconciliation decisions")
    proposal_by_id = {proposal["proposal_id"]: proposal for proposal in artifacts.proposals}
    if len(decisions) != len(proposal_by_id):
        raise ReconciliationError(
            "Reconciliation decisions must cover every proposal exactly once."
        )
    result: dict[str, dict[str, Any]] = {}
    immutable_fields = (
        "proposal_id",
        "reconciliation_schema_version",
        "run_key",
        "source",
        "source_flight_id",
        "validation_snapshot_sha256",
        "accepted_flights_sha256",
        "existing_fingerprint",
        "incoming_fingerprint",
    )
    for decision in decisions:
        proposal_id = decision.get("proposal_id")
        if (
            not isinstance(proposal_id, str)
            or proposal_id not in proposal_by_id
            or proposal_id in result
        ):
            raise ReconciliationError(
                "A reconciliation decision does not belong to this proposal file."
            )
        proposal = proposal_by_id[proposal_id]
        if any(decision.get(field) != proposal.get(field) for field in immutable_fields):
            raise ReconciliationError(
                "Reconciliation decision evidence does not match its proposal."
            )
        if decision.get("decision") not in {"keep_existing", "accept_incoming"}:
            raise ReconciliationError(
                "Reconciliation decision must keep_existing or accept_incoming."
            )
        for field in ("verification_reference", "reviewed_by", "notes"):
            if not isinstance(decision.get(field), str) or not decision[field].strip():
                raise ReconciliationError(f"Reconciliation decision requires non-empty {field}.")
        reviewed_at_utc = decision.get("reviewed_at_utc")
        if not isinstance(reviewed_at_utc, str) or UTC.fullmatch(reviewed_at_utc) is None:
            raise ReconciliationError("Reconciliation decision requires UTC reviewed_at_utc.")
        result[proposal_id] = decision
    return result


def decisions_sha256(artifacts: ReconciliationArtifacts) -> str | None:
    return _digest(artifacts.decisions_path) if artifacts.decisions_path.is_file() else None


def build_quality_notes(
    *,
    canonical: dict[str, Any],
    mapping_key_type: str,
    validation_snapshot_sha256: str,
    accepted_flights_sha256: str,
    artifact_references: object,
    parser_version: str,
    validator_version: str,
    persistence_version: str,
    outcome: str,
    event_sha256: str,
    decision_reference: str | None = None,
) -> str:
    """Build compact, machine-verifiable provenance/quality notes JSON."""

    values = canonical_flight(canonical)
    artifacts_json = json.dumps(artifact_references, sort_keys=True, separators=(",", ":"))
    try:
        artifact_count = len(artifact_references)  # type: ignore[arg-type]
    except TypeError as error:
        raise ReconciliationError("artifact_references must be a sequence.") from error
    flags: set[str] = set()
    if values["validation_level"] == "metadata":
        flags.add("track_not_verified")
    if values["route_type"] == "unknown":
        flags.add("route_type_unknown")
    if values["duration_seconds"] is None:
        flags.add("duration_missing")
    if outcome in {"reviewed_keep_existing", "reviewed_accept_incoming"}:
        flags.add("manual_reconciliation")
    if outcome == "preserved_existing":
        flags.add("incoming_missing_value_preserved")
    value = {
        "schema_version": QUALITY_NOTES_SCHEMA_VERSION,
        "evidence_level": values["validation_level"],
        "parser_version": parser_version,
        "validator_version": validator_version,
        "persistence_version": persistence_version,
        "mapping_key_type": mapping_key_type,
        "mapping_snapshot_sha256": validation_snapshot_sha256,
        "accepted_flights_sha256": accepted_flights_sha256,
        "artifact_reference_count": artifact_count,
        "artifact_references_sha256": hashlib.sha256(artifacts_json.encode()).hexdigest(),
        "quality_flags": sorted(flags),
        "reconciliation": {
            "outcome": outcome,
            "event_sha256": event_sha256,
            "decision_reference": decision_reference,
        },
    }
    validate_quality_notes(value, canonical=values)
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def parse_quality_notes(notes: str, *, canonical: dict[str, Any]) -> dict[str, Any] | None:
    """Validate current JSON notes; legacy T-013 text is deliberately readable."""

    try:
        value = json.loads(notes)
    except json.JSONDecodeError:
        return None
    validate_quality_notes(value, canonical=canonical)
    return value


def validate_quality_notes(value: object, *, canonical: dict[str, Any]) -> None:
    if not isinstance(value, dict) or value.get("schema_version") != QUALITY_NOTES_SCHEMA_VERSION:
        raise ReconciliationError("Quality notes must use supported JSON schema_version.")
    flight = canonical_flight(canonical)
    if value.get("evidence_level") != flight["validation_level"]:
        raise ReconciliationError("Quality notes evidence level does not match the flight.")
    for field in ("parser_version", "validator_version", "persistence_version", "mapping_key_type"):
        if not isinstance(value.get(field), str) or not value[field]:
            raise ReconciliationError(f"Quality notes require {field}.")
    for field in (
        "mapping_snapshot_sha256",
        "accepted_flights_sha256",
        "artifact_references_sha256",
    ):
        if not isinstance(value.get(field), str) or SHA.fullmatch(value[field]) is None:
            raise ReconciliationError(f"Quality notes require lowercase SHA-256 {field}.")
    if (
        not isinstance(value.get("artifact_reference_count"), int)
        or value["artifact_reference_count"] < 1
    ):
        raise ReconciliationError("Quality notes require positive artifact_reference_count.")
    flags = value.get("quality_flags")
    if not isinstance(flags, list) or any(not isinstance(flag, str) for flag in flags):
        raise ReconciliationError("Quality notes quality_flags are invalid.")
    expected_flags = set()
    if flight["validation_level"] == "metadata":
        expected_flags.add("track_not_verified")
    if flight["route_type"] == "unknown":
        expected_flags.add("route_type_unknown")
    if flight["duration_seconds"] is None:
        expected_flags.add("duration_missing")
    if not expected_flags.issubset(set(flags)):
        raise ReconciliationError("Quality notes omit a required quality flag.")
    reconciliation = value.get("reconciliation")
    if not isinstance(reconciliation, dict):
        raise ReconciliationError("Quality notes require reconciliation provenance.")
    if reconciliation.get("outcome") not in {
        "inserted",
        "revalidated_unchanged",
        "enriched",
        "preserved_existing",
        "reviewed_keep_existing",
        "reviewed_accept_incoming",
    }:
        raise ReconciliationError("Quality notes have an unsupported reconciliation outcome.")
    event = reconciliation.get("event_sha256")
    if not isinstance(event, str) or SHA.fullmatch(event) is None:
        raise ReconciliationError("Quality notes require reconciliation event SHA-256.")
    decision_reference = reconciliation.get("decision_reference")
    if reconciliation["outcome"].startswith("reviewed_") and (
        not isinstance(decision_reference, str) or not decision_reference
    ):
        raise ReconciliationError("Manual reconciliation quality notes require decision_reference.")
    if decision_reference is not None and not isinstance(decision_reference, str):
        raise ReconciliationError("Quality notes decision_reference is invalid.")
