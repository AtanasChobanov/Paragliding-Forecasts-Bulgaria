from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from paragliding_forecasts_ml.ingestion.xccontest import pipeline, pipeline_cli
from paragliding_forecasts_ml.ingestion.xccontest.models import CollectorConfig
from paragliding_forecasts_ml.ingestion.xccontest.persistence import PersistenceError

RUN_KEY = "11111111-1111-4111-8111-111111111111"
SNAPSHOT = "a" * 64


def _validation_report(
    root: Path,
    *,
    reason: str | None,
    accepted: int = 1,
    candidate: dict | None = None,
) -> dict:
    relative = Path("data/interim/xccontest") / RUN_KEY / "validation-v2" / SNAPSHOT
    folder = root / relative
    folder.mkdir(parents=True)
    quarantine = folder / "site-quarantine.jsonl"
    if reason is not None:
        quarantine.write_text(
            json.dumps(
                {
                    "reason": reason,
                    "candidate": candidate
                    or {
                        "launch_search_url": (
                            "https://www.xcontest.org/world/en/flights-search/?filter[site]=test-token"
                        )
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
    else:
        quarantine.write_text("", encoding="utf-8")
    return {
        "run_key": RUN_KEY,
        "mapping_snapshot_sha256": SNAPSHOT,
        "site_quarantine_path": (relative / "site-quarantine.jsonl").as_posix(),
        "records_accepted": accepted,
    }


def _stub_offline_stages(monkeypatch, root: Path, report: dict) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(pipeline, "_preflight", lambda *_: ("file:./data/local/test.db", ("BG",)))
    monkeypatch.setattr(pipeline, "repository_root", lambda: root)
    monkeypatch.setattr(
        pipeline,
        "_existing_or_parsed",
        lambda *_: calls.append("parse") or {"parser_version": "xccontest-parser/2"},
    )
    monkeypatch.setattr(
        pipeline,
        "_existing_or_proposed",
        lambda *_: calls.append("propose") or {"proposals_path": "proposal.jsonl"},
    )
    monkeypatch.setattr(
        pipeline,
        "_existing_or_validated",
        lambda *_: calls.append("validate") or report,
    )
    return calls


def test_resume_pauses_for_actionable_mapping_quarantine_without_persistence(
    monkeypatch, tmp_path
) -> None:
    report = _validation_report(tmp_path, reason="unknown_mapping")
    calls = _stub_offline_stages(monkeypatch, tmp_path, report)
    monkeypatch.setattr(
        pipeline,
        "persist_import",
        lambda *_args, **_kwargs: pytest.fail("persistence must wait for mapping review"),
    )

    result = pipeline.resume_run(RUN_KEY, tmp_path / "policy.json")

    assert result["status"] == "awaiting_mapping_review"
    assert result["actionable_mapping_quarantine_count"] == 1
    assert calls == ["parse", "propose", "validate"]


def test_resume_persists_when_rejected_decision_covers_mapping_quarantine(
    monkeypatch, tmp_path
) -> None:
    candidate = {
        "source_flight_id": "rejected-flight",
        "launch_search_url": (
            "https://www.xcontest.org/world/en/flights-search/?filter[site]=rejected-token"
        ),
    }
    key_type, key_value = pipeline._proposal_key(candidate)
    proposal = {
        "proposal_id": pipeline._proposal_id(key_type, key_value),
        "source": "xccontest",
        "key_type": key_type,
        "key_value": key_value,
        "point_latitude_deg": None,
        "point_longitude_deg": None,
    }
    mapping_directory = tmp_path / "data" / "interim" / "xccontest" / RUN_KEY / "site-mapping-v2"
    mapping_directory.mkdir(parents=True)
    (mapping_directory / "mapping-proposals.jsonl").write_text(
        json.dumps(proposal) + "\n", encoding="utf-8"
    )
    (mapping_directory / "mapping-decisions.jsonl").write_text(
        json.dumps({**proposal, "decision": "rejected"}) + "\n", encoding="utf-8"
    )
    report = _validation_report(tmp_path, reason="unknown_mapping", candidate=candidate)
    calls = _stub_offline_stages(monkeypatch, tmp_path, report)
    persisted: list[tuple[str, str]] = []
    monkeypatch.setattr(
        pipeline,
        "persist_import",
        lambda run_key, snapshot, *_args, **_kwargs: (
            persisted.append((run_key, snapshot)) or {"status": "succeeded"}
        ),
    )

    result = pipeline.resume_run(RUN_KEY, tmp_path / "policy.json")

    assert result["status"] == "succeeded"
    assert result["actionable_mapping_quarantine_count"] == 0
    assert result["reviewed_rejected_mapping_quarantine_count"] == 1
    assert calls == ["parse", "propose", "validate"]
    assert persisted == [(RUN_KEY, SNAPSHOT)]


def test_resume_does_not_trust_rejected_decision_for_different_proposal(
    monkeypatch, tmp_path
) -> None:
    candidate = {
        "source_flight_id": "unresolved-flight",
        "launch_search_url": (
            "https://www.xcontest.org/world/en/flights-search/?filter[site]=unresolved-token"
        ),
    }
    mapping_directory = tmp_path / "data" / "interim" / "xccontest" / RUN_KEY / "site-mapping-v2"
    mapping_directory.mkdir(parents=True)
    proposal = {
        "proposal_id": "a" * 64,
        "source": "xccontest",
        "key_type": "source_site_token",
        "key_value": "other-token",
        "point_latitude_deg": None,
        "point_longitude_deg": None,
    }
    (mapping_directory / "mapping-proposals.jsonl").write_text(
        json.dumps(proposal) + "\n", encoding="utf-8"
    )
    (mapping_directory / "mapping-decisions.jsonl").write_text(
        json.dumps({**proposal, "decision": "rejected"}) + "\n", encoding="utf-8"
    )
    report = _validation_report(tmp_path, reason="unknown_mapping", candidate=candidate)
    _stub_offline_stages(monkeypatch, tmp_path, report)
    monkeypatch.setattr(
        pipeline,
        "persist_import",
        lambda *_args, **_kwargs: pytest.fail("unreviewed mapping must still block persistence"),
    )

    result = pipeline.resume_run(RUN_KEY, tmp_path / "policy.json")

    assert result["status"] == "awaiting_mapping_review"
    assert result["actionable_mapping_quarantine_count"] == 1
    assert result["reviewed_rejected_mapping_quarantine_count"] == 0


def test_resume_persists_approved_records_after_review_or_explicit_override(
    monkeypatch, tmp_path
) -> None:
    report = _validation_report(tmp_path, reason="unknown_mapping")
    calls = _stub_offline_stages(monkeypatch, tmp_path, report)
    persisted: list[tuple[str, str]] = []
    monkeypatch.setattr(
        pipeline,
        "persist_import",
        lambda run_key, snapshot, *_args, **_kwargs: (
            persisted.append((run_key, snapshot)) or {"status": "succeeded", "records_accepted": 1}
        ),
    )

    result = pipeline.resume_run(
        RUN_KEY,
        tmp_path / "policy.json",
        persist_approved_only=True,
    )

    assert result["status"] == "succeeded"
    assert calls == ["parse", "propose", "validate"]
    assert persisted == [(RUN_KEY, SNAPSHOT)]


def test_resume_surfaces_reconciliation_review_without_restarting_stages(
    monkeypatch, tmp_path
) -> None:
    report = _validation_report(tmp_path, reason=None)
    calls = _stub_offline_stages(monkeypatch, tmp_path, report)
    monkeypatch.setattr(
        pipeline,
        "persist_import",
        lambda *_args, **_kwargs: {
            "status": "awaiting_reconciliation_review",
            "reconciliation": {"proposal_count": 1},
        },
    )

    result = pipeline.resume_run(RUN_KEY, tmp_path / "policy.json")

    assert result["status"] == "awaiting_reconciliation_review"
    assert "Review reconciliation decisions" in result["next_step"]
    assert calls == ["parse", "propose", "validate"]


def test_resume_stops_when_no_records_are_accepted(monkeypatch, tmp_path) -> None:
    report = _validation_report(tmp_path, reason=None, accepted=0)
    _stub_offline_stages(monkeypatch, tmp_path, report)
    monkeypatch.setattr(
        pipeline,
        "persist_import",
        lambda *_args, **_kwargs: pytest.fail("zero accepted records must not persist"),
    )

    result = pipeline.resume_run(RUN_KEY, tmp_path / "policy.json")

    assert result["status"] == "no_accepted_records"


def test_fresh_stops_after_incomplete_collection_without_offline_stages(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(pipeline, "_preflight", lambda *_: ("file:./data/local/test.db", ("BG",)))
    collection = SimpleNamespace(
        run_key=RUN_KEY,
        status="incomplete",
        manifest_relative_path="data/raw/xccontest/run/manifest.json",
        manifest_sha256="b" * 64,
        country_codes=("BG",),
        completed_seasons=(2024,),
        artifact_count=1,
        row_observations_seen=10,
        distinct_source_flights_seen=10,
        repeated_source_flight_observations=0,
    )
    monkeypatch.setattr(pipeline, "collect_run", lambda _: collection)
    monkeypatch.setattr(
        pipeline,
        "resume_run",
        lambda *_args, **_kwargs: pytest.fail(
            "incomplete collection must not resume automatically"
        ),
    )

    result = pipeline.fresh_run(
        CollectorConfig(seasons=(2024,), country_codes=("BG",)), tmp_path / "policy.json"
    )

    assert result["status"] == "incomplete_coverage"
    assert result["run_key"] == RUN_KEY


def test_fresh_preflight_failure_precedes_collection(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        pipeline,
        "load_policy",
        lambda *_: (_ for _ in ()).throw(PersistenceError("invalid policy")),
    )
    monkeypatch.setattr(
        pipeline,
        "collect_run",
        lambda _: pytest.fail("source collection must not start before preflight"),
    )

    with pytest.raises(pipeline.PipelineError, match="preflight"):
        pipeline.fresh_run(
            CollectorConfig(seasons=(2024,), country_codes=("BG",)), tmp_path / "policy.json"
        )


def test_pipeline_cli_returns_distinct_pause_exit_code(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(
        pipeline_cli,
        "resume_run",
        lambda *_args, **_kwargs: {"status": "awaiting_mapping_review", "run_key": RUN_KEY},
    )

    exit_code = pipeline_cli.main(
        ["resume", "--run-key", RUN_KEY, "--policy-file", str(tmp_path / "policy.json")]
    )

    assert exit_code == 2
    assert '"status": "awaiting_mapping_review"' in capsys.readouterr().out
