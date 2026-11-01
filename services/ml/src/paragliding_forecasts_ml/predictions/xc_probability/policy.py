"""Frozen XC feature inventory; never infer predictors from new weather columns."""

from __future__ import annotations

from importlib.resources import files
from typing import Literal

from pydantic import Field, FiniteFloat, JsonValue, model_validator

from ...ingestion.atmosphere.catalogue import load_catalogue
from ...ingestion.atmosphere.contracts import AtmosphericContract
from ...ingestion.weather.features.policy import load_feature_policy
from ...ingestion.weather.serialization import sha256_bytes

POLICY_RESOURCE = "xc-probability-policy-v1.json"
Stage = Literal["p100", "q200"]
Scope = Literal["daily", "layer_0_1500", "layer_1500_3000"]
GroupId = Literal[
    "surface_temperature",
    "humidity",
    "cloud_cover",
    "thermal_height",
    "thermal_strength",
    "solar_radiation",
    "wind",
    "wind_shear",
    "stability",
    "precipitation",
    "pressure_convergence",
    "vertical_motion",
    "site_context",
    "season_context",
    "horizon_context",
]
LAYER_BOUNDS = {"layer_0_1500": (0, 1500), "layer_1500_3000": (1500, 3000)}


class SourceFeature(AtmosphericContract):
    feature_id: str
    scope: Scope
    feature_key: str
    field_code: str
    canonical_unit: str
    variant: str | None
    statistic: str
    derivation_method: str
    group_id: GroupId
    encoding: Literal["identity", "sin_cos"]


class DriverGroup(AtmosphericContract):
    group_id: GroupId
    label: str = Field(min_length=1)
    kind: Literal["weather", "context"]


class XcPolicy(AtmosphericContract):
    schema_version: Literal["xc-probability-policy/1"]
    method_version: Literal["xc-conditional-logistic/1"]
    confidence_version: Literal["xc-confidence/1"]
    explanation_version: Literal["xc-grouped-logit/1"]
    dataset_schema_version: Literal["weather-flight-joined-dataset/4"]
    pinned_dataset_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    weather_policy_version: Literal["weather-feature-policy-v5"]
    feature_contract_version: Literal["weather-feature-contract/3"]
    feature_builder_version: Literal["weather-feature-builder/5"]
    required_features: tuple[SourceFeature, ...] = Field(min_length=67, max_length=67)
    groups: tuple[DriverGroup, ...] = Field(min_length=15, max_length=15)
    continuous_coordinate_count: Literal[72]
    total_coordinate_count: Literal[82]
    site_category_count: Literal[7]
    horizons: tuple[Literal[1, 2, 3], ...]
    development_seasons: tuple[Literal[2022, 2023, 2024], ...]
    reserved_season: Literal[2025]
    regularization_grid: tuple[FiniteFloat, ...]
    algorithm: dict[str, JsonValue]
    selection: dict[str, JsonValue]
    explanation: dict[str, JsonValue]
    confidence_reasons: dict[str, tuple[str, ...]]
    confidence_notes: dict[str, str]
    templates: dict[str, str]

    @model_validator(mode="after")
    def inventory_is_complete(self) -> XcPolicy:
        ids = [item.feature_id for item in self.required_features]
        if len(set(ids)) != 67:
            raise ValueError("XC source feature identifiers must be unique.")
        groups = {group.group_id: group for group in self.groups}
        if len(groups) != 15:
            raise ValueError("XC driver groups must be unique.")
        expected_counts = {
            "surface_temperature": 4,
            "humidity": 7,
            "cloud_cover": 6,
            "thermal_height": 7,
            "thermal_strength": 6,
            "solar_radiation": 2,
            "wind": 15,
            "wind_shear": 4,
            "stability": 6,
            "precipitation": 2,
            "pressure_convergence": 6,
            "vertical_motion": 2,
        }
        for group_id, count in expected_counts.items():
            if sum(f.group_id == group_id for f in self.required_features) != count:
                raise ValueError(f"XC driver membership differs for {group_id}.")
        for group in self.groups:
            context = group.group_id.endswith("_context")
            if (group.kind == "context") != context:
                raise ValueError("Weather and context groups must stay distinct.")
        for item in self.required_features:
            if item.feature_id != f"{item.scope}.{item.feature_key}":
                raise ValueError("XC identifiers must include their exact source scope.")
            expected_encoding = (
                "sin_cos" if item.field_code == "wind_direction_degrees_from_north" else "identity"
            )
            if item.encoding != expected_encoding:
                raise ValueError("Only wind directions use sin/cos encoding.")
            if item.encoding == "sin_cos" and item.group_id != "wind":
                raise ValueError("Wind direction coordinates must stay in the wind group.")
        if sum(item.encoding == "sin_cos" for item in self.required_features) != 3:
            raise ValueError("Exactly three wind directions expand to sin/cos.")
        if self.horizons != (1, 2, 3) or self.development_seasons != (2022, 2023, 2024):
            raise ValueError("XC horizons and source-season boundaries are fixed.")
        if self.regularization_grid != (0.03, 0.1, 0.3):
            raise ValueError("XC regularization grid is predeclared.")
        if set(self.confidence_reasons) != {"100", "200", "300"}:
            raise ValueError("Confidence reasons must describe all three thresholds.")
        return self


def load_policy() -> tuple[XcPolicy, str]:
    """Load the explicit inventory and check its paths against packaged weather v5."""
    content = files(__package__).joinpath("resources", POLICY_RESOURCE).read_bytes()
    policy = XcPolicy.model_validate_json(content)
    weather, _ = load_feature_policy("weather-feature-policy-v5.json")
    catalogue = load_catalogue()
    for scope, count in (("daily", 43), ("layer_0_1500", 11), ("layer_1500_3000", 13)):
        selected = [item for item in policy.required_features if item.scope == scope]
        if len(selected) != count:
            raise ValueError(f"Wrong XC source inventory size for {scope}.")
        entries = (
            weather.daily_fields
            if scope == "daily"
            else next(
                layer.fields
                for layer in weather.profile_layers
                if (layer.layer_base_agl_m, layer.layer_top_agl_m) == LAYER_BOUNDS[scope]
            )
        )
        weather_by_key = {entry.feature_key: entry for entry in entries}
        for item in selected:
            source = weather_by_key.get(item.feature_key)
            if (
                source is None
                or any(
                    getattr(item, key) != getattr(source, key)
                    for key in ("field_code", "variant", "statistic", "derivation_method")
                )
                or item.canonical_unit != catalogue.field_unit(item.field_code)
            ):
                raise ValueError(f"XC source identity/unit differs: {item.feature_id}.")
    return policy, sha256_bytes(content)


def coordinate_ids(policy: XcPolicy, site_ids: tuple[int, ...]) -> tuple[str, ...]:
    """Ordered encoded vector; categories are frozen from the verified cohort."""
    if (
        len(site_ids) != 7
        or len(set(site_ids)) != 7
        or any(type(site_id) is not int or site_id <= 0 for site_id in site_ids)
    ):
        raise ValueError("Exactly seven distinct positive site IDs are required.")
    physical = tuple(
        coordinate
        for item in policy.required_features
        for coordinate in (
            (f"{item.feature_id}.sin", f"{item.feature_id}.cos")
            if item.encoding == "sin_cos"
            else (item.feature_id,)
        )
    )
    return (
        *physical,
        "season.sin",
        "season.cos",
        *(f"site.{site_id}" for site_id in site_ids),
        *(f"horizon.{horizon}" for horizon in policy.horizons),
    )


def coordinate_groups(policy: XcPolicy) -> tuple[GroupId, ...]:
    return (
        *(
            item.group_id
            for item in policy.required_features
            for _ in range(2 if item.encoding == "sin_cos" else 1)
        ),
        "season_context",
        "season_context",
        *("site_context" for _ in range(7)),
        *("horizon_context" for _ in range(3)),
    )
