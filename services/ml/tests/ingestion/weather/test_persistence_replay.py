from __future__ import annotations

from copy import deepcopy

from paragliding_forecasts_ml.ingestion.weather.persistence import _canonical_run_graph


def test_canonical_run_graph_retains_every_non_surrogate_value() -> None:
    rows = {
        "weather_point_samples": [
            {
                "id": 101,
                "ingestion_run_id": 1,
                "product_valid_time_id": 21,
                "point_footprint_id": 31,
                "coverage_status": "complete",
                "air_temperature_2m_k": 294.5,
            }
        ],
        "weather_point_profile_levels": [
            {
                "id": 201,
                "weather_point_sample_id": 101,
                "pressure_pa": 90000.0,
                "air_temperature_k": 289.0,
            }
        ],
        "weather_point_convection_measurements": [],
        "weather_point_interval_measurements": [],
        "weather_daily_feature_snapshots": [],
        "weather_daily_feature_snapshot_inputs": [],
        "weather_daily_feature_profile_layers": [],
        "weather_field_provenance": [
            {
                "id": 301,
                "weather_point_sample_id": 101,
                "point_profile_level_id": None,
                "point_convection_measurement_id": None,
                "point_interval_measurement_id": None,
                "daily_feature_snapshot_id": None,
                "daily_feature_profile_layer_id": None,
                "field_code": "air_temperature_k",
                "field_variant": "2m",
                "quality_state": "real",
                "missing_reason_code": None,
            }
        ],
    }

    canonical = _canonical_run_graph(rows)
    reordered_ids = deepcopy(rows)
    reordered_ids["weather_point_samples"][0]["id"] = 999
    reordered_ids["weather_point_profile_levels"][0]["weather_point_sample_id"] = 999
    reordered_ids["weather_field_provenance"][0]["weather_point_sample_id"] = 999

    assert _canonical_run_graph(reordered_ids) == canonical

    changed_value = deepcopy(rows)
    changed_value["weather_point_profile_levels"][0]["air_temperature_k"] = 288.5

    assert _canonical_run_graph(changed_value) != canonical
