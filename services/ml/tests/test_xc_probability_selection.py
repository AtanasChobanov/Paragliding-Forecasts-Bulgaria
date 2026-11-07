"""Selection/refit invariants and self-contained JSON model checks, all synthetic."""

import itertools
import json
import math
import socket
import sqlite3
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression

from paragliding_forecasts_ml.ingestion.weather.serialization import (
    canonical_json_bytes,
    pretty_json_bytes,
    sha256_bytes,
)
from paragliding_forecasts_ml.predictions.xc_probability import cli, model_io, selection, trials
from paragliding_forecasts_ml.predictions.xc_probability.experiment import experiment_payloads
from paragliding_forecasts_ml.predictions.xc_probability.learning import (
    encode_inputs,
    grouped_contributions,
    predict_stage,
    standardize,
)
from paragliding_forecasts_ml.predictions.xc_probability.policy import load_policy
from paragliding_forecasts_ml.predictions.xc_probability.scoring_layout import (
    FORECAST_HORIZONS,
    REGULARIZATION_CANDIDATE_COUNT,
    SELECTION_COMPONENT_KEYS,
    SELECTION_SCORE_COMPONENT_COUNT,
    SELECTION_THRESHOLDS_KM,
    TRIAL_FIT_COUNT,
    TRIAL_SCORE_COMPONENT_COUNT,
    VALIDATION_SEASONS,
    score_component_keys,
)
from paragliding_forecasts_ml.predictions.xc_probability.selection import (
    CandidateScore,
    ScoreComponent,
    choose_candidate,
)


def score(c100, c200, brier, loss):
    components = tuple(
        ScoreComponent(fold=fold, horizon=horizon, threshold=threshold, brier=brier, log_loss=loss)
        for fold, horizon, threshold in SELECTION_COMPONENT_KEYS
    )
    return CandidateScore(
        c100=c100,
        c200=c200,
        components=components,
        mean_brier=math.fsum(part.brier for part in components) / len(components),
        mean_log_loss=math.fsum(part.log_loss for part in components) / len(components),
    )


def test_scoring_counts_follow_axes_and_component_keys_are_complete():
    assert (
        SELECTION_SCORE_COMPONENT_COUNT
        == len(VALIDATION_SEASONS) * len(FORECAST_HORIZONS) * len(SELECTION_THRESHOLDS_KM)
        == 12
    )
    assert TRIAL_SCORE_COMPONENT_COUNT == len(FORECAST_HORIZONS) * len(SELECTION_THRESHOLDS_KM) == 6
    assert REGULARIZATION_CANDIDATE_COUNT == 81 and TRIAL_FIT_COUNT == 18
    expanded = score_component_keys((2023, 2024, 2026), (1, 2, 3, 4), (100, 200, 300))
    assert len(expanded) == len(set(expanded)) == 36
    assert (2026, 4, 300) in expanded


@pytest.mark.parametrize(
    "candidates,expected",
    [
        ((score(0.03, 0.03, 0.1, 0.5), score(0.1, 0.03, 0.1 + 2e-12, 0.1)), (0.03, 0.03)),
        ((score(0.03, 0.03, 0.1, 0.5), score(0.1, 0.03, 0.1 + 0.5e-12, 0.1)), (0.1, 0.03)),
        ((score(0.3, 0.03, 0.1, 0.5), score(0.1, 0.3, 0.1, 0.5)), (0.1, 0.3)),
        ((score(0.03, 0.3, 0.1, 0.5), score(0.03, 0.1, 0.1, 0.5)), (0.03, 0.1)),
    ],
)
def test_predeclared_brier_loss_and_c_tie_breaks(candidates, expected):
    for ordering in itertools.permutations(candidates):
        chosen = choose_candidate(ordering)
        assert (chosen.c100, chosen.c200) == expected


def test_tolerance_group_is_anchored_to_global_minimum_not_a_pairwise_chain():
    candidates = (
        score(0.03, 0.03, 0.1, 0.5),
        score(0.1, 0.03, 0.1 + 0.8e-12, 0.4),
        score(0.3, 0.03, 0.1 + 1.6e-12, 0.1),
    )
    assert all(
        choose_candidate(ordering).c100 == 0.1 for ordering in itertools.permutations(candidates)
    )


def fake_trials(study, *, constant=0.25):
    result = {}
    for fold in (2023, 2024):
        candidates = []
        for index, (c100, c200) in enumerate(itertools.product((0.03, 0.1, 0.3), repeat=2)):
            by_horizon = {}
            for horizon in (1, 2, 3):
                by_horizon[str(horizon)] = tuple(
                    SimpleNamespace(
                        threshold_km=threshold,
                        scores=SimpleNamespace(
                            brier=(0.1 if fold == 2023 else 0.2) + horizon * 0.001 + index * 0.0001,
                            log_loss=0.3 + index * 0.001,
                        )
                        if threshold != 300
                        else None,
                    )
                    for threshold in (100, 200, 300)
                )
            candidates.append(SimpleNamespace(c100=c100, c200=c200, by_horizon=by_horizon))
        comparator = SimpleNamespace(
            by_horizon={
                str(h): tuple(
                    SimpleNamespace(
                        threshold_km=t, scores=SimpleNamespace(brier=constant, log_loss=0.75)
                    )
                    for t in (100, 200)
                )
                for h in (1, 2, 3)
            }
        )
        trial = SimpleNamespace(
            metadata=SimpleNamespace(
                fold=fold,
                study_id="a" * 64,
                dataset_id=study.metadata.dataset_id,
                experiment_version=1,
            ),
            evaluation=SimpleNamespace(candidates=tuple(candidates), constant=comparator),
        )
        result[fold] = (str(fold)[-1] * 64, trial)
    return result


def test_selection_rejects_mixed_experiment_versions(synthetic_study):
    mixed = fake_trials(synthetic_study)
    mixed[2024][1].metadata.experiment_version = 2
    with pytest.raises(ValueError, match="cannot mix"):
        selection.build_selection(synthetic_study, "a" * 64, mixed)


def test_selection_uses_twelve_equal_components_and_retains_logistic_without_skill(synthetic_study):
    metadata = selection.build_selection(synthetic_study, "a" * 64, fake_trials(synthetic_study))
    assert metadata.candidates[0].mean_brier == pytest.approx(0.152, abs=1e-15)
    assert len(metadata.candidates[0].components) == 12
    assert {part.threshold for part in metadata.candidates[0].components} == {100, 200}
    assert (metadata.winner.c100, metadata.winner.c200) == (0.03, 0.03)
    unsupported = selection.build_selection(
        synthetic_study, "a" * 64, fake_trials(synthetic_study, constant=0.01)
    )
    assert not unsupported.improves_constant_brier and unsupported.winner == metadata.winner
    assert b"No demonstrated added benefit" in selection.selection_report(unsupported)
    changed = metadata.model_dump(mode="json")
    changed["winner"] = {"c100": 0.3, "c200": 0.3}
    with pytest.raises(ValueError, match="winner"):
        selection.SelectionMetadata.model_validate_json(json.dumps(changed))
    changed = metadata.model_dump(mode="json")
    changed["candidates"][0]["components"][0]["fold"] = 2025
    with pytest.raises(ValueError):
        selection.SelectionMetadata.model_validate_json(json.dumps(changed))


@pytest.mark.parametrize(
    "trial_ids", [[], ["a" * 64], ["a" * 64, "a" * 64], ["a" * 64, "b" * 64, "c" * 64]]
)
def test_selection_rejects_missing_repeated_or_extra_trials_before_source_access(
    tmp_path, monkeypatch, trial_ids
):
    monkeypatch.setattr(
        selection, "load_study", lambda **kwargs: pytest.fail("must reject before loading")
    )
    with pytest.raises(ValueError, match="exactly two distinct"):
        selection.select_recipe(study_id="a" * 64, trial_ids=trial_ids, project_root=tmp_path)


def test_selection_rejects_same_fold_or_different_study(tmp_path, monkeypatch, synthetic_study):
    fakes = fake_trials(synthetic_study)
    monkeypatch.setattr(selection, "load_study", lambda **kwargs: synthetic_study)
    monkeypatch.setattr(selection, "load_trial", lambda **kwargs: fakes[2023][1])
    with pytest.raises(ValueError, match="different chronological folds"):
        selection.select_recipe(
            study_id="a" * 64, trial_ids=["b" * 64, "c" * 64], project_root=tmp_path
        )
    fakes[2024][1].metadata.study_id = "f" * 64
    with pytest.raises(ValueError, match="consumed study"):
        selection.build_selection(synthetic_study, "a" * 64, fakes)


def blocked(*args, **kwargs):
    raise AssertionError("This phase cannot fit or read external/source data.")


def test_final_fit_cannot_start_without_valid_selection(tmp_path, monkeypatch, synthetic_study):
    monkeypatch.setattr(model_io, "load_study", lambda **kwargs: synthetic_study)
    with patch.object(LogisticRegression, "fit", blocked), pytest.raises(FileNotFoundError):
        model_io.train_final(study_id="a" * 64, selection_id="b" * 64, project_root=tmp_path)
    assert not (tmp_path / "data/processed/xc-probability/model").exists()


@pytest.mark.parametrize("experiment_version,candidate_count", [(1, 9), (2, 81)])
def test_verified_selection_final_refit_and_model_only_reload(
    tmp_path, monkeypatch, synthetic_study, experiment_version, candidate_count
):
    for module in (selection, trials, model_io):
        monkeypatch.setattr(module, "load_study", lambda **kwargs: synthetic_study)
    trial_ids = [
        trials.train_trials(
            study_id="a" * 64,
            fold=fold,
            project_root=tmp_path,
            experiment_version=experiment_version,
        )["trial_id"]
        for fold in (2023, 2024)
    ]
    with patch.object(LogisticRegression, "fit", blocked):
        selected = selection.select_recipe(
            study_id="a" * 64, trial_ids=trial_ids, project_root=tmp_path
        )
        repeat = selection.select_recipe(
            study_id="a" * 64, trial_ids=trial_ids[::-1], project_root=tmp_path
        )
    assert selected["selection_id"] == repeat["selection_id"] and repeat["reused"]
    assert selected["component_count"] == 12 and selected["candidate_count"] == candidate_count
    assert selected["experiment_version"] == experiment_version

    def nonconvergent(*args, **kwargs):
        warnings.warn("synthetic final failure", ConvergenceWarning, stacklevel=2)

    with (
        patch.object(LogisticRegression, "fit", nonconvergent),
        pytest.raises(ValueError, match="did not converge"),
    ):
        model_io.train_final(
            study_id="a" * 64, selection_id=selected["selection_id"], project_root=tmp_path
        )
    assert not (tmp_path / "data/processed/xc-probability/model").exists()

    original_fit = LogisticRegression.fit
    fitted_estimators = []

    def fit(estimator, x, y, sample_weight):
        fitted_estimators.append(estimator)
        return original_fit(estimator, x, y, sample_weight=sample_weight)

    monkeypatch.setattr(LogisticRegression, "fit", fit)
    first = model_io.train_final(
        study_id="a" * 64, selection_id=selected["selection_id"], project_root=tmp_path
    )
    assert len(fitted_estimators) == 2
    assert first["training_row_count"] == 126 and first["conditional_training_row_count"] == 63
    assert first["conversion"]["k"] == 2 and first["conversion"]["n"] == 9
    assert first["source_seasons"] == [2022, 2023, 2024]
    model_directory = Path(first["output_directory"])
    assert {path.name for path in model_directory.iterdir()} == {
        "model.json",
        "policy.json",
        "manifest.json",
    } | set(experiment_payloads(experiment_version))
    original_manifest = (model_directory / "manifest.json").read_bytes()
    policy, _ = load_policy()
    with monkeypatch.context() as guard:
        guard.setattr(model_io, "load_study", blocked)
        guard.setattr(model_io, "load_selection", blocked)
        guard.setattr(LogisticRegression, "fit", blocked)
        guard.setattr(sqlite3, "connect", blocked)
        guard.setattr(socket, "create_connection", blocked)
        loaded = model_io.load_model(model_id=first["model_id"], project_root=tmp_path)
    assert (
        loaded.available_confidence_level == "low" and loaded.calibration_status == "not_calibrated"
    )
    assert loaded.selection_id == selected["selection_id"]
    assert loaded.selection_snapshot.experiment_version == experiment_version
    assert sha256_bytes(canonical_json_bytes(loaded.selection_identity)) == loaded.selection_id
    encoded = encode_inputs(
        tuple(row.inputs for row in synthetic_study.rows),
        tuple(site for site, _ in loaded.site_categories),
        policy,
    )
    for fitted, estimator in zip(loaded.models, fitted_estimators, strict=True):
        z = standardize(encoded, fitted.parameters.means, fitted.parameters.scales)
        np.testing.assert_allclose(
            predict_stage(fitted.parameters, encoded),
            estimator.predict_proba(z)[:, 1],
            atol=1e-12,
            rtol=0,
        )
        contributions = grouped_contributions(
            fitted.parameters, encoded, loaded.coordinate_group_ids
        )
        assert len(contributions) == 15
        logits = fitted.parameters.baseline_logit + np.sum(list(contributions.values()), axis=0)
        np.testing.assert_allclose(logits, estimator.decision_function(z), atol=1e-12, rtol=0)
    assert loaded.models[0].parameters.support.site_day_count == 42
    assert loaded.models[1].parameters.support.site_day_count == 21

    payload = json.loads((model_directory / "model.json").read_bytes())
    policy_bytes = (model_directory / "policy.json").read_bytes()
    if experiment_version == 2:
        with pytest.raises(ValueError, match="experiment.json"):
            model_io.validate_model_payload(
                {
                    "model.json": pretty_json_bytes(payload),
                    "policy.json": policy_bytes,
                }
            )
    else:
        assert "experiment_version" not in payload["selection_snapshot"]
    for change in (
        "selected_c",
        "group",
        "support",
        "probe",
        "confidence",
        "selection_snapshot",
        "source_season_summary",
    ):
        changed = json.loads(json.dumps(payload))
        if change == "selected_c":
            chosen = changed["models"][0]["parameters"]["regularization_c"]
            changed["models"][0]["parameters"]["regularization_c"] = 0.3 if chosen != 0.3 else 0.03
        elif change == "group":
            changed["coordinate_group_ids"][0] = "wind"
        elif change == "support":
            changed["training_summary"]["positive_site_days"]["300"] += 1
        elif change == "probe":
            value = changed["models"][0]["self_checks"][0]["expected_probability"]
            changed["models"][0]["self_checks"][0]["expected_probability"] = (
                0.9 if value < 0.5 else 0.1
            )
        elif change == "confidence":
            changed["available_confidence_level"] = "high"
        elif change == "source_season_summary":
            changed["training_summary"]["source_seasons"]["2025"] = changed["training_summary"][
                "source_seasons"
            ].pop("2024")
        else:
            changed["selection_snapshot"]["constant_mean_brier"] += 0.01
        with pytest.raises(ValueError):
            model_io.validate_model_payload(
                {
                    **experiment_payloads(experiment_version),
                    "model.json": pretty_json_bytes(changed),
                    "policy.json": policy_bytes,
                }
            )
    second = model_io.train_final(
        study_id="a" * 64, selection_id=selected["selection_id"], project_root=tmp_path
    )
    assert (
        len(fitted_estimators) == 4 and second["model_id"] == first["model_id"] and second["reused"]
    )
    assert (model_directory / "manifest.json").read_bytes() == original_manifest


def test_cli_select_and_final_require_lineage_and_disallow_manual_c(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        cli, "select_recipe", lambda **kwargs: calls.append(kwargs) or {"selection_id": "a" * 64}
    )
    assert (
        cli.main(
            [
                "select",
                "--study-id",
                "a" * 64,
                "--trial-id",
                "b" * 64,
                "--trial-id",
                "c" * 64,
                "--project-root",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert calls[-1] == {
        "study_id": "a" * 64,
        "trial_ids": ["b" * 64, "c" * 64],
        "project_root": tmp_path,
    }
    assert json.loads(capsys.readouterr().out)["selection_id"] == "a" * 64
    monkeypatch.setattr(
        cli, "train_final", lambda **kwargs: calls.append(kwargs) or {"model_id": "d" * 64}
    )
    assert cli.main(["train-final", "--study-id", "a" * 64, "--selection-id", "b" * 64]) == 0
    assert calls[-1]["selection_id"] == "b" * 64
    for arguments in (
        ["train-final", "--study-id", "a" * 64],
        ["train-final", "--study-id", "a" * 64, "--selection-id", "b" * 64, "--c100", ".3"],
    ):
        with pytest.raises(SystemExit):
            cli.main(arguments)
