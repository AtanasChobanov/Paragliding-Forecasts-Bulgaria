"""Strict GFS request and immutable collection-evidence contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from ..atmosphere.contracts import ArtifactReference, AtmosphericContract, validate_utc_timestamp

GFS_SOURCE_ID = "noaa_gfs_0p25_aws_grib2"
GFS_BUCKET_URL = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
GFS_COLLECTOR_VERSION = "gfs-collector/2"


class GfsRequest(AtmosphericContract):
    """Validated operator intent before a run is resolved."""

    run_key: str
    request_purpose: Literal["historical_forecast", "operational_forecast"]
    valid_at_utc: tuple[str, ...] = Field(min_length=1)
    explicit_run_at_utc: str | None = None
    newest_complete_before_utc: str | None = None
    maximum_cycles_back: int = Field(default=8, ge=1, le=16)
    maximum_range_bytes: int = Field(default=8 * 1024 * 1024, ge=1024)
    maximum_total_bytes: int = Field(default=128 * 1024 * 1024, ge=1024)

    @field_validator("valid_at_utc", "explicit_run_at_utc", "newest_complete_before_utc")
    @classmethod
    def utc_times_must_be_valid(cls, value: tuple[str, ...] | str | None):
        if value is None:
            return value
        if isinstance(value, tuple):
            if len(value) != len(set(value)):
                raise ValueError("GFS valid times must be unique.")
            return tuple(validate_utc_timestamp(item) for item in value)
        return validate_utc_timestamp(value)

    @field_validator("run_key")
    @classmethod
    def run_key_must_be_present(cls, value: str) -> str:
        if not value:
            raise ValueError("GFS run key is required.")
        return value

    def selection_mode(self) -> Literal["explicit", "newest_complete_before"]:
        if (self.explicit_run_at_utc is None) == (self.newest_complete_before_utc is None):
            raise ValueError("Supply exactly one GFS run selection mode.")
        return "explicit" if self.explicit_run_at_utc is not None else "newest_complete_before"


class GfsPlannedRange(AtmosphericContract):
    """One exact selected byte range and its native index identity."""

    lead_hours: int = Field(ge=0, le=384)
    valid_at_utc: str
    grib_url: str
    index_url: str
    index_sha256: str
    object_content_length: int = Field(gt=0)
    object_etag: str | None = None
    object_last_modified_utc: str
    byte_start: int = Field(ge=0)
    byte_end: int = Field(ge=0)
    selector_keys: tuple[str, ...] = Field(min_length=1)
    message_numbers: tuple[int, ...] = Field(min_length=1)

    forecast_descriptors: tuple[str, ...] = Field(min_length=1)

    @field_validator("valid_at_utc", "object_last_modified_utc")
    @classmethod
    def timestamps_must_be_utc(cls, value: str) -> str:
        return validate_utc_timestamp(value)


class GfsResolvedPlan(AtmosphericContract):
    """Source-owned resolved GFS plan embedded in S02 RequestPlan.adapter_request."""

    gfs_request_schema_version: Literal[1] = 1
    selection_mode: Literal["explicit", "newest_complete_before"]
    resolved_run_at_utc: str
    available_at_utc: str
    source_product_key: str
    selector_set_version: Literal[2] = 2
    spatial_footprint: Literal["global_regular_latlon_0p25"] = "global_regular_latlon_0p25"
    ranges: tuple[GfsPlannedRange, ...] = Field(min_length=1)
    licence_reference: str = "https://registry.opendata.aws/noaa-gfs-bdp-pds/"
    attribution_text: str = (
        "NOAA Global Forecast System (GFS), accessed from NOAA Open Data on AWS."
    )

    @field_validator("resolved_run_at_utc", "available_at_utc")
    @classmethod
    def plan_timestamps_must_be_utc(cls, value: str) -> str:
        return validate_utc_timestamp(value)


class GfsArtifactEvidence(AtmosphericContract):
    """Per-artifact source URL/range/provenance retained outside generic manifests."""

    artifact: ArtifactReference
    source_url: str = Field(min_length=1)
    byte_start: int | None = Field(default=None, ge=0)
    byte_end: int | None = Field(default=None, ge=0)
    lead_hours: int | None = Field(default=None, ge=0, le=384)
    valid_at_utc: str | None = None
    message_numbers: tuple[int, ...] = ()
    selector_keys: tuple[str, ...] = ()
    etag: str | None = None
    last_modified_utc: str | None = None
    forecast_descriptors: tuple[str, ...] = ()

    @field_validator("valid_at_utc", "last_modified_utc")
    @classmethod
    def evidence_timestamps_must_be_utc(cls, value: str | None) -> str | None:
        return None if value is None else validate_utc_timestamp(value)


class GfsCollectionRecord(AtmosphericContract):
    """Immutable GFS-specific evidence required by S04 parsing and audit."""

    gfs_collection_schema_version: Literal[1] = 1
    run_key: str
    collector_version: str = GFS_COLLECTOR_VERSION
    source_id: Literal["noaa_gfs_0p25_aws_grib2"] = GFS_SOURCE_ID
    source_product_key: str
    run_at_utc: str
    available_at_utc: str
    retrieved_at_utc: str
    licence_reference: str
    attribution_text: str
    outcome: Literal["complete", "partial", "failed"]
    failure_kind: str | None = None
    artifacts: tuple[GfsArtifactEvidence, ...] = Field(min_length=1)

    @field_validator("run_at_utc", "available_at_utc", "retrieved_at_utc")
    @classmethod
    def collection_timestamps_must_be_utc(cls, value: str) -> str:
        return validate_utc_timestamp(value)
