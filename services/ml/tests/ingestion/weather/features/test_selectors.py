from __future__ import annotations

from dataclasses import dataclass

import pytest

from paragliding_forecasts_ml.ingestion.weather.features.selectors import (
    CanonicalFieldSelector,
    CanonicalSelectorError,
    resolve_canonical_field,
    selector_for_point_feature,
)


@dataclass(frozen=True)
class _Field:
    field_code: str
    grain: str
    dimension: str | None


@pytest.mark.parametrize(
    ("field_code", "variant", "grain", "dimension"),
    (
        ("air_temperature_k", "2m", "surface", "2m_above_ground"),
        ("dew_point_temperature_k", "2m", "surface", "2m_above_ground"),
        ("relative_humidity_percent", "2m", "surface", "2m_above_ground"),
        ("specific_humidity_kg_per_kg", "2m", "surface", "2m_above_ground"),
        ("air_pressure_pa", "surface", "surface", "surface"),
        ("air_pressure_pa", "mean_sea_level", "surface", "mean_sea_level"),
        ("wind_u_m_s", "10m", "surface", "10m_above_ground"),
        ("wind_v_m_s", "10m", "surface", "10m_above_ground"),
        ("provider_boundary_layer_height_agl_m", None, "surface", None),
        ("provider_cloud_base_agl_m", None, "surface", None),
        ("total_column_water_vapour_kg_m2", None, "surface", None),
        (
            "convective_available_potential_energy_j_per_kg",
            "surface_parcel",
            "convection",
            "surface",
        ),
        ("convective_inhibition_magnitude_j_per_kg", "surface_parcel", "convection", "surface"),
        ("cloud_cover_percent", "total", "surface", "total"),
        ("cloud_cover_percent", "low", "surface", "low"),
        ("cloud_cover_percent", "mid", "surface", "mid"),
        ("cloud_cover_percent", "high", "surface", "high"),
    ),
)
def test_locked_policy_identities_resolve_to_exact_canonical_selectors(
    field_code: str, variant: str | None, grain: str, dimension: str | None
) -> None:
    selector = selector_for_point_feature(field_code, variant)

    assert (selector.field_code, selector.grain, selector.dimension) == (
        field_code,
        grain,
        dimension,
    )


def test_exact_match_distinguishes_dimensions_and_grain() -> None:
    selector = selector_for_point_feature("air_pressure_pa", "mean_sea_level")
    expected = _Field("air_pressure_pa", "surface", "mean_sea_level")

    assert (
        resolve_canonical_field(
            (
                _Field("air_pressure_pa", "surface", "surface"),
                expected,
                _Field("air_pressure_pa", "pressure_level", "mean_sea_level"),
            ),
            selector,
        )
        == expected
    )


def test_wrong_dimension_has_no_fallback() -> None:
    selector = selector_for_point_feature("wind_u_m_s", "10m")

    assert resolve_canonical_field((_Field("wind_u_m_s", "surface", None),), selector) is None


def test_zero_matches_returns_none_and_duplicate_exact_match_fails_closed() -> None:
    selector = CanonicalFieldSelector("test", "air_temperature_k", "surface", "2m_above_ground")

    assert resolve_canonical_field((), selector) is None
    with pytest.raises(CanonicalSelectorError, match="test"):
        resolve_canonical_field(
            (
                _Field("air_temperature_k", "surface", "2m_above_ground"),
                _Field("air_temperature_k", "surface", "2m_above_ground"),
            ),
            selector,
        )


def test_unmapped_policy_identity_fails_closed() -> None:
    with pytest.raises(CanonicalSelectorError, match="No canonical selector"):
        selector_for_point_feature("unknown_field", "unknown_variant")
