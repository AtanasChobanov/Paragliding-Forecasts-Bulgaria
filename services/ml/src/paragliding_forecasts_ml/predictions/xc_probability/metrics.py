"""Weighted development diagnostics; no calibrator, intervals or alert policy."""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
from pydantic import Field, FiniteFloat
from sklearn.metrics import average_precision_score, roc_auc_score

from ...ingestion.atmosphere.contracts import AtmosphericContract
from .models import Probability
from .study import StudyRow


class CalibrationBin(AtmosphericContract):
    lower: Probability
    upper: Probability
    upper_inclusive: bool
    row_count: int = Field(ge=0)
    sampling_weight_sum: FiniteFloat = Field(ge=0)
    mean_probability: Probability | None
    observed_frequency: Probability | None


class MetricScores(AtmosphericContract):
    brier: Probability
    log_loss: FiniteFloat = Field(ge=0)
    roc_auc: Probability | None
    roc_auc_undefined_reason: Literal["single_outcome_class"] | None
    average_precision: Probability | None
    average_precision_undefined_reason: Literal["no_positive_outcomes"] | None
    confusion_counts: dict[str, int]
    weighted_confusion_counts: dict[str, FiniteFloat]
    precision: Probability | None
    precision_undefined_reason: Literal["no_predicted_positives"] | None
    recall: Probability | None
    recall_undefined_reason: Literal["no_positive_outcomes"] | None
    calibration: tuple[CalibrationBin, ...] = Field(min_length=5, max_length=5)


class MetricSummary(AtmosphericContract):
    threshold_km: Literal[100, 200, 300]
    row_count: int = Field(gt=0)
    site_day_count: int = Field(gt=0)
    target_date_count: int = Field(gt=0)
    positive_row_count: int = Field(ge=0)
    positive_site_day_count: int = Field(ge=0)
    sampling_weight_sum: FiniteFloat = Field(gt=0)
    scores: MetricScores | None
    missing_reason: Literal["insufficient_300_support"] | None


def evaluate_metric(
    rows: tuple[StudyRow, ...],
    probabilities: list[float | None],
    *,
    threshold: int,
    missing_reason: str | None = None,
) -> MetricSummary:
    if not rows or len(rows) != len(probabilities):
        raise ValueError("XC metric requires one probability per validation row.")
    index = {100: 0, 200: 1, 300: 2}[threshold]
    unique = {(row.inputs.site_id, row.inputs.target_local_date): row for row in rows}
    labels = np.asarray([row.labels[index] for row in rows], dtype=np.int64)
    weights = np.asarray([row.sampling_weight for row in rows], dtype=np.float64)
    counts = {
        "threshold_km": threshold,
        "row_count": len(rows),
        "site_day_count": len(unique),
        "target_date_count": len({row.inputs.target_local_date for row in rows}),
        "positive_row_count": int(labels.sum()),
        "positive_site_day_count": sum(row.labels[index] for row in unique.values()),
        "sampling_weight_sum": math.fsum(weights),
    }
    absent = [value is None for value in probabilities]
    if any(absent):
        if not all(absent) or threshold != 300 or missing_reason != "insufficient_300_support":
            raise ValueError(
                "Trial metrics cannot silently discard missing validation predictions."
            )
        return MetricSummary(**counts, scores=None, missing_reason=missing_reason)
    if missing_reason is not None:
        raise ValueError("Available trial metrics cannot carry a missing reason.")
    values = np.asarray(probabilities, dtype=np.float64)
    if not np.isfinite(values).all() or np.any((values < 0) | (values > 1)):
        raise ValueError("XC metric probabilities must be finite in 0..1.")
    clipped = np.clip(values, 1e-15, 1 - 1e-15)
    predicted = values >= 0.5
    masks = {
        "tp": predicted & (labels == 1),
        "fp": predicted & (labels == 0),
        "tn": ~predicted & (labels == 0),
        "fn": ~predicted & (labels == 1),
    }
    confusion = {key: int(mask.sum()) for key, mask in masks.items()}
    weighted = {key: math.fsum(weights[mask]) for key, mask in masks.items()}
    classes = set(labels.tolist())
    bins = np.searchsorted(np.asarray((0.2, 0.4, 0.6, 0.8)), values, side="right")
    calibration = []
    edges = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
    for bin_index in range(5):
        mask = bins == bin_index
        present = bool(mask.any())
        calibration.append(
            CalibrationBin(
                lower=edges[bin_index],
                upper=edges[bin_index + 1],
                upper_inclusive=bin_index == 4,
                row_count=int(mask.sum()),
                sampling_weight_sum=math.fsum(weights[mask]),
                mean_probability=float(np.average(values[mask], weights=weights[mask]))
                if present
                else None,
                observed_frequency=float(np.average(labels[mask], weights=weights[mask]))
                if present
                else None,
            )
        )
    precision_denominator = weighted["tp"] + weighted["fp"]
    recall_denominator = weighted["tp"] + weighted["fn"]
    return MetricSummary(
        **counts,
        missing_reason=None,
        scores=MetricScores(
            brier=float(np.average((values - labels) ** 2, weights=weights)),
            log_loss=float(
                -np.average(
                    labels * np.log(clipped) + (1 - labels) * np.log1p(-clipped), weights=weights
                )
            ),
            roc_auc=float(roc_auc_score(labels, values, sample_weight=weights))
            if len(classes) == 2
            else None,
            roc_auc_undefined_reason=None if len(classes) == 2 else "single_outcome_class",
            average_precision=float(average_precision_score(labels, values, sample_weight=weights))
            if 1 in classes
            else None,
            average_precision_undefined_reason=None if 1 in classes else "no_positive_outcomes",
            confusion_counts=confusion,
            weighted_confusion_counts=weighted,
            precision=weighted["tp"] / precision_denominator if precision_denominator else None,
            precision_undefined_reason=None if precision_denominator else "no_predicted_positives",
            recall=weighted["tp"] / recall_denominator if recall_denominator else None,
            recall_undefined_reason=None if recall_denominator else "no_positive_outcomes",
            calibration=tuple(calibration),
        ),
    )
