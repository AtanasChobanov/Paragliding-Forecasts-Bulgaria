"""GFS file timing belongs to the forecast hour, not the shared cycle."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from paragliding_forecasts_ml.ingestion.gfs.models import (
    GFS_SOURCE_ID,
    GfsPlannedRange,
    GfsResolvedPlan,
)
from paragliding_forecasts_ml.ingestion.weather.persistence import (
    WeatherPersistenceError,
    _gfs_required_hour_times,
    _resolve_product_run,
    _resolve_valid_time,
)


def _prepared(valid: str, lead: int, ready: str):
    reference = "2021-09-30T06:00:00Z"
    product = "gfs.20210930/06/atmos"
    resolved = GfsResolvedPlan(
        selection_mode="explicit",
        resolved_run_at_utc=reference,
        available_at_utc=ready,
        source_product_key=product,
        ranges=(
            GfsPlannedRange(
                lead_hours=lead,
                valid_at_utc=valid,
                grib_url=f"https://example.test/gfs.f{lead:03d}",
                index_url=f"https://example.test/gfs.f{lead:03d}.idx",
                index_sha256="a" * 64,
                object_content_length=100,
                object_last_modified_utc=ready,
                index_last_modified_utc="2021-09-30T09:00:00Z",
                byte_start=0,
                byte_end=3,
                selector_keys=("tmp_2m",),
                message_numbers=(1,),
                forecast_descriptors=(f"{lead} hour fcst",),
            ),
        ),
    )
    sample = SimpleNamespace(valid_at_utc=valid, lead_hours=lead)
    return SimpleNamespace(
        raw_manifest=SimpleNamespace(
            source_id=GFS_SOURCE_ID,
            source_product_key=product,
            reference_at_utc=reference,
            available_at_utc=ready,
        ),
        request_plan=SimpleNamespace(adapter_request=resolved.model_dump(mode="json")),
        accepted=SimpleNamespace(samples=(sample,)),
    ), sample


def test_two_jobs_share_product_but_keep_distinct_hourly_source_timing() -> None:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE weather_product_runs (
          id INTEGER PRIMARY KEY, source_id INTEGER, source_product_key TEXT,
          reference_at_utc TEXT, available_at_utc TEXT);
        CREATE TABLE weather_product_valid_times (
          id INTEGER PRIMARY KEY, product_run_id INTEGER, valid_at_utc TEXT,
          lead_hours REAL, required_inputs_last_modified_at_utc TEXT);
        """
    )
    first, first_sample = _prepared("2021-10-01T07:00:00Z", 25, "2021-09-30T09:44:37Z")
    second, second_sample = _prepared("2021-10-02T07:00:00Z", 49, "2021-09-30T09:51:16Z")
    first_product = _resolve_product_run(connection, 1, first)
    second_product = _resolve_product_run(connection, 1, second)
    assert first_product == second_product
    for prepared, sample in ((first, first_sample), (second, second_sample)):
        hour = _gfs_required_hour_times(prepared)[sample.valid_at_utc]
        assert hour == (sample.lead_hours, prepared.raw_manifest.available_at_utc)
        _resolve_valid_time(connection, first_product, sample, hour[1])
    rows = connection.execute(
        "SELECT valid_at_utc, required_inputs_last_modified_at_utc "
        "FROM weather_product_valid_times ORDER BY valid_at_utc"
    ).fetchall()
    assert rows == [
        (first_sample.valid_at_utc, first.raw_manifest.available_at_utc),
        (second_sample.valid_at_utc, second.raw_manifest.available_at_utc),
    ]
    with pytest.raises(WeatherPersistenceError, match="source timing differs"):
        _resolve_valid_time(connection, first_product, first_sample, "2021-09-30T10:00:00Z")
    connection.close()
