from __future__ import annotations

import pytest

from paragliding_forecasts_ml.ingestion.weather.features.builder import build_profile_layer
from paragliding_forecasts_ml.ingestion.weather.features.policy import load_feature_policy
from paragliding_forecasts_ml.ingestion.weather.spatial import (
    SampledField,
    SampledProfileLevel,
    SiteAlignedSample,
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
