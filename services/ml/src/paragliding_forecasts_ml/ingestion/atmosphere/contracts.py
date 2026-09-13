"""Strict, versioned atmospheric stage contracts.

The T-017 catalogue validates canonical field names and units at runtime. These
models deliberately use field mappings rather than a second handwritten enum.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .catalogue import CatalogueError, load_catalogue

UTC_TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
LOCAL_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
UUID_V4_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
VERSION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*/[1-9][0-9]*$")

SourceKind = Literal["forecast", "reanalysis"]
QualityState = Literal[
    "real", "derived", "missing", "sentinel_missing", "invalid_payload", "unsupported"
]
StageName = Literal[
    "parser",
    "normalizer",
    "spatial",
    "validator",
    "feature_builder",
    "persistence",
]
StageDisposition = Literal["complete", "failed", "partial", "quarantined", "persisted"]


class AtmosphericContract(BaseModel):
    """Strict JSON-safe base for every durable atmospheric contract."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ArtifactReference(AtmosphericContract):
    """A hash-addressed immutable artifact below the repository data zones."""

    artifact_schema_version: Literal[1] = 1
    artifact_key: str = Field(min_length=1, max_length=160)
    relative_path: str = Field(min_length=1)
    sha256: str
    byte_count: int = Field(ge=0)
    media_type: str = Field(min_length=1, max_length=120)
    record_count: int | None = Field(default=None, ge=0)

    @field_validator("sha256")
    @classmethod
    def sha256_must_be_lowercase(cls, value: str) -> str:
        if SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("SHA-256 must be 64 lowercase hexadecimal characters.")
        return value

    @field_validator("relative_path")
    @classmethod
    def path_must_be_safe_and_relative(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if (
            normalized.startswith(("/", "../"))
            or "/../" in normalized
            or ":" in normalized
            or normalized.endswith("/")
        ):
            raise ValueError("Artifact path must be a safe repository-relative file path.")
        return normalized


class RequestPlan(AtmosphericContract):
    """Source-neutral request envelope with a source-owned strict payload."""

    request_plan_schema_version: Literal[1] = 1
    run_key: str
    source_id: str
    source_kind: SourceKind
    ingestion_method: Literal["public_object_archive", "official_api", "offline_replay"]
    request_purpose: Literal[
        "historical_forecast", "operational_forecast", "reanalysis_backfill", "replay_validation"
    ]
    catalogue_version: str = Field(min_length=1)
    catalogue_sha256: str
    adapter_request_schema_version: int = Field(ge=1)
    adapter_request: dict[str, Any] = Field(min_length=1)
    expected_artifact_keys: tuple[str, ...] = Field(min_length=1)
    created_at_utc: str

    @field_validator("run_key")
    @classmethod
    def run_key_must_be_uuid_v4(cls, value: str) -> str:
        if UUID_V4_PATTERN.fullmatch(value) is None:
            raise ValueError("run_key must be a lowercase UUID v4.")
        return value

    @field_validator("source_id")
    @classmethod
    def source_must_exist_in_catalogue(cls, value: str) -> str:
        try:
            return load_catalogue().validate_source_id(value)
        except CatalogueError as error:
            raise ValueError(str(error)) from error

    @field_validator("catalogue_sha256")
    @classmethod
    def catalogue_hash_must_be_sha256(cls, value: str) -> str:
        if SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("catalogue_sha256 must be a SHA-256.")
        return value

    @field_validator("created_at_utc")
    @classmethod
    def timestamp_must_be_utc(cls, value: str) -> str:
        return validate_utc_timestamp(value)

    @field_validator("expected_artifact_keys")
    @classmethod
    def artifact_keys_must_be_unique(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)) or any(not value.strip() for value in values):
            raise ValueError("Expected artifact keys must be non-empty and unique.")
        return values

    @model_validator(mode="after")
    def catalogue_identity_must_match_runtime(self) -> RequestPlan:
        catalogue = load_catalogue()
        if self.catalogue_version != catalogue.version or self.catalogue_sha256 != catalogue.sha256:
            raise ValueError("Request plan must identify the exact packaged T-017 catalogue.")
        ensure_json_compatible(self.adapter_request)
        return self


class RawManifest(AtmosphericContract):
    """Immutable raw evidence manifest written after a collector attempt."""

    raw_manifest_schema_version: Literal[1] = 1
    run_key: str
    source_id: str
    source_kind: SourceKind
    collector_version: str
    request_plan: ArtifactReference
    source_product_key: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    permission_basis: str = Field(min_length=1)
    permission_reference: str = Field(min_length=1)
    attribution_text: str | None = None
    reference_at_utc: str | None = None
    available_at_utc: str | None = None
    retrieved_at_utc: str
    valid_from_utc: str
    valid_to_utc: str
    artifacts: tuple[ArtifactReference, ...] = Field(min_length=1)
    status: Literal["complete", "partial", "failed"]
    completed_at_utc: str

    @field_validator("run_key")
    @classmethod
    def raw_manifest_run_key_must_be_uuid(cls, value: str) -> str:
        if UUID_V4_PATTERN.fullmatch(value) is None:
            raise ValueError("run_key must be a lowercase UUID v4.")
        return value

    @field_validator("source_id")
    @classmethod
    def raw_manifest_source_must_exist(cls, value: str) -> str:
        try:
            return load_catalogue().validate_source_id(value)
        except CatalogueError as error:
            raise ValueError(str(error)) from error

    @field_validator("collector_version")
    @classmethod
    def collector_version_must_be_versioned(cls, value: str) -> str:
        return validate_component_version(value)

    @field_validator(
        "reference_at_utc",
        "available_at_utc",
        "retrieved_at_utc",
        "valid_from_utc",
        "valid_to_utc",
        "completed_at_utc",
    )
    @classmethod
    def manifest_times_must_be_utc(cls, value: str | None) -> str | None:
        return None if value is None else validate_utc_timestamp(value)

    @field_validator("artifacts")
    @classmethod
    def raw_artifact_keys_must_be_unique(
        cls, values: tuple[ArtifactReference, ...]
    ) -> tuple[ArtifactReference, ...]:
        keys = [item.artifact_key for item in values]
        if len(keys) != len(set(keys)):
            raise ValueError("Raw artifact keys must be unique.")
        return values

    @model_validator(mode="after")
    def raw_manifest_times_and_plan_must_match(self) -> RawManifest:
        if self.request_plan.relative_path != f"data/raw/weather/{self.run_key}/request-plan.json":
            raise ValueError("Raw manifest must reference its run request plan.")
        if self.valid_to_utc < self.valid_from_utc:
            raise ValueError("Raw manifest valid range is inverted.")
        if self.completed_at_utc < self.retrieved_at_utc:
            raise ValueError("Raw manifest cannot complete before retrieval.")
        return self


class FieldProvenance(AtmosphericContract):
    """Native/derivation provenance for one canonical field value."""

    provenance_schema_version: Literal[1] = 1
    quality_state: QualityState
    native_field_name: str | None = None
    native_unit: str | None = None
    native_value: float | None = None
    native_message_reference: str | None = None
    raw_artifact_key: str | None = None
    source_reference_at_utc: str | None = None
    normalization_method: str | None = None
    normalization_version: str | None = None
    derivation_method: str | None = None
    derivation_version: str | None = None

    @field_validator("quality_state")
    @classmethod
    def quality_must_be_catalogue_value(cls, value: QualityState) -> QualityState:
        try:
            load_catalogue().validate_quality_state(value)
        except CatalogueError as error:
            raise ValueError(str(error)) from error
        return value

    @field_validator("native_value")
    @classmethod
    def native_value_must_be_finite(cls, value: float | None) -> float | None:
        return finite_or_none(value)

    @field_validator("source_reference_at_utc")
    @classmethod
    def source_reference_must_be_utc(cls, value: str | None) -> str | None:
        return None if value is None else validate_utc_timestamp(value)

    @model_validator(mode="after")
    def missing_values_and_method_pairs_must_be_consistent(self) -> FieldProvenance:
        if (
            self.quality_state in {"missing", "sentinel_missing", "unsupported"}
            and self.native_value is not None
        ):
            raise ValueError("Missing native values must be represented as null.")
        if (self.normalization_method is None) != (self.normalization_version is None):
            raise ValueError("Normalization method and version must be supplied together.")
        if (self.derivation_method is None) != (self.derivation_version is None):
            raise ValueError("Derivation method and version must be supplied together.")
        return self


class CanonicalFieldValue(AtmosphericContract):
    """One catalogue-defined canonical value and its explicit provenance."""

    field_value_schema_version: Literal[1] = 1
    field_code: str
    canonical_unit: str = Field(min_length=1)
    canonical_value: float | None = None
    provenance: FieldProvenance

    @field_validator("field_code")
    @classmethod
    def field_must_exist_in_catalogue(cls, value: str) -> str:
        try:
            return load_catalogue().validate_field_code(value)
        except CatalogueError as error:
            raise ValueError(str(error)) from error

    @field_validator("canonical_value")
    @classmethod
    def canonical_value_must_be_finite(cls, value: float | None) -> float | None:
        return finite_or_none(value)

    @model_validator(mode="after")
    def unit_and_missing_state_must_match_catalogue(self) -> CanonicalFieldValue:
        catalogue = load_catalogue()
        if self.canonical_unit != catalogue.field_unit(self.field_code):
            raise ValueError("Canonical unit must match the T-017 catalogue.")
        if self.provenance.quality_state in {"missing", "sentinel_missing", "unsupported"}:
            if self.canonical_value is not None:
                raise ValueError("Missing canonical values must be null.")
        elif self.provenance.quality_state in {"real", "derived"} and self.canonical_value is None:
            raise ValueError("Available canonical values cannot be null.")
        return self


class NativeRecord(AtmosphericContract):
    """One parser result before canonical normalization."""

    native_record_schema_version: Literal[1] = 1
    source_product_key: str = Field(min_length=1)
    valid_at_utc: str
    grid_latitude_deg: float = Field(ge=-90, le=90)
    grid_longitude_deg: float = Field(ge=-180, le=180)
    native_field_name: str = Field(min_length=1)
    native_unit: str = Field(min_length=1)
    native_value: float | None = None
    missing_state: Literal["present", "missing", "sentinel_missing", "invalid_payload"]
    native_message_reference: str = Field(min_length=1)
    raw_artifact_key: str = Field(min_length=1)
    pressure_pa: float | None = Field(default=None, gt=0)
    step_start_hours: float | None = Field(default=None, ge=0)
    step_end_hours: float | None = Field(default=None, ge=0)

    @field_validator("valid_at_utc")
    @classmethod
    def native_valid_time_must_be_utc(cls, value: str) -> str:
        return validate_utc_timestamp(value)

    @field_validator("native_value")
    @classmethod
    def native_record_value_must_be_finite(cls, value: float | None) -> float | None:
        return finite_or_none(value)

    @model_validator(mode="after")
    def native_missing_and_step_shapes_must_match(self) -> NativeRecord:
        if self.missing_state != "present" and self.native_value is not None:
            raise ValueError("Missing or invalid native records must have null values.")
        if (self.step_start_hours is None) != (self.step_end_hours is None):
            raise ValueError("Native step start and end must be supplied together.")
        if (
            self.step_start_hours is not None
            and self.step_end_hours is not None
            and self.step_end_hours < self.step_start_hours
        ):
            raise ValueError("Native step end cannot precede its start.")
        return self


class NativeBatch(AtmosphericContract):
    """Versioned parser output before source-neutral normalization."""

    native_batch_schema_version: Literal[1] = 1
    run_key: str
    source_id: str
    parser_version: str
    raw_manifest: ArtifactReference
    records: tuple[NativeRecord, ...] = Field(min_length=1)

    @field_validator("run_key")
    @classmethod
    def native_batch_run_key_must_be_uuid(cls, value: str) -> str:
        if UUID_V4_PATTERN.fullmatch(value) is None:
            raise ValueError("run_key must be a lowercase UUID v4.")
        return value

    @field_validator("source_id")
    @classmethod
    def native_batch_source_must_exist(cls, value: str) -> str:
        try:
            return load_catalogue().validate_source_id(value)
        except CatalogueError as error:
            raise ValueError(str(error)) from error

    @field_validator("parser_version")
    @classmethod
    def parser_version_must_be_versioned(cls, value: str) -> str:
        return validate_component_version(value)


class CanonicalSample(AtmosphericContract):
    """One normalized point sample, without database identifiers."""

    canonical_sample_schema_version: Literal[1] = 1
    sample_key: str = Field(min_length=1)
    source_product_key: str = Field(min_length=1)
    point_footprint_key: str = Field(min_length=1)
    valid_at_utc: str
    valid_local_date: str
    lead_hours: float | None = Field(default=None, ge=0)
    coverage_status: Literal["complete", "partial", "insufficient"]
    fields: tuple[CanonicalFieldValue, ...] = Field(min_length=1)

    @field_validator("valid_at_utc")
    @classmethod
    def sample_valid_time_must_be_utc(cls, value: str) -> str:
        return validate_utc_timestamp(value)

    @field_validator("valid_local_date")
    @classmethod
    def local_date_must_be_iso(cls, value: str) -> str:
        if LOCAL_DATE_PATTERN.fullmatch(value) is None:
            raise ValueError("valid_local_date must be YYYY-MM-DD.")
        return value

    @field_validator("fields")
    @classmethod
    def sample_fields_must_be_unique(
        cls, values: tuple[CanonicalFieldValue, ...]
    ) -> tuple[CanonicalFieldValue, ...]:
        ensure_unique_field_codes(values)
        return values


class ProfileLevel(AtmosphericContract):
    """One canonical pressure level attached to a canonical sample."""

    profile_level_schema_version: Literal[1] = 1
    sample_key: str = Field(min_length=1)
    pressure_pa: float = Field(gt=0)
    fields: tuple[CanonicalFieldValue, ...] = Field(min_length=1)

    @field_validator("fields")
    @classmethod
    def profile_fields_must_be_unique(
        cls, values: tuple[CanonicalFieldValue, ...]
    ) -> tuple[CanonicalFieldValue, ...]:
        ensure_unique_field_codes(values)
        return values


class ValidationIssue(AtmosphericContract):
    """A machine-readable validation outcome without raw payload duplication."""

    issue_schema_version: Literal[1] = 1
    severity: Literal["warning", "error", "quarantine"]
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    sample_key: str | None = None
    field_code: str | None = None

    @field_validator("field_code")
    @classmethod
    def issue_field_must_be_catalogue_field(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            return load_catalogue().validate_field_code(value)
        except CatalogueError as error:
            raise ValueError(str(error)) from error


class ValidationReport(AtmosphericContract):
    """Validator result and immutable accepted/quarantine evidence references."""

    validation_report_schema_version: Literal[1] = 1
    run_key: str
    validator_version: str
    policy_version: str
    policy_sha256: str
    input_stage_manifest: ArtifactReference
    accepted: ArtifactReference | None = None
    quarantined: ArtifactReference | None = None
    samples_seen: int = Field(ge=0)
    samples_accepted: int = Field(ge=0)
    samples_rejected: int = Field(ge=0)
    samples_quarantined: int = Field(ge=0)
    issues: tuple[ValidationIssue, ...] = ()
    disposition: Literal["accepted", "partial", "quarantined", "failed"]

    @field_validator("run_key")
    @classmethod
    def report_run_key_must_be_uuid(cls, value: str) -> str:
        if UUID_V4_PATTERN.fullmatch(value) is None:
            raise ValueError("run_key must be a lowercase UUID v4.")
        return value

    @field_validator("validator_version")
    @classmethod
    def validator_version_must_be_versioned(cls, value: str) -> str:
        return validate_component_version(value)

    @field_validator("policy_sha256")
    @classmethod
    def policy_hash_must_be_sha256(cls, value: str) -> str:
        if SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("policy_sha256 must be a SHA-256.")
        return value

    @model_validator(mode="after")
    def report_counts_and_evidence_must_match(self) -> ValidationReport:
        if (
            self.samples_accepted + self.samples_rejected + self.samples_quarantined
            > self.samples_seen
        ):
            raise ValueError("Validation outcome counts exceed samples_seen.")
        if self.samples_accepted and self.accepted is None:
            raise ValueError("Accepted samples require an accepted artifact reference.")
        if self.samples_quarantined and self.quarantined is None:
            raise ValueError("Quarantined samples require a quarantine artifact reference.")
        if self.disposition == "accepted" and self.samples_quarantined:
            raise ValueError("Accepted validation disposition cannot contain quarantined samples.")
        return self


class FeatureSnapshot(AtmosphericContract):
    """Versioned derived feature values ready for the future persistence boundary."""

    feature_snapshot_schema_version: Literal[1] = 1
    sample_key: str = Field(min_length=1)
    neighbourhood_footprint_key: str = Field(min_length=1)
    feature_contract_version: str
    input_fingerprint_sha256: str
    fields: tuple[CanonicalFieldValue, ...] = Field(min_length=1)

    @field_validator("feature_contract_version")
    @classmethod
    def feature_contract_version_must_be_versioned(cls, value: str) -> str:
        return validate_component_version(value)

    @field_validator("input_fingerprint_sha256")
    @classmethod
    def input_fingerprint_must_be_sha256(cls, value: str) -> str:
        if SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("input_fingerprint_sha256 must be a SHA-256.")
        return value

    @field_validator("fields")
    @classmethod
    def feature_fields_must_be_unique(
        cls, values: tuple[CanonicalFieldValue, ...]
    ) -> tuple[CanonicalFieldValue, ...]:
        ensure_unique_field_codes(values)
        return values


class StageManifest(AtmosphericContract):
    """Hash-chained output manifest for every durable non-raw stage."""

    stage_manifest_schema_version: Literal[1] = 1
    run_key: str
    stage: StageName
    producer_version: str
    input_fingerprint_sha256: str
    inputs: tuple[ArtifactReference, ...] = Field(min_length=1)
    outputs: tuple[ArtifactReference, ...] = Field(min_length=1)
    configuration: dict[str, Any] = Field(default_factory=dict)
    disposition: StageDisposition
    started_at_utc: str
    completed_at_utc: str

    @field_validator("run_key")
    @classmethod
    def stage_run_key_must_be_uuid(cls, value: str) -> str:
        if UUID_V4_PATTERN.fullmatch(value) is None:
            raise ValueError("run_key must be a lowercase UUID v4.")
        return value

    @field_validator("producer_version")
    @classmethod
    def producer_version_must_be_versioned(cls, value: str) -> str:
        return validate_component_version(value)

    @field_validator("input_fingerprint_sha256")
    @classmethod
    def input_fingerprint_must_be_valid(cls, value: str) -> str:
        if SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("input_fingerprint_sha256 must be a SHA-256.")
        return value

    @field_validator("started_at_utc", "completed_at_utc")
    @classmethod
    def stage_times_must_be_utc(cls, value: str) -> str:
        return validate_utc_timestamp(value)

    @model_validator(mode="after")
    def stage_outputs_must_be_unique_and_ordered(self) -> StageManifest:
        outputs = [item.artifact_key for item in self.outputs]
        if len(outputs) != len(set(outputs)):
            raise ValueError("Stage output keys must be unique.")
        if self.completed_at_utc < self.started_at_utc:
            raise ValueError("Stage cannot complete before it starts.")
        ensure_json_compatible(self.configuration)
        return self


class PersistenceReceipt(AtmosphericContract):
    """Future S08 receipt; S02 proves it only with synthetic evidence."""

    persistence_receipt_schema_version: Literal[1] = 1
    run_key: str
    persistence_version: str
    validation_report: ArtifactReference
    feature_stage_manifest: ArtifactReference
    input_fingerprint_sha256: str
    status: Literal["persisted", "no_op"]
    samples_persisted: int = Field(ge=0)
    completed_at_utc: str

    @field_validator("run_key")
    @classmethod
    def receipt_run_key_must_be_uuid(cls, value: str) -> str:
        if UUID_V4_PATTERN.fullmatch(value) is None:
            raise ValueError("run_key must be a lowercase UUID v4.")
        return value

    @field_validator("persistence_version")
    @classmethod
    def persistence_version_must_be_versioned(cls, value: str) -> str:
        return validate_component_version(value)

    @field_validator("input_fingerprint_sha256")
    @classmethod
    def receipt_input_fingerprint_must_be_sha256(cls, value: str) -> str:
        if SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("input_fingerprint_sha256 must be a SHA-256.")
        return value

    @field_validator("completed_at_utc")
    @classmethod
    def receipt_time_must_be_utc(cls, value: str) -> str:
        return validate_utc_timestamp(value)


def validate_utc_timestamp(value: str) -> str:
    """Accept only canonical second-resolution UTC timestamps."""

    if UTC_TIMESTAMP_PATTERN.fullmatch(value) is None:
        raise ValueError("Timestamp must be UTC in YYYY-MM-DDTHH:MM:SSZ form.")
    try:
        datetime.fromisoformat(value).astimezone(UTC)
    except ValueError as error:
        raise ValueError("Timestamp is not a real UTC calendar instant.") from error
    return value


def validate_component_version(value: str) -> str:
    """Require a stable name/revision component identifier."""

    if VERSION_PATTERN.fullmatch(value) is None:
        raise ValueError("Component version must be lower_snake-or-kebab-name/positive-integer.")
    return value


def finite_or_none(value: float | None) -> float | None:
    """JSON contracts never allow NaN or infinity to stand in for missing data."""

    if value is not None and not math.isfinite(value):
        raise ValueError("Numeric values must be finite; use explicit missing provenance instead.")
    return value


def ensure_unique_field_codes(values: tuple[CanonicalFieldValue, ...]) -> None:
    """A canonical owner has at most one value for each catalogue field."""

    codes = [item.field_code for item in values]
    if len(codes) != len(set(codes)):
        raise ValueError("Canonical field codes must be unique per owner.")


def ensure_json_compatible(value: Any) -> None:
    """Reject opaque adapter payloads that cannot receive deterministic JSON hashing."""

    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        finite_or_none(value)
        return
    if isinstance(value, list):
        for item in value:
            ensure_json_compatible(item)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            ensure_json_compatible(item)
        return
    raise ValueError("Adapter request payload must contain only JSON-compatible values.")
