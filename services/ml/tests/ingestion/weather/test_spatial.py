from __future__ import annotations

import math

import numpy as np
import pytest

from paragliding_forecasts_ml.ingestion.atmosphere.contracts import ArtifactReference
from paragliding_forecasts_ml.ingestion.gfs.normalizer import GfsCanonicalGridDefinition
from paragliding_forecasts_ml.ingestion.weather.sampling_policy import load_sampling_policy
from paragliding_forecasts_ml.ingestion.weather.sites import SiteSamplingConfig
from paragliding_forecasts_ml.ingestion.weather.spatial import (
    SampledField,
    _derived_wind_fields,
    _haversine_km,
    bilinear_footprint,
    pressure_level_agl_heights,
    radius_footprint,
    strict_bilinear_value,
)

EARTH_RADIUS_KM = 6371.0088


def _reference() -> ArtifactReference:
    return ArtifactReference(
        artifact_key="model_elevation",
        relative_path="data/interim/weather/test/model-elevation.npy",
        sha256="a" * 64,
        byte_count=1,
        media_type="application/x-npy",
        record_count=12,
    )


def _grid(*, columns: int = 4, longitude_step: float = 90.0) -> GfsCanonicalGridDefinition:
    return GfsCanonicalGridDefinition(
        row_count=3,
        column_count=columns,
        first_latitude_deg=1.0,
        first_longitude_deg=0.0,
        latitude_step_deg=-1.0,
        longitude_step_deg=longitude_step,
        geometry_sha256="b" * 64,
        model_elevation_msl_m=_reference(),
        model_elevation_source_selector_keys=("orog",),
    )


def _site(latitude: float, longitude: float) -> SiteSamplingConfig:
    return SiteSamplingConfig(
        site_id=1,
        site_slug="test-site",
        site_name="Test site",
        site_time_zone="Europe/Sofia",
        latitude_deg=latitude,
        longitude_deg=longitude,
        coordinate_reference="test-v1",
        reference_elevation_msl_m=100,
        elevation_reference="test-dem-v1",
    )


def _point(latitude: float, longitude: float):
    return bilinear_footprint(
        _grid(),
        _site(latitude, longitude),
        method_version="regular-latlon-bilinear-v1",
        earth_radius_km=EARTH_RADIUS_KM,
    )


def test_bilinear_proves_affine_grid_value_and_exact_node_shapes() -> None:
    grid = _grid()
    values = np.array(
        [
            latitude + longitude
            for latitude in (1.0, 0.0, -1.0)
            for longitude in (0.0, 90.0, 180.0, 270.0)
        ]
    )
    footprint = _point(0.5, 45.0)

    assert len(footprint.nodes) == 4
    assert [node.interpolation_weight for node in footprint.nodes] == pytest.approx(
        [0.25, 0.25, 0.25, 0.25]
    )
    assert strict_bilinear_value(values, grid, footprint) == pytest.approx(45.5)

    exact = _point(0.0, 90.0)
    assert len(exact.nodes) == 1
    assert exact.nodes[0].interpolation_weight == 1
    assert strict_bilinear_value(values, grid, exact) == pytest.approx(90.0)


def test_bilinear_wraps_longitude_and_never_renormalizes_missing_nodes() -> None:
    grid = _grid()
    footprint = _point(0.5, -45.0)

    assert {node.column_index for node in footprint.nodes} == {0, 3}
    values = np.arange(12, dtype=float)
    values[footprint.nodes[0].row_index * 4 + footprint.nodes[0].column_index] = np.nan
    assert strict_bilinear_value(values, grid, footprint) is None


def test_radius_is_physical_inclusive_and_wraps_both_dateline_sides() -> None:
    grid = _grid(columns=360, longitude_step=1.0)
    site = _site(0.0, 0.0)
    boundary = _haversine_km(0.0, 0.0, 0.0, 1.0, EARTH_RADIUS_KM)

    footprint = radius_footprint(
        grid,
        site,
        radius_km=boundary,
        method_version="haversine-radius-v1",
        earth_radius_km=EARTH_RADIUS_KM,
    )

    columns = {node.column_index for node in footprint.nodes if node.row_index == 1}
    assert {0, 1, 359}.issubset(columns)
    assert max(node.distance_km for node in footprint.nodes) <= boundary + 1e-9
    assert all(node.interpolation_weight is None for node in footprint.nodes)


def test_wind_is_derived_after_component_sampling_not_as_a_circular_scalar() -> None:
    common = {
        "grain": "surface",
        "canonical_unit": "m/s",
        "quality_state": "real",
        "source_selector_keys": ("component",),
        "source_raw_artifact_keys": ("raw",),
        "source_native_message_references": ("message",),
    }
    u = SampledField(field_code="wind_u_m_s", canonical_value=1.0, **common)
    v = SampledField(field_code="wind_v_m_s", canonical_value=0.0, **common)

    speed, direction = _derived_wind_fields(u, v, grain="surface", pressure_pa=None)

    assert speed.canonical_value == 1.0
    assert direction.canonical_value == 270.0
    assert direction.derivation_method == "meteorological_direction_from_bilinear_u_v"


def test_pressure_levels_below_either_terrain_are_excluded_without_clamping() -> None:
    assert pressure_level_agl_heights(1500, 1000, 900) == (500, 600)
    assert pressure_level_agl_heights(950, 1000, 900) is None
    assert pressure_level_agl_heights(950, 900, 1000) is None


def test_policy_contains_only_bilinear_and_physical_radius_sampling() -> None:
    policy, policy_sha256 = load_sampling_policy()

    assert policy.policy_version == "canonical-site-sampling-policy-v2"
    assert policy.point_sampling.method == "bilinear"
    assert policy.neighbourhood_sampling.method == "physical_radius"
    assert policy.neighbourhood_sampling.radius_km == 50
    assert [item.dimension for item in policy.neighbourhood_sampling.fields[:3]] == [
        "mean_sea_level",
        "10m_above_ground",
        "10m_above_ground",
    ]
    assert "nearest" not in policy.model_dump_json()
    assert len(policy_sha256) == 64 and not math.isnan(float(int(policy_sha256, 16)))


def test_footprint_fingerprint_is_equal_for_equal_inputs_and_sensitive_to_coordinates() -> None:
    first = _point(0.5, 45.0)
    second = _point(0.5, 45.0)
    moved = _point(0.5, 45.1)

    assert first.definition_sha256 == second.definition_sha256
    assert first.nodes == second.nodes
    assert first.definition_sha256 != moved.definition_sha256
