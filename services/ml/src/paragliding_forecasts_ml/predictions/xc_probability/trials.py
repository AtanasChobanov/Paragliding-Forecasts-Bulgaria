"""Six fits per chronological trial, nine conditional combinations and diagnostics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from typing import Literal

import numpy as np
from pydantic import Field, JsonValue, model_validator
from threadpoolctl import threadpool_limits

from ...ingestion.atmosphere.contracts import AtmosphericContract
from ...ingestion.weather.serialization import canonical_json_bytes, pretty_json_bytes
from .artifacts import artifact_directory, json_lines, publish_bundle, read_bundle
from .learning import (
    LOGISTIC_ARGUMENTS,
    FittedStage,
    conversion_support,
    encode_inputs,
    fit_stage,
    predict_stage,
    stage_support,
    weighted_scaler,
)
from .metrics import MetricSummary, evaluate_metric
from .models import ArtifactParent, ConversionSupport, Probability, Sha256
from .policy import XcPolicy, load_policy
from .scoring_layout import (
    EVALUATED_THRESHOLDS_KM,
    FORECAST_HORIZONS,
    MODEL_STAGES,
    REGULARIZATION_CANDIDATE_COUNT,
    SELECTION_THRESHOLDS_KM,
    TRIAL_FIT_COUNT,
    TRIAL_SCORE_COMPONENT_COUNT,
)
from .study import LoadedStudy, StudyRow, load_study, summarize

CValue = Literal[0.03, 0.1, 0.3]


class ValidationPrediction(AtmosphericContract):
    c100: CValue
    c200: CValue
    row_id: Sha256
    site_id: int = Field(gt=0)
    target_local_date: str
    horizon_days: Literal[1, 2, 3]
    p100: Probability
    q200: Probability
    p200: Probability
    p300: Probability | None
    p300_missing_reason: Literal["insufficient_300_support"] | None

    @model_validator(mode="after")
    def values_follow_conditional_chain(self) -> ValidationPrediction:
        if not math.isclose(self.p200, self.p100 * self.q200, abs_tol=1e-12, rel_tol=0):
            raise ValueError("Trial p200 must equal p100*q200.")
        if self.p200 > self.p100 or (self.p300 is not None and self.p300 > self.p200):
            raise ValueError("Trial probabilities must remain nested.")
        if (self.p300 is None) != (self.p300_missing_reason is not None):
            raise ValueError("Missing 300+ validation predictions require a support reason.")
        return self


class CandidateEvaluation(AtmosphericContract):
    c100: CValue | None
    c200: CValue | None
    mean_brier: Probability
    mean_log_loss: float = Field(ge=0, allow_inf_nan=False)
    by_horizon: dict[str, tuple[MetricSummary, ...]]
    pooled: tuple[MetricSummary, ...]


class TrialEvaluation(AtmosphericContract):
    schema_version: Literal["xc-probability-trial-metrics/1"] = "xc-probability-trial-metrics/1"
    candidates: tuple[CandidateEvaluation, ...] = Field(
        min_length=REGULARIZATION_CANDIDATE_COUNT, max_length=REGULARIZATION_CANDIDATE_COUNT
    )
    constant: CandidateEvaluation
    constant_training_rates: dict[str, Probability | None]


class TrialMetadata(AtmosphericContract):
    schema_version: Literal["xc-probability-trial/1"] = "xc-probability-trial/1"
    study_id: Sha256
    dataset_id: Sha256
    fold: Literal[2023, 2024]
    exclusive_training_cutoff: str
    training_summary: dict[str, JsonValue]
    validation_summary: dict[str, JsonValue]
    models: tuple[FittedStage, ...] = Field(min_length=TRIAL_FIT_COUNT, max_length=TRIAL_FIT_COUNT)
    conversion: ConversionSupport
    algorithm: dict[str, JsonValue]
    logistic_arguments: dict[str, JsonValue]
    threadpoolctl_version: str
    validation_status: Literal["development_only"] = "development_only"
    data_status: Literal["baseline"] = "baseline"
    calibration_status: Literal["not_calibrated"] = "not_calibrated"
    confidence_policy_version: Literal["xc-confidence/1"] = "xc-confidence/1"


@dataclass(frozen=True)
class LoadedTrial:
    metadata: TrialMetadata
    predictions: tuple[ValidationPrediction, ...]
    evaluation: TrialEvaluation


def fold_rows(study: LoadedStudy, fold: int) -> tuple[tuple[StudyRow, ...], tuple[StudyRow, ...]]:
    selected = next((part for part in study.metadata.folds if part.validation_season == fold), None)
    if selected is None:
        raise ValueError("XC trial fold must be 2023 or 2024 from the consumed study.")
    by_id = {row.row_id: row for row in study.rows}
    return (
        tuple(by_id[key] for key in selected.training_row_ids),
        tuple(by_id[key] for key in selected.validation_row_ids),
    )


def validation_predictions(
    models: tuple[FittedStage, ...],
    rows: tuple[StudyRow, ...],
    *,
    conversion: ConversionSupport,
    site_ids: tuple[int, ...],
    policy: XcPolicy,
) -> tuple[ValidationPrediction, ...]:
    grid = tuple((stage, c) for stage in MODEL_STAGES for c in policy.regularization_grid)
    if (
        tuple((model.parameters.stage, model.parameters.regularization_c) for model in models)
        != grid
    ):
        raise ValueError("Trial requires the ordered six predeclared stage/C fits.")
    encoded = encode_inputs(tuple(row.inputs for row in rows), site_ids, policy)
    stage_values = {
        (model.parameters.stage, model.parameters.regularization_c): predict_stage(
            model.parameters, encoded
        )
        for model in models
    }
    supported = conversion.support_state == "supported"
    result = []
    for c100 in policy.regularization_grid:
        for c200 in policy.regularization_grid:
            for index, row in enumerate(rows):
                p100 = float(stage_values["p100", c100][index])
                q200 = float(stage_values["q200", c200][index])
                p200 = p100 * q200
                result.append(
                    ValidationPrediction(
                        c100=c100,
                        c200=c200,
                        row_id=row.row_id,
                        site_id=row.inputs.site_id,
                        target_local_date=row.inputs.target_local_date,
                        horizon_days=row.inputs.horizon_days,
                        p100=p100,
                        q200=q200,
                        p200=p200,
                        p300=p200 * conversion.ratio if supported else None,
                        p300_missing_reason=None if supported else "insufficient_300_support",
                    )
                )
    return tuple(result)


def constant_rates(rows: tuple[StudyRow, ...], conversion: ConversionSupport) -> dict:
    unique = {(row.inputs.site_id, row.inputs.target_local_date): row for row in rows}
    total = math.fsum(row.sampling_weight for row in unique.values())
    positive100 = math.fsum(row.sampling_weight for row in unique.values() if row.labels[0])
    positive200 = math.fsum(row.sampling_weight for row in unique.values() if row.labels[1])
    p100, p200 = positive100 / total, positive200 / total
    return {
        "p100": p100,
        "q200": positive200 / positive100 if positive100 else None,
        "p200": p200,
        "p300": p200 * conversion.ratio if conversion.support_state == "supported" else None,
    }


def evaluate_candidate(
    rows: tuple[StudyRow, ...],
    probabilities: dict[str, list],
    *,
    c100: float | None,
    c200: float | None,
) -> CandidateEvaluation:
    def metrics_for(indices):
        selected = tuple(rows[index] for index in indices)
        return tuple(
            evaluate_metric(
                selected,
                [probabilities[str(t)][index] for index in indices],
                threshold=t,
                missing_reason="insufficient_300_support"
                if probabilities[str(t)][0] is None
                else None,
            )
            for t in EVALUATED_THRESHOLDS_KM
        )

    by_horizon = {
        str(horizon): metrics_for(
            [index for index, row in enumerate(rows) if row.inputs.horizon_days == horizon]
        )
        for horizon in FORECAST_HORIZONS
    }
    primary = [
        summary.scores
        for metrics in by_horizon.values()
        for summary in metrics
        if summary.threshold_km in SELECTION_THRESHOLDS_KM
    ]
    if len(primary) != TRIAL_SCORE_COMPONENT_COUNT or any(scores is None for scores in primary):
        raise ValueError(
            "Trial candidate selection components must cover both thresholds and all three horizons."
        )
    return CandidateEvaluation(
        c100=c100,
        c200=c200,
        by_horizon=by_horizon,
        pooled=metrics_for(list(range(len(rows)))),
        mean_brier=math.fsum(scores.brier for scores in primary) / TRIAL_SCORE_COMPONENT_COUNT,
        mean_log_loss=math.fsum(scores.log_loss for scores in primary)
        / TRIAL_SCORE_COMPONENT_COUNT,
    )


def evaluate_trial(
    training: tuple[StudyRow, ...],
    validation: tuple[StudyRow, ...],
    predictions: tuple[ValidationPrediction, ...],
    conversion: ConversionSupport,
    policy: XcPolicy,
) -> TrialEvaluation:
    candidates = []
    for c100 in policy.regularization_grid:
        for c200 in policy.regularization_grid:
            subset = tuple(row for row in predictions if (row.c100, row.c200) == (c100, c200))
            if tuple(row.row_id for row in subset) != tuple(row.row_id for row in validation):
                raise ValueError(
                    "Trial predictions must cover each validation row once per grid pair."
                )
            values = {
                str(t): [getattr(row, f"p{t}") for row in subset] for t in EVALUATED_THRESHOLDS_KM
            }
            candidates.append(evaluate_candidate(validation, values, c100=c100, c200=c200))
    rates = constant_rates(training, conversion)
    return TrialEvaluation(
        candidates=tuple(candidates),
        constant_training_rates=rates,
        constant=evaluate_candidate(
            validation,
            {str(t): [rates[f"p{t}"]] * len(validation) for t in EVALUATED_THRESHOLDS_KM},
            c100=None,
            c200=None,
        ),
    )


def trial_report(metadata: TrialMetadata, evaluation: TrialEvaluation) -> bytes:
    constant = evaluation.constant
    improvement_count = sum(
        candidate.mean_brier < constant.mean_brier for candidate in evaluation.candidates
    )
    conversion = metadata.conversion
    conversion_note = (
        f"300+ validation predictions/metrics are missing: insufficient_300_support (training {conversion.k}/{conversion.n})."
        if conversion.support_state != "supported"
        else f"300+ uses the pooled unsmoothed training conversion {conversion.k}/{conversion.n}; no separate weather model."
    )
    lines = [
        f"# XC chronological development trial: {metadata.fold}",
        "",
        f"Train seasons: {', '.join(map(str, conversion.training_source_seasons))}; validation season: {metadata.fold}.",
        f"Exclusive training cutoff: {metadata.exclusive_training_cutoff}.",
        (
            f"Training: {metadata.training_summary['row_count']} rows / {metadata.training_summary['site_day_count']} site-days; "
            f"validation: {metadata.validation_summary['row_count']} rows / {metadata.validation_summary['site_day_count']} site-days."
        ),
        "",
        "Six weighted L2 logistic fits produce the nine combinations below. Mean scores give equal weight to",
        "100+ and final 200+ at each of three horizons (six components). 300+ does not enter this comparison.",
        "",
        "| C100 | C200 | Mean weighted Brier | Mean weighted log loss | Brier minus constant |",
        "| ---: | ---: | ---: | ---: | ---: |",
        *[
            f"| {candidate.c100} | {candidate.c200} | {candidate.mean_brier:.12g} | {candidate.mean_log_loss:.12g} | "
            f"{candidate.mean_brier - constant.mean_brier:+.12g} |"
            for candidate in evaluation.candidates
        ],
        "",
        f"Training-only constant comparator: Brier {constant.mean_brier:.12g}; log loss {constant.mean_log_loss:.12g}.",
        f"Candidates with lower development Brier than constant: {improvement_count}/9.",
        *(
            ["No demonstrated added benefit in this development trial."]
            if improvement_count == 0
            else []
        ),
        "",
        conversion_note,
        "",
        "This is uncalibrated baseline development evidence, not an independent evaluation or a selected final model.",
        "Confidence remains low. 2025 is untouched. Both chronological trials are required before selection.",
        "The 0.5 confusion threshold is diagnostic, not an alert rule. Counts distinguish repeated horizon rows",
        "from unique site-days; no intervals treating rows as independent are reported.",
        "metrics.json retains weighted ranking/calibration diagnostics, raw and weighted confusion counts,",
        "and explicit undefined reasons. Empty calibration bins have null means/frequencies.",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def validate_trial_payload(
    payloads: dict[str, bytes], *, study: LoadedStudy, study_id: str
) -> LoadedTrial:
    if set(payloads) != {
        "policy.json",
        "trial.json",
        "validation_predictions.jsonl",
        "metrics.json",
        "report.md",
    }:
        raise ValueError("Trial bundle has unexpected or missing files.")
    policy, _ = load_policy()
    metadata = TrialMetadata.model_validate_json(payloads["trial.json"])
    if (
        metadata.study_id != study_id
        or metadata.dataset_id != study.metadata.dataset_id
        or (
            metadata.algorithm != policy.algorithm
            or metadata.logistic_arguments != LOGISTIC_ARGUMENTS
            or metadata.threadpoolctl_version != version("threadpoolctl")
        )
    ):
        raise ValueError("Trial study lineage, algorithm or library compatibility differs.")
    training, validation = fold_rows(study, metadata.fold)
    fold = next(part for part in study.metadata.folds if part.validation_season == metadata.fold)
    if (
        metadata.training_summary != summarize(training)
        or metadata.validation_summary != summarize(validation)
        or (
            metadata.exclusive_training_cutoff != fold.exclusive_training_cutoff
            or metadata.conversion != conversion_support(training, study_id=study_id)
        )
    ):
        raise ValueError(
            "Trial support or chronological boundaries differ from the consumed study."
        )
    site_ids = tuple(site for site, _ in study.metadata.site_categories)
    by_id = {row.row_id: row for row in study.rows}
    for fitted in metadata.models:
        parameters = fitted.parameters
        weights = next(
            part
            for part in study.weights
            if part.training_scope == str(metadata.fold) and part.stage == parameters.stage
        )
        rows = tuple(by_id[key] for key in weights.row_ids)
        encoded = encode_inputs(tuple(row.inputs for row in rows), site_ids, policy)
        means, scales, reference = weighted_scaler(encoded, np.asarray(weights.row_weights))
        if parameters.support != stage_support(rows, weights) or any(
            not np.array_equal(np.asarray(actual), expected)
            for actual, expected in (
                (parameters.means, means),
                (parameters.scales, scales),
                (parameters.reference, reference),
            )
        ):
            raise ValueError(
                "Trial scaler/reference/support differs from its training-only subset."
            )
        for check in fitted.self_checks:
            if check.source_row_id not in set(fold.training_row_ids) | set(
                fold.validation_row_ids
            ) or (
                not np.array_equal(
                    np.asarray(check.encoded),
                    encode_inputs((by_id[check.source_row_id].inputs,), site_ids, policy)[0],
                )
            ):
                raise ValueError("Trial numerical probe differs from its frozen source row.")
    expected = validation_predictions(
        metadata.models,
        validation,
        conversion=metadata.conversion,
        site_ids=site_ids,
        policy=policy,
    )
    json_lines(payloads["validation_predictions.jsonl"])
    predictions = tuple(
        ValidationPrediction.model_validate_json(line)
        for line in payloads["validation_predictions.jsonl"].splitlines()
    )
    values = {"p100", "q200", "p200", "p300"}
    if len(predictions) != len(expected) or any(
        actual.model_dump(exclude=values) != reference.model_dump(exclude=values)
        or any(
            (getattr(actual, key) is None) != (getattr(reference, key) is None)
            or (
                getattr(actual, key) is not None
                and not math.isclose(
                    getattr(actual, key), getattr(reference, key), abs_tol=1e-12, rel_tol=0
                )
            )
            for key in values
        )
        for actual, reference in zip(predictions, expected, strict=True)
    ):
        raise ValueError("Trial validation predictions differ from the saved conditional stages.")
    evaluation = TrialEvaluation.model_validate_json(payloads["metrics.json"])
    if evaluation != evaluate_trial(training, validation, predictions, metadata.conversion, policy):
        raise ValueError(
            "Trial diagnostics differ from validation predictions and original sampling weights."
        )
    if payloads["report.md"] != trial_report(metadata, evaluation):
        raise ValueError("Trial report differs from its candidate comparisons and limitations.")
    return LoadedTrial(metadata=metadata, predictions=predictions, evaluation=evaluation)


def load_trial(
    *, trial_id: str, study_id: str, study: LoadedStudy, project_root: Path
) -> LoadedTrial:
    directory = artifact_directory(project_root, "trial", trial_id)
    manifest, payloads = read_bundle(directory, kind="trial", artifact_id=trial_id)
    if manifest.parents != (ArtifactParent(kind="study", artifact_id=study_id),):
        raise ValueError("Trial manifest must name exactly the consumed study parent.")
    return validate_trial_payload(payloads, study=study, study_id=study_id)


def train_trials(*, study_id: str, fold: int, project_root: Path) -> dict:
    started_at = perf_counter()
    study = load_study(study_id=study_id, project_root=project_root)
    policy, _ = load_policy()
    training, validation = fold_rows(study, fold)
    site_ids = tuple(site for site, _ in study.metadata.site_categories)
    by_id = {row.row_id: row for row in training}
    models = []
    with threadpool_limits(limits=1):
        for stage in MODEL_STAGES:
            weights = next(
                part
                for part in study.weights
                if part.training_scope == str(fold) and part.stage == stage
            )
            eligible = tuple(by_id[key] for key in weights.row_ids)
            for c in policy.regularization_grid:
                models.append(
                    fit_stage(
                        eligible,
                        weights,
                        regularization_c=c,
                        site_ids=site_ids,
                        policy=policy,
                        check_rows=validation,
                    )
                )
        conversion = conversion_support(training, study_id=study_id)
        predictions = validation_predictions(
            tuple(models), validation, conversion=conversion, site_ids=site_ids, policy=policy
        )
        evaluation = evaluate_trial(training, validation, predictions, conversion, policy)
    metadata = TrialMetadata(
        study_id=study_id,
        dataset_id=study.metadata.dataset_id,
        fold=fold,
        exclusive_training_cutoff=next(
            part.exclusive_training_cutoff
            for part in study.metadata.folds
            if part.validation_season == fold
        ),
        training_summary=summarize(training),
        validation_summary=summarize(validation),
        models=tuple(models),
        conversion=conversion,
        algorithm=policy.algorithm,
        logistic_arguments=LOGISTIC_ARGUMENTS,
        threadpoolctl_version=version("threadpoolctl"),
    )
    payloads = {
        "trial.json": pretty_json_bytes(metadata),
        "metrics.json": pretty_json_bytes(evaluation),
        "validation_predictions.jsonl": b"".join(canonical_json_bytes(row) for row in predictions),
        "report.md": trial_report(metadata, evaluation),
    }
    result = publish_bundle(
        root=project_root.resolve(),
        kind="trial",
        payloads=payloads,
        started_at=started_at,
        parents=(ArtifactParent(kind="study", artifact_id=study_id),),
        validate_payload=lambda contents: validate_trial_payload(
            contents, study=study, study_id=study_id
        ),
    )
    return {
        **result,
        "fold": fold,
        "fit_count": len(models),
        "candidate_count": len(evaluation.candidates),
        "training_row_count": len(training),
        "validation_row_count": len(validation),
        "validation_prediction_count": len(predictions),
        "conversion": conversion.model_dump(mode="json"),
        "constant_mean_brier": evaluation.constant.mean_brier,
        "constant_mean_log_loss": evaluation.constant.mean_log_loss,
        "validation_status": "development_only",
        "calibration_status": "not_calibrated",
    }
