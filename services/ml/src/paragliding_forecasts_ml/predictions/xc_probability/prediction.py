"""Offline inference and replayable XC prediction bundles."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Literal

from pydantic import Field

from ...ingestion.atmosphere.contracts import AtmosphericContract
from ...ingestion.weather.serialization import canonical_json_bytes, pretty_json_bytes, sha256_bytes
from .artifacts import artifact_directory, publish_bundle, read_bundle
from .inputs import ForecastInput, validate_features
from .learning import encode_inputs, grouped_contributions, predict_stage
from .model_io import FinalModel, load_model
from .models import (
    ArtifactParent,
    AvailableMetric,
    Confidence,
    ConversionSupport,
    LocalDriver,
    MissingMetric,
    Sha256,
    StageExplanation,
    ThresholdProbabilities,
    TrainingSupport,
)
from .policy import Stage, XcPolicy, load_policy
from .retained import read_retained_inputs


class Message(AtmosphericContract):
    message_code: str
    message_params: dict[str, str]
    text: str = Field(min_length=1)


class ThresholdExplanation(AtmosphericContract):
    stages: tuple[Stage, ...]
    formula: Literal["p100", "p100*q200", "p200*(k/n)"] | None
    message: Message | None = None


class PredictionRow(AtmosphericContract):
    model_id: Sha256
    input_sha256: Sha256
    run_key: str
    site_id: int
    site_slug: str
    target_local_date: str
    issue_local_date: str
    horizon_days: Literal[1, 2, 3]
    cycle_reference_utc: str
    issue_cutoff_utc: str
    source_ready_at_utc: str
    probabilities: ThresholdProbabilities
    stage_drivers: tuple[StageExplanation, ...]
    stage_messages: dict[Stage, tuple[Message, ...]]
    threshold_explanations: dict[Literal["p100", "p200", "p300"], ThresholdExplanation]
    limitation: Message


class PredictionMetadata(AtmosphericContract):
    schema_version: Literal["xc-probability-prediction/1"] = "xc-probability-prediction/1"
    model_id: Sha256
    run_keys: tuple[str, ...]
    row_count: int
    missing_by_reason: dict[str, int]
    training_support: dict[Stage, TrainingSupport]
    conversion: ConversionSupport
    confidence_policy_version: Literal["xc-confidence/1"]
    explanation_policy_version: Literal["xc-grouped-logit/1"]
    calibration_status: Literal["not_calibrated"]
    independent_reliability_status: Literal["unverified"]


@dataclass(frozen=True)
class PredictionBatch:
    metadata: PredictionMetadata
    inputs: tuple[ForecastInput, ...]
    rows: tuple[PredictionRow, ...]


def _message(model: FinalModel, code: str, **params: str) -> Message:
    return Message(
        message_code=code, message_params=params, text=model.templates[code].format(**params)
    )


def _available(model: FinalModel, threshold: str, value: float) -> AvailableMetric:
    note = model.confidence_notes[threshold].format(k=model.conversion.k, n=model.conversion.n)
    return AvailableMetric(
        value=value,
        confidence=Confidence(
            note=note,
            policy_version=model.confidence_policy_version,
            reason_codes=model.confidence_reasons[threshold],
        ),
        calibration_status=model.calibration_status,
    )


def _stage_explanations(
    model: FinalModel, policy: XcPolicy, encoded
) -> list[tuple[StageExplanation, ...]]:
    per_stage = []
    labels = policy.explanation["stage_labels"]
    for fitted in model.models:
        parameters = fitted.parameters
        probabilities = predict_stage(parameters, encoded)
        contributions = grouped_contributions(parameters, encoded, model.coordinate_group_ids)
        explanations = []
        for index, probability in enumerate(probabilities):
            groups = []
            for group in model.driver_groups:
                amount = float(contributions[group.group_id][index])
                if abs(amount) <= 1e-12:
                    direction, code = "zero", "no_distinct_driver"
                elif amount > 0:
                    direction, code = "raises", "group_supports"
                else:
                    direction, code = "lowers", "group_reduces"
                groups.append(
                    LocalDriver(
                        stage=parameters.stage,
                        group_id=group.group_id,
                        kind=group.kind,
                        direction=direction,
                        contribution_logit=amount,
                        source_feature_ids=tuple(
                            spec.feature_id
                            for spec in policy.required_features
                            if spec.group_id == group.group_id
                        ),
                        message_code=code,
                        message_params={
                            "group_label": group.label,
                            "stage_label": labels[parameters.stage],
                        }
                        if direction != "zero"
                        else {},
                    )
                )
            ranked = sorted(
                (group for group in groups if group.direction != "zero"),
                key=lambda group: (-abs(group.contribution_logit), group.group_id),
            )
            explanations.append(
                StageExplanation(
                    stage=parameters.stage,
                    policy_version=model.explanation_policy_version,
                    baseline_logit=parameters.baseline_logit,
                    decision_logit=parameters.baseline_logit
                    + math.fsum(g.contribution_logit for g in groups),
                    probability=float(probability),
                    groups=tuple(groups),
                    top_group_ids=tuple(group.group_id for group in ranked[:3]),
                )
            )
        per_stage.append(explanations)
    return list(zip(*per_stage, strict=True))


def predict_records(
    model: FinalModel, model_id: str, inputs: tuple[ForecastInput, ...], policy: XcPolicy
) -> tuple[PredictionRow, ...]:
    """Calculate predictions from the exact saved inputs and frozen model alone."""
    if not inputs:
        raise ValueError("XC prediction requires at least one forecast input.")
    keys = [(row.run_key, row.site_id) for row in inputs]
    if keys != sorted(set(keys)):
        raise ValueError("XC prediction inputs require distinct ordered run/site keys.")
    site_categories = dict(model.site_categories)
    missing = []
    for row in inputs:
        validate_features(row, policy, require_available=False)
        if site_categories.get(row.site_id) != row.site_slug:
            raise ValueError("XC input site identity differs from the frozen model categories.")
        missing.append(tuple(obs.feature_id for obs in row.observations if obs.value is None))

    available = tuple(row for row, absent in zip(inputs, missing, strict=True) if not absent)
    stages = iter(
        _stage_explanations(model, policy, encode_inputs(available, tuple(site_categories), policy))
        if available
        else ()
    )
    result = []
    for row, absent in zip(inputs, missing, strict=True):
        stage_messages = {}
        if absent:
            missing_metric = MissingMetric(
                missing_reason="required_inputs_missing", missing_feature_ids=absent
            )
            probabilities = ThresholdProbabilities(
                p100=missing_metric, p200=missing_metric, p300=missing_metric
            )
            stage_drivers = ()
            unavailable = ThresholdExplanation(
                stages=(),
                formula=None,
                message=_message(model, "required_inputs_missing", feature_ids=", ".join(absent)),
            )
            explanations = dict.fromkeys(("p100", "p200", "p300"), unavailable)
        else:
            stage_drivers = next(stages)
            first, conditional = stage_drivers
            p200 = first.probability * conditional.probability
            conversion = model.conversion
            if conversion.support_state == "supported":
                p300 = _available(model, "300", p200 * conversion.ratio)
                explanation300 = ThresholdExplanation(
                    stages=("p100", "q200"),
                    formula="p200*(k/n)",
                    message=_message(
                        model, "empirical_300_method", k=str(conversion.k), n=str(conversion.n)
                    ),
                )
            else:
                p300 = MissingMetric(missing_reason="insufficient_300_support")
                explanation300 = ThresholdExplanation(
                    stages=(),
                    formula=None,
                    message=_message(model, "insufficient_300_support"),
                )
            probabilities = ThresholdProbabilities(
                p100=_available(model, "100", first.probability),
                p200=_available(model, "200", p200),
                p300=p300,
            )
            explanations = {
                "p100": ThresholdExplanation(stages=("p100",), formula="p100"),
                "p200": ThresholdExplanation(stages=("p100", "q200"), formula="p100*q200"),
                "p300": explanation300,
            }
            for stage in stage_drivers:
                groups = {group.group_id: group for group in stage.groups}
                stage_messages[stage.stage] = tuple(
                    _message(
                        model, groups[group_id].message_code, **groups[group_id].message_params
                    )
                    for group_id in stage.top_group_ids
                ) or (_message(model, "no_distinct_driver"),)
        result.append(
            PredictionRow(
                **row.model_dump(exclude={"observations", "source_lineage", "valid_times_utc"}),
                model_id=model_id,
                input_sha256=sha256_bytes(canonical_json_bytes(row)),
                probabilities=probabilities,
                stage_drivers=stage_drivers,
                stage_messages=stage_messages,
                threshold_explanations=explanations,
                limitation=_message(model, "baseline_limitation"),
            )
        )
    return tuple(result)


def _metadata(
    model: FinalModel, model_id: str, rows: tuple[PredictionRow, ...]
) -> PredictionMetadata:
    missing = Counter(
        metric.missing_reason
        for row in rows
        for metric in (row.probabilities.p100, row.probabilities.p200, row.probabilities.p300)
        if isinstance(metric, MissingMetric)
    )
    return PredictionMetadata(
        model_id=model_id,
        run_keys=tuple(sorted({row.run_key for row in rows})),
        row_count=len(rows),
        missing_by_reason=dict(missing),
        training_support={
            stage.parameters.stage: stage.parameters.support for stage in model.models
        },
        conversion=model.conversion,
        confidence_policy_version=model.confidence_policy_version,
        explanation_policy_version=model.explanation_policy_version,
        calibration_status=model.calibration_status,
        independent_reliability_status=model.independent_reliability_status,
    )


def _validate_payload(
    payloads: dict[str, bytes], model: FinalModel, model_id: str, policy: XcPolicy
) -> PredictionBatch:
    if set(payloads) != {"policy.json", "prediction.json", "inputs.jsonl", "predictions.jsonl"}:
        raise ValueError("Unexpected XC prediction bundle inventory.")
    inputs = tuple(
        ForecastInput.model_validate_json(line) for line in payloads["inputs.jsonl"].splitlines()
    )
    if payloads["inputs.jsonl"] != b"".join(canonical_json_bytes(row) for row in inputs):
        raise ValueError("XC bundle inputs must retain their canonical record bytes.")
    rows = predict_records(model, model_id, inputs, policy)
    metadata = _metadata(model, model_id, rows)
    if payloads["predictions.jsonl"] != b"".join(
        canonical_json_bytes(row) for row in rows
    ) or payloads["prediction.json"] != pretty_json_bytes(metadata):
        raise ValueError("XC prediction bundle differs from replay of its exact inputs.")
    return PredictionBatch(metadata, inputs, rows)


def load_prediction(*, prediction_id: str, project_root: Path) -> PredictionBatch:
    """Verify and replay an existing prediction bundle without SQLite or raw evidence."""
    manifest, payloads = read_bundle(
        artifact_directory(project_root, "prediction", prediction_id),
        kind="prediction",
        artifact_id=prediction_id,
    )
    if len(manifest.parents) != 1 or manifest.parents[0].kind != "model":
        raise ValueError("XC prediction must have one final-model parent.")
    model_id = manifest.parents[0].artifact_id
    model = load_model(model_id=model_id, project_root=project_root)
    policy, _ = load_policy()
    return _validate_payload(payloads, model, model_id, policy)


def predict_runs(
    *, model_id: str, run_keys: tuple[str, ...], project_root: Path, database_url: str | None = None
) -> dict:
    started_at = perf_counter()
    model = load_model(model_id=model_id, project_root=project_root)
    policy, _ = load_policy()
    inputs = read_retained_inputs(
        run_keys, project_root=project_root, policy=policy, database_url=database_url
    )
    rows = predict_records(model, model_id, inputs, policy)
    metadata = _metadata(model, model_id, rows)
    result = publish_bundle(
        root=project_root.resolve(),
        kind="prediction",
        started_at=started_at,
        parents=(ArtifactParent(kind="model", artifact_id=model_id),),
        payloads={
            "prediction.json": pretty_json_bytes(metadata),
            "inputs.jsonl": b"".join(canonical_json_bytes(row) for row in inputs),
            "predictions.jsonl": b"".join(canonical_json_bytes(row) for row in rows),
        },
        validate_payload=lambda contents: _validate_payload(contents, model, model_id, policy),
    )
    return {**result, **metadata.model_dump(mode="json", exclude={"schema_version"})}
