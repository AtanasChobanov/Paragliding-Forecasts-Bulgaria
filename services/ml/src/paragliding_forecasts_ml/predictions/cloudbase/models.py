"""Language-neutral, finite-valued inputs and outputs for the cloudbase batch."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, JsonValue, model_validator

Regime = Literal["cumulus", "blue", "other_cloud", "indeterminate", "missing"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ProfileLevel(Contract):
    pressure_pa: FiniteFloat = Field(gt=0)
    height_msl_m: FiniteFloat
    temperature_k: FiniteFloat = Field(gt=0)
    specific_humidity_kg_kg: FiniteFloat = Field(ge=0, lt=1)


class HourlyInput(Contract):
    run_key: str
    site_id: int = Field(gt=0)
    site_slug: str = Field(min_length=1)
    target_local_date: str
    valid_at_utc: str
    reference_at_utc: str
    issue_cutoff_utc: str
    source_ready_at_utc: str | None
    horizon_days: int = Field(ge=1, le=3)
    site_elevation_msl_m: FiniteFloat
    model_elevation_msl_m: FiniteFloat | None = None
    surface_pressure_pa: FiniteFloat | None = None
    temperature_2m_k: FiniteFloat | None = None
    specific_humidity_2m_kg_kg: FiniteFloat | None = None
    pbl_model_agl_m: FiniteFloat | None = None
    low_cloud_percent: FiniteFloat | None = None
    total_cloud_percent: FiniteFloat | None = None
    sensible_heat_flux_w_m2: FiniteFloat | None = None
    latent_heat_flux_w_m2: FiniteFloat | None = None
    sensible_interval: tuple[str, str] | None = None
    latent_interval: tuple[str, str] | None = None
    stored_lcl_model_agl_m: FiniteFloat | None = None
    profile: tuple[ProfileLevel, ...] = ()
    input_issues: tuple[str, ...] = ()


class Height(Contract):
    msl_m: FiniteFloat
    model_agl_m: FiniteFloat = Field(ge=0)
    site_agl_m: FiniteFloat


class HourlyResult(Contract):
    run_key: str
    site_id: int
    site_slug: str
    target_local_date: str
    valid_at_utc: str
    valid_at_local: str
    reference_at_utc: str
    horizon_days: int
    data_status: Literal["baseline", "missing"]
    regime: Regime
    potential_base: Height | None
    estimated_cloudbase: Height | None
    confidence: Literal["low"] | None
    validation_status: Literal["not_observationally_calibrated"] = "not_observationally_calibrated"
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]
    diagnostics: dict[str, JsonValue]
    input_sha256: str

    @model_validator(mode="after")
    def state_and_values_agree(self) -> HourlyResult:
        if (self.regime == "missing") != (self.data_status == "missing"):
            raise ValueError("Missing regime and data status must agree.")
        if self.regime == "missing" and (
            self.potential_base is not None or self.confidence is not None
        ):
            raise ValueError("Missing result cannot claim a potential height or confidence.")
        if self.regime != "missing" and self.potential_base is None:
            raise ValueError("A baseline result requires a valid potential base.")
        if self.regime != "missing" and self.confidence != "low":
            raise ValueError("The uncalibrated baseline must declare low confidence.")
        if (self.regime == "cumulus") != (self.estimated_cloudbase is not None):
            raise ValueError("Only cumulus has an estimated cloudbase.")
        if self.regime == "cumulus" and self.estimated_cloudbase != self.potential_base:
            raise ValueError("The numeric cumulus estimate must use the central mixed LCL.")
        return self


class CloudContextHour(Contract):
    valid_at_utc: str
    valid_at_local: str


class DailyResult(Contract):
    run_key: str
    site_id: int
    site_slug: str
    target_local_date: str
    reference_at_utc: str
    horizon_days: int
    summary_state: Literal[
        "cloudbase_available",
        "potential_base_available",
        "blue",
        "other_cloud",
        "indeterminate",
        "missing",
    ]
    max_cloudbase: Height | None
    max_at_utc: str | None
    max_at_local: str | None
    maximum_basis: Literal["estimated_hours_only"] = "estimated_hours_only"
    max_potential_base: Height | None
    potential_max_at_utc: str | None
    potential_max_at_local: str | None
    potential_maximum_basis: Literal["indeterminate_hours_only"] = "indeterminate_hours_only"
    significant_cloud_hours: tuple[CloudContextHour, ...]
    reason_codes: tuple[str, ...]
    regime_counts: dict[str, int]
    expected_hours: Literal[11] = 11
    present_hours: int = Field(ge=0, le=11)
    classified_hours: int = Field(ge=0, le=11)
    coverage_complete: bool
    confidence: Literal["low"] | None
    limitations: tuple[str, ...]

    @model_validator(mode="after")
    def summary_and_coverage_agree(self) -> DailyResult:
        keys = {"cumulus", "blue", "other_cloud", "indeterminate", "missing"}
        if set(self.regime_counts) != keys or any(n < 0 for n in self.regime_counts.values()):
            raise ValueError("Daily summary requires every nonnegative regime count.")
        if sum(self.regime_counts.values()) != 11:
            raise ValueError("Daily regime counts must cover eleven hours.")
        classified = sum(self.regime_counts[key] for key in ("cumulus", "blue", "other_cloud"))
        if (
            self.present_hours != 11 - self.regime_counts["missing"]
            or self.classified_hours != classified
        ):
            raise ValueError("Daily coverage disagrees with regime counts.")
        if self.coverage_complete != (classified == 11):
            raise ValueError("Complete coverage requires eleven classified hours.")
        available = self.summary_state == "cloudbase_available"
        if available != (self.max_cloudbase is not None):
            raise ValueError("Only a numeric summary can have a maximum cloudbase.")
        if available != (self.max_at_utc is not None) or available != (
            self.max_at_local is not None
        ):
            raise ValueError("A numeric maximum and its timestamps must be present together.")
        if available != (self.regime_counts["cumulus"] > 0):
            raise ValueError("Every day with an estimated cumulus base must report its maximum.")
        potential = self.max_potential_base is not None
        if potential != (self.potential_max_at_utc is not None) or potential != (
            self.potential_max_at_local is not None
        ):
            raise ValueError("A potential maximum and its timestamps must be present together.")
        if potential and self.regime_counts["indeterminate"] == 0:
            raise ValueError("Potential maximum requires an indeterminate hour.")
        if (self.summary_state == "potential_base_available") != (potential and not available):
            raise ValueError("Potential fallback applies only without an estimated maximum.")
        if (
            self.summary_state in {"blue", "other_cloud", "missing"}
            and self.regime_counts[self.summary_state] != 11
        ):
            raise ValueError("An all-day state requires every hour to have that state.")
        if (self.summary_state == "missing") != (self.confidence is None):
            raise ValueError("Only a wholly missing day has no baseline confidence.")
        return self
