from __future__ import annotations

from types import SimpleNamespace

from paragliding_forecasts_ml.ingestion.weather import feature_cli

RUN_KEY = "99999999-9999-4999-8999-999999999999"


def test_feature_cli_calls_shared_service_and_carries_snapshot(tmp_path, monkeypatch) -> None:
    context = SimpleNamespace(snapshot="before", verification_summary=dict)
    service_result = SimpleNamespace(disposition="complete", as_dict=lambda: {"ok": True})
    monkeypatch.setattr(feature_cli.WeatherRunContext, "open", lambda *_a, **_k: context)
    monkeypatch.setattr(feature_cli, "build_features", lambda actual: (service_result, "after"))

    result = feature_cli.main(["--run-key", RUN_KEY, "--project-root", str(tmp_path)])

    assert result == 0
    assert context.snapshot == "after"


def test_feature_cli_preserves_quarantine_exit_code(tmp_path, monkeypatch) -> None:
    context = SimpleNamespace(snapshot="before", verification_summary=dict)
    service_result = SimpleNamespace(disposition="quarantined", as_dict=lambda: {"ok": False})
    monkeypatch.setattr(feature_cli.WeatherRunContext, "open", lambda *_a, **_k: context)
    monkeypatch.setattr(
        feature_cli,
        "build_features",
        lambda actual: (service_result, actual.snapshot),
    )

    result = feature_cli.main(["--run-key", RUN_KEY, "--project-root", str(tmp_path)])

    assert result == 2
