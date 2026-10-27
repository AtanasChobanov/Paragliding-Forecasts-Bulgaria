from __future__ import annotations

import json
import socket
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from paragliding_forecasts_ml.ingestion.weather.features.aggregation import sofia_flying_window
from paragliding_forecasts_ml.predictions.cloudbase import cli, service
from paragliding_forecasts_ml.predictions.cloudbase.models import (
    DailyResult,
    HourlyInput,
    HourlyResult,
)


def synthetic_run(column, key):
    rows = []
    for valid in sofia_flying_window(
        datetime.fromisoformat(column.target_local_date).date()
    ).expected_instants_utc:
        interval = (
            (datetime.fromisoformat(valid) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            valid,
        )
        rows.append(
            column.model_copy(
                update={
                    "run_key": key,
                    "valid_at_utc": valid,
                    "sensible_interval": interval,
                    "latent_interval": interval,
                }
            )
        )
    return rows, {"run_key": key, "references": [], "verification_scope": "synthetic"}


@pytest.fixture
def fake_reader(cloudbase_column, monkeypatch):
    monkeypatch.setattr(
        service, "read_inputs", lambda key, **_: synthetic_run(cloudbase_column, key)
    )
    monkeypatch.setattr(
        socket.socket, "connect", lambda *_: pytest.fail("Cloudbase must not use network")
    )
    return cloudbase_column.run_key


def test_batch_is_deterministic_deduplicated_and_language_neutral(tmp_path, fake_reader):
    second = "22222222-2222-4222-8222-222222222222"
    result = service.build_predictions([second, fake_reader, second], project_root=tmp_path)
    directory = Path(result["output_directory"])
    original = {p.name: p.read_bytes() for p in directory.iterdir()}
    again = service.build_predictions([fake_reader, second], project_root=tmp_path)
    assert result == again
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == original
    assert result["hourly_count"] == 22 and result["daily_count"] == 2
    manifest = json.loads(original["manifest.json"])
    assert manifest["numerical_versions"]["metpy"] == "1.7.1"
    assert len(manifest["artifact_id"]) == 64
    assert set(original) == {
        "manifest.json",
        "policy.json",
        "inputs.jsonl",
        "hourly.jsonl",
        "daily.jsonl",
        "report.md",
    }
    for line in original["inputs.jsonl"].splitlines():
        HourlyInput.model_validate_json(line)
    for line in original["hourly.jsonl"].splitlines():
        HourlyResult.model_validate_json(line)
    for line in original["daily.jsonl"].splitlines():
        DailyResult.model_validate_json(line)


def test_existing_artifact_tampering_is_not_overwritten(tmp_path, fake_reader):
    result = service.build_predictions([fake_reader], project_root=tmp_path)
    path = Path(result["output_directory"]) / "hourly.jsonl"
    path.write_bytes(b"tampered\n")
    with pytest.raises(ValueError, match="differs"):
        service.build_predictions([fake_reader], project_root=tmp_path)
    assert path.read_bytes() == b"tampered\n"


def test_failed_input_never_publishes_partial_batch(tmp_path, cloudbase_column, monkeypatch):
    def reader(key, **_):
        if key.startswith("2"):
            raise ValueError("broken evidence")
        return synthetic_run(cloudbase_column, key)

    monkeypatch.setattr(service, "read_inputs", reader)
    with pytest.raises(ValueError, match="broken evidence"):
        service.build_predictions(
            [cloudbase_column.run_key, "22222222-2222-4222-8222-222222222222"],
            project_root=tmp_path,
        )
    assert not (tmp_path / "data/processed/cloudbase").exists()


def test_safely_rejects_empty_and_duplicate_input_rows(tmp_path, cloudbase_column, monkeypatch):
    with pytest.raises(ValueError, match="run-key"):
        service.build_predictions([], project_root=tmp_path)
    monkeypatch.setattr(service, "read_inputs", lambda *_, **__: ([cloudbase_column] * 2, {}))
    with pytest.raises(ValueError, match="Duplicate"):
        service.build_predictions([cloudbase_column.run_key], project_root=tmp_path)


def test_cli_help_and_missing_arguments_do_not_read_inputs(monkeypatch, capsys):
    monkeypatch.setattr(
        cli, "build_predictions", lambda *_, **__: pytest.fail("Unexpected calculation")
    )
    with pytest.raises(SystemExit) as result:
        cli.main(["--help"])
    assert result.value.code == 0 and "--run-key" in capsys.readouterr().out
    with pytest.raises(SystemExit) as result:
        cli.main([])
    assert result.value.code == 2


def test_cli_reports_success_and_failure_without_fabricating_outputs(tmp_path, fake_reader, capsys):
    assert cli.main(["--run-key", fake_reader, "--project-root", str(tmp_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["hourly_count"] == 11 and result["network_access"] is False


def test_cli_data_failure_is_nonzero_and_has_no_success_stdout(monkeypatch, capsys):
    def fail(*_, **__):
        raise ValueError("bad retained source")

    monkeypatch.setattr(cli, "build_predictions", fail)
    assert cli.main(["--run-key", "11111111-1111-4111-8111-111111111111"]) == 1
    output = capsys.readouterr()
    assert not output.out and "bad retained source" in output.err
