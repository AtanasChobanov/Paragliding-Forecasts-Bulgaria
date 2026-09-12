"""Strict contracts for source-neutral weather SQLite persistence."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from ..atmosphere.contracts import (
    SHA256_PATTERN,
    UUID_V4_PATTERN,
    ArtifactReference,
    AtmosphericContract,
    validate_component_version,
    validate_utc_timestamp,
)
from .serialization import sha256_bytes

WEATHER_PERSISTENCE_VERSION = "weather-persistence/1"


WeatherSourceId = Literal["gfs", "era5"]


class _WeatherUsagePolicyBase(AtmosphericContract):
    """Explicit local source authority, supplied like XCContest's import policy."""

    permission_basis: str = Field(min_length=1)
    permission_reference: str = Field(min_length=1)
    model_training_allowed: bool
    operational_use_allowed: bool

    @field_validator("permission_basis", "permission_reference")
    @classmethod
    def permission_text_must_be_present(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Weather usage-policy permission text must be non-empty.")
        return normalized


class GfsUsagePolicy(_WeatherUsagePolicyBase):
    gfs_usage_policy_schema_version: Literal[1] = 1


class Era5UsagePolicy(_WeatherUsagePolicyBase):
    era5_usage_policy_schema_version: Literal[1] = 1


WeatherUsagePolicy = GfsUsagePolicy | Era5UsagePolicy


class WeatherPersistenceFailure(AtmosphericContract):
    """Immutable, secret-free evidence for one retryable persistence failure."""

    weather_persistence_failure_schema_version: Literal[1] = 1
    run_key: str
    failure_kind: Literal["prepare", "schema_preflight", "transaction", "conflict", "receipt"]
    error_summary: str = Field(min_length=1, max_length=400)
    feature_manifest: ArtifactReference | None = None
    persistence_input_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    occurred_at_utc: str

    @field_validator("run_key")
    @classmethod
    def run_key_must_be_uuid_v4(cls, value: str) -> str:
        if UUID_V4_PATTERN.fullmatch(value) is None:
            raise ValueError("run_key must be a lowercase UUID v4.")
        return value

    @field_validator("occurred_at_utc")
    @classmethod
    def occurred_at_must_be_utc(cls, value: str) -> str:
        return validate_utc_timestamp(value)


class WeatherPersistenceReceipt(AtmosphericContract):
    """Post-commit durable report for an atomically persisted weather run."""

    weather_persistence_receipt_schema_version: Literal[1] = 1
    run_key: str
    source_id: str
    source_product_key: str
    target_local_date: str
    database_identity: str = Field(pattern=r"^data/[a-z0-9_./-]+$")
    feature_manifest: ArtifactReference
    usage_policy_sha256: str = Field(pattern=SHA256_PATTERN)
    persistence_input_sha256: str = Field(pattern=SHA256_PATTERN)
    pipeline_version: str
    persistence_version: str = WEATHER_PERSISTENCE_VERSION
    disposition: Literal["inserted", "revalidated_no_op", "recovered_committed_write"]
    table_counts: Mapping[str, int]
    persisted_graph_sha256: str = Field(pattern=SHA256_PATTERN)
    missing_quality_count: int = Field(ge=0)
    unsupported_quality_count: int = Field(ge=0)
    missing_reason_counts: Mapping[str, int]
    below_terrain_evidence: Literal["artifact_only"] = "artifact_only"
    completed_at_utc: str

    @field_validator("run_key")
    @classmethod
    def run_key_must_be_uuid_v4(cls, value: str) -> str:
        if UUID_V4_PATTERN.fullmatch(value) is None:
            raise ValueError("run_key must be a lowercase UUID v4.")
        return value

    @field_validator("persistence_version")
    @classmethod
    def persistence_version_must_be_versioned(cls, value: str) -> str:
        return validate_component_version(value)

    @field_validator("pipeline_version")
    @classmethod
    def pipeline_version_must_be_a_versioned_tuple(cls, value: str) -> str:
        parts = value.split("|")
        if not parts or any(not part for part in parts):
            raise ValueError("pipeline_version must contain non-empty component versions.")
        for part in parts:
            validate_component_version(part)
        return value

    @field_validator("completed_at_utc")
    @classmethod
    def completed_at_must_be_utc(cls, value: str) -> str:
        return validate_utc_timestamp(value)

    @field_validator("table_counts", "missing_reason_counts")
    @classmethod
    def counts_must_be_non_negative(cls, value: Mapping[str, int]) -> Mapping[str, int]:
        if any(not isinstance(key, str) or not key or count < 0 for key, count in value.items()):
            raise ValueError(
                "Persistence receipt counts must have non-empty keys and non-negative values."
            )
        return value


def default_weather_usage_policy_path(source_id: WeatherSourceId, project_root: Path) -> Path:
    """Return the local source-bound policy path; policy contents remain operator-owned."""

    return project_root / "data" / "local" / f"{source_id}-usage-policy.json"


def load_weather_usage_policy(
    path: Path | None,
    *,
    expected_source_id: WeatherSourceId,
    project_root: Path | None = None,
) -> tuple[WeatherUsagePolicy, str]:
    """Load a strict source-specific local policy and return its immutable bytes hash."""

    model_type = {"gfs": GfsUsagePolicy, "era5": Era5UsagePolicy}.get(expected_source_id)
    if model_type is None:
        raise ValueError(
            f"No weather usage-policy contract exists for source {expected_source_id!r}."
        )
    resolved_path = path or default_weather_usage_policy_path(
        expected_source_id, (project_root or Path.cwd()).resolve()
    )
    try:
        payload = resolved_path.read_bytes()
    except OSError as error:
        raise ValueError(
            f"{expected_source_id} usage policy file cannot be read: {resolved_path.name}."
        ) from error
    try:
        policy = model_type.model_validate_json(payload, strict=True)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{expected_source_id} usage policy file is invalid or belongs to another source."
        ) from error
    return policy, sha256_bytes(payload)
