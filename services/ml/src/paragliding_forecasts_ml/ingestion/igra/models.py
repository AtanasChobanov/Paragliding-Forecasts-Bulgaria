"""Strict durable contracts for the artifact-first NOAA IGRA boundary."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import ConfigDict, Field, field_validator, model_validator

from ..atmosphere.contracts import (
    SHA256_PATTERN,
    UUID_V4_PATTERN,
    ArtifactReference,
    AtmosphericContract,
    ensure_json_compatible,
    finite_or_none,
    validate_component_version,
    validate_utc_timestamp,
)
from .versions import IGRA_SOURCE_ID, IGRA_STATION_ID

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HHMM_RE = re.compile(r"^\d{4}$")


class IgraContract(AtmosphericContract):
    """All contracts are strict, frozen, JSON-safe and observation-specific."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class IgraRemoteObject(IgraContract):
    """One provider object after its HEAD response passed the source policy."""

    artifact_key: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=1)
    final_url: str = Field(min_length=1)
    safe_basename: str = Field(min_length=1, max_length=180)
    media_class: Literal["zip", "text"]
    expected_member_name: str | None = None
    head_status: int = Field(ge=200, lt=400)
    content_length: int = Field(gt=0)
    etag: str | None = None
    last_modified: str | None = None

    @field_validator("url", "final_url")
    @classmethod
    def https_urls(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("IGRA remote URLs must be absolute HTTPS URLs.")
        return value

    @field_validator("safe_basename")
    @classmethod
    def safe_basename_must_be_safe(cls, value: str) -> str:
        if value in {".", ".."} or "/" in value or "\\" in value:
            raise ValueError("Remote basename must be one safe filename.")
        return value

    @model_validator(mode="after")
    def version_and_member_shape(self) -> IgraRemoteObject:
        if self.etag is None and self.last_modified is None:
            raise ValueError("HEAD inventory requires ETag or Last-Modified evidence.")
        if (self.media_class == "zip") != (self.expected_member_name is not None):
            raise ValueError("Only ZIP objects declare one expected member name.")
        return self


class IgraRequestPlan(IgraContract):
    """Immutable selection, source-policy, and cap authorization for one run."""

    request_plan_schema_version: Literal[1] = 1
    run_key: str
    source_id: Literal["noaa_igra_bum00015614"] = IGRA_SOURCE_ID
    station_id: Literal["BUM00015614"] = IGRA_STATION_ID
    source_kind: Literal["observation"] = "observation"
    request_purpose: Literal["observational_validation"] = "observational_validation"
    dates_utc: tuple[str, ...] = Field(min_length=1, max_length=366)
    nominal_hours: tuple[int, ...] = ()
    requested_archive_mode: Literal["auto", "recent", "period-of-record"]
    resolved_archive_mode: Literal["recent", "period-of-record"]
    maximum_total_mib: int = Field(gt=0)
    source_policy_version: str
    source_policy_sha256: str
    component_versions: dict[str, str] = Field(min_length=1)
    created_at_utc: str
    remote_objects: tuple[IgraRemoteObject, ...] = Field(min_length=5, max_length=5)

    @field_validator("run_key")
    @classmethod
    def uuid_v4(cls, value: str) -> str:
        if UUID_V4_PATTERN.fullmatch(value) is None:
            raise ValueError("run_key must be a lowercase UUID v4.")
        return value

    @field_validator("dates_utc")
    @classmethod
    def sorted_dates(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)) or tuple(sorted(values)) != values:
            raise ValueError("IGRA dates must be sorted and unique.")
        for value in values:
            if _DATE_RE.fullmatch(value) is None:
                raise ValueError("IGRA dates must be YYYY-MM-DD.")
            try:
                date.fromisoformat(value)
            except ValueError as error:
                raise ValueError("IGRA date is not a valid calendar date.") from error
        return values

    @field_validator("nominal_hours")
    @classmethod
    def sorted_hours(cls, values: tuple[int, ...]) -> tuple[int, ...]:
        if any(value < 0 or value > 23 for value in values):
            raise ValueError("IGRA nominal hours must be from 0 through 23.")
        if len(values) != len(set(values)) or tuple(sorted(values)) != values:
            raise ValueError("IGRA nominal hours must be sorted and unique.")
        return values

    @field_validator("source_policy_version")
    @classmethod
    def source_policy_versioned(cls, value: str) -> str:
        return validate_component_version(value)

    @field_validator("source_policy_sha256")
    @classmethod
    def source_policy_hash(cls, value: str) -> str:
        if SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("source_policy_sha256 must be a SHA-256.")
        return value

    @field_validator("created_at_utc")
    @classmethod
    def created_utc(cls, value: str) -> str:
        return validate_utc_timestamp(value)

    @model_validator(mode="after")
    def complete_plan(self) -> IgraRequestPlan:
        if len({item.artifact_key for item in self.remote_objects}) != 5:
            raise ValueError("The request plan must contain five distinct remote objects.")
        for version in self.component_versions.values():
            validate_component_version(version)
        ensure_json_compatible(self.component_versions)
        return self


class IgraInventoryResult(IgraContract):
    """Pure inventory result; no run key and no local creation side effect."""

    inventory_result_schema_version: Literal[1] = 1
    station_id: Literal["BUM00015614"] = IGRA_STATION_ID
    requested_dates_utc: tuple[str, ...] = Field(min_length=1)
    requested_nominal_hours: tuple[int, ...] = ()
    resolved_archive_mode: Literal["recent", "period-of-record"]
    remote_objects: tuple[IgraRemoteObject, ...] = Field(min_length=5, max_length=5)
    total_compressed_bytes: int = Field(gt=0)
    minimum_required_mib: int = Field(gt=0)
    warnings: tuple[str, ...] = ()


class IgraSourceSnapshotManifest(IgraContract):
    """Shared provider snapshot: content-addressed and independent of selection."""

    source_snapshot_manifest_schema_version: Literal[1] = 1
    source_snapshot_id: str
    source_id: Literal["noaa_igra_bum00015614"] = IGRA_SOURCE_ID
    station_id: Literal["BUM00015614"] = IGRA_STATION_ID
    archive_mode: Literal["recent", "period-of-record"]
    source_policy_version: str
    source_policy_sha256: str
    collector_version: str
    artifacts: tuple[ArtifactReference, ...] = Field(min_length=5, max_length=5)
    remote_objects: tuple[IgraRemoteObject, ...] = Field(min_length=5, max_length=5)
    retrieved_started_at_utc: str
    retrieved_completed_at_utc: str
    citation: str = Field(min_length=1)

    @field_validator("source_snapshot_id", "source_policy_sha256")
    @classmethod
    def sha256(cls, value: str) -> str:
        if SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("Snapshot identities must be SHA-256 values.")
        return value

    @field_validator("source_policy_version", "collector_version")
    @classmethod
    def versioned(cls, value: str) -> str:
        return validate_component_version(value)

    @field_validator("retrieved_started_at_utc", "retrieved_completed_at_utc")
    @classmethod
    def retrieval_utc(cls, value: str) -> str:
        return validate_utc_timestamp(value)

    @model_validator(mode="after")
    def snapshot_shape(self) -> IgraSourceSnapshotManifest:
        if self.retrieved_completed_at_utc < self.retrieved_started_at_utc:
            raise ValueError("Snapshot completion cannot precede retrieval start.")
        if len({item.artifact_key for item in self.artifacts}) != 5:
            raise ValueError("Snapshot artifacts must have distinct keys.")
        return self


class NativeIgraLevel(IgraContract):
    """One raw fixed-width level. Sentinels remain native integers until normalization."""

    native_level_schema_version: Literal[1] = 1
    sounding_record_sha256: str
    ordinal: int = Field(ge=1)
    level_type_major: str = Field(min_length=1, max_length=1)
    level_type_minor: str = Field(min_length=1, max_length=1)
    elapsed_time: int | None = None
    pressure: int | None = None
    pressure_flag: str = Field(max_length=1)
    geopotential_height: int | None = None
    geopotential_height_flag: str = Field(max_length=1)
    temperature: int | None = None
    temperature_flag: str = Field(max_length=1)
    relative_humidity: int | None = None
    dew_point_depression: int | None = None
    wind_direction: int | None = None
    wind_speed: int | None = None
    raw_artifact_key: str = Field(min_length=1)
    line_number: int = Field(ge=1)

    @field_validator("sounding_record_sha256")
    @classmethod
    def record_hash(cls, value: str) -> str:
        if SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("Record hash must be a SHA-256.")
        return value


class NativeIgraSounding(IgraContract):
    """One selected raw header plus exactly NUMLEV native levels."""

    native_sounding_schema_version: Literal[1] = 1
    station_id: str = Field(min_length=1)
    nominal_date_utc: str
    nominal_hour_utc: int | None = Field(default=None, ge=0, le=23)
    release_time_hhmm: str | None = None
    level_count: int = Field(ge=0)
    pressure_source: str = Field(max_length=8)
    nonpressure_source: str = Field(max_length=8)
    latitude_native: int | None = None
    longitude_native: int | None = None
    record_ordinal: int = Field(ge=1)
    record_sha256: str
    raw_artifact_key: str = Field(min_length=1)
    header_line_number: int = Field(ge=1)
    levels: tuple[NativeIgraLevel, ...]

    @field_validator("nominal_date_utc")
    @classmethod
    def nominal_date(cls, value: str) -> str:
        if _DATE_RE.fullmatch(value) is None:
            raise ValueError("Nominal date must be YYYY-MM-DD.")
        date.fromisoformat(value)
        return value

    @field_validator("release_time_hhmm")
    @classmethod
    def native_release(cls, value: str | None) -> str | None:
        if value is not None and _HHMM_RE.fullmatch(value) is None:
            raise ValueError("Native release time must preserve exactly four digits.")
        return value

    @field_validator("record_sha256")
    @classmethod
    def native_record_hash(cls, value: str) -> str:
        if SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("Record hash must be a SHA-256.")
        return value

    @model_validator(mode="after")
    def exact_level_count(self) -> NativeIgraSounding:
        if self.level_count != len(self.levels):
            raise ValueError("NUMLEV must equal the number of following level rows.")
        return self


class CanonicalSounding(IgraContract):
    """Normalized observation identity, coordinates, timing and profile summary."""

    canonical_sounding_schema_version: Literal[1] = 1
    sounding_key: str = Field(min_length=1)
    source_snapshot_id: str
    record_sha256: str
    station_id: str = Field(min_length=1)
    nominal_at_utc: str | None = None
    nominal_date_utc: str
    nominal_hour_utc: int | None = Field(default=None, ge=0, le=23)
    release_at_utc: str | None = None
    release_precision: Literal["missing", "hour", "minute"]
    release_delta_seconds: int | None = None
    latitude_deg: float | None = None
    longitude_deg: float | None = None
    inventory_latitude_deg: float | None = None
    inventory_longitude_deg: float | None = None
    thermodynamic_usable: bool
    wind_usable: bool

    @field_validator("source_snapshot_id", "record_sha256")
    @classmethod
    def canonical_hash(cls, value: str) -> str:
        if SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("Canonical source identities must be SHA-256.")
        return value

    @field_validator("nominal_at_utc", "release_at_utc")
    @classmethod
    def optional_utc(cls, value: str | None) -> str | None:
        return None if value is None else validate_utc_timestamp(value)

    @field_validator(
        "latitude_deg", "longitude_deg", "inventory_latitude_deg", "inventory_longitude_deg"
    )
    @classmethod
    def finite_coordinate(cls, value: float | None) -> float | None:
        return finite_or_none(value)


class CanonicalSoundingLevel(IgraContract):
    """Flattened normalized level; native order is preserved by ordinal."""

    canonical_sounding_level_schema_version: Literal[1] = 1
    sounding_key: str = Field(min_length=1)
    ordinal: int = Field(ge=1)
    pressure_pa: int | None = Field(default=None, gt=0)
    geopotential_height_msl_m: float | None = None
    temperature_k: float | None = None
    dew_point_k: float | None = None
    relative_humidity_percent: float | None = None
    wind_direction_degrees: float | None = None
    wind_speed_m_s: float | None = None
    u_wind_m_s: float | None = None
    v_wind_m_s: float | None = None
    elapsed_seconds: int | None = Field(default=None, ge=0)
    provenance: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @field_validator(
        "geopotential_height_msl_m",
        "temperature_k",
        "dew_point_k",
        "relative_humidity_percent",
        "wind_direction_degrees",
        "wind_speed_m_s",
        "u_wind_m_s",
        "v_wind_m_s",
    )
    @classmethod
    def finite_numbers(cls, value: float | None) -> float | None:
        return finite_or_none(value)


class IgraStageManifest(IgraContract):
    """Hash-verified immutable boundary for one run-specific stage."""

    stage_manifest_schema_version: Literal[1] = 1
    run_key: str
    stage: Literal["source_snapshot", "parser", "normalizer", "validator"]
    producer_version: str
    input_fingerprint_sha256: str
    inputs: tuple[ArtifactReference, ...] = Field(min_length=1)
    outputs: tuple[ArtifactReference, ...] = Field(min_length=1)
    disposition: Literal["complete", "quarantined"]
    counts: dict[str, int] = Field(default_factory=dict)
    configuration: dict[str, Any] = Field(default_factory=dict)
    completed_at_utc: str

    @field_validator("run_key")
    @classmethod
    def manifest_uuid(cls, value: str) -> str:
        if UUID_V4_PATTERN.fullmatch(value) is None:
            raise ValueError("run_key must be a lowercase UUID v4.")
        return value

    @field_validator("producer_version")
    @classmethod
    def producer_version(cls, value: str) -> str:
        return validate_component_version(value)

    @field_validator("input_fingerprint_sha256")
    @classmethod
    def stage_hash(cls, value: str) -> str:
        if SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("Stage fingerprint must be a SHA-256.")
        return value

    @field_validator("completed_at_utc")
    @classmethod
    def complete_utc(cls, value: str) -> str:
        return validate_utc_timestamp(value)

    @model_validator(mode="after")
    def output_contract(self) -> IgraStageManifest:
        if len({item.artifact_key for item in self.outputs}) != len(self.outputs):
            raise ValueError("Stage output keys must be unique.")
        if any(value < 0 for value in self.counts.values()):
            raise ValueError("Stage counts cannot be negative.")
        ensure_json_compatible(self.configuration)
        return self


class IgraRunStateEvent(IgraContract):
    """One immutable, hash-linked run transition."""

    state_event_schema_version: Literal[1] = 1
    run_key: str
    sequence: int = Field(ge=1)
    invocation_mode: Literal["fresh", "resume"]
    stage: Literal["planned", "source_snapshot_complete", "parsed", "normalized", "validated"]
    disposition: Literal["ready", "complete", "quarantined", "failed"]
    occurred_at_utc: str
    previous_event_sha256: str | None = None
    evidence: ArtifactReference | None = None
    supersedes_sequence: int | None = Field(default=None, ge=1)
    detail: str | None = None

    @field_validator("run_key")
    @classmethod
    def state_uuid(cls, value: str) -> str:
        if UUID_V4_PATTERN.fullmatch(value) is None:
            raise ValueError("run_key must be a lowercase UUID v4.")
        return value

    @field_validator("occurred_at_utc")
    @classmethod
    def occurred_utc(cls, value: str) -> str:
        return validate_utc_timestamp(value)

    @field_validator("previous_event_sha256")
    @classmethod
    def predecessor_hash(cls, value: str | None) -> str | None:
        if value is not None and SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("State predecessor must be a SHA-256.")
        return value

    @model_validator(mode="after")
    def state_contract(self) -> IgraRunStateEvent:
        if self.stage == "planned" and self.disposition != "ready":
            raise ValueError("The first planned stage is always ready.")
        if self.disposition == "quarantined" and self.stage != "validated":
            raise ValueError("Only validation can quarantine an IGRA run.")
        return self


class NativeIgraDerivedLevel(IgraContract):
    """Every documented derived pressure-level field, retained before unit conversion."""

    native_derived_level_schema_version: Literal[1] = 1
    derived_record_sha256: str
    ordinal: int = Field(ge=1)
    values: dict[str, int | None] = Field(min_length=1)
    raw_artifact_key: str = Field(min_length=1)
    line_number: int = Field(ge=1)

    @field_validator("derived_record_sha256")
    @classmethod
    def derived_hash(cls, value: str) -> str:
        if SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("Derived record hash must be a SHA-256.")
        return value


class NativeIgraDerivedSounding(IgraContract):
    """Derived header parameters and independent NUMLEV sequence for one nominal observation."""

    native_derived_sounding_schema_version: Literal[1] = 1
    station_id: str = Field(min_length=1)
    nominal_date_utc: str
    nominal_hour_utc: int | None = Field(default=None, ge=0, le=23)
    release_time_hhmm: str | None = None
    level_count: int = Field(ge=0)
    parameters: dict[str, int | None] = Field(min_length=1)
    record_ordinal: int = Field(ge=1)
    record_sha256: str
    raw_artifact_key: str = Field(min_length=1)
    header_line_number: int = Field(ge=1)
    levels: tuple[NativeIgraDerivedLevel, ...]

    @field_validator("nominal_date_utc")
    @classmethod
    def derived_nominal_date(cls, value: str) -> str:
        if _DATE_RE.fullmatch(value) is None:
            raise ValueError("Derived nominal date must be YYYY-MM-DD.")
        date.fromisoformat(value)
        return value

    @field_validator("release_time_hhmm")
    @classmethod
    def derived_release(cls, value: str | None) -> str | None:
        if value is not None and _HHMM_RE.fullmatch(value) is None:
            raise ValueError("Derived release time must preserve exactly four digits.")
        return value

    @field_validator("record_sha256")
    @classmethod
    def derived_record_hash(cls, value: str) -> str:
        if SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("Derived record hash must be a SHA-256.")
        return value

    @model_validator(mode="after")
    def exact_derived_level_count(self) -> NativeIgraDerivedSounding:
        if self.level_count != len(self.levels):
            raise ValueError("Derived NUMLEV must match its following rows.")
        return self


class ProviderDerivedSoundingParameters(IgraContract):
    """Normalized NOAA-derived header parameters; they never overwrite raw observations."""

    provider_derived_parameters_schema_version: Literal[1] = 1
    sounding_key: str = Field(min_length=1)
    native_record_sha256: str
    values: dict[str, float | int | None] = Field(min_length=1)
    provenance: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ProviderDerivedSoundingLevel(IgraContract):
    """Normalized NOAA-derived pressure level, kept as a distinct provider variant."""

    provider_derived_level_schema_version: Literal[1] = 1
    sounding_key: str = Field(min_length=1)
    ordinal: int = Field(ge=1)
    values: dict[str, float | int | None] = Field(min_length=1)
    provenance: dict[str, dict[str, Any]] = Field(default_factory=dict)
