"""Frozen experiment grids, version isolation and explicit CLI reproduction."""

import json

import pytest

from paragliding_forecasts_ml.predictions.xc_probability import cli, experiment


def test_frozen_grids_and_exact_experiment_payload():
    assert experiment.regularization_values(1) == (0.03, 0.1, 0.3)
    assert experiment.regularization_values(2) == (
        0.001,
        0.003,
        0.01,
        0.03,
        0.1,
        0.3,
        1.0,
        3.0,
        10.0,
    )
    assert experiment.experiment_payloads(1) == {}
    payload = experiment.experiment_payloads(2)
    experiment.validate_experiment_payload(payload, 2)
    for version, contents in ((1, payload), (2, {}), (2, {"experiment.json": b"{}"})):
        with pytest.raises(ValueError, match="experiment.json"):
            experiment.validate_experiment_payload(contents, version)
    for unsupported in (0, 3):
        with pytest.raises(ValueError, match="Unsupported"):
            experiment.regularization_values(unsupported)


@pytest.mark.parametrize("grid", [[0.03, 0.03], [0.1, 0.03], [0], [-1], [float("inf")]])
def test_experiment_rejects_invalid_grid(grid):
    with pytest.raises(ValueError):
        experiment.RegularizationExperiment.model_validate_json(
            json.dumps(
                {
                    "schema_version": "xc-regularization-experiment/1",
                    "experiment_version": 2,
                    "regularization_grid": grid,
                }
            )
        )


def test_cli_explicit_legacy_experiment_and_unknown_version(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(cli, "train_trials", lambda **kwargs: calls.append(kwargs) or {})
    args = [
        "train-trials",
        "--study-id",
        "a" * 64,
        "--fold",
        "2023",
        "--project-root",
        str(tmp_path),
        "--experiment-version",
    ]
    assert cli.main([*args, "1"]) == 0
    assert calls[0]["experiment_version"] == 1
    with pytest.raises(SystemExit):
        cli.main([*args, "3"])
    assert len(calls) == 1
    capsys.readouterr()
