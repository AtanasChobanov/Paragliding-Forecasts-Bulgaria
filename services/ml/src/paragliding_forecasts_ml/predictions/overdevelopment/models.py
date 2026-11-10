"""Input records and exact daily observation layout shared by scoring and replay."""

from datetime import date, datetime, time
from typing import Literal, Self
from zoneinfo import ZoneInfo

from pydantic import Field, FiniteFloat, model_validator

from ...ingestion.atmosphere.contracts import AtmosphericContract, validate_utc_timestamp
from ...ingestion.gfs.models import GFS_SOURCE_ID
from ...ingestion.weather.features.aggregation import FlyingWindow, sofia_flying_window

FieldKey = Literal["rain", "cape", "cin", "low_cloud", "humidity", "wind"]
FIELD_UNITS: dict[FieldKey, str] = {
    "rain": "mm",
    "cape": "J/kg",
    "cin": "J/kg",
    "low_cloud": "%",
    "humidity": "%",
    "wind": "m/s",
}


def observation_layout(window: FlyingWindow) -> tuple[tuple[str, FieldKey, str | None], ...]:
    instants = window.expected_instants_utc
    return tuple(
        (instant, key, instants[index + 1] if key == "rain" else None)
        for index, instant in enumerate(instants)
        for key in FIELD_UNITS
        if index < len(instants) - 1 or key not in {"rain", "cape", "cin"}
    )


class Observation(AtmosphericContract):
    key: FieldKey
    valid_at_utc: str
    interval_end_utc: str | None = None
    unit: str
    value: FiniteFloat | None
    quality: Literal["real", "derived", "missing", "sentinel_missing", "unsupported"]
    missing_reason: str | None
    source_selector_keys: tuple[str, ...] = ()
    source_native_message_references: tuple[str, ...] = ()
    source_raw_artifact_keys: tuple[str, ...] = ()

    @model_validator(mode="after")
    def valid_measurement(self) -> Self:
        if self.unit != FIELD_UNITS[self.key]:
            raise ValueError(f"Unexpected unit for {self.key}: {self.unit}")
        if self.value is None:
            if not self.missing_reason:
                raise ValueError("An unavailable observation requires a reason.")
        elif (
            self.missing_reason is not None
            or self.quality not in {"real", "derived"}
            or self.value < 0
            or (self.unit == "%" and self.value > 100)
        ):
            raise ValueError(f"Invalid observation: {self.key}")
        return self


class ForecastDay(AtmosphericContract):
    run_key: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    site_id: int = Field(gt=0)
    site_slug: str = Field(min_length=1)
    point_footprint_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_local_date: str
    source_id: Literal[GFS_SOURCE_ID] = GFS_SOURCE_ID
    source_product_key: str = Field(min_length=1)
    issue_local_date: str
    cycle_reference_utc: str
    horizon_days: Literal[1, 2, 3]
    window_start_utc: str
    window_end_utc: str
    hourly_source_ready_at_utc: tuple[str, ...]
    source_ready_at_utc: str
    observations: tuple[Observation, ...]

    @model_validator(mode="after")
    def consistent_window(self) -> Self:
        target = date.fromisoformat(self.target_local_date)
        window = sofia_flying_window(target)
        if (
            self.target_local_date != target.isoformat()
            or self.window_start_utc != window.interval_start_utc
            or self.window_end_utc != window.interval_end_utc
            or tuple((o.valid_at_utc, o.key, o.interval_end_utc) for o in self.observations)
            != observation_layout(window)
        ):
            raise ValueError("OD observations do not match the exact Sofia window.")
        cycle = datetime.fromisoformat(validate_utc_timestamp(self.cycle_reference_utc))
        issue = cycle.astimezone(ZoneInfo("Europe/Sofia")).date()
        cutoff = datetime.combine(issue, time(16), ZoneInfo("Europe/Sofia"))
        if (
            cycle.time() != time(6)
            or self.issue_local_date != issue.isoformat()
            or (target - issue).days != self.horizon_days
            or len(self.hourly_source_ready_at_utc) != len(window.expected_instants_utc)
            or not all(
                cycle <= datetime.fromisoformat(validate_utc_timestamp(timestamp)) <= cutoff
                for timestamp in self.hourly_source_ready_at_utc
            )
            or self.source_ready_at_utc != max(self.hourly_source_ready_at_utc)
        ):
            raise ValueError("OD issue, horizon or source readiness is invalid.")
        return self

    @property
    def key(self) -> tuple[str, int, str]:
        return self.run_key, self.site_id, self.target_local_date
