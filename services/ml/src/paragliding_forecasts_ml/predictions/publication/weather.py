"""Exact persisted GFS identities used for forecast publication."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from sqlite3 import Connection, Row
from zoneinfo import ZoneInfo

from ...ingestion.atmosphere.contracts import validate_utc_timestamp
from ...ingestion.gfs.models import GFS_SOURCE_ID, sofia_window_instants

SOFIA = ZoneInfo("Europe/Sofia")
SITE_COUNT = 7
RUN_SELECT = """
    SELECT r.*, p.reference_at_utc, p.source_product_key, s.code AS source_code, s.source_kind
    FROM weather_ingestion_runs AS r
    JOIN weather_product_runs AS p ON p.id = r.product_run_id
    JOIN weather_sources AS s ON s.id = p.source_id
"""


@dataclass(frozen=True, order=True)
class ForecastHorizon:
    issue_date: date
    days: int

    @property
    def target_date(self) -> date:
        return self.issue_date + timedelta(days=self.days)

    @property
    def cycle(self) -> str:
        return f"{self.issue_date}T06:00:00Z"

    @property
    def cutoff(self) -> str:
        return utc_text(datetime.combine(self.issue_date, time(16), SOFIA))

    @property
    def deadline(self) -> datetime:
        return datetime.combine(self.issue_date, time(20), SOFIA)

    @property
    def hours(self) -> tuple[str, ...]:
        return sofia_window_instants(self.target_date.isoformat())


@dataclass(frozen=True)
class ForecastWeather:
    id: int
    run_key: str
    purpose: str
    horizon: ForecastHorizon
    source_product_key: str
    raw_manifest: tuple[str, str]
    feature_manifest: tuple[str, str]
    persistence_input_sha256: str
    ready_times: dict[str, str]


def utc_text(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_weather(connection: Connection, run_key: str) -> ForecastWeather:
    row = connection.execute(RUN_SELECT + " WHERE r.run_key = ?", (run_key,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown persisted weather run {run_key}.")
    return _weather(connection, row)


def _weather(connection: Connection, row: Row) -> ForecastWeather:
    cycle = datetime.fromisoformat(validate_utc_timestamp(row["reference_at_utc"] or ""))
    target = date.fromisoformat(row["target_local_date"])
    horizon = ForecastHorizon(cycle.date(), (target - cycle.date()).days)
    if (
        row["source_code"] != GFS_SOURCE_ID
        or row["source_kind"] != "forecast"
        or row["status"] != "succeeded"
        or row["operational_use_allowed"] != 1
        or row["reference_at_utc"] != horizon.cycle
        or horizon.days not in (1, 2, 3)
        or row["source_product_key"] != f"gfs.{cycle:%Y%m%d}/06/atmos"
    ):
        raise ValueError(f"Run {row['run_key']} is ineligible for operational GFS 06Z publication.")
    hours = horizon.hours
    slots = ", ".join("?" for _ in hours)
    rows = connection.execute(
        f"""SELECT valid_at_utc, lead_hours, required_inputs_last_modified_at_utc
            FROM weather_product_valid_times
            WHERE product_run_id = ? AND valid_at_utc IN ({slots}) ORDER BY valid_at_utc""",
        (row["product_run_id"], *hours),
    ).fetchall()
    if tuple(item[0] for item in rows) != hours:
        raise ValueError(f"Run {row['run_key']} lacks the exact eleven GFS valid hours.")
    ready_times = {}
    for valid, lead, ready_at in rows:
        validate_utc_timestamp(ready_at or "")
        if (
            lead != (datetime.fromisoformat(valid) - cycle).total_seconds() / 3600
            or not horizon.cycle <= ready_at <= horizon.cutoff
        ):
            raise ValueError(f"Run {row['run_key']} has ineligible source readiness at {valid}.")
        ready_times[valid] = ready_at
    return ForecastWeather(
        row["id"],
        row["run_key"],
        row["request_purpose"],
        horizon,
        row["source_product_key"],
        (row["raw_manifest_path"], row["raw_manifest_sha256"]),
        (row["feature_manifest_path"], row["feature_manifest_sha256"]),
        row["persistence_input_sha256"],
        ready_times,
    )


def candidate_weather_runs(connection: Connection, horizon: ForecastHorizon) -> tuple[str, ...]:
    """List automatic-mode candidates newest persisted first."""
    return tuple(
        row[0]
        for row in connection.execute(
            """SELECT r.run_key FROM weather_ingestion_runs AS r
               JOIN weather_product_runs AS p ON p.id = r.product_run_id
               JOIN weather_sources AS s ON s.id = p.source_id
               WHERE s.code = ? AND p.reference_at_utc = ? AND r.target_local_date = ?
                 AND r.status = 'succeeded' AND r.operational_use_allowed = 1
                 AND r.request_purpose = 'operational_forecast'
               ORDER BY r.id DESC""",
            (GFS_SOURCE_ID, horizon.cycle, horizon.target_date.isoformat()),
        )
    )
