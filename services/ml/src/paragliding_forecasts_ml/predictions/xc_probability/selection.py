"""Deterministic recipe selection from exactly two verified development trials."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Literal

from pydantic import Field, FiniteFloat, model_validator

from ...ingestion.atmosphere.contracts import AtmosphericContract
from ...ingestion.weather.serialization import pretty_json_bytes
from .artifacts import artifact_directory, identity, publish_bundle, read_bundle
from .experiment import (
    CValue,
    ExperimentVersion,
    experiment_payloads,
    regularization_values,
    validate_experiment_payload,
)
from .models import ArtifactParent, Probability, Sha256
from .scoring_layout import (
    FORECAST_HORIZONS,
    SELECTION_COMPONENT_KEYS,
    SELECTION_SCORE_COMPONENT_COUNT,
    SELECTION_THRESHOLDS_KM,
    VALIDATION_SEASONS,
)
from .study import LoadedStudy, load_study
from .trials import LoadedTrial, load_trial


class Choice(AtmosphericContract):
    c100: CValue
    c200: CValue


class ScoreComponent(AtmosphericContract):
    fold: Literal[2023, 2024]
    horizon: Literal[1, 2, 3]
    threshold: Literal[100, 200]
    brier: Probability
    log_loss: FiniteFloat = Field(ge=0)


class CandidateScore(Choice):
    components: tuple[ScoreComponent, ...] = Field(
        min_length=SELECTION_SCORE_COMPONENT_COUNT, max_length=SELECTION_SCORE_COMPONENT_COUNT
    )
    mean_brier: Probability
    mean_log_loss: FiniteFloat = Field(ge=0)


class TrialReference(AtmosphericContract):
    fold: Literal[2023, 2024]
    trial_id: Sha256


class SelectionMetadata(AtmosphericContract):
    schema_version: Literal["xc-probability-selection/1"] = "xc-probability-selection/1"
    experiment_version: ExperimentVersion = Field(default=1, exclude_if=lambda value: value == 1)
    study_id: Sha256
    dataset_id: Sha256
    trials: tuple[TrialReference, ...] = Field(
        min_length=len(VALIDATION_SEASONS), max_length=len(VALIDATION_SEASONS)
    )
    candidates: tuple[CandidateScore, ...] = Field(min_length=1)
    constant_components: tuple[ScoreComponent, ...] = Field(
        min_length=SELECTION_SCORE_COMPONENT_COUNT, max_length=SELECTION_SCORE_COMPONENT_COUNT
    )
    constant_mean_brier: Probability
    constant_mean_log_loss: FiniteFloat = Field(ge=0)
    winner: Choice
    improves_constant_brier: bool
    brier_tie_tolerance: Literal[1e-12] = 1e-12
    validation_status: Literal["development_only"] = "development_only"
    calibration_status: Literal["not_calibrated"] = "not_calibrated"

    @model_validator(mode="after")
    def frozen_scores_follow_recipe(self) -> SelectionMetadata:
        values = regularization_values(self.experiment_version)
        if tuple(ref.fold for ref in self.trials) != VALIDATION_SEASONS or len(
            {ref.trial_id for ref in self.trials}
        ) != len(VALIDATION_SEASONS):
            raise ValueError("Selection requires two distinct trial IDs for folds 2023 and 2024.")
        grid = tuple((a, b) for a in values for b in values)
        if tuple((score.c100, score.c200) for score in self.candidates) != grid:
            raise ValueError("Selection candidate grid differs from its declared experiment.")
        expected_keys = SELECTION_COMPONENT_KEYS
        for components, brier, loss in (
            *((c.components, c.mean_brier, c.mean_log_loss) for c in self.candidates),
            (self.constant_components, self.constant_mean_brier, self.constant_mean_log_loss),
        ):
            if tuple((c.fold, c.horizon, c.threshold) for c in components) != expected_keys:
                raise ValueError(
                    f"Selection scores must retain exactly {SELECTION_SCORE_COMPONENT_COUNT} ordered components."
                )
            if (
                brier != math.fsum(c.brier for c in components) / SELECTION_SCORE_COMPONENT_COUNT
                or loss
                != math.fsum(c.log_loss for c in components) / SELECTION_SCORE_COMPONENT_COUNT
            ):
                raise ValueError(
                    f"Selection means differ from their {SELECTION_SCORE_COMPONENT_COUNT} equal-weight components."
                )
        winner = choose_candidate(self.candidates, self.brier_tie_tolerance)
        if self.winner != Choice(c100=winner.c100, c200=winner.c200) or (
            self.improves_constant_brier != (winner.mean_brier < self.constant_mean_brier)
        ):
            raise ValueError("Selection winner or baseline comparison violates the frozen recipe.")
        return self


def choose_candidate(
    candidates: tuple[CandidateScore, ...], tolerance: float = 1e-12
) -> CandidateScore:
    if not candidates:
        raise ValueError("Selection requires candidates.")
    minimum = min(candidate.mean_brier for candidate in candidates)
    tied = [
        candidate for candidate in candidates if abs(candidate.mean_brier - minimum) <= tolerance
    ]
    return min(
        tied, key=lambda candidate: (candidate.mean_log_loss, candidate.c100, candidate.c200)
    )


def selection_parents(metadata: SelectionMetadata) -> tuple[ArtifactParent, ...]:
    return (
        ArtifactParent(kind="study", artifact_id=metadata.study_id),
        *(ArtifactParent(kind="trial", artifact_id=ref.trial_id) for ref in metadata.trials),
    )


def build_selection(
    study: LoadedStudy, study_id: str, trials: dict[int, tuple[str, LoadedTrial]]
) -> SelectionMetadata:
    if set(trials) != set(VALIDATION_SEASONS):
        raise ValueError("Selection requires both chronological folds exactly once.")
    versions = {trial.metadata.experiment_version for _, trial in trials.values()}
    if len(versions) != 1:
        raise ValueError("Selection cannot mix regularization experiment versions across folds.")
    experiment_version = versions.pop()
    values = regularization_values(experiment_version)

    def components(c100=None, c200=None):
        result = []
        for fold in VALIDATION_SEASONS:
            trial = trials[fold][1]
            if (
                trial.metadata.fold != fold
                or trial.metadata.study_id != study_id
                or trial.metadata.dataset_id != study.metadata.dataset_id
            ):
                raise ValueError(
                    "Selection trials differ from the consumed study or fold identity."
                )
            candidate = (
                trial.evaluation.constant
                if c100 is None
                else next(
                    candidate
                    for candidate in trial.evaluation.candidates
                    if (candidate.c100, candidate.c200) == (c100, c200)
                )
            )
            for horizon in FORECAST_HORIZONS:
                for threshold in SELECTION_THRESHOLDS_KM:
                    metric = next(
                        metric
                        for metric in candidate.by_horizon[str(horizon)]
                        if metric.threshold_km == threshold
                    )
                    if metric.scores is None:
                        raise ValueError(
                            "Selection cannot omit a required 100+/200+ score component."
                        )
                    result.append(
                        ScoreComponent(
                            fold=fold,
                            horizon=horizon,
                            threshold=threshold,
                            brier=metric.scores.brier,
                            log_loss=metric.scores.log_loss,
                        )
                    )
        return tuple(result)

    candidates = []
    for c100 in values:
        for c200 in values:
            parts = components(c100, c200)
            candidates.append(
                CandidateScore(
                    c100=c100,
                    c200=c200,
                    components=parts,
                    mean_brier=math.fsum(c.brier for c in parts) / SELECTION_SCORE_COMPONENT_COUNT,
                    mean_log_loss=math.fsum(c.log_loss for c in parts)
                    / SELECTION_SCORE_COMPONENT_COUNT,
                )
            )
    winner = choose_candidate(tuple(candidates))
    constant = components()
    baseline_brier = math.fsum(c.brier for c in constant) / SELECTION_SCORE_COMPONENT_COUNT
    return SelectionMetadata(
        experiment_version=experiment_version,
        study_id=study_id,
        dataset_id=study.metadata.dataset_id,
        trials=tuple(
            TrialReference(fold=fold, trial_id=trials[fold][0]) for fold in VALIDATION_SEASONS
        ),
        candidates=tuple(candidates),
        constant_components=constant,
        constant_mean_brier=baseline_brier,
        constant_mean_log_loss=math.fsum(c.log_loss for c in constant)
        / SELECTION_SCORE_COMPONENT_COUNT,
        winner=Choice(c100=winner.c100, c200=winner.c200),
        improves_constant_brier=winner.mean_brier < baseline_brier,
    )


def selection_report(metadata: SelectionMetadata) -> bytes:
    return (
        "\n".join(
            [
                "# XC development recipe selection",
                "",
                *(
                    [
                        f"Regularization experiment {metadata.experiment_version}: {len(metadata.candidates)} candidate pairs.",
                        "",
                    ]
                    if metadata.experiment_version != 1
                    else []
                ),
                "Exactly twelve equally weighted components: two thresholds (100+/final 200+),",
                "three horizons and two chronological development trials. 300+ never selects the recipe.",
                "",
                "| C100 | C200 | Mean weighted Brier | Mean weighted log loss | Brier minus constant |",
                "| ---: | ---: | ---: | ---: | ---: |",
                *[
                    f"| {c.c100} | {c.c200} | {c.mean_brier:.12g} | {c.mean_log_loss:.12g} | {c.mean_brier - metadata.constant_mean_brier:+.12g} |"
                    for c in metadata.candidates
                ],
                "",
                f"Selected C100={metadata.winner.c100}, C200={metadata.winner.c200}.",
                "Brier ties are candidates within absolute 1e-12 of the minimum; ties use lower mean log loss,",
                "then smaller C100, then smaller C200. Trial argument order does not affect selection.",
                f"Constant comparator: Brier {metadata.constant_mean_brier:.12g}, log loss {metadata.constant_mean_log_loss:.12g}.",
                (
                    "The selected candidate improves the development Brier comparator."
                    if metadata.improves_constant_brier
                    else "No demonstrated added benefit in development validation; the selected logistic recipe is retained."
                ),
                "",
                "These data selected the recipe. Scores are development evidence, not independent final-model accuracy.",
                "Confidence remains low and probabilities are uncalibrated. 2025 remains reserved for T-026.",
                "Final fitting starts from scratch on all eligible 2022–2024 rows; temporary fold purges do not carry over.",
            ]
        )
        + "\n"
    ).encode("utf-8")


def validate_selection_payload(
    payloads: dict[str, bytes],
    *,
    study: LoadedStudy,
    study_id: str,
    trials: dict[int, tuple[str, LoadedTrial]],
) -> SelectionMetadata:
    metadata = SelectionMetadata.model_validate_json(payloads["selection.json"])
    validate_experiment_payload(payloads, metadata.experiment_version)
    if set(payloads) != {"policy.json", "selection.json", "report.md"} | set(
        experiment_payloads(metadata.experiment_version)
    ):
        raise ValueError("Selection bundle has unexpected or missing files.")
    if metadata != build_selection(study, study_id, trials) or payloads[
        "report.md"
    ] != selection_report(metadata):
        raise ValueError(
            "Selection content differs from the two verified trial scores and fixed recipe."
        )
    return metadata


@dataclass(frozen=True)
class LoadedSelection:
    metadata: SelectionMetadata
    content_identity: dict


def load_selection(
    *, selection_id: str, study_id: str, study: LoadedStudy, project_root: Path
) -> LoadedSelection:
    manifest, payloads = read_bundle(
        artifact_directory(project_root, "selection", selection_id),
        kind="selection",
        artifact_id=selection_id,
    )
    metadata = SelectionMetadata.model_validate_json(payloads["selection.json"])
    if metadata.study_id != study_id or manifest.parents != selection_parents(metadata):
        raise ValueError("Selection manifest parents differ from the consumed study/trials.")
    trials = {
        ref.fold: (
            ref.trial_id,
            load_trial(
                trial_id=ref.trial_id, study_id=study_id, study=study, project_root=project_root
            ),
        )
        for ref in metadata.trials
    }
    metadata = validate_selection_payload(payloads, study=study, study_id=study_id, trials=trials)
    return LoadedSelection(metadata, identity(manifest))


def select_recipe(*, study_id: str, trial_ids: list[str], project_root: Path) -> dict:
    started_at = perf_counter()
    if len(trial_ids) != len(VALIDATION_SEASONS) or len(set(trial_ids)) != len(VALIDATION_SEASONS):
        raise ValueError("Pass exactly two distinct --trial-id values.")
    study = load_study(study_id=study_id, project_root=project_root)
    trials = {}
    for trial_id in trial_ids:
        trial = load_trial(
            trial_id=trial_id, study_id=study_id, study=study, project_root=project_root
        )
        if trial.metadata.fold in trials:
            raise ValueError("Selection requires two different chronological folds.")
        trials[trial.metadata.fold] = trial_id, trial
    metadata = build_selection(study, study_id, trials)
    result = publish_bundle(
        root=project_root.resolve(),
        kind="selection",
        started_at=started_at,
        parents=selection_parents(metadata),
        payloads={
            **experiment_payloads(metadata.experiment_version),
            "selection.json": pretty_json_bytes(metadata),
            "report.md": selection_report(metadata),
        },
        validate_payload=lambda contents: validate_selection_payload(
            contents, study=study, study_id=study_id, trials=trials
        ),
    )
    winner = next(
        c
        for c in metadata.candidates
        if (c.c100, c.c200) == (metadata.winner.c100, metadata.winner.c200)
    )
    return {
        **result,
        "study_id": study_id,
        "experiment_version": metadata.experiment_version,
        "candidate_count": len(metadata.candidates),
        "component_count": len(winner.components),
        **metadata.winner.model_dump(),
        "mean_brier": winner.mean_brier,
        "mean_log_loss": winner.mean_log_loss,
        "constant_mean_brier": metadata.constant_mean_brier,
        "constant_mean_log_loss": metadata.constant_mean_log_loss,
        "improves_constant_brier": metadata.improves_constant_brier,
        "validation_status": "development_only",
    }
