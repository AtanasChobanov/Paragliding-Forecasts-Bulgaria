"""Portable weighted training and trial diagnostics using only synthetic weather."""

import json
import math
import warnings
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from threadpoolctl import threadpool_info

from paragliding_forecasts_ml.ingestion.gfs.models import sofia_window_instants
from paragliding_forecasts_ml.ingestion.weather.serialization import (
    pretty_json_bytes,
)
from paragliding_forecasts_ml.predictions.xc_probability import cli, trials
from paragliding_forecasts_ml.predictions.xc_probability.artifacts import read_bundle
from paragliding_forecasts_ml.predictions.xc_probability.inputs import ForecastInput
from paragliding_forecasts_ml.predictions.xc_probability.learning import (
    FittedStage,
    conversion_support,
    encode_inputs,
    fit_stage,
    predict_stage,
    standardize,
)
from paragliding_forecasts_ml.predictions.xc_probability.metrics import evaluate_metric
from paragliding_forecasts_ml.predictions.xc_probability.policy import coordinate_ids, load_policy


def fit_rows(study, *, stage="p100", fold=2023):
    weights = next(
        part for part in study.weights if part.training_scope == str(fold) and part.stage == stage
    )
    by_id = {row.row_id: row for row in study.rows}
    return tuple(by_id[key] for key in weights.row_ids), weights


def test_encoding_wind_circle_leap_year_context_and_fixed_categories(synthetic_study):
    policy, _ = load_policy()
    row = synthetic_study.rows[0].inputs
    identifiers = coordinate_ids(policy, (1, 2, 3, 4, 5, 6, 7))
    directions = {
        spec.feature_id for spec in policy.required_features if spec.encoding == "sin_cos"
    }
    near = [
        row.model_copy(
            update={
                "observations": tuple(
                    value.model_copy(update={"value": float(angle)})
                    if value.feature_id in directions
                    else value
                    for value in row.observations
                )
            }
        )
        for angle in (359, 1)
    ]
    encoded = encode_inputs(tuple(near), (1, 2, 3, 4, 5, 6, 7), policy)
    for feature_id in directions:
        sin_index, cos_index = (
            identifiers.index(feature_id + ".sin"),
            identifiers.index(feature_id + ".cos"),
        )
        assert encoded[0, sin_index] == pytest.approx(-encoded[1, sin_index], abs=1e-14)
        assert encoded[0, cos_index] == pytest.approx(encoded[1, cos_index], abs=1e-14)
        assert (
            np.linalg.norm(encoded[0, [sin_index, cos_index]] - encoded[1, [sin_index, cos_index]])
            < 0.04
        )
    target = date(2024, 12, 31)
    issue = target - timedelta(days=row.horizon_days)
    payload = row.model_dump()
    payload.update(
        target_local_date=str(target),
        issue_local_date=str(issue),
        cycle_reference_utc=f"{issue}T06:00:00Z",
        source_ready_at_utc=f"{issue}T10:00:00Z",
        issue_cutoff_utc=datetime.combine(issue, time(16), tzinfo=ZoneInfo("Europe/Sofia"))
        .astimezone(UTC)
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        valid_times_utc=sofia_window_instants(str(target)),
    )
    vector = encode_inputs((ForecastInput.model_validate(payload),), (1, 2, 3, 4, 5, 6, 7), policy)[
        0
    ]
    assert vector[70] == pytest.approx(math.sin(2 * math.pi * 365 / 366), abs=1e-15)
    assert vector[71] == pytest.approx(math.cos(2 * math.pi * 365 / 366), abs=1e-15)
    assert vector[72:79].sum() == vector[79:82].sum() == 1
    with pytest.raises(ValueError, match="outside the frozen"):
        encode_inputs((row.model_copy(update={"site_id": 99}),), (1, 2, 3, 4, 5, 6, 7), policy)


def test_scaler_references_and_fit_use_own_weighted_subset_and_portable_json(synthetic_study):
    policy, _ = load_policy()
    sites = (1, 2, 3, 4, 5, 6, 7)
    for stage in ("p100", "q200"):
        rows, weights = fit_rows(synthetic_study, stage=stage)
        rows = tuple(
            row.model_copy(
                update={
                    "inputs": row.inputs.model_copy(
                        update={
                            "observations": (
                                row.inputs.observations[0].model_copy(update={"value": 100000.0}),
                                *row.inputs.observations[1:],
                            )
                        }
                    )
                }
            )
            for row in rows
        )
        fitted = fit_stage(rows, weights, regularization_c=0.1, site_ids=sites, policy=policy)
        encoded = encode_inputs(tuple(row.inputs for row in rows), sites, policy)
        parameters = fitted.parameters
        assert parameters.means[0] == 100000 and parameters.scales[0] == 1
        expected_mean = np.average(encoded[:, :72], axis=0, weights=weights.row_weights)
        np.testing.assert_allclose(parameters.means, expected_mean, atol=1e-10, rtol=0)
        np.testing.assert_allclose(
            parameters.reference[72:],
            np.average(encoded[:, 72:], axis=0, weights=weights.row_weights),
            atol=1e-15,
            rtol=0,
        )
        standardized = standardize(encoded, parameters.means, parameters.scales)
        np.testing.assert_array_equal(standardized[:, 72:], encoded[:, 72:])
        assert parameters.reference[:72] == (0.0,) * 72
        assert parameters.support.normalized_weight_sum == pytest.approx(
            parameters.support.site_day_count
        )
        restored = FittedStage.model_validate_json(fitted.model_dump_json())
        np.testing.assert_allclose(
            predict_stage(restored.parameters, encoded),
            predict_stage(parameters, encoded),
            atol=1e-12,
            rtol=0,
        )
        modified = fitted.model_dump(mode="json")
        modified["self_checks"][0]["expected_probability"] = (
            1 - modified["self_checks"][0]["expected_probability"]
        )
        with pytest.raises(ValueError, match="numerical self-check"):
            FittedStage.model_validate_json(json.dumps(modified))


def test_validation_inputs_and_labels_cannot_change_training_parameters(synthetic_study):
    policy, _ = load_policy()
    training, validation = trials.fold_rows(synthetic_study, 2023)
    weights = next(
        part
        for part in synthetic_study.weights
        if part.training_scope == "2023" and part.stage == "p100"
    )
    changed = tuple(
        row.model_copy(
            update={
                "labels": (0, 0, 0),
                "inputs": row.inputs.model_copy(
                    update={
                        "observations": tuple(
                            value.model_copy(update={"value": value.value + 1e6})
                            for value in row.inputs.observations
                        )
                    }
                ),
            }
        )
        for row in validation
    )
    before = fit_stage(
        training,
        weights,
        regularization_c=0.03,
        site_ids=(1, 2, 3, 4, 5, 6, 7),
        policy=policy,
        check_rows=validation,
    )
    after = fit_stage(
        training,
        weights,
        regularization_c=0.03,
        site_ids=(1, 2, 3, 4, 5, 6, 7),
        policy=policy,
        check_rows=changed,
    )
    assert before.parameters == after.parameters
    constant = trials.constant_rates(training, conversion_support(training, study_id="a" * 64))
    assert constant["p100"] == 11 / 25 and constant["p200"] == 3 / 25
    assert constant["q200"] == 3 / 11 and constant["p300"] is None


@pytest.mark.parametrize("stage", ["p100", "q200"])
def test_single_class_is_rejected_instead_of_a_fake_classifier(synthetic_study, stage):
    rows, weights = fit_rows(synthetic_study, stage=stage)
    changed = tuple(
        row.model_copy(update={"labels": (0, 0, 0) if stage == "p100" else (1, 0, 0)})
        for row in rows
    )
    with (
        patch.object(
            LogisticRegression, "fit", side_effect=AssertionError("must reject before fit")
        ),
        pytest.raises(ValueError, match="requires both outcome classes"),
    ):
        fit_stage(
            changed,
            weights,
            regularization_c=0.03,
            site_ids=(1, 2, 3, 4, 5, 6, 7),
            policy=load_policy()[0],
        )


def metric_rows(synthetic_study, labels, weights):
    source = [row for row in synthetic_study.rows if row.inputs.horizon_days == 1][: len(labels)]
    return tuple(
        row.model_copy(update={"labels": (label, 0, 0), "sampling_weight": float(weight)})
        for row, label, weight in zip(source, labels, weights, strict=True)
    )


def test_weighted_metrics_fixed_bins_endpoint_clipping_and_diagnostic_counts(synthetic_study):
    probabilities = [0.0, 0.2, 0.5, 0.8, 1.0]
    rows = metric_rows(synthetic_study, [0, 1, 0, 1, 1], [1, 2, 3, 4, 5])
    result = evaluate_metric(rows, probabilities, threshold=100)
    scores = result.scores
    assert scores.brier == pytest.approx(2.19 / 15)
    assert scores.roc_auc == pytest.approx(38 / 44)
    assert scores.average_precision == pytest.approx(74 / 77)
    clipped = [max(1e-15, min(1 - 1e-15, value)) for value in probabilities]
    expected_loss = (
        -math.fsum(
            weight * (label * math.log(p) + (1 - label) * math.log1p(-p))
            for weight, label, p in zip([1, 2, 3, 4, 5], [0, 1, 0, 1, 1], clipped, strict=True)
        )
        / 15
    )
    assert scores.log_loss == pytest.approx(expected_loss, abs=1e-14)
    assert scores.confusion_counts == {"tp": 2, "fp": 1, "tn": 1, "fn": 1}
    assert scores.weighted_confusion_counts == {"tp": 9.0, "fp": 3.0, "tn": 1.0, "fn": 2.0}
    assert scores.precision == 0.75 and scores.recall == pytest.approx(9 / 11)
    assert [part.row_count for part in scores.calibration] == [1, 1, 1, 0, 2]
    assert (
        scores.calibration[3].mean_probability is None
        and scores.calibration[3].observed_frequency is None
    )
    assert scores.calibration[-1].upper_inclusive
    assert scores.calibration[-1].mean_probability == pytest.approx(8.2 / 9)
    assert probabilities == [0.0, 0.2, 0.5, 0.8, 1.0]


def test_undefined_metrics_and_unsupported_300_are_explicit(synthetic_study):
    rows = metric_rows(synthetic_study, [0, 0], [1, 2])
    scores = evaluate_metric(rows, [0.0, 0.0], threshold=100).scores
    assert scores.roc_auc is None and scores.roc_auc_undefined_reason == "single_outcome_class"
    assert (
        scores.average_precision is None
        and scores.average_precision_undefined_reason == "no_positive_outcomes"
    )
    assert scores.precision is None and scores.recall is None
    missing = evaluate_metric(
        rows, [None, None], threshold=300, missing_reason="insufficient_300_support"
    )
    assert missing.scores is None and missing.missing_reason == "insufficient_300_support"
    for values in ([None, 0.1], [float("nan"), 0.1], [float("inf"), 0.1], [1.1, 0.1]):
        with pytest.raises(ValueError):
            evaluate_metric(rows, values, threshold=300)


@pytest.mark.parametrize("fold,expected_k,expected_n", [(2023, 0, 3), (2024, 1, 6)])
@pytest.mark.parametrize("experiment_version,fit_count,candidate_count", [(1, 6, 9), (2, 18, 81)])
def test_versioned_trial_saved_predictions_metrics_and_reuse(
    tmp_path,
    monkeypatch,
    synthetic_study,
    fold,
    expected_k,
    expected_n,
    experiment_version,
    fit_count,
    candidate_count,
):
    monkeypatch.setattr(trials, "load_study", lambda **kwargs: synthetic_study)
    original_fit = LogisticRegression.fit
    fitted_estimators = []

    def fit(estimator, x, y, sample_weight):
        assert all(pool["num_threads"] == 1 for pool in threadpool_info())
        assert estimator.l1_ratio == 0 and estimator.max_iter == 5000 and estimator.tol == 1e-8
        assert estimator.class_weight is None and estimator.solver == "lbfgs"
        fitted_estimators.append((estimator, x.copy(), sample_weight.copy()))
        return original_fit(estimator, x, y, sample_weight=sample_weight)

    monkeypatch.setattr(LogisticRegression, "fit", fit)
    first = trials.train_trials(
        study_id="a" * 64, fold=fold, project_root=tmp_path, experiment_version=experiment_version
    )
    assert len(fitted_estimators) == first["fit_count"] == fit_count
    assert first["candidate_count"] == candidate_count
    assert first["validation_prediction_count"] == candidate_count * 42
    assert first["conversion"]["k"] == expected_k and first["conversion"]["n"] == expected_n
    loaded = trials.load_trial(
        trial_id=first["trial_id"], study_id="a" * 64, study=synthetic_study, project_root=tmp_path
    )
    assert len(fitted_estimators) == fit_count  # Reload never refits.
    assert loaded.metadata.experiment_version == experiment_version
    for fitted, (estimator, encoded, _) in zip(
        loaded.metadata.models, fitted_estimators, strict=True
    ):
        actual_logits = (
            encoded @ np.asarray(fitted.parameters.coefficients) + fitted.parameters.intercept
        )
        np.testing.assert_allclose(
            actual_logits, estimator.decision_function(encoded), atol=1e-12, rtol=0
        )
    for prediction in loaded.predictions:
        assert 0 <= prediction.p200 <= prediction.p100 <= 1
        if expected_k:
            assert prediction.p300 == pytest.approx(
                prediction.p200 * expected_k / expected_n, abs=1e-15
            )
        else:
            assert (
                prediction.p300 is None
                and prediction.p300_missing_reason == "insufficient_300_support"
            )
    for candidate in loaded.evaluation.candidates:
        component_scores = [
            metric.scores
            for values in candidate.by_horizon.values()
            for metric in values
            if metric.threshold_km in (100, 200)
        ]
        assert candidate.mean_brier == math.fsum(scores.brier for scores in component_scores) / 6
        assert (
            candidate.mean_log_loss == math.fsum(scores.log_loss for scores in component_scores) / 6
        )
        if not expected_k:
            assert all(values[2].scores is None for values in candidate.by_horizon.values())
    directory = Path(first["output_directory"])
    original_manifest = (directory / "manifest.json").read_bytes()
    second = trials.train_trials(
        study_id="a" * 64, fold=fold, project_root=tmp_path, experiment_version=experiment_version
    )
    assert second["trial_id"] == first["trial_id"] and second["reused"]
    assert (directory / "manifest.json").read_bytes() == original_manifest
    assert len(fitted_estimators) == 2 * fit_count
    _, payloads = read_bundle(directory, kind="trial", artifact_id=first["trial_id"])
    saved_metadata = json.loads(payloads["trial.json"])
    if experiment_version == 1:
        assert "experiment_version" not in saved_metadata and "experiment.json" not in payloads
    else:
        assert saved_metadata["experiment_version"] == 2
        with pytest.raises(ValueError, match="experiment.json"):
            trials.validate_trial_payload(
                {name: raw for name, raw in payloads.items() if name != "experiment.json"},
                study=synthetic_study,
                study_id="a" * 64,
            )
    altered = json.loads(payloads["trial.json"])
    altered["models"][0]["parameters"]["regularization_c"] = 0.002
    with pytest.raises(ValueError, match="ordered stage/C"):
        trials.validate_trial_payload(
            {**payloads, "trial.json": pretty_json_bytes(altered)},
            study=synthetic_study,
            study_id="a" * 64,
        )
    metrics = json.loads(payloads["metrics.json"])
    metrics["candidates"][0]["mean_brier"] += 0.01
    with pytest.raises(ValueError, match="diagnostics differ"):
        trials.validate_trial_payload(
            {**payloads, "metrics.json": pretty_json_bytes(metrics)},
            study=synthetic_study,
            study_id="a" * 64,
        )
    assert "2025 is untouched" in payloads["report.md"].decode()


def test_convergence_failure_does_not_publish_or_retry(tmp_path, monkeypatch, synthetic_study):
    monkeypatch.setattr(trials, "load_study", lambda **kwargs: synthetic_study)
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        warnings.warn("synthetic failure", ConvergenceWarning, stacklevel=2)

    monkeypatch.setattr(LogisticRegression, "fit", fail)
    with pytest.raises(ValueError, match="did not converge"):
        trials.train_trials(study_id="a" * 64, fold=2023, project_root=tmp_path)
    assert len(calls) == 1 and not (tmp_path / "data").exists()


def test_cli_trial_options_and_json(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        cli, "train_trials", lambda **kwargs: calls.append(kwargs) or {"trial_id": "a" * 64}
    )
    assert (
        cli.main(
            [
                "train-trials",
                "--study-id",
                "b" * 64,
                "--fold",
                "2023",
                "--project-root",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert calls == [
        {"study_id": "b" * 64, "fold": 2023, "project_root": tmp_path, "experiment_version": 2}
    ]
    assert json.loads(capsys.readouterr().out) == {"trial_id": "a" * 64}
    with pytest.raises(SystemExit):
        cli.main(["train-trials", "--study-id", "b" * 64, "--fold", "2025"])
