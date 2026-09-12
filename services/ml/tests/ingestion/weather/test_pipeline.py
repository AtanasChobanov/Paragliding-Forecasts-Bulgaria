from __future__ import annotations

import json
from pathlib import Path

import pytest

from paragliding_forecasts_ml.ingestion.weather import pipeline, pipeline_cli

RUN_KEY = "123e4567-e89b-42d3-a456-426614174000"


def _cli(payload: dict[str, object], exit_code: int = 0):
    def invoke(_arguments: list[str]) -> int:
        print(json.dumps(payload))
        return exit_code

    return invoke


def test_cli_stage_allows_structured_quarantine_result() -> None:
    result = pipeline._run_cli_stage(
        _cli({"disposition": "quarantined"}, exit_code=2),
        [],
        "validator",
        allowed_exit_codes=frozenset({0, 2}),
    )

    assert result == {"disposition": "quarantined"}


def test_resume_is_offline_and_stops_before_features_on_quarantine(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    monkeypatch.setattr(pipeline, "_preflight", lambda *_args: "file:./data/local/test.db")
    monkeypatch.setattr(pipeline, "_raw_state", lambda *_args: "complete")
    monkeypatch.setattr(
        pipeline,
        "gfs_parse_cli",
        lambda arguments: (calls.append("parse"), _cli({"stage": "parse"})(arguments))[1],
    )
    monkeypatch.setattr(
        pipeline,
        "gfs_sample_cli",
        lambda arguments: (calls.append("sample"), _cli({"stage": "sample"})(arguments))[1],
    )
    monkeypatch.setattr(
        pipeline,
        "weather_validate_cli",
        lambda arguments: (
            calls.append("validate"),
            _cli({"disposition": "quarantined"}, exit_code=2)(arguments),
        )[1],
    )
    monkeypatch.setattr(
        pipeline,
        "weather_features_cli",
        lambda _arguments: pytest.fail("quarantined run must not build features"),
    )
    monkeypatch.setattr(
        pipeline,
        "persist_weather_run",
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
    monkeypatch.setattr(pipeline, "_preflight", lambda *_args: "file:./data/local/test.db")
    monkeypatch.setattr(pipeline, "_raw_state", lambda *_args: "partial")
    monkeypatch.setattr(
        pipeline,
        "gfs_parse_cli",
        lambda _arguments: pytest.fail("partial raw coverage must not be parsed"),
    )

    result = pipeline.resume_run(RUN_KEY, tmp_path / "policy.json", project_root=tmp_path)

    assert result == {
        "status": "incomplete_coverage",
        "run_key": RUN_KEY,
        "raw_disposition": "partial",
        "network_access": False,
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
    monkeypatch.setattr(pipeline, "_preflight", lambda *_args: "file:./data/local/test.db")
    monkeypatch.setattr(
        pipeline,
        "collect_gfs_run",
        lambda *_args, **_kwargs: {"run_key": RUN_KEY, "status": "already_succeeded"},
    )
    monkeypatch.setattr(
        pipeline,
        "resume_run",
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
    monkeypatch.setattr(pipeline, "_preflight", lambda *_args: "file:./data/local/test.db")
    monkeypatch.setattr(
        pipeline,
        "collect_gfs_run",
        lambda *_args, **_kwargs: {"run_key": RUN_KEY, "status": "partial"},
    )
    monkeypatch.setattr(
        pipeline,
        "resume_run",
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
