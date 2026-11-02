"""JSON-safe contracts for immutable XC artifacts and fitted numerical state."""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import Field, FiniteFloat, field_validator, model_validator

from ...ingestion.atmosphere.contracts import AtmosphericContract, validate_utc_timestamp
from .policy import GroupId, Stage

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Probability = Annotated[FiniteFloat, Field(ge=0, le=1)]
ArtifactKind = Literal["study", "trial", "selection", "model", "prediction"]


class FileDigest(AtmosphericContract):
    sha256: Sha256
    byte_count: int = Field(ge=0)


class ArtifactParent(AtmosphericContract):
    kind: ArtifactKind
    artifact_id: Sha256


class PublicationTiming(AtmosphericContract):
    elapsed_seconds_before_publication: FiniteFloat = Field(ge=0)


class ArtifactManifest(AtmosphericContract):
    schema_version: Literal["xc-probability-artifact/1"] = "xc-probability-artifact/1"
    kind: ArtifactKind
    artifact_id: Sha256
    method_version: Literal["xc-conditional-logistic/1"] = "xc-conditional-logistic/1"
    policy_sha256: Sha256
    parents: tuple[ArtifactParent, ...]
    files: dict[str, FileDigest] = Field(min_length=1)
    numerical_versions: dict[str, str] = Field(min_length=1)
    created_at_utc: str
    execution: PublicationTiming

    @field_validator("created_at_utc")
    @classmethod
    def creation_metadata_is_utc(cls, value: str) -> str:
        return validate_utc_timestamp(value)

    @model_validator(mode="after")
    def safe_files_and_unique_parents(self) -> ArtifactManifest:
        for name in self.files:
            if (
                name in {".", "..", "manifest.json"}
                or not name
                or any(character in name for character in ("/", "\\", ":"))
            ):
                raise ValueError("Manifest files must be safe single-component names.")
        identities = [(parent.kind, parent.artifact_id) for parent in self.parents]
        if len(identities) != len(set(identities)):
            raise ValueError("Artifact parents cannot repeat.")
        if any(not value.strip() for value in self.numerical_versions.values()):
            raise ValueError("Numerical versions must be explicit.")
        return self


class TrainingSupport(AtmosphericContract):
    """Unique site-days describe support; horizon rows are repeated outcomes."""

    row_count: int = Field(gt=0)
    site_day_count: int = Field(gt=0)
    target_date_count: int = Field(gt=0)
    positive_site_day_count: int = Field(gt=0)
    source_seasons: tuple[Literal[2022, 2023, 2024], ...] = Field(min_length=1)
    normalized_weight_sum: FiniteFloat = Field(gt=0)

    @model_validator(mode="after")
    def support_counts_agree(self) -> TrainingSupport:
        if self.row_count != 3 * self.site_day_count:
            raise ValueError("Training must retain exactly three horizons per site-day.")
        if not self.positive_site_day_count < self.site_day_count:
            raise ValueError("Each learned stage requires both outcome classes.")
        if self.target_date_count > self.site_day_count:
            raise ValueError("Target-date support cannot exceed site-day support.")
        if tuple(sorted(set(self.source_seasons))) != self.source_seasons:
            raise ValueError("Source seasons must be sorted, distinct development seasons.")
        if not math.isclose(
            self.normalized_weight_sum, self.site_day_count, abs_tol=1e-10, rel_tol=1e-12
        ):
            raise ValueError("Normalized horizon weights must sum to unique site-day count.")
        return self


class ConversionSupport(AtmosphericContract):
    """Unsmoothed unique training-site-day frequency, never a fitted 300+ model."""

    method: Literal["pooled_empirical_unsmoothed"] = "pooled_empirical_unsmoothed"
    k: int = Field(ge=0)
    n: int = Field(ge=0)
    ratio: Probability | None
    support_state: Literal["supported", "insufficient_300_support"]
    study_id: Sha256
    training_source_seasons: tuple[Literal[2022, 2023, 2024], ...] = Field(min_length=1)

    @model_validator(mode="after")
    def ratio_and_support_agree(self) -> ConversionSupport:
        if self.k > self.n:
            raise ValueError("Nested 300+ count cannot exceed 200+ count.")
        expected = self.k / self.n if self.n else None
        if self.ratio != expected:
            raise ValueError("300+ conversion must equal the exact observed k/n without smoothing.")
        supported = self.n > 0 and self.k > 0
        if (self.support_state == "supported") != supported:
            raise ValueError("Zero numerator or denominator means insufficient 300+ support.")
        if tuple(sorted(set(self.training_source_seasons))) != self.training_source_seasons:
            raise ValueError("Conversion lineage requires sorted, distinct source seasons.")
        return self


class StageParameters(AtmosphericContract):
    stage: Stage
    regularization_c: Literal[0.03, 0.1, 0.3]
    means: tuple[FiniteFloat, ...] = Field(min_length=72, max_length=72)
    scales: tuple[Annotated[FiniteFloat, Field(gt=0)], ...] = Field(min_length=72, max_length=72)
    coefficients: tuple[FiniteFloat, ...] = Field(min_length=82, max_length=82)
    intercept: FiniteFloat
    reference: tuple[FiniteFloat, ...] = Field(min_length=82, max_length=82)
    baseline_logit: FiniteFloat
    support: TrainingSupport

    @model_validator(mode="after")
    def training_reference_is_consistent(self) -> StageParameters:
        if any(value != 0 for value in self.reference[:72]):
            raise ValueError("Standardized continuous reference means must be stored as zero.")
        for frequencies in (self.reference[72:79], self.reference[79:82]):
            if any(value < 0 or value > 1 for value in frequencies) or not math.isclose(
                sum(frequencies), 1, abs_tol=1e-12, rel_tol=0
            ):
                raise ValueError("One-hot references must retain weighted training frequencies.")
        expected = self.intercept + math.fsum(
            coefficient * value for coefficient, value in zip(self.coefficients, self.reference)
        )
        if not math.isclose(expected, self.baseline_logit, abs_tol=1e-12, rel_tol=0):
            raise ValueError("Stored baseline logit must reconstruct the training reference.")
        return self


class Confidence(AtmosphericContract):
    level: Literal["low"] = "low"
    note: str = Field(min_length=1)
    policy_version: Literal["xc-confidence/1"] = "xc-confidence/1"
    reason_codes: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def reasons_are_explicit(self) -> Confidence:
        if not self.note.strip() or any(not code.strip() for code in self.reason_codes):
            raise ValueError("Confidence note and reasons cannot be blank.")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("Confidence reasons cannot repeat.")
        return self


class AvailableMetric(AtmosphericContract):
    value: Probability
    data_status: Literal["baseline"] = "baseline"
    confidence: Confidence
    calibration_status: Literal["not_calibrated"] = "not_calibrated"


class MissingMetric(AtmosphericContract):
    value: None = None
    data_status: Literal["missing"] = "missing"
    confidence: None = None
    missing_reason: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    missing_feature_ids: tuple[str, ...] = ()


Metric = Annotated[AvailableMetric | MissingMetric, Field(discriminator="data_status")]


class ThresholdProbabilities(AtmosphericContract):
    p100: Metric
    p200: Metric
    p300: Metric

    @model_validator(mode="after")
    def probabilities_are_nested(self) -> ThresholdProbabilities:
        for lower, upper in ((self.p200, self.p100), (self.p300, self.p200)):
            if lower.value is not None and (upper.value is None or lower.value > upper.value):
                raise ValueError("Available XC probabilities must be nested in 0..1.")
        return self


class LocalDriver(AtmosphericContract):
    stage: Stage
    group_id: GroupId
    kind: Literal["weather", "context"]
    direction: Literal["raises", "lowers", "zero"]
    contribution_logit: FiniteFloat
    source_feature_ids: tuple[str, ...]
    message_code: Literal["group_supports", "group_reduces", "no_distinct_driver"]
    message_params: dict[str, str]

    @model_validator(mode="after")
    def direction_and_group_agree(self) -> LocalDriver:
        expected = (
            "raises"
            if self.contribution_logit > 1e-12
            else ("lowers" if self.contribution_logit < -1e-12 else "zero")
        )
        if self.direction != expected:
            raise ValueError("Driver direction must describe its grouped logit contribution.")
        expected_code = {
            "raises": "group_supports",
            "lowers": "group_reduces",
            "zero": "no_distinct_driver",
        }[expected]
        if self.message_code != expected_code:
            raise ValueError("Driver message must agree with its direction.")
        if (self.kind == "context") != self.group_id.endswith("_context"):
            raise ValueError("Context effects cannot be described as weather effects.")
        return self


class StageExplanation(AtmosphericContract):
    stage: Stage
    policy_version: Literal["xc-grouped-logit/1"] = "xc-grouped-logit/1"
    baseline_logit: FiniteFloat
    decision_logit: FiniteFloat
    probability: Probability
    groups: tuple[LocalDriver, ...] = Field(min_length=15, max_length=15)
    top_group_ids: tuple[GroupId, ...] = Field(max_length=3)

    @model_validator(mode="after")
    def contributions_reconstruct_stage(self) -> StageExplanation:
        group_ids = [group.group_id for group in self.groups]
        if len(set(group_ids)) != 15 or any(group.stage != self.stage for group in self.groups):
            raise ValueError("Explanation requires every group exactly once for its own stage.")
        if not math.isclose(
            self.baseline_logit + math.fsum(group.contribution_logit for group in self.groups),
            self.decision_logit,
            abs_tol=1e-12,
            rel_tol=0,
        ):
            raise ValueError("Grouped contributions must reconstruct the stage decision logit.")
        if self.decision_logit >= 0:
            expected = 1 / (1 + math.exp(-self.decision_logit))
        else:
            exponential = math.exp(self.decision_logit)
            expected = exponential / (1 + exponential)
        if not math.isclose(self.probability, expected, abs_tol=1e-12, rel_tol=0):
            raise ValueError("Stage probability must match the stable sigmoid of its logit.")
        ranked = sorted(
            (group for group in self.groups if abs(group.contribution_logit) > 1e-12),
            key=lambda group: (-abs(group.contribution_logit), group.group_id),
        )
        if self.top_group_ids != tuple(group.group_id for group in ranked[:3]):
            raise ValueError("Top drivers must follow the fixed magnitude and group-ID ranking.")
        return self
