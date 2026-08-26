from __future__ import annotations

import sqlite3
from pathlib import Path

from paragliding_forecasts_ml.ingestion.weather.spatial import (
    SampledField,
    SampledProfileLevel,
    SiteAlignedSample,
    TerrainDiagnostic,
)
from paragliding_forecasts_ml.ingestion.weather.validation import (
    _check_sample,
    load_validation_policy,
    load_weather_source,
)

_FIELD_VALUES = {
    "geopotential_height_msl_m": 1500.0,
    "air_temperature_k": 280.0,
    "relative_humidity_percent": 50.0,
    "wind_u_m_s": 1.0,
    "wind_v_m_s": 1.0,
}
_FIELD_UNITS = {
    "geopotential_height_msl_m": "m",
    "air_temperature_k": "K",
    "relative_humidity_percent": "%",
    "wind_u_m_s": "m/s",
    "wind_v_m_s": "m/s",
}


def _field(field_code: str, value: float | None, *, pressure_pa: float | None = None):
    return SampledField(
        field_code=field_code,
        grain="pressure_level" if pressure_pa is not None else "surface",
        canonical_unit=_FIELD_UNITS[field_code],
        canonical_value=value,
        quality_state="real" if value is not None else "missing",
        pressure_pa=pressure_pa,
        source_selector_keys=(field_code,),
        source_raw_artifact_keys=("raw",),
        source_native_message_references=("message",),
    )


def _sample(*, lead_hours: int | None = 6, pressures=(92500, 85000, 70000)):
    profiles = tuple(
        SampledProfileLevel(
            pressure_pa=pressure,
            geopotential_height_msl_m=1500.0,
            level_height_agl_m=500.0,
            model_level_height_agl_m=400.0,
            fields=tuple(
                _field(field, _FIELD_VALUES[field], pressure_pa=pressure) for field in _FIELD_VALUES
            ),
        )
        for pressure in pressures
    )
    return SiteAlignedSample(
        sample_identity_key="a" * 64,
        site_id=1,
        point_footprint_key="b" * 64,
        neighbourhood_footprint_key="c" * 64,
        reference_at_utc="2026-08-24T00:00:00Z",
        valid_at_utc="2026-08-24T06:00:00Z",
        valid_local_date="2026-08-24",
        lead_hours=lead_hours,
        terrain=TerrainDiagnostic(
            site_elevation_msl_m=100.0,
            model_elevation_msl_m=150.0,
            model_minus_site_elevation_m=50.0,
            absolute_mismatch_m=50.0,
        ),
        fields=(_field("air_temperature_k", 280.0),),
        profile_levels=profiles,
    )


def test_policy_requires_gfs_core_profiles_and_allows_era5_without_lead() -> None:
    policy, _ = load_validation_policy()

    missing_gfs, _ = _check_sample(
        _sample(pressures=(92500, 85000)), policy.sources["noaa_gfs_0p25_aws_grib2"]
    )
    valid_era5, _ = _check_sample(
        _sample(
            lead_hours=None,
            pressures=(100000, 97500, 95000, 92500, 90000, 87500, 85000, 80000, 75000, 70000),
        ),
        policy.sources["copernicus_era5"],
    )

    assert {reason.code for reason in missing_gfs} == {"required_profile_missing"}
    assert valid_era5 == []


def test_policy_quarantines_reanalysis_with_forecast_lead() -> None:
    policy, _ = load_validation_policy()
    reasons, _ = _check_sample(
        _sample(
            lead_hours=6,
            pressures=(100000, 97500, 95000, 92500, 90000, 87500, 85000, 80000, 75000, 70000),
        ),
        policy.sources["copernicus_era5"],
    )

    assert [reason.code for reason in reasons] == ["lead_hours_forbidden"]


def test_source_registry_snapshot_is_read_only_and_hashes_exact_row(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "local" / "weather.db"
    database_path.parent.mkdir(parents=True)
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE weather_sources (
          code TEXT, provider_name TEXT, dataset_name TEXT, source_kind TEXT,
          base_url TEXT, is_active INTEGER
        )
        """
    )
    connection.execute(
        """
        INSERT INTO weather_sources VALUES (
          'noaa_gfs_0p25_aws_grib2', 'NOAA', 'Global Forecast System 0.25° GRIB2',
          'forecast', 'https://noaa-gfs-bdp-pds.s3.amazonaws.com', 1
        )
        """
    )
    connection.commit()
    connection.close()
    original_bytes = database_path.read_bytes()

    source = load_weather_source(
        "file:./data/local/weather.db", "noaa_gfs_0p25_aws_grib2", tmp_path
    )

    assert source.is_active is True
    assert source.source_kind == "forecast"
    assert len(source.sha256) == 64
    assert database_path.read_bytes() == original_bytes
