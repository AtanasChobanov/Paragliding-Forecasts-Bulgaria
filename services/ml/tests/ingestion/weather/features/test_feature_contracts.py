from __future__ import annotations

import pytest
from pydantic import ValidationError

from paragliding_forecasts_ml.ingestion.atmosphere.contracts import FeatureSnapshot
from paragliding_forecasts_ml.ingestion.weather.features.contracts import (
    DailyFeatureSnapshot,
    FeatureLayer,
    FeatureQualitySummary,
    FeatureValue,
    MissingFeatureLocator,
)
from paragliding_forecasts_ml.ingestion.weather.features.policy import load_feature_policy

_RUN_KEY = "11111111-1111-4111-8111-111111111111"
_HASH = "a" * 64


def _value(
    feature_key: str,
    field_code: str,
    unit: str,
    value: float | None,
    *,
    missing_reason: str | None = None,
) -> FeatureValue:
    return FeatureValue(
        feature_key=feature_key,
        field_code=field_code,
        canonical_unit=unit,
        statistic="mean",
        canonical_value=value,
        quality_state="derived" if value is not None else "missing",
        missing_reason=missing_reason,
        derivation_method="test_derivation/1",
        derivation_version="test_derivation/1",
        input_field_codes=(field_code,),
    )


def test_feature_policy_uses_database_aligned_keys_and_excludes_inversion_metrics() -> None:
    policy, policy_sha256 = load_feature_policy()

    assert len(policy_sha256) == 64
    assert [(layer.layer_base_agl_m, layer.layer_top_agl_m) for layer in policy.profile_layers] == [
        (0.0, 1500.0),
        (1500.0, 3000.0),
    ]
    assert [entry.feature_key for entry in policy.daily_fields] == [
        "air_temperature_2m_mean_k",
        "air_temperature_2m_min_k",
        "air_temperature_2m_max_k",
        "dew_point_temperature_2m_mean_k",
        "relative_humidity_2m_mean_percent",
        "relative_humidity_2m_max_percent",
        "surface_pressure_mean_pa",
        "mean_sea_level_pressure_mean_pa",
        "wind_u_10m_mean_m_s",
        "wind_v_10m_mean_m_s",
        "wind_speed_10m_mean_m_s",
        "wind_speed_10m_max_m_s",
        "wind_direction_10m_mean_degrees_from_north",
        "provider_boundary_layer_height_agl_mean_m",
        "provider_boundary_layer_height_agl_max_m",
        "provider_cloud_base_agl_mean_m",
        "provider_cloud_base_agl_min_m",
        "provider_cloud_base_agl_max_m",
        "total_column_water_vapour_mean_kg_m2",
        "total_cloud_cover_mean_percent",
        "total_cloud_cover_max_percent",
        "low_cloud_cover_mean_percent",
        "low_cloud_cover_max_percent",
        "mid_cloud_cover_mean_percent",
        "high_cloud_cover_mean_percent",
        "precipitation_total_mm",
        "precipitation_max_hourly_mm",
        "shortwave_radiation_mean_w_m2",
        "shortwave_radiation_max_w_m2",
        "surface_sensible_heat_flux_mean_w_m2",
        "surface_latent_heat_flux_mean_w_m2",
        "cape_max_j_per_kg",
        "cin_magnitude_max_j_per_kg",
        "neighbourhood_pressure_gradient_mean_pa_per_km",
        "neighbourhood_pressure_gradient_max_pa_per_km",
        "neighbourhood_low_level_divergence_mean_s_inverse",
        "neighbourhood_low_level_divergence_min_s_inverse",
    ]
    assert [entry.feature_key for entry in policy.profile_layer_fields] == [
        "temperature_lapse_rate_mean_k_per_km",
        "temperature_lapse_rate_max_k_per_km",
        "relative_humidity_mean_percent",
        "specific_humidity_mean_kg_per_kg",
        "wind_u_mean_m_s",
        "wind_v_mean_m_s",
        "wind_speed_mean_m_s",
        "wind_speed_max_m_s",
        "wind_direction_mean_degrees_from_north",
        "wind_shear_mean_m_s_per_km",
        "wind_shear_max_m_s_per_km",
        "vertical_velocity_mean_pa_s",
        "vertical_velocity_min_pa_s",
    ]
    all_keys = [
        *(entry.feature_key for entry in policy.hourly_fields),
        *(entry.feature_key for entry in policy.daily_fields),
        *(entry.feature_key for entry in policy.profile_layer_fields),
    ]
    assert not any("inversion" in key for key in all_keys)


def test_v2_daily_contract_keeps_layer_identity_outside_feature_key() -> None:
    daily = _value("air_temperature_2m_mean_k", "air_temperature_k", "K", 290.0)
    lower = _value(
        "temperature_lapse_rate_mean_k_per_km", "temperature_lapse_rate_k_per_km", "K/km", 6.0
    )
    upper = _value(
        "temperature_lapse_rate_mean_k_per_km",
        "temperature_lapse_rate_k_per_km",
        "K/km",
        None,
        missing_reason="missing_hour",
    )

    snapshot = DailyFeatureSnapshot(
        run_key=_RUN_KEY,
        site_id=1,
        point_footprint_key=_HASH,
        neighbourhood_footprint_key="b" * 64,
        source_product_key="gfs.t00z.pgrb2.0p25.f006",
        local_date="2026-09-10",
        feature_contract_version="weather-feature-contract/2",
        input_fingerprint_sha256="c" * 64,
        input_sample_identity_keys=("d" * 64, "e" * 64),
        daily_fields=(daily,),
        profile_layers=(
            FeatureLayer(layer_base_agl_m=0.0, layer_top_agl_m=1500.0, fields=(lower,)),
            FeatureLayer(layer_base_agl_m=1500.0, layer_top_agl_m=3000.0, fields=(upper,)),
        ),
        missing_features=(
            MissingFeatureLocator(
                feature_key="temperature_lapse_rate_mean_k_per_km",
                layer_base_agl_m=1500.0,
                layer_top_agl_m=3000.0,
                missing_reason="missing_hour",
            ),
        ),
        quality_summary=FeatureQualitySummary(
            total_features=3, quality_counts={"derived": 2, "missing": 1}
        ),
    )

    assert (
        snapshot.profile_layers[0].fields[0].feature_key
        == snapshot.profile_layers[1].fields[0].feature_key
    )
    assert snapshot.missing_features[0].layer_base_agl_m == 1500.0


def test_v2_contract_rejects_missing_value_without_locator_or_reason() -> None:
    with pytest.raises(ValidationError, match="missing_reason"):
        _value("air_temperature_2m_mean_k", "air_temperature_k", "K", None)

    missing = _value(
        "air_temperature_2m_mean_k", "air_temperature_k", "K", None, missing_reason="missing_hour"
    )
    with pytest.raises(ValidationError, match="missing_features"):
        DailyFeatureSnapshot(
            run_key=_RUN_KEY,
            site_id=1,
            point_footprint_key=_HASH,
            neighbourhood_footprint_key="b" * 64,
            source_product_key="gfs.t00z.pgrb2.0p25.f006",
            local_date="2026-09-10",
            feature_contract_version="weather-feature-contract/2",
            input_fingerprint_sha256="c" * 64,
            input_sample_identity_keys=("d" * 64,),
            daily_fields=(missing,),
            profile_layers=(
                FeatureLayer(
                    layer_base_agl_m=0.0,
                    layer_top_agl_m=1500.0,
                    fields=(
                        _value(
                            "temperature_lapse_rate_mean_k_per_km",
                            "temperature_lapse_rate_k_per_km",
                            "K/km",
                            6.0,
                        ),
                    ),
                ),
            ),
            quality_summary=FeatureQualitySummary(
                total_features=2, quality_counts={"derived": 1, "missing": 1}
            ),
        )


def test_legacy_feature_snapshot_contract_remains_v1() -> None:
    assert FeatureSnapshot.model_fields["feature_snapshot_schema_version"].default == 1
