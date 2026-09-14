from __future__ import annotations

import json

import pytest

from paragliding_forecasts_ml.ingestion.atmosphere.contracts import ArtifactReference
from paragliding_forecasts_ml.ingestion.weather import artifact_audit_cli
from paragliding_forecasts_ml.ingestion.weather.artifact_audit import (
    audit_weather_artifacts,
)
from paragliding_forecasts_ml.ingestion.weather.artifacts import (
    ArtifactError,
    WeatherArtifactStore,
)
from paragliding_forecasts_ml.ingestion.weather.state import RunStateLedger

RUN_KEY = "123e4567-e89b-42d3-a456-426614174000"
UTC = "2026-08-21T12:00:00Z"


def reference(key: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_key="stage_manifest",
        relative_path=f"data/interim/weather/{RUN_KEY}/{key}/stage-manifest.json",
        sha256=key * 64,
        byte_count=1,
        media_type="application/json",
    )


def ledger_with_superseded_parser(tmp_path) -> tuple[ArtifactReference, ArtifactReference]:
    store = WeatherArtifactStore.create_fresh(RUN_KEY, project_root=tmp_path)
    ledger = RunStateLedger(store)
    ledger.initialize(occurred_at_utc=UTC)
    ledger.append(
        invocation_mode="resume",
        stage="raw_complete",
        disposition="complete",
        occurred_at_utc=UTC,
    )
    old = reference("a")
    ledger.append(
        invocation_mode="resume",
        stage="parsed",
        disposition="complete",
        occurred_at_utc=UTC,
        evidence=old,
    )
    ledger.append(
        invocation_mode="resume",
        stage="normalized",
        disposition="complete",
        occurred_at_utc=UTC,
    )
    current = reference("b")
    ledger.append(
        invocation_mode="resume",
        stage="parsed",
        disposition="complete",
        occurred_at_utc=UTC,
        evidence=current,
        supersedes_sequence=3,
    )
    return old, current


def test_effective_audit_ignores_unused_superseded_evidence(tmp_path, monkeypatch) -> None:
    old, current = ledger_with_superseded_parser(tmp_path)
    verified: list[ArtifactReference] = []

    def verify(_store, artifact):
        verified.append(artifact)
        if artifact == old:
            raise ArtifactError("superseded evidence is corrupt")
        return tmp_path

    monkeypatch.setattr(WeatherArtifactStore, "verify_boundary", verify)

    report = audit_weather_artifacts(RUN_KEY, scope="effective", project_root=tmp_path)

    assert verified == [current]
    assert report["verified_boundary_count"] == 1
    assert report["verified_boundaries"][0]["sequence"] == 5


def test_all_history_audit_reports_corrupt_superseded_evidence(tmp_path, monkeypatch) -> None:
    old, _ = ledger_with_superseded_parser(tmp_path)

    def verify(_store, artifact):
        if artifact == old:
            raise ArtifactError("superseded evidence is corrupt")
        return tmp_path

    monkeypatch.setattr(WeatherArtifactStore, "verify_boundary", verify)

    with pytest.raises(ArtifactError, match="superseded evidence"):
        audit_weather_artifacts(RUN_KEY, scope="all", project_root=tmp_path)


def test_artifact_audit_cli_emits_machine_readable_scope_report(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        artifact_audit_cli,
        "audit_weather_artifacts",
        lambda run_key, *, scope, project_root: {
            "run_key": run_key,
            "scope": scope,
            "project_root": str(project_root),
            "verified_boundary_count": 0,
        },
    )

    exit_code = artifact_audit_cli.main(
        [
            "audit",
            "--run-key",
            RUN_KEY,
            "--scope",
            "effective",
            "--project-root",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["scope"] == "effective"
