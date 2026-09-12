"""Packaged, hash-pinned output policy for versioned weather feature artifacts."""

from __future__ import annotations

from importlib.resources import files
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ...atmosphere.catalogue import CatalogueError, load_catalogue
from ...atmosphere.contracts import AtmosphericContract, validate_component_version
from ..serialization import sha256_bytes
from .aggregation import SOFIA_TIME_ZONE, SOFIA_WINDOW_VERSION
from .contracts import FEATURE_KEY_PATTERN

POLICY_RESOURCE = "weather-feature-policy-v3.json"


class FeaturePolicyError(ValueError):
    """A packaged weather feature policy is invalid or drifts from the catalogue."""


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
    """One AGL layer identity and the keys that apply to that layer."""

    layer_base_agl_m: float = Field(ge=0)
    layer_top_agl_m: float = Field(gt=0)
    fields: tuple[FeaturePolicyEntry, ...] = ()

    @model_validator(mode="after")
    def bounds_and_fields_must_be_valid(self) -> FeatureLayerPolicy:
        if self.layer_top_agl_m <= self.layer_base_agl_m:
            raise ValueError("Feature layer bounds must be strictly increasing.")
        keys = [entry.feature_key for entry in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("Layer feature keys must be unique.")
        return self


class FeaturePolicy(AtmosphericContract):
    """All deterministic output order and formula identities for v1/v2 artifacts."""

    feature_policy_schema_version: Literal[1, 2] = 2
    policy_version: Literal[
        "weather-feature-policy-v1", "weather-feature-policy-v2", "weather-feature-policy-v3"
    ]
    feature_contract_version: Literal["weather-feature-contract/2", "weather-feature-contract/3"]
    feature_builder_version: Literal[
        "weather-feature-builder/1", "weather-feature-builder/2", "weather-feature-builder/3"
    ]
    time_zone: Literal["Europe/Sofia"]
    flying_window_version: Literal["sofia-flying-window/1"]
    hourly_fields: tuple[FeaturePolicyEntry, ...] = Field(min_length=1)
    daily_fields: tuple[FeaturePolicyEntry, ...] = Field(min_length=1)
    profile_layers: tuple[FeatureLayerPolicy, ...] = Field(min_length=1)
    profile_layer_fields: tuple[FeaturePolicyEntry, ...] = ()

    @model_validator(mode="after")
    def entries_and_layers_must_be_unique(self) -> FeaturePolicy:
        for label, values in (
            ("hourly_fields", self.hourly_fields),
            ("daily_fields", self.daily_fields),
        ):
            keys = [value.feature_key for value in values]
            if len(keys) != len(set(keys)):
                raise ValueError(f"{label} feature keys must be unique.")
        layers = [(item.layer_base_agl_m, item.layer_top_agl_m) for item in self.profile_layers]
        if len(layers) != len(set(layers)):
            raise ValueError("profile_layers must be unique.")
        if self.time_zone != SOFIA_TIME_ZONE or self.flying_window_version != SOFIA_WINDOW_VERSION:
            raise ValueError("Feature policy must use the fixed Sofia flying-window contract.")
        expected_versions = {
            1: {
                (
                    "weather-feature-policy-v1",
                    "weather-feature-contract/2",
                    "weather-feature-builder/1",
                )
            },
            2: {
                (
                    "weather-feature-policy-v2",
                    "weather-feature-contract/3",
                    "weather-feature-builder/2",
                ),
                (
                    "weather-feature-policy-v3",
                    "weather-feature-contract/3",
                    "weather-feature-builder/3",
                ),
            },
        }[self.feature_policy_schema_version]
        if (
            self.policy_version,
            self.feature_contract_version,
            self.feature_builder_version,
        ) not in expected_versions:
            raise ValueError("Feature policy/version tuple is inconsistent.")
        if self.feature_policy_schema_version == 1:
            if not self.profile_layer_fields or any(layer.fields for layer in self.profile_layers):
                raise ValueError("v1 policy requires one shared non-empty profile field list.")
        elif self.profile_layer_fields or any(not layer.fields for layer in self.profile_layers):
            raise ValueError("v2 policy requires non-empty fields on every layer only.")
        return self

    def entries_for_layer(self, layer: FeatureLayerPolicy) -> tuple[FeaturePolicyEntry, ...]:
        """Return the policy fields applicable to one explicit AGL layer."""

        return (
            self.profile_layer_fields if self.feature_policy_schema_version == 1 else layer.fields
        )


def load_feature_policy(resource_name: str = POLICY_RESOURCE) -> tuple[FeaturePolicy, str]:
    """Load exact packaged policy bytes and reject catalogue drift."""

    payload = (
        files("paragliding_forecasts_ml.ingestion.weather.resources")
        .joinpath(resource_name)
        .read_bytes()
    )
    try:
        policy = FeaturePolicy.model_validate_json(payload, strict=True)
    except (TypeError, ValueError) as error:
        raise FeaturePolicyError("Packaged weather feature policy is invalid.") from error
    return policy, sha256_bytes(payload)
