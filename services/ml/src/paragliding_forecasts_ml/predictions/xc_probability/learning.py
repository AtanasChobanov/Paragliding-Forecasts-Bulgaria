"""Training-only weighted logistic stages and portable float64 inference."""

from __future__ import annotations

import calendar
import math
import warnings
from datetime import date

import numpy as np
from pydantic import Field, FiniteFloat, model_validator
from scipy.special import expit
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from threadpoolctl import threadpool_limits

from ...ingestion.atmosphere.contracts import AtmosphericContract
from .inputs import ForecastInput, validate_features
from .models import ConversionSupport, Probability, Sha256, StageParameters, TrainingSupport
from .policy import XcPolicy, coordinate_ids
from .study import FitWeights, StudyRow

LOGISTIC_ARGUMENTS = {
    "l1_ratio": 0.0,
    "solver": "lbfgs",
    "fit_intercept": True,
    "max_iter": 5000,
    "tol": 1e-8,
    "class_weight": None,
}


def encode_inputs(
    rows: tuple[ForecastInput, ...], site_ids: tuple[int, ...], policy: XcPolicy
) -> np.ndarray:
    """Encode physical/context inputs only; canonical source units stay unchanged."""
    coordinate_ids(policy, site_ids)
    result = []
    for row in rows:
        validate_features(row, policy, require_available=True)
        if row.site_id not in site_ids:
            raise ValueError("XC input site is outside the frozen cohort categories.")
        physical = []
        for observation, spec in zip(row.observations, policy.required_features, strict=True):
            if spec.encoding == "sin_cos":
                angle = math.radians(observation.value)
                physical.extend((math.sin(angle), math.cos(angle)))
            else:
                physical.append(observation.value)
        target = date.fromisoformat(row.target_local_date)
        phase = (
            2
            * math.pi
            * (target.timetuple().tm_yday - 1)
            / (366 if calendar.isleap(target.year) else 365)
        )
        result.append(
            [
                *physical,
                math.sin(phase),
                math.cos(phase),
                *(float(row.site_id == site) for site in site_ids),
                *(float(row.horizon_days == horizon) for horizon in policy.horizons),
            ]
        )
    matrix = np.asarray(result, dtype=np.float64).reshape((-1, 82))
    if not np.isfinite(matrix).all():
        raise ValueError("XC encoded inputs must be finite float64 values.")
    return matrix


def standardize(encoded: np.ndarray, means, scales) -> np.ndarray:
    result = np.array(encoded, dtype=np.float64, copy=True)
    if result.ndim != 2 or result.shape[1] != 82 or not np.isfinite(result).all():
        raise ValueError("XC inference requires a finite matrix with 82 coordinates.")
    result[:, :72] = (result[:, :72] - np.asarray(means)) / np.asarray(scales)
    if not np.isfinite(result).all():
        raise ValueError("XC standardized inputs must remain finite.")
    return result


def weighted_scaler(
    encoded: np.ndarray, sample_weights: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Training-only weighted population moments; exact constants use scale one."""
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        try:
            means = np.average(encoded[:, :72], axis=0, weights=sample_weights)
            constant = np.all(encoded[:, :72] == encoded[0, :72], axis=0)
            means[constant] = encoded[0, :72][constant]
            variance = np.average((encoded[:, :72] - means) ** 2, axis=0, weights=sample_weights)
            scales = np.sqrt(variance)
            scales[constant | (scales == 0)] = 1.0
        except FloatingPointError as error:
            raise ValueError("XC weighted training scaler is not numerically finite.") from error
    reference = np.concatenate(
        (np.zeros(72), np.average(encoded[:, 72:], axis=0, weights=sample_weights))
    )
    return means, scales, reference


def stage_support(rows: tuple[StudyRow, ...], weights: FitWeights) -> TrainingSupport:
    unique = {(row.inputs.site_id, row.inputs.target_local_date): row for row in rows}
    return TrainingSupport(
        row_count=len(rows),
        site_day_count=len(unique),
        target_date_count=len({row.inputs.target_local_date for row in rows}),
        positive_site_day_count=sum(
            row.labels[0 if weights.stage == "p100" else 1] for row in unique.values()
        ),
        source_seasons=tuple(sorted({row.source_season for row in rows})),
        normalized_weight_sum=math.fsum(weights.row_weights),
    )


def predict_stage(parameters: StageParameters, encoded: np.ndarray) -> np.ndarray:
    """Pure JSON-parameter inference; no sklearn estimator, labels or storage."""
    with threadpool_limits(limits=1):
        standardized = standardize(encoded, parameters.means, parameters.scales)
        logits = (
            standardized @ np.asarray(parameters.coefficients, dtype=np.float64)
            + parameters.intercept
        )
        if not np.isfinite(logits).all():
            raise ValueError("XC decision logits must remain finite.")
        return expit(logits)


def grouped_contributions(
    parameters: StageParameters, encoded: np.ndarray, coordinate_group_ids: tuple[str, ...]
) -> dict[str, np.ndarray]:
    """Faithful local logit contributions around the stored training reference."""
    if len(coordinate_group_ids) != 82 or len(set(coordinate_group_ids)) != 15:
        raise ValueError("XC contributions require one of fifteen groups per coordinate.")
    standardized = standardize(encoded, parameters.means, parameters.scales)
    contributions = (standardized - np.asarray(parameters.reference)) * np.asarray(
        parameters.coefficients
    )
    result = {
        group: np.sum(
            contributions[:, [i for i, value in enumerate(coordinate_group_ids) if value == group]],
            axis=1,
        )
        for group in sorted(set(coordinate_group_ids))
    }
    reconstructed = parameters.baseline_logit + np.sum(np.asarray(list(result.values())), axis=0)
    with threadpool_limits(limits=1):
        logits = standardized @ np.asarray(parameters.coefficients) + parameters.intercept
    if not np.allclose(reconstructed, logits, atol=1e-12, rtol=0):
        raise ValueError(
            "Grouped XC contributions fail to reconstruct the stage decision function."
        )
    return result


class StageCheck(AtmosphericContract):
    source_row_id: Sha256
    encoded: tuple[FiniteFloat, ...] = Field(min_length=82, max_length=82)
    expected_probability: Probability


class FittedStage(AtmosphericContract):
    parameters: StageParameters
    iterations: int = Field(ge=1, le=5000)
    self_checks: tuple[StageCheck, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def portable_predictions_match(self) -> FittedStage:
        encoded = np.asarray([check.encoded for check in self.self_checks], dtype=np.float64)
        expected = [check.expected_probability for check in self.self_checks]
        if not np.allclose(predict_stage(self.parameters, encoded), expected, atol=1e-12, rtol=0):
            raise ValueError("XC JSON stage fails its sklearn numerical self-check.")
        return self


def fit_stage(
    rows: tuple[StudyRow, ...],
    weights: FitWeights,
    *,
    regularization_c: float,
    site_ids: tuple[int, ...],
    policy: XcPolicy,
    check_rows: tuple[StudyRow, ...] = (),
) -> FittedStage:
    if regularization_c not in policy.regularization_grid:
        raise ValueError("XC regularization must come from the predeclared grid.")
    if tuple(row.row_id for row in rows) != weights.row_ids:
        raise ValueError("XC fit rows differ from their frozen ordered weights.")
    stage = weights.stage
    if stage == "q200" and any(row.labels[0] != 1 for row in rows):
        raise ValueError("q200 training must contain only positive 100+ site-days.")
    labels = np.asarray([row.labels[0 if stage == "p100" else 1] for row in rows], dtype=np.int64)
    if set(labels.tolist()) != {0, 1}:
        raise ValueError(f"{stage} training requires both outcome classes.")
    encoded = encode_inputs(tuple(row.inputs for row in rows), site_ids, policy)
    sample_weights = np.asarray(weights.row_weights, dtype=np.float64)
    means, scales, reference = weighted_scaler(encoded, sample_weights)
    standardized = standardize(encoded, means, scales)
    estimator = LogisticRegression(C=regularization_c, **LOGISTIC_ARGUMENTS)
    with threadpool_limits(limits=1), warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        try:
            estimator.fit(standardized, labels, sample_weight=sample_weights)
        except ConvergenceWarning as error:
            raise ValueError(
                f"{stage} training did not converge at C={regularization_c}."
            ) from error
    coefficients = tuple(float(value) for value in estimator.coef_[0])
    intercept = float(estimator.intercept_[0])
    parameters = StageParameters(
        stage=stage,
        regularization_c=regularization_c,
        means=tuple(float(value) for value in means),
        scales=tuple(float(value) for value in scales),
        coefficients=coefficients,
        intercept=intercept,
        reference=tuple(float(value) for value in reference),
        baseline_logit=intercept
        + math.fsum(
            coefficient * value for coefficient, value in zip(coefficients, reference, strict=True)
        ),
        support=stage_support(rows, weights),
    )
    checks = list(
        {row.row_id: row for row in (rows[0], rows[-1], *check_rows[:1], *check_rows[-1:])}.values()
    )
    check_encoded = encode_inputs(tuple(row.inputs for row in checks), site_ids, policy)
    with threadpool_limits(limits=1):
        expected = estimator.predict_proba(standardize(check_encoded, means, scales))[:, 1]
        # Verify all fitting rows too, not only the compact persisted probes.
        if not np.allclose(
            predict_stage(parameters, encoded),
            estimator.predict_proba(standardized)[:, 1],
            atol=1e-12,
            rtol=0,
        ):
            raise ValueError("XC JSON inference differs from sklearn predict_proba.")
        if check_rows:
            validation_encoded = encode_inputs(
                tuple(row.inputs for row in check_rows), site_ids, policy
            )
            if not np.allclose(
                predict_stage(parameters, validation_encoded),
                estimator.predict_proba(standardize(validation_encoded, means, scales))[:, 1],
                atol=1e-12,
                rtol=0,
            ):
                raise ValueError("XC JSON validation inference differs from sklearn predict_proba.")
    return FittedStage(
        parameters=parameters,
        iterations=int(estimator.n_iter_[0]),
        self_checks=tuple(
            StageCheck(
                source_row_id=row.row_id,
                encoded=tuple(float(v) for v in vector),
                expected_probability=float(probability),
            )
            for row, vector, probability in zip(checks, check_encoded, expected, strict=True)
        ),
    )


def conversion_support(rows: tuple[StudyRow, ...], *, study_id: str) -> ConversionSupport:
    unique = {(row.inputs.site_id, row.inputs.target_local_date): row for row in rows}
    if not unique:
        raise ValueError("Conversion support requires training site-days.")
    if any(row.sampling_weight != 1 for row in unique.values() if row.labels[1]):
        raise ValueError("200+ conversion evidence must have inclusion weight one.")
    k, n = (
        sum(row.labels[2] for row in unique.values()),
        sum(row.labels[1] for row in unique.values()),
    )
    return ConversionSupport(
        k=k,
        n=n,
        ratio=k / n if n else None,
        support_state="supported" if k and n else "insufficient_300_support",
        study_id=study_id,
        training_source_seasons=tuple(sorted({row.source_season for row in rows})),
    )
