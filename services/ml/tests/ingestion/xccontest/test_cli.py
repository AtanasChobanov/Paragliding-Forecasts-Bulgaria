from __future__ import annotations

from types import SimpleNamespace

import pytest

from paragliding_forecasts_ml.ingestion.xccontest import cli
from paragliding_forecasts_ml.storage.sqlite import DatabaseConfigurationError


def test_database_discovery_failure_precedes_artifact_or_browser_creation(
    monkeypatch, capsys
) -> None:
    def fail_discovery(_database_url: str) -> tuple[str, ...]:
        raise DatabaseConfigurationError("sites table is unavailable")

    def unexpected_collection(*_args, **_kwargs):
        raise AssertionError("collection must not start before country discovery")

    monkeypatch.setattr(cli, "load_site_country_codes", fail_discovery)
    monkeypatch.setattr(cli, "collect_run", unexpected_collection)

    assert cli.main(["--season", "2025"]) == 1
    assert "could not resolve its database country scope" in capsys.readouterr().err


def test_resume_command_uses_only_a_run_key_and_skips_database_discovery(
    monkeypatch, capsys
) -> None:
    report = SimpleNamespace(
        run_key="resume-run",
        status="complete",
        manifest_relative_path="data/raw/xccontest/resume-run/manifest.json",
        manifest_sha256="a" * 64,
        started_at_utc=SimpleNamespace(isoformat=lambda: "2026-09-25T12:00:00+00:00"),
        completed_at_utc=SimpleNamespace(isoformat=lambda: "2026-09-25T12:01:00+00:00"),
        country_codes=("BG",),
        completed_seasons=(2025,),
        completed_target_count=1,
        unresolved_scope_count=0,
        artifact_count=2,
        row_observations_seen=2,
        distinct_source_flights_seen=2,
        repeated_source_flight_observations=0,
    )
    monkeypatch.setattr(cli, "resume_collect_run", lambda run_key: report)
    monkeypatch.setattr(
        cli,
        "load_site_country_codes",
        lambda *_: (_ for _ in ()).throw(AssertionError("resume must not rediscover countries")),
    )

    assert cli.main(["resume", "--run-key", "resume-run"]) == 0
    assert '"run_key": "resume-run"' in capsys.readouterr().out

    with pytest.raises(SystemExit):
        cli.build_resume_parser().parse_args(["--run-key", "resume-run", "--date", "2025-07-01"])
