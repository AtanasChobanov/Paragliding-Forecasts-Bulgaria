"""Strict v2 contracts for source-neutral S07 weather feature artifacts."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ...atmosphere.catalogue import CatalogueError, load_catalogue
from ...atmosphere.contracts import (
    LOCAL_DATE_PATTERN,
    SHA256_PATTERN,
    UUID_V4_PATTERN,
    AtmosphericContract,
    QualityState,
    validate_component_version,
    validate_utc_timestamp,
)

FEATURE_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
MISSING_REASON_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")




class FeatureValue(AtmosphericContract):
    """One named S07 output with catalogue identity and derivation evidence."""

    feature_value_schema_version: Literal[2] = 2
    feature_key: str
    field_code: str
    canonical_unit: str = Field(min_length=1)
    variant: str | None = Field(default=None, min_length=1)
    statistic: str | None = Field(default=None, min_length=1)
    canonical_value: float | None = None
    quality_state: QualityState
    missing_reason: str | None = None
    derivation_method: str
    derivation_version: str
    input_field_codes: tuple[str, ...] = Field(min_length=1)

    @field_validator("feature_key")
    @classmethod
    def feature_key_must_be_database_aligned(cls, value: str) -> str:
        if FEATURE_KEY_PATTERN.fullmatch(value) is None:
            raise ValueError("feature_key must be lower_snake_case.")
        return value

    @field_validator("field_code")
    @classmethod
    def field_code_must_be_catalogued(cls, value: str) -> str:
        try:
            return load_catalogue().validate_field_code(value)
        except CatalogueError as error:
            raise ValueError(str(error)) from error

    @field_validator("canonical_value")
    @classmethod
    def feature_value_must_be_finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("canonical_value must be finite when supplied.")
        return value

    @field_validator("quality_state")
    @classmethod
    def feature_quality_must_be_catalogued(cls, value: QualityState) -> QualityState:
        try:
            return load_catalogue().validate_quality_state(value)
        except CatalogueError as error:
            raise ValueError(str(error)) from error

    @field_validator("missing_reason")
    @classmethod
    def missing_reason_must_be_machine_readable(cls, value: str | None) -> str | None:
        if value is not None and MISSING_REASON_PATTERN.fullmatch(value) is None:
            raise ValueError("missing_reason must be lower_snake_case.")
        return value

    @field_validator("derivation_method", "derivation_version")
    @classmethod
    def derivation_identity_must_be_versioned(cls, value: str) -> str:
        return validate_component_version(value)

    @field_validator("input_field_codes")
    @classmethod
    def input_field_codes_must_be_catalogued_and_unique(
        cls, values: tuple[str, ...]
    ) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("input_field_codes must be unique.")
        catalogue = load_catalogue()
        try:
            return tuple(catalogue.validate_field_code(value) for value in values)
        except CatalogueError as error:
            raise ValueError(str(error)) from error

    @model_validator(mode="after")
    def value_state_and_unit_must_match(self) -> FeatureValue:
        if self.canonical_unit != load_catalogue().field_unit(self.field_code):
            raise ValueError("canonical_unit must match the T-017 catalogue field unit.")
        absent_states = {"missing", "sentinel_missing", "invalid_payload", "unsupported"}
        if self.quality_state in absent_states:
            if self.canonical_value is not None:
                raise ValueError("Missing or unsupported feature values must be null.")
            if self.missing_reason is None:
                raise ValueError("Missing or unsupported feature values require missing_reason.")
        elif self.canonical_value is None:
            raise ValueError("Available feature values must be finite numbers.")
        elif self.missing_reason is not None:
            raise ValueError("Available feature values cannot carry missing_reason.")
        return self


class FeatureLayer(AtmosphericContract):
    """One repeatable AGL layer; field identity is (bounds, feature_key)."""

    layer_base_agl_m: float = Field(ge=0)
    layer_top_agl_m: float = Field(gt=0)
    fields: tuple[FeatureValue, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def layer_bounds_and_keys_must_be_unique(self) -> FeatureLayer:
        if not self.layer_top_agl_m > self.layer_base_agl_m:
            raise ValueError("layer_top_agl_m must exceed layer_base_agl_m.")
        _ensure_unique_feature_keys(self.fields)
        return self


class MissingFeatureLocator(AtmosphericContract):
    """An ordered missing-mask entry without inventing a layer-name prefix."""

    feature_key: str
    layer_base_agl_m: float | None = Field(default=None, ge=0)
    layer_top_agl_m: float | None = Field(default=None, gt=0)
    missing_reason: str

    @field_validator("feature_key")
    @classmethod
    def locator_key_must_be_database_aligned(cls, value: str) -> str:
        if FEATURE_KEY_PATTERN.fullmatch(value) is None:
            raise ValueError("feature_key must be lower_snake_case.")
        return value

    @field_validator("missing_reason")
    @classmethod
    def locator_reason_must_be_machine_readable(cls, value: str) -> str:
        if MISSING_REASON_PATTERN.fullmatch(value) is None:
            raise ValueError("missing_reason must be lower_snake_case.")
        return value

    @model_validator(mode="after")
    def locator_bounds_must_be_paired(self) -> MissingFeatureLocator:
        if (self.layer_base_agl_m is None) != (self.layer_top_agl_m is None):
            raise ValueError("Missing feature layer bounds must be supplied together.")
        if (
            self.layer_base_agl_m is not None
            and self.layer_top_agl_m is not None
            and self.layer_top_agl_m <= self.layer_base_agl_m
        ):
            raise ValueError("Missing feature layer bounds must be strictly increasing.")
        return self


class FeatureQualitySummary(AtmosphericContract):
    """Counts every emitted feature value by explicit quality state."""

    total_features: int = Field(ge=1)
    quality_counts: dict[QualityState, int] = Field(min_length=1)

    @model_validator(mode="after")
    def counts_must_be_non_negative_and_totalled(self) -> FeatureQualitySummary:
        if any(count < 0 for count in self.quality_counts.values()):
            raise ValueError("quality_counts cannot be negative.")
        if sum(self.quality_counts.values()) != self.total_features:
            raise ValueError("quality_counts must total total_features.")
        return self


class HourlyFeatureSnapshot(AtmosphericContract):
    """One deterministic S07 v2 feature view of a validated hourly site sample."""

    hourly_feature_snapshot_schema_version: Literal[2] = 2
    run_key: str
    sample_identity_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    site_id: int = Field(gt=0)
    point_footprint_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    neighbourhood_footprint_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    valid_at_utc: str
    valid_local_date: str
    feature_contract_version: str
    input_fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fields: tuple[FeatureValue, ...] = Field(min_length=1)
    missing_features: tuple[MissingFeatureLocator, ...] = ()
    quality_summary: FeatureQualitySummary

    @field_validator("run_key")
    @classmethod
    def run_key_must_be_uuid_v4(cls, value: str) -> str:
        if UUID_V4_PATTERN.fullmatch(value) is None:
            raise ValueError("run_key must be a lowercase UUID v4.")
        return value

    @field_validator("valid_at_utc")
    @classmethod
    def valid_time_must_be_utc(cls, value: str) -> str:
        return validate_utc_timestamp(value)

    @field_validator("valid_local_date")
    @classmethod
    def local_date_must_be_iso(cls, value: str) -> str:
        if LOCAL_DATE_PATTERN.fullmatch(value) is None:
            raise ValueError("valid_local_date must be YYYY-MM-DD.")
        return value

    @field_validator("feature_contract_version")
    @classmethod
    def contract_version_must_be_versioned(cls, value: str) -> str:
        return validate_component_version(value)

    @model_validator(mode="after")
    def hourly_feature_shape_must_be_consistent(self) -> HourlyFeatureSnapshot:
        _ensure_unique_feature_keys(self.fields)
        _validate_mask_and_summary(self.fields, (), self.missing_features, self.quality_summary)
        return self


class DailyFeatureSnapshot(AtmosphericContract):
    """One deterministic site/local-day S07 v2 feature boundary."""

    daily_feature_snapshot_schema_version: Literal[2] = 2
    run_key: str
    site_id: int = Field(gt=0)
    point_footprint_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    neighbourhood_footprint_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_product_key: str = Field(min_length=1)
    local_date: str
    feature_contract_version: str
    input_fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_sample_identity_keys: tuple[str, ...] = Field(min_length=1)
    daily_fields: tuple[FeatureValue, ...] = Field(min_length=1)
    profile_layers: tuple[FeatureLayer, ...] = Field(min_length=1)
    missing_features: tuple[MissingFeatureLocator, ...] = ()
    quality_summary: FeatureQualitySummary

    @field_validator("run_key")
    @classmethod
    def daily_run_key_must_be_uuid_v4(cls, value: str) -> str:
        if UUID_V4_PATTERN.fullmatch(value) is None:
            raise ValueError("run_key must be a lowercase UUID v4.")
        return value

    @field_validator("local_date")
    @classmethod
    def daily_local_date_must_be_iso(cls, value: str) -> str:
        if LOCAL_DATE_PATTERN.fullmatch(value) is None:
            raise ValueError("local_date must be YYYY-MM-DD.")
        return value

    @field_validator("feature_contract_version")
    @classmethod
    def daily_contract_version_must_be_versioned(cls, value: str) -> str:
        return validate_component_version(value)

    @field_validator("input_sample_identity_keys")
    @classmethod
    def input_samples_must_be_unique_hashes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)) or any(
            SHA256_PATTERN.fullmatch(value) is None for value in values
        ):
            raise ValueError("input_sample_identity_keys must be unique SHA-256 values.")
        return values

    @model_validator(mode="after")
    def daily_feature_shape_must_be_consistent(self) -> DailyFeatureSnapshot:
        _ensure_unique_feature_keys(self.daily_fields)
        layer_identities = [
            (layer.layer_base_agl_m, layer.layer_top_agl_m) for layer in self.profile_layers
        ]
        if len(layer_identities) != len(set(layer_identities)):
            raise ValueError("profile_layers must have unique AGL bound identities.")
        _validate_mask_and_summary(
            self.daily_fields, self.profile_layers, self.missing_features, self.quality_summary
        )
        return self


def _ensure_unique_feature_keys(values: tuple[FeatureValue, ...]) -> None:
    keys = [value.feature_key for value in values]
    if len(keys) != len(set(keys)):
        raise ValueError("Feature keys must be unique within one feature scope.")


def _validate_mask_and_summary(
    daily_fields: tuple[FeatureValue, ...],
    profile_layers: tuple[FeatureLayer, ...],
    missing_features: tuple[MissingFeatureLocator, ...],
    quality_summary: FeatureQualitySummary,
) -> None:
    all_values = [*daily_fields, *(value for layer in profile_layers for value in layer.fields)]
    expected_counts = Counter(value.quality_state for value in all_values)
    if quality_summary.total_features != len(all_values) or quality_summary.quality_counts != dict(
        expected_counts
    ):
        raise ValueError("quality_summary must exactly describe all emitted feature values.")
    missing_values: dict[tuple[str, float | None, float | None], FeatureValue] = {
        (value.feature_key, None, None): value
        for value in daily_fields
        if value.canonical_value is None
    }
    for layer in profile_layers:
        for value in layer.fields:
            if value.canonical_value is None:
                missing_values[
                    (value.feature_key, layer.layer_base_agl_m, layer.layer_top_agl_m)
                ] = value
    locators = [
        (item.feature_key, item.layer_base_agl_m, item.layer_top_agl_m) for item in missing_features
    ]
    if len(locators) != len(set(locators)):
        raise ValueError("missing_features must not repeat a feature identity.")
    if set(locators) != set(missing_values):
        raise ValueError("missing_features must locate every and only null feature value.")
    for locator in missing_features:
        value = missing_values[
            (locator.feature_key, locator.layer_base_agl_m, locator.layer_top_agl_m)
        ]
        if locator.missing_reason != value.missing_reason:
            raise ValueError("Missing feature locator reason must match its feature value.")
