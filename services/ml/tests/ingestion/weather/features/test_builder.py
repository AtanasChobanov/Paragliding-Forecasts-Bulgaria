from __future__ import annotations

import pytest

from paragliding_forecasts_ml.ingestion.weather.features.builder import (
    build_daily_interval_features,
    build_daily_neighbourhood_features,
    build_daily_point_features,
    build_profile_layer,
)
from paragliding_forecasts_ml.ingestion.weather.features.policy import load_feature_policy
from paragliding_forecasts_ml.ingestion.weather.spatial import (
    NeighbourhoodFieldValues,
    NeighbourhoodNodeRecord,
    SampledField,
    SampledProfileLevel,
    SamplingFootprint,
    SamplingNode,
    SiteAlignedSample,
    SiteConfigSnapshot,
    TerrainDiagnostic,
)


def _field(field_code: str, value: float, *, grain: str = "surface", pressure: float | None = None):
    units = {
        "air_temperature_k": "K",
        "relative_humidity_percent": "%",
        "specific_humidity_kg_per_kg": "kg/kg",
        "wind_u_m_s": "m/s",
        "wind_v_m_s": "m/s",
        "vertical_velocity_pa_s": "Pa/s",
    }
    return SampledField(
        field_code=field_code,
        grain=grain,
        canonical_unit=units[field_code],
        canonical_value=value,
        quality_state="real",
        pressure_pa=pressure,
        source_selector_keys=(field_code,),
        source_raw_artifact_keys=("raw",),
        source_native_message_references=("message",),
    )


def _sample(hour: int) -> SiteAlignedSample:
    profiles = tuple(
        SampledProfileLevel(
            pressure_pa=pressure,
            geopotential_height_msl_m=height + 100.0,
            level_height_agl_m=height,
            model_level_height_agl_m=height - 50.0,
            fields=(
                _field("air_temperature_k", temperature, grain="pressure_level", pressure=pressure),
                _field(
                    "relative_humidity_percent", humidity, grain="pressure_level", pressure=pressure
                ),
                _field(
                    "specific_humidity_kg_per_kg",
                    humidity / 10000.0,
                    grain="pressure_level",
                    pressure=pressure,
                ),
                _field("wind_u_m_s", wind_u, grain="pressure_level", pressure=pressure),
                _field("wind_v_m_s", wind_v, grain="pressure_level", pressure=pressure),
                _field("vertical_velocity_pa_s", omega, grain="pressure_level", pressure=pressure),
            ),
        )
        for pressure, height, temperature, humidity, wind_u, wind_v, omega in (
            (85000.0, 1500.0, 280.0, 50.0, 4.0, 6.0, -0.1),
            (70000.0, 3000.0, 270.0, 40.0, 7.0, 8.0, -0.2),
        )
    )
    return SiteAlignedSample(
        sample_identity_key=f"{hour:064x}",
        site_id=1,
        point_footprint_key="a" * 64,
        neighbourhood_footprint_key="b" * 64,
        reference_at_utc="2026-09-10T00:00:00Z",
        valid_at_utc=f"2026-09-10T{hour:02d}:00:00Z",
        valid_local_date="2026-09-10",
        lead_hours=hour,
        terrain=TerrainDiagnostic(
            site_elevation_msl_m=100.0,
            model_elevation_msl_m=150.0,
            model_minus_site_elevation_m=50.0,
            absolute_mismatch_m=50.0,
        ),
        fields=(
            _field("air_temperature_k", 290.0),
            _field("relative_humidity_percent", 60.0),
            _field("specific_humidity_kg_per_kg", 0.006),
            _field("wind_u_m_s", 1.0),
            _field("wind_v_m_s", 2.0),
        ),
        profile_levels=profiles,
    )


def test_profile_builder_uses_surface_anchors_and_marks_lower_omega_missing() -> None:
    policy, _ = load_feature_policy()
    samples = tuple(_sample(hour) for hour in range(10, 21))
    layer = build_profile_layer(
        samples,
        policy.profile_layers[0],
        policy.profile_layer_fields,
        expected_instants_utc=tuple(sample.valid_at_utc for sample in samples),
    )
    values = {field.feature_key: field for field in layer.fields}

    assert values["temperature_lapse_rate_mean_k_per_km"].canonical_value == pytest.approx(
        10000.0 / 1498.0
    )
    assert values["vertical_velocity_mean_pa_s"].canonical_value is None
    assert values["vertical_velocity_mean_pa_s"].missing_reason == "lower_boundary_not_bracketed"
    assert values["wind_direction_mean_degrees_from_north"].canonical_value is not None


def test_profile_builder_keeps_each_feature_strict_when_an_hour_is_missing() -> None:
    policy, _ = load_feature_policy()
    samples = tuple(_sample(hour) for hour in range(10, 20))
    layer = build_profile_layer(
        samples,
        policy.profile_layers[1],
        policy.profile_layer_fields,
        expected_instants_utc=tuple(f"2026-09-10T{hour:02d}:00:00Z" for hour in range(10, 21)),
    )

    assert all(field.canonical_value is None for field in layer.fields)
    values = {field.feature_key: field for field in layer.fields}
    assert values["temperature_lapse_rate_mean_k_per_km"].missing_reason == "missing_hour"
    assert (
        values["wind_direction_mean_degrees_from_north"].missing_reason == "wind_components_missing"
    )


def test_point_builder_reduces_daily_scalar_wind_and_leaves_intervals_for_their_own_reducer() -> (
    None
):
    policy, _ = load_feature_policy()
    samples = tuple(_sample(hour) for hour in range(10, 21))
    values = build_daily_point_features(
        samples,
        policy.daily_fields,
        expected_instants_utc=tuple(sample.valid_at_utc for sample in samples),
    )
    by_key = {value.feature_key: value for value in values}

    assert by_key["air_temperature_2m_mean_k"].canonical_value == 290.0
    assert by_key["wind_speed_10m_mean_m_s"].canonical_value == pytest.approx(5**0.5)
    assert by_key["wind_direction_10m_mean_degrees_from_north"].canonical_value is not None
    assert "precipitation_total_mm" not in by_key


def _interval(field_code: str, value: float, start_hour: int) -> SampledField:
    units = {
        "precipitation_amount_mm": "mm",
        "shortwave_radiation_w_m2": "W/m2",
        "surface_sensible_heat_flux_upward_w_m2": "W/m2",
        "surface_latent_heat_flux_upward_w_m2": "W/m2",
    }
    return SampledField(
        field_code=field_code,
        grain="interval",
        canonical_unit=units[field_code],
        canonical_value=value,
        quality_state="real",
        interval_start_utc=f"2026-09-10T{start_hour:02d}:00:00Z",
        interval_end_utc=f"2026-09-10T{start_hour + 1:02d}:00:00Z",
        source_selector_keys=(field_code,),
        source_raw_artifact_keys=("raw",),
        source_native_message_references=("message",),
    )


def test_interval_builder_requires_complete_exact_coverage() -> None:
    policy, _ = load_feature_policy()
    samples = tuple(
        _sample(hour).model_copy(
            update={
                "fields": (
                    *_sample(hour).fields,
                    _interval("precipitation_amount_mm", float(hour - 9), hour),
                    _interval("shortwave_radiation_w_m2", float(hour), hour),
                    _interval("surface_sensible_heat_flux_upward_w_m2", 40.0, hour),
                    _interval("surface_latent_heat_flux_upward_w_m2", 20.0, hour),
                )
            }
        )
        for hour in range(10, 19)
    )
    values = build_daily_interval_features(
        samples,
        policy.daily_fields,
        expected_instants_utc=tuple(f"2026-09-10T{hour:02d}:00:00Z" for hour in range(10, 21)),
    )
    by_key = {value.feature_key: value for value in values}

    assert by_key["precipitation_total_mm"].canonical_value is None
    assert by_key["precipitation_total_mm"].missing_reason == "interval_coverage_gap"


def test_interval_builder_reduces_exact_hourly_coverage() -> None:
    policy, _ = load_feature_policy()
    samples = tuple(
        _sample(hour).model_copy(
            update={
                "fields": (
                    *_sample(hour).fields,
                    _interval("precipitation_amount_mm", float(hour - 9), hour),
                    _interval("shortwave_radiation_w_m2", float(hour), hour),
                    _interval("surface_sensible_heat_flux_upward_w_m2", 40.0, hour),
                    _interval("surface_latent_heat_flux_upward_w_m2", 20.0, hour),
                )
            }
        )
        for hour in range(10, 20)
    )
    values = build_daily_interval_features(
        samples,
        policy.daily_fields,
        expected_instants_utc=tuple(f"2026-09-10T{hour:02d}:00:00Z" for hour in range(10, 21)),
    )
    by_key = {value.feature_key: value for value in values}

    assert by_key["precipitation_total_mm"].canonical_value == 55.0
    assert by_key["precipitation_max_hourly_mm"].canonical_value == 10.0
    assert by_key["shortwave_radiation_mean_w_m2"].canonical_value == 14.5
    assert by_key["shortwave_radiation_max_w_m2"].canonical_value == 19.0


def _neighbourhood_inputs(hours: range):
    footprint = SamplingFootprint(
        footprint_key="b" * 64,
        site_id=1,
        purpose="neighbourhood",
        sampling_method="radius",
        sampling_method_version="radius/1",
        radius_km=5.0,
        definition_sha256="c" * 64,
        nodes=(
            SamplingNode(row_index=0, column_index=0, latitude_deg=42.0, longitude_deg=23.0, distance_km=1.0),
            SamplingNode(row_index=0, column_index=1, latitude_deg=42.0, longitude_deg=23.1, distance_km=1.0),
            SamplingNode(row_index=1, column_index=0, latitude_deg=42.1, longitude_deg=23.0, distance_km=1.0),
        ),
    )
    site = SiteConfigSnapshot(
        site_id=1, site_slug="site", site_name="Site", site_time_zone="Europe/Sofia",
        latitude_deg=42.0, longitude_deg=23.0, coordinate_reference="WGS84",
        reference_elevation_msl_m=100.0, elevation_reference="msl",
    )
    records = tuple(
        NeighbourhoodNodeRecord(
            site_id=1, footprint_key="b" * 64, valid_at_utc=f"2026-09-10T{hour:02d}:00:00Z",
            fields=(
                NeighbourhoodFieldValues(field_code="air_pressure_pa", grain="surface", dimension="mean_sea_level", canonical_unit="Pa", values=(100000.0, 100010.0, 100020.0), source_selector_keys=("p",)),
                NeighbourhoodFieldValues(field_code="wind_u_m_s", grain="surface", canonical_unit="m/s", values=(1.0, 2.0, 1.0), source_selector_keys=("u",)),
                NeighbourhoodFieldValues(field_code="wind_v_m_s", grain="surface", canonical_unit="m/s", values=(1.0, 1.0, 2.0), source_selector_keys=("v",)),
            ),
        )
        for hour in hours
    )
    return (footprint,), (site,), records


def test_neighbourhood_builder_is_strict_and_uses_surface_msl_inputs() -> None:
    policy, _ = load_feature_policy()
    samples = tuple(_sample(hour) for hour in range(10, 21))
    footprints, sites, records = _neighbourhood_inputs(range(10, 21))
    values = build_daily_neighbourhood_features(
        samples, records, footprints, sites, policy.daily_fields,
        expected_instants_utc=tuple(sample.valid_at_utc for sample in samples),
    )
    by_key = {value.feature_key: value for value in values}

    assert by_key["neighbourhood_pressure_gradient_mean_pa_per_km"].canonical_value is not None
    assert by_key["neighbourhood_low_level_divergence_mean_s_inverse"].canonical_value is not None