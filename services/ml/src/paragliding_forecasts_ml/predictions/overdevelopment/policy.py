"""Validate and retain the exact versioned numerical policy."""

from importlib.resources import files
from typing import Annotated, Literal, Self

from pydantic import Field, FiniteFloat, model_validator

from ...ingestion.atmosphere.contracts import AtmosphericContract

Nonnegative = Annotated[FiniteFloat, Field(ge=0)]
Positive = Annotated[FiniteFloat, Field(gt=0)]
Fraction = Annotated[FiniteFloat, Field(ge=0, le=1)]


class Ramp(AtmosphericContract):
    lower: Nonnegative
    upper: Positive

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.lower >= self.upper:
            raise ValueError("A ramp requires lower < upper.")
        return self

    def apply(self, value: float) -> float:
        return min(1.0, max(0.0, (value - self.lower) / (self.upper - self.lower)))


class Policy(AtmosphericContract):
    schema_version: Literal[1]
    policy_version: str = Field(pattern=r"^overdevelopment-policy/[1-9][0-9]*$")
    medium_threshold: Positive
    high_threshold: Positive
    rain_weight: int = Field(ge=0)
    instability_weight: int = Field(ge=0)
    cloud_weight: int = Field(ge=0)
    rain_peak: Ramp
    rain_total: Ramp
    cape: Ramp
    cin: Ramp
    low_cloud: Ramp
    humidity: Ramp
    cin_discount: Fraction
    humidity_weight: Fraction
    override_hourly_rain_mm: Positive
    override_total_rain_mm: Positive
    override_convective_cape_j_per_kg: Positive
    override_convective_cin_j_per_kg: Nonnegative
    override_convective_rain_mm: Positive
    override_wind_m_s: Positive

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if not self.medium_threshold < self.high_threshold <= 100:
            raise ValueError("Risk thresholds must satisfy 0 < medium < high <= 100.")
        if self.rain_weight + self.instability_weight + self.cloud_weight != 100:
            raise ValueError("Contribution weights must sum to 100.")
        if max(self.low_cloud.upper, self.humidity.upper) > 100:
            raise ValueError("Cloud and RH ramps must be in [0, 100].")
        if self.override_convective_cape_j_per_kg <= self.cape.lower:
            raise ValueError("The convective override must require CIN above the CAPE ramp floor.")
        return self


def load_policy() -> tuple[Policy, bytes]:
    payload = (
        files(__package__).joinpath("resources", "overdevelopment-policy-v1.json").read_bytes()
    )
    return Policy.model_validate_json(payload), payload
