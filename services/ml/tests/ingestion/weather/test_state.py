from __future__ import annotations

import pytest

from paragliding_forecasts_ml.ingestion.weather.artifacts import WeatherArtifactStore
from paragliding_forecasts_ml.ingestion.weather.state import RunStateLedger, StateError

RUN_KEY = "123e4567-e89b-42d3-a456-426614174000"
UTC = "2026-08-21T12:00:00Z"


def initialized_ledger(tmp_path) -> RunStateLedger:
    store = WeatherArtifactStore.create_fresh(RUN_KEY, project_root=tmp_path)
    ledger = RunStateLedger(store)
    ledger.initialize(occurred_at_utc=UTC)
    return ledger


def test_failed_stage_can_resume_from_last_verified_success(tmp_path) -> None:
    ledger = initialized_ledger(tmp_path)
    ledger.append(
        invocation_mode="resume",
        stage="raw_complete",
        disposition="complete",
        occurred_at_utc=UTC,
    )
    ledger.append(
        invocation_mode="resume",
        stage="parsed",
        disposition="failed",
        occurred_at_utc=UTC,
        detail="synthetic parser fault",
    )
    retried = ledger.append(
        invocation_mode="resume",
        stage="parsed",
        disposition="complete",
        occurred_at_utc=UTC,
    )

    assert retried.sequence == 4
    assert [event.disposition for event in ledger.load_events()] == [
        "ready",
        "complete",
        "failed",
        "complete",
    ]


def test_partial_and_persisted_runs_are_terminal(tmp_path) -> None:
    partial = initialized_ledger(tmp_path)
    partial.append(
        invocation_mode="resume",
        stage="raw_complete",
        disposition="partial",
        occurred_at_utc=UTC,
    )
    with pytest.raises(StateError, match="terminal"):
        partial.append(
            invocation_mode="resume",
            stage="raw_complete",
            disposition="complete",
            occurred_at_utc=UTC,
        )

    persisted = initialized_ledger(tmp_path / "persisted")
    for stage in (
        "raw_complete",
        "parsed",
        "normalized",
        "spatially_aligned",
        "validated",
        "features_built",
    ):
        persisted.append(
            invocation_mode="resume",
            stage=stage,
            disposition="complete",
            occurred_at_utc=UTC,
        )
    persisted.append(
        invocation_mode="resume",
        stage="persisted",
        disposition="persisted",
        occurred_at_utc=UTC,
    )
    with pytest.raises(StateError, match="terminal"):
        persisted.append(
            invocation_mode="resume",
            stage="persisted",
            disposition="persisted",
            occurred_at_utc=UTC,
        )


def test_quarantine_can_only_be_resolved_by_new_validation_output(tmp_path) -> None:
    ledger = initialized_ledger(tmp_path)
    for stage in ("raw_complete", "parsed", "normalized", "spatially_aligned"):
        ledger.append(
            invocation_mode="resume",
            stage=stage,
            disposition="complete",
            occurred_at_utc=UTC,
        )
    ledger.append(
        invocation_mode="resume",
        stage="validated",
        disposition="quarantined",
        occurred_at_utc=UTC,
    )
    resolved = ledger.append(
        invocation_mode="resume",
        stage="validated",
        disposition="complete",
        occurred_at_utc=UTC,
    )

    assert resolved.stage == "validated"
    assert resolved.sequence == 7


def test_state_ledger_rejects_a_tampered_predecessor(tmp_path) -> None:
    ledger = initialized_ledger(tmp_path)
    ledger.append(
        invocation_mode="resume",
        stage="raw_complete",
        disposition="complete",
        occurred_at_utc=UTC,
    )
    first = ledger.events_directory / "0001-planned-ready.json"
    first.write_text(
        first.read_text(encoding="utf-8").replace("12:00:00Z", "12:00:01Z"), encoding="utf-8"
    )

    with pytest.raises(StateError, match="predecessor hash"):
        ledger.load_events()
