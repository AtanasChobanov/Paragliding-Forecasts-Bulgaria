"""Synthetic offline boundary tests; no private data or source transport."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from paragliding_forecasts_ml.datasets.flight_label_audit import (
    EvidenceReader,
    audit_labels,
    encoded,
)
from paragliding_forecasts_ml.datasets.flight_labels import LabelAuditError
from paragliding_forecasts_ml.ingestion.xccontest.artifacts import RawArtifactStore
from paragliding_forecasts_ml.ingestion.xccontest.models import (
    PRIMARY_GLIDER_CATEGORY,
    PageObservation,
    RowObservation,
    TargetCollectionStatus,
    source_default_scope,
)
from paragliding_forecasts_ml.ingestion.xccontest.persistence import digest

KEY = "89841b61-c681-4008-b833-031d4aee636e"
TEST_SITE_SLUGS = {
    "sofia-vitosha-kominite",
    "zlatitsa",
    "sopot",
    "nevsha",
    "shumen",
    "pastrina",
    "dobrich-region",
}


@pytest.fixture
def evidence(tmp_path):
    # Small reader-contract database. Production never owns DDL or migrations.
    database = tmp_path / "data/local/test.db"
    database.parent.mkdir(parents=True)
    connection = sqlite3.connect(database)
    connection.executescript("""
        CREATE TABLE sites (id INTEGER PRIMARY KEY, slug TEXT, country_code_iso2 TEXT);
        CREATE TABLE source_site_mappings (id INTEGER PRIMARY KEY, site_id INTEGER, status TEXT);
        CREATE TABLE flight_ingestion_runs (id INTEGER PRIMARY KEY, run_key TEXT, source_id INTEGER,
            status TEXT, model_training_allowed INTEGER, raw_manifest_path TEXT, raw_manifest_sha256 TEXT,
            notes TEXT, pipeline_version TEXT);
        CREATE TABLE flight_records (id INTEGER PRIMARY KEY, source_id INTEGER, source_flight_id TEXT,
            source_site_mapping_id INTEGER, takeoff_at_utc TEXT, scored_distance_km REAL,
            last_validated_by_ingestion_run_id INTEGER);
    """)
    catalog = [(i, slug, "BG") for i, slug in enumerate(sorted(TEST_SITE_SLUGS), 1)]
    connection.executemany("INSERT INTO sites VALUES (?,?,?)", catalog)
    shumen = next(i for i, slug, _ in catalog if slug == "shumen")
    connection.execute("INSERT INTO source_site_mappings VALUES (10,?, 'approved')", (shumen,))
    store = RawArtifactStore(
        project_root=tmp_path, run_key=KEY, clock=lambda: datetime(2026, 9, 30, tzinfo=UTC)
    )
    html = (
        '<div id="flights"><select name="filter[date]">'
        '<option value="2025-06-12" selected>12.06.2025</option></select>'
        '<table class="XClist"><tbody><tr id="flight-123">'
        '<td></td><td><span class="full">12.06.25</span></td>'
        '<td class="km"><strong>55.0</strong></td></tr></tbody></table></div>'
    )
    store.write_page(
        PageObservation(
            season=2025,
            scope=source_default_scope(PRIMARY_GLIDER_CATEGORY, date_filter="2025-06-12"),
            country_filter="BG",
            glider_category_filter="FAI3",
            date_filter="2025-06-12",
            rows=(RowObservation("123", 55, "BG"),),
            fragment_html=html,
            has_next_page=False,
        ),
        acquisition_purpose="all_distance_activity",
    )
    raw_path = store.finalize_manifest(
        requested_seasons=(2025,),
        country_codes=("BG",),
        completed_seasons=(2025,),
        target_statuses=(TargetCollectionStatus(2025, "BG", "complete_primary", ()),),
        delay_seconds=30,
        acknowledge_rate_limit_risk=False,
    )
    folder = tmp_path / "data/interim/xccontest" / KEY / "validation-v4" / ("a" * 64)
    folder.mkdir(parents=True)
    accepted = {
        "source": "xccontest",
        "validation_status": "accepted",
        "source_flight_id": "123",
        "site_id": shumen,
        "source_site_mapping_id": 10,
        "takeoff_at_utc": "2025-06-12T10:00:00Z",
        "scored_distance_km": 55,
    }
    (folder / "accepted-flights.jsonl").write_bytes(encoded(accepted))
    (folder / "site-quarantine.jsonl").write_bytes(b"")
    (folder / "normalized-flights.jsonl").write_bytes(encoded(accepted))
    (folder / "parse-report.json").write_bytes(
        encoded(
            {
                "records_rejected": 0,
                "conflict_candidates": 0,
                "normalized_candidates": 1,
                "source": "xccontest",
                "run_key": KEY,
                "parser_version": "xccontest-parser/2",
                "raw_manifest_path": raw_path.relative_to(tmp_path).as_posix(),
            }
        )
    )
    (folder / "parse-rejections.jsonl").write_bytes(b"")
    report = {
        "source": "xccontest",
        "run_key": KEY,
        "parser_version": "xccontest-parser/2",
        "validator_version": "xccontest-validation/4",
        "mapping_snapshot_sha256": "a" * 64,
        "records_accepted": 1,
        "records_seen": 1,
        "records_rejected": 0,
        "records_quarantined": 0,
        "records_deduplicated": 0,
    }
    for name, path in {
        "raw_manifest": raw_path,
        "accepted_flights": folder / "accepted-flights.jsonl",
        "site_quarantine": folder / "site-quarantine.jsonl",
        "parser_normalized": folder / "normalized-flights.jsonl",
        "parser_report": folder / "parse-report.json",
    }.items():
        report[name + "_path"] = path.relative_to(tmp_path).as_posix()
        report[name + "_sha256"] = digest(path)
    report_path = folder / "validation-report.json"
    report_path.write_bytes(encoded(report))
    event = {
        "validation_snapshot_sha256": "a" * 64,
        "validation_report_path": report_path.relative_to(tmp_path).as_posix(),
        "validation_report_sha256": digest(report_path),
        "accepted_flights_path": report["accepted_flights_path"],
        "accepted_flights_sha256": report["accepted_flights_sha256"],
        "mapping_review_complete": True,
    }
    event_body = {
        "schema_version": 1,
        "run_key": KEY,
        **{
            k: event[k]
            for k in (
                "validation_snapshot_sha256",
                "validation_report_sha256",
                "accepted_flights_sha256",
                "mapping_review_complete",
            )
        },
    }
    event["event_sha256"] = hashlib.sha256(
        json.dumps(event_body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    connection.execute(
        "INSERT INTO flight_ingestion_runs VALUES (1,?,1,'succeeded',1,?,?,?,'synthetic-test/1')",
        (
            KEY,
            raw_path.relative_to(tmp_path).as_posix(),
            digest(raw_path),
            json.dumps({"persistence_events": [event]}),
        ),
    )
    connection.execute(
        "INSERT INTO flight_records VALUES (1,1,'123',10,'2025-06-12T10:00:00Z',55,1)"
    )
    connection.commit()
    connection.close()
    return tmp_path, database, report_path


def run(root, **kwargs):
    return audit_labels(
        seasons=(2025,), database_url="file:./data/local/test.db", project_root=root, **kwargs
    )


def test_replay_is_byte_identical_and_database_untouched(evidence):
    root, database, _ = evidence
    before = digest(database)
    first = run(root)
    second = run(root)
    assert first == second
    assert digest(database) == before
    assert first["summary"]["accepted_positive_distance_flights"] == 1
    assert first["summary"]["thresholds"]["100"]["negative"] == 1
    folder = Path(first["output_directory"])
    known = [
        json.loads(l) for l in (folder / "known_site_day_labels.jsonl").read_text().splitlines()
    ]
    assert len(known) == 1 and known[0]["site_slug"] == "shumen"
    assert first["summary"]["site_days"] == 2555
    manifest = json.loads((folder / "manifest.json").read_text())
    for name, metadata in manifest["outputs"].items():
        assert digest(folder / name) == metadata["sha256"]


@pytest.mark.parametrize(
    "target",
    [
        "accepted-flights.jsonl",
        "site-quarantine.jsonl",
        "normalized-flights.jsonl",
        "parse-report.json",
    ],
)
def test_changed_staging_hash_fails_before_publication(evidence, target):
    root, _, report = evidence
    (report.parent / target).write_bytes(b"tampered\n")
    with pytest.raises(LabelAuditError, match="hash mismatch"):
        run(root)
    assert not (root / "data/processed").exists()


def test_raw_date_and_database_distance_mismatch_fail(evidence):
    root, database, _ = evidence
    connection = sqlite3.connect(database)
    connection.execute("UPDATE flight_records SET scored_distance_km=100")
    connection.commit()
    connection.close()
    with pytest.raises(LabelAuditError, match="disagrees"):
        run(root)


def test_changed_output_never_overwrites_previous_audit(evidence):
    root, _, _ = evidence
    first = run(root)
    output = Path(first["output_directory"])
    (output / "summary.json").write_bytes(b"owner edits\n")
    with pytest.raises(LabelAuditError, match="refusing to overwrite"):
        run(root)
    assert (output / "summary.json").read_bytes() == b"owner edits\n"


def test_training_permission_required_and_output_path_bounded(evidence):
    root, database, _ = evidence
    with pytest.raises(LabelAuditError, match="data/processed"):
        run(root, output_directory=root / "docs/output")
    connection = sqlite3.connect(database)
    connection.execute("UPDATE flight_ingestion_runs SET model_training_allowed=0")
    connection.commit()
    connection.close()
    with pytest.raises(LabelAuditError, match="training-permitted"):
        run(root)


def test_unreviewed_future_maturity_is_not_inferred():
    from paragliding_forecasts_ml.datasets.audit_policy import load_policy

    assert 2026 not in load_policy().seasons


def test_input_change_during_audit_is_detected(evidence):
    root, _, report = evidence
    reader = EvidenceReader(root, {})
    reader.file(report.relative_to(root).as_posix())
    report.write_bytes(b"changed\n")
    with pytest.raises(LabelAuditError, match="changed during audit"):
        reader.recheck()


def reseal(root, database, report_path):
    """Generate internally consistent synthetic provenance after a deliberate fixture change."""
    report = json.loads(report_path.read_text())
    for name in (
        "accepted_flights",
        "site_quarantine",
        "parser_normalized",
        "parser_report",
        "raw_manifest",
    ):
        report[name + "_sha256"] = digest(root / report[name + "_path"])
    report_path.write_bytes(encoded(report))
    connection = sqlite3.connect(database)
    notes = json.loads(connection.execute("SELECT notes FROM flight_ingestion_runs").fetchone()[0])
    event = notes["persistence_events"][-1]
    event["validation_report_sha256"] = digest(report_path)
    event["accepted_flights_sha256"] = report["accepted_flights_sha256"]
    body = {
        "schema_version": 1,
        "run_key": KEY,
        **{
            k: event[k]
            for k in (
                "validation_snapshot_sha256",
                "validation_report_sha256",
                "accepted_flights_sha256",
                "mapping_review_complete",
            )
        },
    }
    event["event_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    connection.execute(
        "UPDATE flight_ingestion_runs SET raw_manifest_sha256=?,notes=?",
        (report["raw_manifest_sha256"], json.dumps(notes)),
    )
    connection.commit()
    connection.close()


def fixture_manifest(evidence):
    root, _, report_path = evidence
    report = json.loads(report_path.read_text())
    path = root / report["raw_manifest_path"]
    return path, json.loads(path.read_text())


def test_stale_selected_date_is_rejected_even_with_consistent_hashes(evidence):
    root, database, report = evidence
    path, manifest = fixture_manifest(evidence)
    raw = root / manifest["artifacts"][0]["path"]
    raw.write_text(raw.read_text().replace('value="2025-06-12"', 'value="2025-06-11"'))
    manifest["artifacts"][0]["sha256"] = digest(raw)
    path.write_bytes(encoded(manifest))
    reseal(root, database, report)
    with pytest.raises(ValueError, match="selected date"):
        run(root)


def test_paginated_parent_does_not_prove_negative_coverage(evidence):
    root, database, report = evidence
    path, manifest = fixture_manifest(evidence)
    manifest["artifacts"][0]["has_next_page"] = True
    manifest["activity_scope_statuses"][0]["status"] = "partial_saturated"
    path.write_bytes(encoded(manifest))
    reseal(root, database, report)
    summary = run(root)["summary"]
    assert summary["thresholds"]["100"]["negative"] == 0
    assert summary["thresholds"]["100"]["unknown_reasons"]["incomplete_daily_activity_scope"] == 1


def test_threshold_rejection_blocks_only_thresholds_it_could_hide(evidence):
    root, database, report_path = evidence
    path, manifest = fixture_manifest(evidence)
    artifact = manifest["artifacts"][0]
    raw = root / artifact["path"]
    extra = (
        '<tr id="flight-456"><td></td><td><span class="full">12.06.25</span></td>'
        '<td class="km"><strong>150</strong></td></tr>'
    )
    raw.write_text(raw.read_text().replace("</tbody>", extra + "</tbody>"))
    artifact.update(
        sha256=digest(raw),
        source_flight_ids=["123", "456"],
        row_observation_count=2,
        at_or_above_100km_row_observation_count=1,
    )
    manifest["observation_counts"].update(
        row_observations_seen=2,
        distinct_source_flights_seen=2,
        at_or_above_100km_row_observations=1,
    )
    path.write_bytes(encoded(manifest))
    parser_path = report_path.parent / "parse-report.json"
    parser = json.loads(parser_path.read_text())
    parser["records_rejected"] = 1
    parser_path.write_bytes(encoded(parser))
    (report_path.parent / "parse-rejections.jsonl").write_bytes(
        encoded(
            {
                "source_flight_id": "456",
                "artifact_reference": {
                    "artifact_path": artifact["path"],
                    "artifact_sha256": artifact["sha256"],
                },
            }
        )
    )
    report = json.loads(report_path.read_text())
    report.update(records_rejected=1, records_seen=2)
    report_path.write_bytes(encoded(report))
    reseal(root, database, report_path)
    summary = run(root)["summary"]
    assert summary["thresholds"]["100"]["negative"] == 0
    assert summary["thresholds"]["200"]["negative"] == 1
    assert summary["thresholds"]["300"]["negative"] == 1


def test_unresolved_mapping_and_reviewed_rejection_are_distinct(evidence):
    from paragliding_forecasts_ml.ingestion.xccontest.site_mapping import _proposal_id

    root, database, report_path = evidence
    candidate = {"source_flight_id": "456", "launch_name_raw": "Outside test site"}
    quarantine = {
        "reason": "unknown_mapping",
        "mapping_disposition": "review_required",
        "candidate": candidate,
    }
    (report_path.parent / "site-quarantine.jsonl").write_bytes(encoded(quarantine))
    normalized_path = report_path.parent / "normalized-flights.jsonl"
    normalized_path.write_bytes(normalized_path.read_bytes() + encoded(candidate))
    parser_path = report_path.parent / "parse-report.json"
    parser = json.loads(parser_path.read_text())
    parser["normalized_candidates"] = 2
    parser_path.write_bytes(encoded(parser))
    report = json.loads(report_path.read_text())
    report.update(records_quarantined=1, records_seen=2)
    report_path.write_bytes(encoded(report))
    reseal(root, database, report_path)
    assert run(root)["summary"]["thresholds"]["100"]["negative"] == 0
    directory = root / "data/interim/xccontest" / KEY / "site-mapping-v4"
    directory.mkdir()
    proposal = {
        "source": "xccontest",
        "key_type": "normalized_name",
        "key_value": "outside test site",
        "proposal_id": _proposal_id("normalized_name", "outside test site"),
    }
    (directory / "mapping-proposals.jsonl").write_bytes(encoded(proposal))
    (directory / "mapping-decisions.jsonl").write_bytes(
        encoded({**proposal, "decision": "rejected"})
    )
    result = run(root)
    assert result["summary"]["thresholds"]["100"]["negative"] == 1


def test_cli_reports_verification_failure(monkeypatch, capsys):
    from paragliding_forecasts_ml.datasets import flight_label_cli

    def failure(**kwargs):
        raise LabelAuditError("synthetic verification failure")

    monkeypatch.setattr(flight_label_cli, "audit_labels", failure)
    assert flight_label_cli.main(["--season", "2025"]) == 1
    assert "synthetic verification failure" in capsys.readouterr().err


def test_new_site_is_loaded_from_database(evidence):
    root, database, _ = evidence
    connection = sqlite3.connect(database)
    connection.execute("INSERT INTO sites VALUES (8,'new-launch','BG')")
    connection.commit()
    connection.close()
    result = run(root)
    assert result["summary"]["site_days"] == 8 * 365
    rows = [
        json.loads(line)
        for line in (Path(result["output_directory"]) / "site_day_label_audit.jsonl")
        .read_text()
        .splitlines()
    ]
    new = [r for r in rows if r["site_slug"] == "new-launch"]
    assert len(new) == 365 and all(r["flight_count"] == 0 for r in new)


def test_false_maturity_in_configuration_blocks_negatives_without_losing_activity(evidence):
    from paragliding_forecasts_ml.datasets.audit_policy import load_policy

    root, _, _ = evidence
    policy = load_policy().document
    policy["coverage_runs"] = [e for e in policy["coverage_runs"] if e["run_key"] == KEY]
    policy["coverage_runs"][0]["mature"] = False
    path = root / "data/local/audit-policy.json"
    path.write_bytes(encoded(policy))
    result = run(root, policy_file=path)
    assert result["summary"]["accepted_positive_distance_flights"] == 1
    assert result["summary"]["thresholds"]["100"]["negative"] == 0
    assert result["summary"]["thresholds"]["100"]["unknown_reasons"]["evidence_not_mature"] == 1


def test_new_snapshot_uuid_does_not_require_source_changes(evidence):
    from paragliding_forecasts_ml.datasets.audit_policy import load_policy

    root, database, report_path = evidence
    new_key = "11111111-1111-4111-8111-111111111111"
    # Change only synthetic identity and its immutable references, not product code.
    for zone in ("raw", "interim"):
        (root / "data" / zone / "xccontest" / KEY).rename(
            root / "data" / zone / "xccontest" / new_key
        )
    for path in (root / "data").rglob("*.json*"):
        path.write_bytes(path.read_bytes().replace(KEY.encode(), new_key.encode()))
    report_path = Path(str(report_path).replace(KEY, new_key))
    connection = sqlite3.connect(database)
    row = connection.execute("SELECT notes,raw_manifest_path FROM flight_ingestion_runs").fetchone()
    connection.execute(
        "UPDATE flight_ingestion_runs SET run_key=?,notes=?,raw_manifest_path=?",
        (new_key, row[0].replace(KEY, new_key), row[1].replace(KEY, new_key)),
    )
    connection.commit()
    connection.close()
    # Reseal using this synthetic key, following the existing persistence contract.
    report = json.loads(report_path.read_text())
    for name in (
        "accepted_flights",
        "site_quarantine",
        "parser_normalized",
        "parser_report",
        "raw_manifest",
    ):
        report[name + "_sha256"] = digest(root / report[name + "_path"])
    report_path.write_bytes(encoded(report))
    connection = sqlite3.connect(database)
    notes = json.loads(connection.execute("SELECT notes FROM flight_ingestion_runs").fetchone()[0])
    event = notes["persistence_events"][-1]
    event["validation_report_sha256"] = digest(report_path)
    body = {
        "schema_version": 1,
        "run_key": new_key,
        **{
            k: event[k]
            for k in (
                "validation_snapshot_sha256",
                "validation_report_sha256",
                "accepted_flights_sha256",
                "mapping_review_complete",
            )
        },
    }
    event["event_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    connection.execute(
        "UPDATE flight_ingestion_runs SET raw_manifest_sha256=?,notes=?",
        (report["raw_manifest_sha256"], json.dumps(notes)),
    )
    connection.commit()
    connection.close()
    policy = load_policy().document
    policy["coverage_runs"] = [{"run_key": new_key, "seasons": [2025], "mature": True}]
    path = root / "data/local/audit-policy.json"
    path.write_bytes(encoded(policy))
    assert run(root, policy_file=path)["summary"]["thresholds"]["100"]["negative"] == 1
