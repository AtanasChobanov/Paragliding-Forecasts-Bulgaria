from __future__ import annotations

from types import SimpleNamespace

from paragliding_forecasts_ml.ingestion.weather import spatial_cli
from paragliding_forecasts_ml.ingestion.weather.spatial_cli import build_parser, main


def test_gfs_sample_cli_has_no_network_option() -> None:
    parser = build_parser()
    option_strings = {option for action in parser._actions for option in action.option_strings}
    assert "--allow-live-network" not in option_strings
    assert "--run-key" in option_strings


def test_successful_cli_calls_shared_service_and_carries_snapshot(
    tmp_path, monkeypatch, capsys
) -> None:
    context = SimpleNamespace(snapshot="before", verification_summary=dict)
    service_result = SimpleNamespace(as_dict=lambda: {"spatial_manifest": "spatial.json"})
    monkeypatch.setattr(spatial_cli.WeatherRunContext, "open", lambda *_a, **_k: context)
    monkeypatch.setattr(spatial_cli, "sample_sites", lambda actual: (service_result, "after"))

    result = main(
        [
            "--run-key",
            "99999999-9999-4999-8999-999999999999",
            "--project-root",
            str(tmp_path),
            "--database-url",
            "file:./data/local/weather.db",
        ]
    )

    assert result == 0
    assert context.snapshot == "after"
    output = capsys.readouterr().out
    assert '"spatial_manifest": "spatial.json"' in output
    assert '"verification_summary": {}' in output
