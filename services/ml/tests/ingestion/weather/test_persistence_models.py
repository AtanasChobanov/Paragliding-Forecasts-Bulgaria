from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from paragliding_forecasts_ml.ingestion.atmosphere.contracts import ArtifactReference
from paragliding_forecasts_ml.ingestion.weather.features.policy import load_feature_policy
from paragliding_forecasts_ml.ingestion.weather.persistence import (
    CONVECTION_FEATURE_KEYS,
    DAILY_COLUMNS,
    HOURLY_POINT_COLUMNS,
    LAYER_COLUMNS,
    _point_column_for_source_field,
)
from paragliding_forecasts_ml.ingestion.weather.persistence_models import (
    WeatherPersistenceFailure,
    WeatherPersistenceReceipt,
    load_weather_usage_policy,
)

RUN_KEY = "123e4567-e89b-42d3-a456-426614174000"


def test_gfs_usage_policy_is_source_specific_and_hashes_exact_bytes(tmp_path) -> None:
    policy_path = tmp_path / "gfs-usage-policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "gfs_usage_policy_schema_version": 1,
                "permission_basis": "source_terms",
                "permission_reference": "Reviewed GFS usage terms",
                "model_training_allowed": True,
                "operational_use_allowed": False,
            }
        ),
        encoding="utf-8",
    )

    policy, digest = load_weather_usage_policy(policy_path, expected_source_id="gfs")

    assert policy.permission_basis == "source_terms"
    assert policy.model_training_allowed is True
    assert policy.operational_use_allowed is False
    assert len(digest) == 64


def test_weather_usage_policy_rejects_missing_or_untyped_usage_flags(tmp_path) -> None:
    policy_path = tmp_path / "invalid-weather-usage-policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "gfs_usage_policy_schema_version": 1,
                "permission_basis": "source_terms",
                "permission_reference": "Reviewed GFS usage terms",
                "model_training_allowed": "true",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="usage policy file is invalid"):
        load_weather_usage_policy(policy_path, expected_source_id="gfs")


def test_era5_policy_is_rejected_for_gfs_and_default_paths_are_source_bound(tmp_path) -> None:
    from paragliding_forecasts_ml.ingestion.weather.persistence_models import (
        default_weather_usage_policy_path,
    )

    policy_path = default_weather_usage_policy_path("era5", tmp_path)
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        json.dumps(
            {
                "era5_usage_policy_schema_version": 1,
                "permission_basis": "source_terms",
                "permission_reference": "Reviewed ERA5 usage terms",
                "model_training_allowed": False,
                "operational_use_allowed": False,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="gfs usage policy file is invalid"):
        load_weather_usage_policy(policy_path, expected_source_id="gfs")

    policy, _ = load_weather_usage_policy(
        None,
        expected_source_id="era5",
        project_root=tmp_path,
    )
    assert policy.permission_reference == "Reviewed ERA5 usage terms"
    assert default_weather_usage_policy_path("gfs", tmp_path) == (
        tmp_path / "data" / "local" / "gfs-usage-policy.json"
    )


def test_source_neutral_point_mapping_uses_explicit_canonical_vertical_identity() -> None:
    assert (
        _point_column_for_source_field(
            SimpleNamespace(field_code="air_temperature_k", dimension="2m_above_ground")
        )
        == "air_temperature_2m_k"
    )
    assert (
        _point_column_for_source_field(
            SimpleNamespace(field_code="wind_u_m_s", dimension="10m_above_ground")
        )
        == "wind_u_10m_m_s"
    )
    assert (
        _point_column_for_source_field(
            SimpleNamespace(field_code="cloud_cover_percent", dimension="low")
        )
        == "low_cloud_cover_percent"
    )


def test_active_policy_keys_have_exactly_one_persistence_destination() -> None:
    policy, _ = load_feature_policy()

    assert {entry.feature_key for entry in policy.hourly_fields} == (
        set(HOURLY_POINT_COLUMNS) | set(CONVECTION_FEATURE_KEYS)
    )
    assert {entry.feature_key for entry in policy.daily_fields} == set(DAILY_COLUMNS)
    assert {
        entry.feature_key
        for layer in policy.profile_layers
        for entry in policy.entries_for_layer(layer)
    } == set(LAYER_COLUMNS)


def test_failure_evidence_exposes_only_safe_retry_metadata() -> None:
    failure = WeatherPersistenceFailure(
        run_key=RUN_KEY,
        failure_kind="transaction",
        error_summary="OperationalError: synthetic mid-transaction failure",
        persistence_input_sha256="a" * 64,
        occurred_at_utc="2026-08-21T12:00:00Z",
    )

    assert failure.feature_manifest is None
    assert failure.failure_kind == "transaction"


@pytest.mark.parametrize("failure_kind", ["network", "failed", "unknown"])
def test_failure_evidence_rejects_unclassified_failure_kind(failure_kind: str) -> None:
    with pytest.raises(ValueError, match="failure_kind"):
        WeatherPersistenceFailure(
            run_key=RUN_KEY,
            failure_kind=failure_kind,
            error_summary="synthetic failure",
            occurred_at_utc="2026-08-21T12:00:00Z",
        )


def test_receipt_accepts_a_pipe_delimited_version_tuple() -> None:
    receipt = WeatherPersistenceReceipt(
        run_key=RUN_KEY,
        source_id="noaa_gfs_0p25_aws_grib2",
        source_product_key="gfs.t00z.pgrb2.0p25.f024",
        target_local_date="2026-08-21",
        database_identity="data/local/weather.db",
        feature_manifest=ArtifactReference(
            artifact_key="stage_manifest",
            relative_path="data/interim/weather/123e4567-e89b-42d3-a456-426614174000/feature/stage-manifest.json",
            sha256="a" * 64,
            byte_count=1,
            media_type="application/json",
        ),
        usage_policy_sha256="b" * 64,
        persistence_input_sha256="c" * 64,
        pipeline_version="gfs-collector/6|weather-spatial/4|weather-persistence/1",
        disposition="inserted",
        table_counts={"weather_point_samples": 11},
        persisted_graph_sha256="d" * 64,
        missing_quality_count=0,
        unsupported_quality_count=1,
        missing_reason_counts={"source_field_unavailable": 1},
        completed_at_utc="2026-08-21T12:00:00Z",
    )

    assert receipt.pipeline_version.endswith("weather-persistence/1")
