"""Packaged and hash-identified canonical site sampling policy."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .serialization import canonical_json_bytes, sha256_bytes


class NeighbourhoodFieldPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field_code: str
    grain: Literal["surface", "pressure_level"]
    dimension: str | None
    pressure_pa: float | None


class PointSamplingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    method: Literal["bilinear"]
    method_version: str
    missing_node_policy: Literal["strict_no_renormalization"]
    wind_derivation: Literal["interpolate_u_v_then_derive"]


class NeighbourhoodSamplingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    method: Literal["physical_radius"]
    method_version: str
    radius_km: float = Field(gt=0)
    boundary: Literal["inclusive"]
    earth_mean_radius_km: float = Field(gt=0)
    fields: tuple[NeighbourhoodFieldPolicy, ...] = Field(min_length=1)


class TerrainPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_site_mismatch: Literal["always_report_signed_and_absolute"]
    pressure_level_agl_reference: Literal["reviewed_site_elevation_msl"]
    below_terrain_policy: Literal["exclude_if_site_or_model_agl_is_negative"]


class SamplingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: Literal[
        "canonical-site-sampling-policy-v1", "canonical-site-sampling-policy-v2"
    ]
    point_sampling: PointSamplingPolicy
    neighbourhood_sampling: NeighbourhoodSamplingPolicy
    terrain: TerrainPolicy


def load_sampling_policy() -> tuple[SamplingPolicy, str]:
    resource = files("paragliding_forecasts_ml.ingestion.weather.resources").joinpath(
        "canonical-site-sampling-policy-v2.json"
    )
    payload = json.loads(resource.read_text(encoding="utf-8"))
    policy = SamplingPolicy.model_validate(payload)
    return policy, sha256_bytes(canonical_json_bytes(policy))
