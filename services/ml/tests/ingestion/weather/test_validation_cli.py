from __future__ import annotations

from types import SimpleNamespace

from paragliding_forecasts_ml.ingestion.weather import validation_cli

RUN_KEY = "99999999-9999-4999-8999-999999999999"


def test_validation_cli_calls_shared_service_and_carries_snapshot(tmp_path, monkeypatch) -> None:
    context = SimpleNamespace(snapshot="before", verification_summary=dict)
    service_result = SimpleNamespace(disposition="complete", as_dict=lambda: {"ok": True})
    monkeypatch.setattr(validation_cli.WeatherRunContext, "open", lambda *_a, **_k: context)
    monkeypatch.setattr(validation_cli, "validate_run", lambda actual: (service_result, "after"))

    result = validation_cli.main(
        [
            "--run-key",
            RUN_KEY,
            "--project-root",
            str(tmp_path),
            "--database-url",
            "file:./data/local/weather.db",
        ]
    )

    assert result == 0
    assert context.snapshot == "after"


def test_validation_cli_preserves_quarantine_exit_code(tmp_path, monkeypatch) -> None:
    context = SimpleNamespace(snapshot="same", verification_summary=dict)
    service_result = SimpleNamespace(disposition="quarantined", as_dict=lambda: {"ok": False})
    monkeypatch.setattr(validation_cli.WeatherRunContext, "open", lambda *_a, **_k: context)
    monkeypatch.setattr(
        validation_cli,
        "validate_run",
        lambda actual: (service_result, actual.snapshot),
    )

    assert (
        validation_cli.main(
            [
                "--run-key",
                RUN_KEY,
                "--project-root",
                str(tmp_path),
                "--database-url",
                "file:./data/local/weather.db",
            ]
        )
        == 2
    )
