from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from paragliding_forecasts_ml.ingestion.weather import pipeline, pipeline_cli

RUN_KEY = "123e4567-e89b-42d3-a456-426614174000"


def _preflight() -> pipeline.WeatherPreflight:
    return pipeline.WeatherPreflight(
        database_url="file:./data/local/test.db",
        site_config_sha256="a" * 64,
        sampling_policy_sha256="b" * 64,
        compact_selection_version="regular-grid-footprint-crop/1",
    )


def _context(raw_disposition: str = "complete") -> SimpleNamespace:
    raw_event = SimpleNamespace(disposition=raw_disposition, evidence=object())
    snapshot = SimpleNamespace(
        effective_event=lambda stage: raw_event if stage == "raw_complete" else None
    )
    return SimpleNamespace(
        run_key=RUN_KEY,
        snapshot=snapshot,
        store=SimpleNamespace(verify_raw_manifest=lambda reference: reference),
        verification_summary=lambda: {"files_hashed": 1},
    )


def _result(**values):
    return SimpleNamespace(**values, as_dict=lambda: dict(values))


def test_offline_services_use_one_context_and_carry_each_snapshot(monkeypatch) -> None:
    context = _context()
    snapshots = [context.snapshot, object(), object(), object(), object(), object()]
    calls: list[tuple[str, object]] = []

    def stage(name, result, index):
        def invoke(actual, *_args):
            assert actual is context
            assert actual.snapshot is snapshots[index]
            calls.append((name, actual))
            return result, snapshots[index + 1]

        return invoke

    monkeypatch.setattr(
        pipeline,
        "parse_and_normalize",
        stage("parse", _result(stage="parse"), 0),
    )
    monkeypatch.setattr(pipeline, "sample_sites", stage("sample", _result(stage="sample"), 1))
    monkeypatch.setattr(
        pipeline,
        "validate_run",
        stage("validate", _result(disposition="complete"), 2),
    )
    monkeypatch.setattr(
        pipeline,
        "build_features",
        stage("features", _result(disposition="complete"), 3),
    )
    persistence = SimpleNamespace(
        report={"status": "inserted"},
        as_dict=lambda: {"status": "inserted"},
    )
    monkeypatch.setattr(pipeline, "persist_run", stage("persist", persistence, 4))

    result = pipeline._offline_services(context, Path("policy.json"))

    assert result["status"] == "inserted"
    assert [name for name, _context in calls] == [
        "parse",
        "sample",
        "validate",
        "features",
        "persist",
    ]
    assert len({id(actual) for _name, actual in calls}) == 1
    assert context.snapshot is snapshots[-1]


def test_acquisition_identity_changes_with_compact_configuration() -> None:
    common = {
        "source_id": "noaa_gfs_0p25_aws_grib2",
        "source_kind": "forecast",
        "ingestion_method": "public_object_archive",
        "request_purpose": "historical_forecast",
        "catalogue_version": "catalogue/1",
        "catalogue_sha256": "d" * 64,
        "adapter_request_schema_version": 2,
        "expected_artifact_keys": ("raw",),
    }
    first = SimpleNamespace(
        **common,
        adapter_request={
            "site_config_sha256": "a" * 64,
            "sampling_policy_sha256": "b" * 64,
            "compact_selection_version": "regular-grid-footprint-crop/1",
        },
    )
    changed = SimpleNamespace(
        **common,
        adapter_request={
            **first.adapter_request,
            "site_config_sha256": "c" * 64,
        },
    )

    assert pipeline._acquisition_identity(first) != pipeline._acquisition_identity(changed)


def test_resume_is_offline_and_stops_before_features_on_quarantine(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    context = _context()
    monkeypatch.setattr(pipeline, "_preflight", lambda *_args: _preflight())
    monkeypatch.setattr(pipeline.WeatherRunContext, "open", lambda *_a, **_k: context)
    monkeypatch.setattr(
        pipeline,
        "parse_and_normalize",
        lambda actual: (calls.append("parse"), (_result(stage="parse"), actual.snapshot))[1],
    )
    monkeypatch.setattr(
        pipeline,
        "sample_sites",
        lambda actual: (calls.append("sample"), (_result(stage="sample"), actual.snapshot))[1],
    )
    monkeypatch.setattr(
        pipeline,
        "validate_run",
        lambda actual: (
            calls.append("validate"),
            (_result(disposition="quarantined"), actual.snapshot),
        )[1],
    )
    monkeypatch.setattr(
        pipeline,
        "build_features",
        lambda _context: pytest.fail("quarantined run must not build features"),
    )
    monkeypatch.setattr(
        pipeline,
        "persist_run",
        lambda *_args, **_kwargs: pytest.fail("quarantined run must not persist"),
    )

    result = pipeline.resume_run(
        RUN_KEY,
        tmp_path / "policy.json",
        project_root=tmp_path,
    )

    assert result["status"] == "quarantined"
    assert result["network_access"] is False
    assert calls == ["parse", "sample", "validate"]


def test_resume_rejects_partial_raw_coverage_without_stage_calls(monkeypatch, tmp_path) -> None:
    context = _context("partial")
    monkeypatch.setattr(pipeline, "_preflight", lambda *_args: _preflight())
    monkeypatch.setattr(pipeline.WeatherRunContext, "open", lambda *_a, **_k: context)
    monkeypatch.setattr(
        pipeline,
        "parse_and_normalize",
        lambda _arguments: pytest.fail("partial raw coverage must not be parsed"),
    )

    result = pipeline.resume_run(RUN_KEY, tmp_path / "policy.json", project_root=tmp_path)

    assert result == {
        "status": "incomplete_coverage",
        "run_key": RUN_KEY,
        "raw_disposition": "partial",
        "network_access": False,
        "verification_summary": {"files_hashed": 1},
        "next_step": "Start a new fresh GFS collection; partial raw coverage cannot resume.",
    }


def test_fresh_rejects_network_before_any_preflight_or_collection(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        pipeline,
        "_preflight",
        lambda *_args: pytest.fail("network acknowledgement must be checked first"),
    )
    monkeypatch.setattr(
        pipeline,
        "collect_gfs_run",
        lambda *_args, **_kwargs: pytest.fail("collection must not start"),
    )

    with pytest.raises(pipeline.WeatherPipelineError, match="--allow-live-network"):
        pipeline.fresh_run(
            local_date="2026-08-21",
            purpose="operational_forecast",
            policy_path=Path(tmp_path / "policy.json"),
            explicit_run_at="2026-08-20T00:00:00Z",
            maximum_total_mib=256,
            allow_live_network=False,
            project_root=tmp_path,
        )


def test_fresh_returns_exact_completed_acquisition_without_resume(monkeypatch, tmp_path) -> None:
    captured: list[object] = []
    monkeypatch.setattr(pipeline, "_preflight", lambda *_args: _preflight())
    monkeypatch.setattr(
        pipeline,
        "collect_gfs_run",
        lambda request, **_kwargs: (
            captured.append(request),
            {"run_key": RUN_KEY, "status": "already_succeeded"},
        )[1],
    )
    monkeypatch.setattr(
        pipeline,
        "_offline_services",
        lambda *_args, **_kwargs: pytest.fail("exact completed acquisition must not resume"),
    )

    result = pipeline.fresh_run(
        local_date="2026-08-21",
        purpose="historical_forecast",
        policy_path=tmp_path / "policy.json",
        newest_complete_before="2026-08-20T12:00:00Z",
        maximum_total_mib=256,
        allow_live_network=True,
        project_root=tmp_path,
    )

    assert result["status"] == "already_succeeded"
    assert result["run_key"] == RUN_KEY
    assert result["network_access"] == "inventory_only"
    request = captured[0]
    assert request.site_config_sha256 == "a" * 64
    assert request.sampling_policy_sha256 == "b" * 64
    assert request.compact_selection_version == "regular-grid-footprint-crop/1"


def test_pipeline_cli_accepts_existing_acquisition_as_success(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        pipeline_cli,
        "fresh_run",
        lambda **_kwargs: {"status": "already_succeeded", "run_key": RUN_KEY},
    )

    assert (
        pipeline_cli.main(
            [
                "fresh",
                "--local-date",
                "2026-08-21",
                "--purpose",
                "historical_forecast",
                "--newest-complete-before",
                "2026-08-20T12:00:00Z",
                "--maximum-total-mib",
                "256",
                "--policy-file",
                str(tmp_path / "policy.json"),
                "--allow-live-network",
            ]
        )
        == 0
    )


def test_fresh_returns_partial_collection_without_resume(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(pipeline, "_preflight", lambda *_args: _preflight())
    monkeypatch.setattr(
        pipeline,
        "collect_gfs_run",
        lambda *_args, **_kwargs: {"run_key": RUN_KEY, "status": "partial"},
    )
    monkeypatch.setattr(
        pipeline,
        "_offline_services",
        lambda *_args, **_kwargs: pytest.fail("partial collection must not resume"),
    )

    result = pipeline.fresh_run(
        local_date="2026-08-21",
        purpose="historical_forecast",
        policy_path=tmp_path / "policy.json",
        newest_complete_before="2026-08-20T12:00:00Z",
        maximum_total_mib=256,
        allow_live_network=True,
        project_root=tmp_path,
    )

    assert result["status"] == "incomplete_coverage"
    assert result["run_key"] == RUN_KEY
