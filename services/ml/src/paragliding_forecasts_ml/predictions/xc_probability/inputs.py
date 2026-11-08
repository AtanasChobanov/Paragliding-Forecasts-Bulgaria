"""Label-free frozen weather records shared by study preparation and inference."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, FiniteFloat, JsonValue, field_validator, model_validator

from ...ingestion.atmosphere.contracts import AtmosphericContract, validate_utc_timestamp
from ...ingestion.gfs.models import sofia_window_instants
from .policy import LAYER_BOUNDS, XcPolicy

ABSENT_STATES = {"missing", "sentinel_missing", "invalid_payload", "unsupported"}


class Observation(AtmosphericContract):
    feature_id: str
    value: FiniteFloat | None
    canonical_unit: str = Field(min_length=1)
    quality_state: Literal[
        "real", "derived", "missing", "sentinel_missing", "invalid_payload", "unsupported"
    ]
    missing_reason: str | None
    provenance: dict[str, JsonValue] = Field(min_length=1)

    @model_validator(mode="after")
    def value_and_quality_agree(self) -> Observation:
        absent = self.quality_state in ABSENT_STATES
        if absent != (self.value is None) or absent != (self.missing_reason is not None):
            raise ValueError("XC feature value, quality and missing reason disagree.")
        if self.missing_reason is not None and not self.missing_reason.strip():
            raise ValueError("A missing feature requires a concrete reason.")
        return self


class ForecastInput(AtmosphericContract):
    run_key: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    site_id: int = Field(gt=0)
    site_slug: str = Field(min_length=1)
    target_local_date: str
    issue_local_date: str
    horizon_days: Literal[1, 2, 3]
    cycle_reference_utc: str
    issue_cutoff_utc: str
    source_ready_at_utc: str
    valid_times_utc: tuple[str, ...] = Field(min_length=11, max_length=11)
    observations: tuple[Observation, ...] = Field(min_length=67, max_length=67)
    source_lineage: dict[str, JsonValue] = Field(min_length=1)

    @field_validator("cycle_reference_utc", "issue_cutoff_utc", "source_ready_at_utc")
    @classmethod
    def timestamp_is_canonical_utc(cls, value: str) -> str:
        return validate_utc_timestamp(value)

    @model_validator(mode="after")
    def forecast_identity_agrees(self) -> ForecastInput:
        target = date.fromisoformat(self.target_local_date)
        issue = date.fromisoformat(self.issue_local_date)
        if (
            target.isoformat() != self.target_local_date
            or issue.isoformat() != self.issue_local_date
        ):
            raise ValueError("XC dates must be canonical ISO local dates.")
        if issue != target - timedelta(days=self.horizon_days):
            raise ValueError("XC issue date must match target date and horizon.")
        if self.cycle_reference_utc != f"{issue}T06:00:00Z":
            raise ValueError("XC inputs require issue-date GFS 06Z.")
        expected_cutoff = datetime.combine(issue, time(16), tzinfo=ZoneInfo("Europe/Sofia"))
        if datetime.fromisoformat(self.issue_cutoff_utc) != expected_cutoff:
            raise ValueError("XC cutoff must be 16:00 Europe/Sofia.")
        if datetime.fromisoformat(self.source_ready_at_utc) > expected_cutoff:
            raise ValueError("XC source became ready after the issue cutoff.")
        if datetime.fromisoformat(self.source_ready_at_utc) < datetime.fromisoformat(
            self.cycle_reference_utc
        ):
            raise ValueError("XC source readiness cannot precede the forecast cycle.")
        if self.valid_times_utc != sofia_window_instants(self.target_local_date):
            raise ValueError("XC inputs require the complete eleven-hour Sofia flying window.")
        if len({item.feature_id for item in self.observations}) != 67:
            raise ValueError("XC physical input identities cannot repeat.")
        return self


def validate_features(row: ForecastInput, policy: XcPolicy, *, require_available: bool) -> None:
    if tuple(item.feature_id for item in row.observations) != tuple(
        item.feature_id for item in policy.required_features
    ):
        raise ValueError("XC feature order or inventory differs from the frozen policy.")
    for observation, spec in zip(row.observations, policy.required_features, strict=True):
        if observation.canonical_unit != spec.canonical_unit:
            raise ValueError(f"XC feature unit differs: {spec.feature_id}.")
        if require_available and observation.value is None:
            raise ValueError(f"Required training feature is missing: {spec.feature_id}.")


def joined_input(row: dict, policy: XcPolicy) -> ForecastInput:
    """Project only selected physical inputs; flight evidence never enters this record."""
    weather = row["weather"]
    if weather["feature_contract_version"] != policy.feature_contract_version:
        raise ValueError("Joined XC input has an incompatible weather feature contract.")
    layers = weather["profile_layers"]
    by_bounds = {
        (item["layer_base_agl_m"], item["layer_top_agl_m"]): (index, item)
        for index, item in enumerate(layers)
    }
    if len(by_bounds) != len(layers):
        raise ValueError("Joined profile layers repeat their bounds.")
    observations = []
    for spec in policy.required_features:
        if spec.scope == "daily":
            values, provenance = weather["features"], weather["feature_quality"]
        else:
            index, values = by_bounds[LAYER_BOUNDS[spec.scope]]
            provenance = [
                item for item in weather["profile_layer_quality"] if item["layer_index"] == index
            ]
        matches = [
            item
            for item in provenance
            if (item["field_code"], item["field_variant"], item["statistic_type"])
            == (spec.field_code, spec.variant or "canonical", spec.statistic)
        ]
        if len(matches) != 1 or matches[0]["native_unit"] != spec.canonical_unit:
            raise ValueError(
                f"Joined XC feature lacks unique canonical provenance: {spec.feature_id}."
            )
        evidence = matches[0]
        observations.append(
            Observation(
                feature_id=spec.feature_id,
                value=values[spec.feature_key],
                canonical_unit=evidence["native_unit"],
                quality_state=evidence["quality_state"],
                missing_reason=evidence["missing_reason_code"],
                provenance=evidence,
            )
        )
    result = ForecastInput(
        **{
            key: row[key]
            for key in (
                "site_id",
                "site_slug",
                "target_local_date",
                "issue_local_date",
                "horizon_days",
                "cycle_reference_utc",
                "issue_cutoff_utc",
            )
        },
        run_key=weather["run_key"],
        source_ready_at_utc=weather["required_inputs_last_modified_at_utc"],
        valid_times_utc=tuple(row["valid_times_utc"]),
        observations=tuple(observations),
        source_lineage={
            key: weather[key]
            for key in (
                "raw_manifest_sha256",
                "feature_manifest_sha256",
                "persistence_input_sha256",
            )
        },
    )
    validate_features(result, policy, require_available=True)
    return result
