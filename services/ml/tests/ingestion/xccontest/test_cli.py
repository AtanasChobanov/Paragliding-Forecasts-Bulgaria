from __future__ import annotations

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
