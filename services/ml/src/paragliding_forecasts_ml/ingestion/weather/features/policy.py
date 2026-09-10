"""Packaged, hash-pinned output policy for S07 v2 feature artifacts."""

from __future__ import annotations

from importlib.resources import files
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ...atmosphere.catalogue import CatalogueError, load_catalogue
from ...atmosphere.contracts import AtmosphericContract, validate_component_version
from ..serialization import sha256_bytes
from .aggregation import SOFIA_TIME_ZONE, SOFIA_WINDOW_VERSION
from .contracts import FEATURE_KEY_PATTERN

POLICY_RESOURCE = "weather-feature-policy-v1.json"


class FeaturePolicyError(ValueError):
    """The packaged S07 feature policy is invalid or drifts from the catalogue."""


class FeaturePolicyEntry(AtmosphericContract):
    """One ordered database-aligned output key and its canonical identity."""

    feature_key: str
    field_code: str
    variant: str | None = Field(default=None, min_length=1)
    statistic: Literal["instantaneous", "mean", "min", "max", "total"]
    derivation_method: str

    @field_validator("feature_key")
    @classmethod
    def key_must_be_database_aligned(cls, value: str) -> str:
        if FEATURE_KEY_PATTERN.fullmatch(value) is None:
            raise ValueError("feature_key must be lower_snake_case.")
        return value

    @field_validator("field_code")
    @classmethod
    def field_must_be_catalogued(cls, value: str) -> str:
        try:
            return load_catalogue().validate_field_code(value)
        except CatalogueError as error:
            raise ValueError(str(error)) from error

    @field_validator("derivation_method")
    @classmethod
    def method_must_be_versioned(cls, value: str) -> str:
        return validate_component_version(value)


class FeatureLayerPolicy(AtmosphericContract):
    """One ordered AGL layer identity retained in daily v2 output."""

    layer_base_agl_m: float = Field(ge=0)
    layer_top_agl_m: float = Field(gt=0)

    @model_validator(mode="after")
    def bounds_must_increase(self) -> FeatureLayerPolicy:
        if self.layer_top_agl_m <= self.layer_base_agl_m:
            raise ValueError("Feature layer bounds must be strictly increasing.")
        return self


class FeaturePolicy(AtmosphericContract):
    """All deterministic output order and formula identities for S07 v2."""

    feature_policy_schema_version: Literal[1] = 1
    policy_version: Literal["weather-feature-policy-v1"]
    feature_contract_version: Literal["weather-feature-contract/2"]
    feature_builder_version: Literal["weather-feature-builder/1"]
    time_zone: Literal["Europe/Sofia"]
    flying_window_version: Literal["sofia-flying-window/1"]
    hourly_fields: tuple[FeaturePolicyEntry, ...] = Field(min_length=1)
    daily_fields: tuple[FeaturePolicyEntry, ...] = Field(min_length=1)
    profile_layers: tuple[FeatureLayerPolicy, ...] = Field(min_length=1)
    profile_layer_fields: tuple[FeaturePolicyEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def entries_and_layers_must_be_unique(self) -> FeaturePolicy:
        for label, values in (
            ("hourly_fields", self.hourly_fields),
            ("daily_fields", self.daily_fields),
            ("profile_layer_fields", self.profile_layer_fields),
        ):
            keys = [value.feature_key for value in values]
            if len(keys) != len(set(keys)):
                raise ValueError(f"{label} feature keys must be unique.")
        layers = [(item.layer_base_agl_m, item.layer_top_agl_m) for item in self.profile_layers]
        if len(layers) != len(set(layers)):
            raise ValueError("profile_layers must be unique.")
        if self.time_zone != SOFIA_TIME_ZONE or self.flying_window_version != SOFIA_WINDOW_VERSION:
            raise ValueError("S07 feature policy must use the fixed Sofia flying-window contract.")
        return self


def load_feature_policy() -> tuple[FeaturePolicy, str]:
    """Load the exact packaged policy bytes and reject catalogue drift."""

    payload = (
        files("paragliding_forecasts_ml.ingestion.weather.resources")
        .joinpath(POLICY_RESOURCE)
        .read_bytes()
    )
    try:
        policy = FeaturePolicy.model_validate_json(payload, strict=True)
    except (TypeError, ValueError) as error:
        raise FeaturePolicyError("Packaged weather feature policy is invalid.") from error
    return policy, sha256_bytes(payload)
