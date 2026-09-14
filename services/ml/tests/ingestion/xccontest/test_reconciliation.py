from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from paragliding_forecasts_ml.ingestion.xccontest import persistence_cli, pipeline
from paragliding_forecasts_ml.ingestion.xccontest.persistence import (
    PersistenceError,
    digest,
    mapping_hash,
    persist_import,
)
from paragliding_forecasts_ml.ingestion.xccontest.reconciliation import (
    build_quality_notes,
    compare_flight,
    load_review_decisions,
    parse_quality_notes,
    write_or_load_proposals,
)
from paragliding_forecasts_ml.ingestion.xccontest.site_mapping import (
    apply_mapping_decisions,
    repository_root,
)
from paragliding_forecasts_ml.ingestion.xccontest.versions import (
    PARSER_VERSION,
    PERSISTENCE_VERSION,
    VALIDATION_VERSION,
)


def flight(
    source_flight_id: str = "100",
    *,
    distance: float = 150.0,
    duration: int | None = 3600,
    route_type: str = "free_flight",
) -> dict:
    return {
        "source_flight_url": "https://www.xcontest.org/world/en/flights/detail:test",
        "source_site_mapping_id": 10,
        "takeoff_at_utc": "2026-08-01T12:00:00Z",
        "duration_seconds": duration,
        "scored_distance_km": distance,
        "route_type": route_type,
        "track_url": None,
        "validation_level": "metadata",
    }


def test_compare_flight_distinguishes_revalidation_enrichment_and_conflict() -> None:
    exact = compare_flight("100", flight(), flight())
    assert exact.outcome == "revalidated_unchanged"

    enriched = compare_flight("100", {**flight(), "duration_seconds": None}, flight())
    assert enriched.outcome == "enriched"
    assert enriched.updates == {"duration_seconds": 3600}

    preserved = compare_flight("100", flight(), {**flight(), "route_type": "unknown"})
    assert preserved.outcome == "preserved_existing"
    assert preserved.preserved_fields == ("route_type",)

    conflicting = compare_flight("100", flight(), flight(distance=150.01))
    assert conflicting.outcome == "conflict"
    assert conflicting.conflicting_fields == {
        "scored_distance_km": {"existing": "150", "incoming": "150.01"}
    }


def test_reconciliation_decisions_must_match_immutable_proposals(tmp_path: Path) -> None:
    action = compare_flight("100", flight(), flight(distance=151.0))
    run_key = "11111111-1111-4111-8111-111111111111"
    artifacts = write_or_load_proposals(
        tmp_path,
        run_key=run_key,
        validation_snapshot_sha256="a" * 64,
        accepted_flights_sha256="b" * 64,
        actions=(action,),
    )
    proposal = artifacts.proposals[0]
    artifacts.decisions_path.write_text(
        json.dumps(
            {
                **{
                    key: proposal[key]
                    for key in (
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
                },
                "decision": "keep_existing",
                "verification_reference": "raw-artifact:manual-check",
                "reviewed_by": "AB",
                "reviewed_at_utc": "2026-08-12T09:00:00Z",
                "notes": "The source page confirms the previous distance.",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    decisions = load_review_decisions(artifacts)
    assert decisions is not None
    assert decisions[proposal["proposal_id"]]["decision"] == "keep_existing"

    stale = json.loads(artifacts.decisions_path.read_text(encoding="utf-8"))
    stale["incoming_fingerprint"] = "c" * 64
    artifacts.decisions_path.write_text(json.dumps(stale) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="does not match its proposal"):
        load_review_decisions(artifacts)


def test_persistence_cli_returns_a_distinct_review_pause(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(
        persistence_cli,
        "persist_import",
        lambda *_args, **_kwargs: {"status": "awaiting_reconciliation_review"},
    )

    exit_code = persistence_cli.main(
        [
            "--run-key",
            "11111111-1111-4111-8111-111111111111",
            "--validation-snapshot",
            "a" * 64,
            "--policy-file",
            str(tmp_path / "policy.json"),
        ]
    )

    assert exit_code == 2
    assert '"status": "awaiting_reconciliation_review"' in capsys.readouterr().out


def test_quality_notes_are_semantically_tied_to_canonical_values() -> None:
    notes = build_quality_notes(
        canonical=flight(route_type="unknown", duration=None),
        mapping_key_type="source_site_token",
        validation_snapshot_sha256="a" * 64,
        accepted_flights_sha256="b" * 64,
        artifact_references=[{"artifact_path": "data/raw/example.html", "row_index": 1}],
        parser_version=PARSER_VERSION,
        validator_version=VALIDATION_VERSION,
        persistence_version=PERSISTENCE_VERSION,
        outcome="inserted",
        event_sha256="c" * 64,
    )

    parsed = parse_quality_notes(notes, canonical=flight(route_type="unknown", duration=None))
    assert parsed is not None
    assert parsed["quality_flags"] == [
        "duration_missing",
        "route_type_unknown",
        "track_not_verified",
    ]


TEST_RUN_KEYS = (
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
    "33333333-3333-4333-8333-333333333333",
    "44444444-4444-4444-8444-444444444444",
    "55555555-5555-4555-8555-555555555555",
    "66666666-6666-4666-8666-666666666666",
    "77777777-7777-4777-8777-777777777777",
    "88888888-8888-4888-8888-888888888888",
    "99999999-9999-4999-8999-999999999999",
)


@pytest.fixture
def migrated_database():
    root = repository_root()
    name = f"t014-reconciliation-test-{uuid4()}"
    database_url = f"file:./data/local/{name}/flights.db"
    directory = root / "data" / "local" / name
    environment = {**os.environ, "DATABASE_URL": database_url}
    subprocess.run(
        [
            "npm.cmd",
            "run",
            "db:migrate",
            "--workspace",
            "@paragliding-forecasts/database",
        ],
        cwd=root,
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )
    try:
        yield root, database_url, name
    finally:
        shutil.rmtree(directory, ignore_errors=True)
        for run_key in TEST_RUN_KEYS:
            shutil.rmtree(root / "data" / "raw" / "xccontest" / run_key, ignore_errors=True)
            shutil.rmtree(root / "data" / "interim" / "xccontest" / run_key, ignore_errors=True)
            (root / "data" / "local" / f"{run_key}-policy.json").unlink(missing_ok=True)


def _create_mapping(root: Path, database_url: str, token: str) -> tuple[int, str]:
    database_path = root / database_url.removeprefix("file:")
    connection = sqlite3.connect(database_path)
    try:
        source_id = int(
            connection.execute("SELECT id FROM flight_sources WHERE code = 'xccontest'").fetchone()[
                0
            ]
        )
        site_id = int(connection.execute("SELECT id FROM sites WHERE slug = 'sopot'").fetchone()[0])
        cursor = connection.execute(
            "INSERT INTO source_site_mappings (source_id,site_id,key_type,key_value,status,verification_reference,verified_at_utc) VALUES (?,?,?,?,?,?,?)",
            (
                source_id,
                site_id,
                "source_site_token",
                token,
                "approved",
                "test-fixture:manual-review",
                "2026-08-12T09:00:00Z",
            ),
        )
        snapshot = mapping_hash(connection, source_id)
        connection.commit()
        return int(cursor.lastrowid), snapshot
    finally:
        connection.close()


def _write_run(
    root: Path,
    *,
    run_key: str,
    snapshot: str,
    mapping_id: int,
    records: list[dict],
    quarantine_records: list[dict] | None = None,
) -> Path:
    raw = root / "data" / "raw" / "xccontest" / run_key
    parser = root / "data" / "interim" / "xccontest" / run_key / "parser-v2"
    output = parser.parent / "validation-v2" / snapshot
    raw.mkdir(parents=True, exist_ok=True)
    parser.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    raw_manifest = raw / "manifest.json"
    if not raw_manifest.exists():
        raw_manifest.write_text(
            json.dumps(
                {
                    "source": "xccontest",
                    "run_key": run_key,
                    "status": "complete",
                    "collector_version": "xccontest-collector/test",
                    "source_url": "https://www.xcontest.org/world/en/flights/",
                    "started_at_utc": "2026-08-12T08:00:00Z",
                }
            ),
            encoding="utf-8",
        )
    normalized = parser / "normalized-flights.jsonl"
    normalized.write_text("{}\n" * (len(records) + len(quarantine_records or [])), encoding="utf-8")
    parser_report = parser / "parse-report.json"
    parser_report.write_text(
        json.dumps(
            {
                "source": "xccontest",
                "run_key": run_key,
                "parser_version": PARSER_VERSION,
                "normalized_candidates": len(records) + len(quarantine_records or []),
                "row_observations_seen": len(records) + len(quarantine_records or []),
                "records_rejected": 0,
                "duplicate_observations_removed": 0,
                "raw_manifest_path": raw_manifest.relative_to(root).as_posix(),
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    accepted = output / "accepted-flights.jsonl"
    accepted_records = [
        {
            "source": "xccontest",
            "validation_status": "accepted",
            "validator_version": VALIDATION_VERSION,
            "source_flight_id": item["source_flight_id"],
            "source_flight_url": item["source_flight_url"],
            "source_site_mapping_id": item.get("source_site_mapping_id", mapping_id),
            "site_id": item.get("site_id", 3),
            "mapping_key_type": item.get("mapping_key_type", "source_site_token"),
            "takeoff_at_utc": item.get("takeoff_at_utc", "2026-08-01T12:00:00Z"),
            "duration_seconds": item.get("duration_seconds", 3600),
            "scored_distance_km": item.get("scored_distance_km", 150.0),
            "route_type": item.get("route_type", "free_flight"),
            "artifact_references": [{"artifact_path": "data/raw/fixture.html", "row_index": 1}],
            "validated_at_utc": item.get("validated_at_utc", "2026-08-12T10:00:00Z"),
        }
        for item in records
    ]
    accepted.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in accepted_records),
        encoding="utf-8",
    )
    quarantine = output / "site-quarantine.jsonl"
    quarantined = quarantine_records or []
    quarantine.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in quarantined),
        encoding="utf-8",
    )
    report = {
        "source": "xccontest",
        "run_key": run_key,
        "validator_version": VALIDATION_VERSION,
        "parser_version": PARSER_VERSION,
        "mapping_snapshot_sha256": snapshot,
        "accepted_flights_path": accepted.relative_to(root).as_posix(),
        "accepted_flights_sha256": digest(accepted),
        "site_quarantine_path": quarantine.relative_to(root).as_posix(),
        "site_quarantine_sha256": digest(quarantine),
        "parser_normalized_path": normalized.relative_to(root).as_posix(),
        "parser_normalized_sha256": digest(normalized),
        "parser_report_path": parser_report.relative_to(root).as_posix(),
        "parser_report_sha256": digest(parser_report),
        "raw_manifest_path": raw_manifest.relative_to(root).as_posix(),
        "raw_manifest_sha256": digest(raw_manifest),
        "records_seen": len(records) + len(quarantined),
        "records_accepted": len(records),
        "records_rejected": 0,
        "records_quarantined": len(quarantined),
        "records_deduplicated": 0,
    }
    (output / "validation-report.json").write_text(
        json.dumps(report, sort_keys=True), encoding="utf-8"
    )
    policy = root / "data" / "local" / f"{run_key}-policy.json"
    policy.write_text(
        json.dumps(
            {
                "permission_basis": "written_permission",
                "permission_reference": "test permission",
                "model_training_allowed": True,
                "operational_use_allowed": True,
            }
        ),
        encoding="utf-8",
    )
    return policy


def _database(root: Path, database_url: str) -> sqlite3.Connection:
    connection = sqlite3.connect(root / database_url.removeprefix("file:"))
    connection.row_factory = sqlite3.Row
    return connection


def _review_decision(proposal: dict, decision: str) -> dict:
    return {
        **{
            key: proposal[key]
            for key in (
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
        },
        "decision": decision,
        "verification_reference": "raw-artifact:manual-check",
        "reviewed_by": "AB",
        "reviewed_at_utc": "2026-08-13T09:00:00Z",
        "notes": "Synthetic reconciliation review for an isolated SQLite test.",
    }


def _generated_records(start: int, count: int, *, mapping_id: int) -> list[dict]:
    return [
        {
            "source_flight_id": str(source_flight_id),
            "source_flight_url": (
                f"https://www.xcontest.org/world/en/flights/detail:fixture-{source_flight_id}"
            ),
            "source_site_mapping_id": mapping_id,
        }
        for source_flight_id in range(start, start + count)
    ]


def _unknown_mapping_quarantines(count: int) -> list[dict]:
    return [
        {
            "reason": "unknown_mapping",
            "candidate": {
                "launch_search_url": (
                    "https://www.xcontest.org/world/en/flights-search/?filter[site]="
                    f"fixture-unreviewed-{number}"
                )
            },
        }
        for number in range(count)
    ]


def _write_mapping_proposal_report(root: Path, run_key: str) -> None:
    directory = root / "data" / "interim" / "xccontest" / run_key / "site-mapping-v2"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "proposal-report.json").write_text(
        json.dumps({"source": "xccontest", "run_key": run_key}), encoding="utf-8"
    )


def _write_mapping_rejections(
    root: Path, run_key: str, quarantines: list[dict], database_url: str
) -> dict[str, int]:
    _write_mapping_proposal_report(root, run_key)
    directory = root / "data" / "interim" / "xccontest" / run_key / "site-mapping-v2"
    proposals: list[dict] = []
    for quarantine in quarantines:
        candidate = quarantine["candidate"]
        key_type, key_value = pipeline._proposal_key(candidate)
        proposals.append(
            {
                "proposal_id": pipeline._proposal_id(key_type, key_value),
                "source": "xccontest",
                "key_type": key_type,
                "key_value": key_value,
                "point_latitude_deg": None,
                "point_longitude_deg": None,
            }
        )
    (directory / "mapping-proposals.jsonl").write_text(
        "".join(json.dumps(proposal) + "\n" for proposal in proposals), encoding="utf-8"
    )
    decisions_path = directory / "mapping-decisions.jsonl"
    decisions_path.write_text(
        "".join(json.dumps({**proposal, "decision": "rejected"}) + "\n" for proposal in proposals),
        encoding="utf-8",
    )
    return apply_mapping_decisions(decisions_path, database_url=database_url, project_root=root)


def _apply_mapping_approvals(
    root: Path, database_url: str, quarantines: list[dict]
) -> tuple[dict[str, int], str, list[int]]:
    database_path = root / database_url.removeprefix("file:")
    review_path = database_path.parent / "approved-mapping-decisions.jsonl"
    decision_rows: list[dict] = []
    keys: list[str] = []
    for quarantine in quarantines:
        key_type, key_value = pipeline._proposal_key(quarantine["candidate"])
        assert key_type == "source_site_token"
        assert isinstance(key_value, str)
        keys.append(key_value)
        decision_rows.append(
            {
                "decision": "approved",
                "key_type": key_type,
                "key_value": key_value,
                "site_slug": "sopot",
                "verification_reference": "synthetic component mapping review",
                "verified_at_utc": "2026-08-13T09:00:00Z",
            }
        )
    review_path.write_text(
        "".join(json.dumps(row) + "\n" for row in decision_rows), encoding="utf-8"
    )
    result = apply_mapping_decisions(review_path, database_url=database_url, project_root=root)
    connection = _database(root, database_url)
    try:
        source_id = int(
            connection.execute("SELECT id FROM flight_sources WHERE code = 'xccontest'").fetchone()[
                0
            ]
        )
        mapping_ids = [
            int(
                connection.execute(
                    "SELECT id FROM source_site_mappings WHERE source_id = ? AND "
                    "key_type = 'source_site_token' AND key_value = ?",
                    (source_id, key),
                ).fetchone()[0]
            )
            for key in keys
        ]
        return result, mapping_hash(connection, source_id), mapping_ids
    finally:
        connection.close()


def _canonical_columns(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT source_flight_id, source_flight_url, source_site_mapping_id, takeoff_at_utc, "
        "duration_seconds, scored_distance_km, route_type, track_url, validation_level, "
        "created_by_ingestion_run_id, last_validated_by_ingestion_run_id "
        "FROM flight_records ORDER BY source_flight_id"
    ).fetchall()


def test_partial_resume_reconciles_and_replay_is_a_no_op(migrated_database) -> None:
    root, database_url, _name = migrated_database
    run_key = "11111111-1111-4111-8111-111111111111"
    mapping_id, first_snapshot = _create_mapping(root, database_url, "first-token")
    policy = _write_run(
        root,
        run_key=run_key,
        snapshot=first_snapshot,
        mapping_id=mapping_id,
        records=[
            {
                "source_flight_id": "100",
                "source_flight_url": "https://www.xcontest.org/world/en/flights/detail:one",
            }
        ],
    )
    first = persist_import(
        run_key,
        first_snapshot,
        policy,
        database_url=database_url,
        project_root=root,
        mapping_review_complete=False,
    )
    assert first["reconciliation"]["counts"] == {
        "enriched": 0,
        "inserted": 1,
        "preserved_existing": 0,
        "revalidated_unchanged": 0,
        "reviewed_accept_incoming": 0,
        "reviewed_keep_existing": 0,
    }

    _second_mapping, second_snapshot = _create_mapping(root, database_url, "second-token")
    policy = _write_run(
        root,
        run_key=run_key,
        snapshot=second_snapshot,
        mapping_id=mapping_id,
        records=[
            {
                "source_flight_id": "100",
                "source_flight_url": "https://www.xcontest.org/world/en/flights/detail:one",
                "validated_at_utc": "2026-08-13T10:00:00Z",
            },
            {
                "source_flight_id": "101",
                "source_flight_url": "https://www.xcontest.org/world/en/flights/detail:two",
            },
        ],
    )
    resumed = persist_import(
        run_key,
        second_snapshot,
        policy,
        database_url=database_url,
        project_root=root,
    )
    assert resumed["reconciliation"]["counts"]["inserted"] == 1
    assert resumed["reconciliation"]["counts"]["revalidated_unchanged"] == 1

    connection = _database(root, database_url)
    try:
        assert connection.execute("SELECT count(*) FROM flight_records").fetchone()[0] == 2
        row = connection.execute(
            "SELECT source_flight_url, validation_notes, validated_at_utc, "
            "last_validated_by_ingestion_run_id, updated_at_utc "
            "FROM flight_records WHERE source_flight_id = '100'"
        ).fetchone()
        assert row["source_flight_url"].endswith("detail:one")
        assert json.loads(row["validation_notes"])["schema_version"] == 1
        assert row["validated_at_utc"] == "2026-08-13T10:00:00Z"
        last_validated_by = row["last_validated_by_ingestion_run_id"]
        updated_at = row["updated_at_utc"]
    finally:
        connection.close()

    replay = persist_import(
        run_key,
        second_snapshot,
        policy,
        database_url=database_url,
        project_root=root,
    )
    assert replay["reconciliation"]["status"] == "no_op"
    connection = _database(root, database_url)
    try:
        replayed = connection.execute(
            "SELECT last_validated_by_ingestion_run_id, updated_at_utc "
            "FROM flight_records WHERE source_flight_id = '100'"
        ).fetchone()
        assert replayed["last_validated_by_ingestion_run_id"] == last_validated_by
        assert replayed["updated_at_utc"] == updated_at
    finally:
        connection.close()


def test_conflict_blocks_writes_until_a_reviewed_decision(migrated_database) -> None:
    root, database_url, _name = migrated_database
    first_key = "11111111-1111-4111-8111-111111111111"
    conflict_key = "22222222-2222-4222-8222-222222222222"
    mapping_id, snapshot = _create_mapping(root, database_url, "test-token")
    first_policy = _write_run(
        root,
        run_key=first_key,
        snapshot=snapshot,
        mapping_id=mapping_id,
        records=[
            {
                "source_flight_id": "100",
                "source_flight_url": "https://www.xcontest.org/world/en/flights/detail:one",
            }
        ],
    )
    persist_import(first_key, snapshot, first_policy, database_url=database_url, project_root=root)
    policy = _write_run(
        root,
        run_key=conflict_key,
        snapshot=snapshot,
        mapping_id=mapping_id,
        records=[
            {
                "source_flight_id": "100",
                "source_flight_url": "https://www.xcontest.org/world/en/flights/detail:one",
                "scored_distance_km": 151.0,
            },
            {
                "source_flight_id": "101",
                "source_flight_url": "https://www.xcontest.org/world/en/flights/detail:two",
            },
        ],
    )
    pending = persist_import(
        conflict_key, snapshot, policy, database_url=database_url, project_root=root
    )
    assert pending["status"] == "awaiting_reconciliation_review"
    connection = _database(root, database_url)
    try:
        assert connection.execute("SELECT count(*) FROM flight_ingestion_runs").fetchone()[0] == 1
        row = connection.execute(
            "SELECT source_flight_url FROM flight_records WHERE source_flight_id = '100'"
        ).fetchone()
        assert row["source_flight_url"].endswith("detail:one")
        assert connection.execute("SELECT count(*) FROM flight_records").fetchone()[0] == 1
    finally:
        connection.close()

    proposal_path = root / pending["reconciliation"]["proposals_path"]
    proposal = json.loads(proposal_path.read_text(encoding="utf-8").strip())
    decisions_path = root / pending["reconciliation"]["decisions_path"]
    decisions_path.write_text(
        json.dumps(
            {
                **{
                    key: proposal[key]
                    for key in (
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
                },
                "decision": "keep_existing",
                "verification_reference": "raw-artifact:manual-check",
                "reviewed_by": "AB",
                "reviewed_at_utc": "2026-08-12T11:00:00Z",
                "notes": "Keep the original scored distance.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    resolved = persist_import(
        conflict_key, snapshot, policy, database_url=database_url, project_root=root
    )
    assert resolved["reconciliation"]["counts"]["inserted"] == 1
    assert resolved["reconciliation"]["counts"]["reviewed_keep_existing"] == 1
    connection = _database(root, database_url)
    try:
        assert connection.execute("SELECT count(*) FROM flight_ingestion_runs").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM flight_records").fetchone()[0] == 2
        distance = connection.execute(
            "SELECT scored_distance_km FROM flight_records WHERE source_flight_id = '100'"
        ).fetchone()[0]
        assert distance == 150.0
        row = connection.execute(
            "SELECT source_flight_url FROM flight_records WHERE source_flight_id = '100'"
        ).fetchone()
        assert row["source_flight_url"].endswith("detail:one")
    finally:
        connection.close()

    accepted_policy = _write_run(
        root,
        run_key="33333333-3333-4333-8333-333333333333",
        snapshot=snapshot,
        mapping_id=mapping_id,
        records=[
            {
                "source_flight_id": "100",
                "source_flight_url": "https://www.xcontest.org/world/en/flights/detail:one",
                "scored_distance_km": 151.0,
            }
        ],
    )
    accepted_pending = persist_import(
        "33333333-3333-4333-8333-333333333333",
        snapshot,
        accepted_policy,
        database_url=database_url,
        project_root=root,
    )
    accepted_proposal = json.loads(
        (root / accepted_pending["reconciliation"]["proposals_path"]).read_text(encoding="utf-8")
    )
    (root / accepted_pending["reconciliation"]["decisions_path"]).write_text(
        json.dumps(
            {
                **{
                    key: accepted_proposal[key]
                    for key in (
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
                },
                "decision": "accept_incoming",
                "verification_reference": "raw-artifact:manual-check",
                "reviewed_by": "AB",
                "reviewed_at_utc": "2026-08-12T12:00:00Z",
                "notes": "Accept the corrected scored distance.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    accepted = persist_import(
        "33333333-3333-4333-8333-333333333333",
        snapshot,
        accepted_policy,
        database_url=database_url,
        project_root=root,
    )
    assert accepted["reconciliation"]["counts"]["reviewed_accept_incoming"] == 1
    connection = _database(root, database_url)
    try:
        distance = connection.execute(
            "SELECT scored_distance_km FROM flight_records WHERE source_flight_id = '100'"
        ).fetchone()[0]
        assert distance == 151.0
        row = connection.execute(
            "SELECT source_flight_url FROM flight_records WHERE source_flight_id = '100'"
        ).fetchone()
        assert row["source_flight_url"].endswith("detail:one")
    finally:
        connection.close()


def test_cross_run_exact_duplicate_revalidates_the_existing_record(migrated_database) -> None:
    root, database_url, _name = migrated_database
    first_key = "11111111-1111-4111-8111-111111111111"
    repeat_key = "33333333-3333-4333-8333-333333333333"
    mapping_id, snapshot = _create_mapping(root, database_url, "test-token")
    records = [
        {
            "source_flight_id": "100",
            "source_flight_url": "https://www.xcontest.org/world/en/flights/detail:one",
        }
    ]
    first_policy = _write_run(
        root,
        run_key=first_key,
        snapshot=snapshot,
        mapping_id=mapping_id,
        records=records,
    )
    first = persist_import(
        first_key, snapshot, first_policy, database_url=database_url, project_root=root
    )
    repeat_policy = _write_run(
        root,
        run_key=repeat_key,
        snapshot=snapshot,
        mapping_id=mapping_id,
        records=[{**records[0], "validated_at_utc": "2026-08-13T10:00:00Z"}],
    )
    repeated = persist_import(
        repeat_key, snapshot, repeat_policy, database_url=database_url, project_root=root
    )

    assert repeated["reconciliation"]["counts"]["revalidated_unchanged"] == 1
    connection = _database(root, database_url)
    try:
        row = connection.execute(
            "SELECT source_flight_url, validated_at_utc, created_by_ingestion_run_id, "
            "last_validated_by_ingestion_run_id FROM flight_records"
        ).fetchone()
        assert row["source_flight_url"].endswith("detail:one")
        assert row["validated_at_utc"] == "2026-08-13T10:00:00Z"
        assert row["created_by_ingestion_run_id"] == first["ingestion_run_id"]
        assert row["last_validated_by_ingestion_run_id"] == repeated["ingestion_run_id"]
        assert connection.execute("SELECT count(*) FROM flight_records").fetchone()[0] == 1
    finally:
        connection.close()


def test_reconciliation_preserves_missing_values_and_uses_validation_artifact_time(
    migrated_database,
) -> None:
    root, database_url, _name = migrated_database
    first_key = "44444444-4444-4444-8444-444444444444"
    enrichment_key = "55555555-5555-4555-8555-555555555555"
    preservation_key = "66666666-6666-4666-8666-666666666666"
    mapping_id, snapshot = _create_mapping(root, database_url, "test-token")
    initial = _write_run(
        root,
        run_key=first_key,
        snapshot=snapshot,
        mapping_id=mapping_id,
        records=[
            {
                "source_flight_id": "100",
                "source_flight_url": "https://www.xcontest.org/world/en/flights/detail:one",
                "duration_seconds": None,
            }
        ],
    )
    first = persist_import(
        first_key, snapshot, initial, database_url=database_url, project_root=root
    )
    enriched = _write_run(
        root,
        run_key=enrichment_key,
        snapshot=snapshot,
        mapping_id=mapping_id,
        records=[
            {
                "source_flight_id": "100",
                "source_flight_url": "https://www.xcontest.org/world/en/flights/detail:one",
                "duration_seconds": 7200,
            }
        ],
    )
    enrichment = persist_import(
        enrichment_key, snapshot, enriched, database_url=database_url, project_root=root
    )
    assert enrichment["reconciliation"]["counts"]["enriched"] == 1

    preserved = _write_run(
        root,
        run_key=preservation_key,
        snapshot=snapshot,
        mapping_id=mapping_id,
        records=[
            {
                "source_flight_id": "100",
                "source_flight_url": "https://www.xcontest.org/world/en/flights/detail:one",
                "duration_seconds": None,
            }
        ],
    )
    preservation = persist_import(
        preservation_key, snapshot, preserved, database_url=database_url, project_root=root
    )
    assert preservation["reconciliation"]["counts"]["preserved_existing"] == 1
    connection = _database(root, database_url)
    try:
        row = connection.execute(
            "SELECT duration_seconds, source_flight_url, validated_at_utc, "
            "created_by_ingestion_run_id, last_validated_by_ingestion_run_id, validation_notes "
            "FROM flight_records WHERE source_flight_id = '100'"
        ).fetchone()
        assert row["duration_seconds"] == 7200
        assert row["source_flight_url"].endswith("detail:one")
        assert row["validated_at_utc"] == "2026-08-12T10:00:00Z"
        assert row["created_by_ingestion_run_id"] == first["ingestion_run_id"]
        assert row["last_validated_by_ingestion_run_id"] == preservation["ingestion_run_id"]
        notes = json.loads(row["validation_notes"])
        parsed_notes = parse_quality_notes(
            row["validation_notes"],
            canonical={
                "source_flight_url": row["source_flight_url"],
                "source_site_mapping_id": mapping_id,
                "takeoff_at_utc": "2026-08-01T12:00:00Z",
                "duration_seconds": row["duration_seconds"],
                "scored_distance_km": 150.0,
                "route_type": "free_flight",
                "track_url": None,
                "validation_level": "metadata",
            },
        )
        assert parsed_notes is not None
        assert notes["reconciliation"]["outcome"] == "preserved_existing"
        assert "incoming_missing_value_preserved" in notes["quality_flags"]
    finally:
        connection.close()


def test_invalid_decision_and_mid_transaction_error_rollback_every_write(migrated_database) -> None:
    root, database_url, _name = migrated_database
    first_key = "44444444-4444-4444-8444-444444444444"
    conflict_key = "55555555-5555-4555-8555-555555555555"
    mapping_id, snapshot = _create_mapping(root, database_url, "test-token")
    first_policy = _write_run(
        root,
        run_key=first_key,
        snapshot=snapshot,
        mapping_id=mapping_id,
        records=[
            {
                "source_flight_id": "100",
                "source_flight_url": "https://www.xcontest.org/world/en/flights/detail:one",
            }
        ],
    )
    persist_import(first_key, snapshot, first_policy, database_url=database_url, project_root=root)
    before_connection = _database(root, database_url)
    try:
        before_rows = [tuple(row) for row in _canonical_columns(before_connection)]
    finally:
        before_connection.close()

    policy = _write_run(
        root,
        run_key=conflict_key,
        snapshot=snapshot,
        mapping_id=mapping_id,
        records=[
            {
                "source_flight_id": "100",
                "source_flight_url": "https://www.xcontest.org/world/en/flights/detail:one",
                "scored_distance_km": 151.0,
            },
            {
                "source_flight_id": "101",
                "source_flight_url": "https://www.xcontest.org/world/en/flights/detail:two",
            },
        ],
    )
    pending = persist_import(
        conflict_key, snapshot, policy, database_url=database_url, project_root=root
    )
    decision_path = root / pending["reconciliation"]["decisions_path"]
    proposal = json.loads(
        (root / pending["reconciliation"]["proposals_path"]).read_text(encoding="utf-8")
    )
    stale = _review_decision(proposal, "keep_existing")
    stale["incoming_fingerprint"] = "0" * 64
    decision_path.write_text(json.dumps(stale) + "\n", encoding="utf-8")
    with pytest.raises(PersistenceError, match="does not match its proposal"):
        persist_import(conflict_key, snapshot, policy, database_url=database_url, project_root=root)

    decision_path.write_text(
        json.dumps(_review_decision(proposal, "keep_existing")) + "\n", encoding="utf-8"
    )
    connection = _database(root, database_url)
    try:
        connection.execute(
            "CREATE TRIGGER fail_second_insert BEFORE INSERT ON flight_records "
            "WHEN NEW.source_flight_id = '101' "
            "BEGIN SELECT RAISE(ABORT, 'synthetic mid-transaction failure'); END"
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(
        PersistenceError, match="SQLite reconciliation transaction did not complete"
    ):
        persist_import(conflict_key, snapshot, policy, database_url=database_url, project_root=root)

    after_connection = _database(root, database_url)
    try:
        assert [tuple(row) for row in _canonical_columns(after_connection)] == before_rows
        assert (
            after_connection.execute("SELECT count(*) FROM flight_ingestion_runs").fetchone()[0]
            == 1
        )
    finally:
        after_connection.close()


def test_component_partial_mapping_review_resume_and_no_op(migrated_database, monkeypatch) -> None:
    root, database_url, _name = migrated_database
    run_key = "77777777-7777-4777-8777-777777777777"
    mapping_id, first_snapshot = _create_mapping(root, database_url, "first-token")
    first_records = _generated_records(1000, 174, mapping_id=mapping_id)
    quarantines = _unknown_mapping_quarantines(8)
    policy = _write_run(
        root,
        run_key=run_key,
        snapshot=first_snapshot,
        mapping_id=mapping_id,
        records=first_records,
        quarantine_records=quarantines,
    )
    _write_mapping_proposal_report(root, run_key)
    monkeypatch.setattr(pipeline, "repository_root", lambda: root)
    first = pipeline.resume_run(
        run_key, policy, database_url=database_url, persist_approved_only=True
    )
    assert first["status"] == "succeeded"
    assert first["persistence"]["reconciliation"]["counts"]["inserted"] == 174

    approval, second_snapshot, reviewed_mapping_ids = _apply_mapping_approvals(
        root, database_url, quarantines
    )
    assert approval == {
        "records_seen": 8,
        "inserted": 8,
        "promoted": 0,
        "unchanged": 0,
        "rejected": 0,
    }
    newly_mapped_records = [
        {**record, "source_site_mapping_id": reviewed_mapping_id}
        for record, reviewed_mapping_id in zip(
            _generated_records(2000, 8, mapping_id=mapping_id), reviewed_mapping_ids, strict=True
        )
    ]
    policy = _write_run(
        root,
        run_key=run_key,
        snapshot=second_snapshot,
        mapping_id=mapping_id,
        records=[*first_records, *newly_mapped_records],
        quarantine_records=[],
    )
    resumed = pipeline.resume_run(run_key, policy, database_url=database_url)
    assert resumed["status"] == "succeeded"
    assert resumed["persistence"]["reconciliation"]["counts"] == {
        "inserted": 8,
        "revalidated_unchanged": 174,
        "enriched": 0,
        "preserved_existing": 0,
        "reviewed_keep_existing": 0,
        "reviewed_accept_incoming": 0,
    }
    replay = pipeline.resume_run(run_key, policy, database_url=database_url)
    assert replay["status"] == "succeeded"
    assert replay["persistence"]["reconciliation"]["status"] == "no_op"
    connection = _database(root, database_url)
    try:
        assert connection.execute("SELECT count(*) FROM flight_ingestion_runs").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM flight_records").fetchone()[0] == 182
    finally:
        connection.close()


def test_component_rejected_mappings_revalidate_without_business_field_change(
    migrated_database, monkeypatch
) -> None:
    root, database_url, _name = migrated_database
    run_key = "88888888-8888-4888-8888-888888888888"
    mapping_id, snapshot = _create_mapping(root, database_url, "test-token")
    records = _generated_records(3000, 2, mapping_id=mapping_id)
    quarantines = _unknown_mapping_quarantines(2)
    policy = _write_run(
        root,
        run_key=run_key,
        snapshot=snapshot,
        mapping_id=mapping_id,
        records=records,
        quarantine_records=quarantines,
    )
    _write_mapping_proposal_report(root, run_key)
    monkeypatch.setattr(pipeline, "repository_root", lambda: root)
    first = pipeline.resume_run(
        run_key, policy, database_url=database_url, persist_approved_only=True
    )
    assert first["persistence"]["reconciliation"]["counts"]["inserted"] == 2
    connection = _database(root, database_url)
    try:
        business_before = [tuple(row) for row in _canonical_columns(connection)]
        before_last_validated = [row[10] for row in business_before]
    finally:
        connection.close()
    rejected = _write_mapping_rejections(root, run_key, quarantines, database_url)
    assert rejected == {
        "records_seen": 2,
        "inserted": 0,
        "promoted": 0,
        "unchanged": 0,
        "rejected": 2,
    }

    resumed = pipeline.resume_run(run_key, policy, database_url=database_url)
    assert resumed["status"] == "succeeded"
    assert resumed["reviewed_rejected_mapping_quarantine_count"] == 2
    assert resumed["persistence"]["reconciliation"]["counts"]["revalidated_unchanged"] == 2
    connection = _database(root, database_url)
    try:
        business_after = [tuple(row) for row in _canonical_columns(connection)]
        assert [row[:9] for row in business_after] == [row[:9] for row in business_before]
        assert [row[9] for row in business_after] == [row[9] for row in business_before]
        assert [row[10] for row in business_after] == before_last_validated
    finally:
        connection.close()
