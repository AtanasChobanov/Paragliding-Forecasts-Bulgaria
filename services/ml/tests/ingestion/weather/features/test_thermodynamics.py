from __future__ import annotations

import pytest

from paragliding_forecasts_ml.ingestion.weather.features.thermodynamics import (
    HeightProfilePoint,
    PressureProfilePoint,
    ThermodynamicError,
    mixed_layer_lcl_agl_m,
    romps_liquid_lcl_agl_m,
    thermal_strength_from_surface_fluxes,
)


def _pressure_profile() -> tuple[PressureProfilePoint, ...]:
    return (
        PressureProfilePoint(95_000.0, 292.0, 0.010),
        PressureProfilePoint(90_000.0, 290.0, 0.009),
        PressureProfilePoint(85_000.0, 288.0, 0.008),
        PressureProfilePoint(80_000.0, 286.0, 0.007),
        PressureProfilePoint(75_000.0, 284.0, 0.006),
    )


def _height_profile() -> tuple[HeightProfilePoint, ...]:
    return (
        HeightProfilePoint(500.0, 85_000.0, 287.0, 0.009),
        HeightProfilePoint(1_500.0, 80_000.0, 282.0, 0.008),
        HeightProfilePoint(3_000.0, 70_000.0, 275.0, 0.006),
    )


def test_romps_liquid_lcl_matches_the_author_reference_and_saturated_parcel() -> None:
    assert romps_liquid_lcl_agl_m(100_000.0, 300.0, 0.5) == pytest.approx(1433.844139279, rel=1e-10)
    assert romps_liquid_lcl_agl_m(100_000.0, 300.0, 1.0) == 0.0
    assert romps_liquid_lcl_agl_m(100_000.0, 300.0, 0.3) > romps_liquid_lcl_agl_m(
        100_000.0, 300.0, 0.5
    )


def test_romps_dry_and_supersaturated_limit_cases() -> None:
    assert romps_liquid_lcl_agl_m(100_000.0, 300.0, 0.0) == pytest.approx(1004.04 * 300.0 / 9.81)
    assert romps_liquid_lcl_agl_m(100_000.0, 300.0, 1.01) == 0.0
    with pytest.raises(ThermodynamicError, match="parcel_relative_humidity_invalid"):
        romps_liquid_lcl_agl_m(100_000.0, 300.0, -0.01)


def test_mixed_layer_lcl_requires_the_complete_lowest_100_hpa_layer() -> None:
    result = mixed_layer_lcl_agl_m(
        surface_pressure_pa=90_000.0,
        surface_temperature_k=290.0,
        surface_specific_humidity_kg_per_kg=0.009,
        profile=_pressure_profile(),
    )

    assert result > 0.0
    # The direct surface observation is the p_s anchor; the below-terrain
    # 95-kPa profile point must not be required for a 90--80-kPa layer.
    assert (
        mixed_layer_lcl_agl_m(
            surface_pressure_pa=90_000.0,
            surface_temperature_k=290.0,
            surface_specific_humidity_kg_per_kg=0.009,
            profile=_pressure_profile()[1:],
        )
        > 0.0
    )
    with pytest.raises(ThermodynamicError, match="pressure_boundary_not_bracketed"):
        mixed_layer_lcl_agl_m(
            surface_pressure_pa=90_000.0,
            surface_temperature_k=290.0,
            surface_specific_humidity_kg_per_kg=0.009,
            profile=_pressure_profile()[2:3],
        )


def test_mixed_layer_lcl_matches_an_independent_constant_theta_and_humidity_parcel() -> None:
    # At 100 kPa and 300 K, q=0.011091604604739841 gives 50% liquid RH.
    # The 90-kPa point has the same potential temperature and q, so pressure
    # mixing leaves the surface parcel unchanged. The LCL is the Romps reference.
    q = 0.011091604604739841
    result = mixed_layer_lcl_agl_m(
        surface_pressure_pa=100_000.0,
        surface_temperature_k=300.0,
        surface_specific_humidity_kg_per_kg=q,
        profile=(PressureProfilePoint(90_000.0, 291.0984368857919, q),),
    )

    assert result == pytest.approx(1433.844139279, rel=1e-9)


@pytest.mark.parametrize(
    ("surface_pressure", "surface_temperature", "surface_humidity"),
    (
        (0.0, 290.0, 0.009),
        (90_000.0, 0.0, 0.009),
        (90_000.0, 290.0, -0.001),
        (90_000.0, 290.0, 1.0),
        (float("nan"), 290.0, 0.009),
    ),
)
def test_mixed_layer_lcl_rejects_invalid_surface_states(
    surface_pressure: float, surface_temperature: float, surface_humidity: float
) -> None:
    with pytest.raises(ThermodynamicError, match="thermodynamic_input_invalid"):
        mixed_layer_lcl_agl_m(
            surface_pressure_pa=surface_pressure,
            surface_temperature_k=surface_temperature,
            surface_specific_humidity_kg_per_kg=surface_humidity,
            profile=_pressure_profile(),
        )


def test_mixed_layer_lcl_rejects_duplicate_pressure_even_with_enough_depth() -> None:
    with pytest.raises(ThermodynamicError, match="mixed_layer_profile_duplicate_pressure"):
        mixed_layer_lcl_agl_m(
            surface_pressure_pa=90_000.0,
            surface_temperature_k=290.0,
            surface_specific_humidity_kg_per_kg=0.009,
            profile=(_pressure_profile()[2], _pressure_profile()[2], *_pressure_profile()[3:]),
        )


def test_thermal_strength_preserves_signed_buoyancy_and_zeroes_nonconvective_w_star() -> None:
    kwargs = {
        "surface_pressure_pa": 90_000.0,
        "surface_temperature_k": 290.0,
        "surface_specific_humidity_kg_per_kg": 0.009,
        "provider_boundary_layer_height_agl_m": 1_000.0,
        "profile": _height_profile(),
    }
    positive = thermal_strength_from_surface_fluxes(
        **kwargs,
        sensible_heat_flux_upward_w_m2=150.0,
        latent_heat_flux_upward_w_m2=100.0,
    )
    neutral = thermal_strength_from_surface_fluxes(
        **kwargs,
        sensible_heat_flux_upward_w_m2=0.0,
        latent_heat_flux_upward_w_m2=0.0,
    )
    negative = thermal_strength_from_surface_fluxes(
        **kwargs,
        sensible_heat_flux_upward_w_m2=-100.0,
        latent_heat_flux_upward_w_m2=0.0,
    )

    assert positive.surface_buoyancy_flux_kinematic_m2_s3 > 0.0
    assert positive.convective_velocity_scale_m_s > 0.0
    assert neutral.surface_buoyancy_flux_kinematic_m2_s3 == 0.0
    assert neutral.convective_velocity_scale_m_s == 0.0
    assert negative.surface_buoyancy_flux_kinematic_m2_s3 < 0.0
    assert negative.convective_velocity_scale_m_s == 0.0


def test_thermal_strength_matches_a_constant_virtual_potential_temperature_reference() -> None:
    result = thermal_strength_from_surface_fluxes(
        surface_pressure_pa=100_000.0,
        surface_temperature_k=300.0,
        surface_specific_humidity_kg_per_kg=0.0,
        sensible_heat_flux_upward_w_m2=100.0,
        latent_heat_flux_upward_w_m2=0.0,
        provider_boundary_layer_height_agl_m=1_000.0,
        profile=(HeightProfilePoint(1_000.0, 100_000.0, 300.0, 0.0),),
    )
    # With constant p, T and q=0, mean theta_v=300 K exactly.
    density = 100_000.0 / (287.04 * 300.0)
    expected_buoyancy = (9.81 / 300.0) * 100.0 / (density * 1004.04)

    assert result.surface_buoyancy_flux_kinematic_m2_s3 == pytest.approx(expected_buoyancy)
    assert result.convective_velocity_scale_m_s == pytest.approx(
        (expected_buoyancy * 1_000.0) ** (1.0 / 3.0)
    )


@pytest.mark.parametrize(
    ("pbl_height", "sensible", "profile", "expected_reason"),
    (
        (2.0, 100.0, _height_profile(), "provider_boundary_layer_height_invalid"),
        (float("inf"), 100.0, _height_profile(), "provider_boundary_layer_height_invalid"),
        (1_000.0, float("nan"), _height_profile(), "surface_heat_flux_invalid"),
        (
            1_000.0,
            100.0,
            (HeightProfilePoint(500.0, 85_000.0, 287.0, 0.009),) * 2,
            "thermal_profile_duplicate_height",
        ),
        (
            1_000.0,
            100.0,
            (HeightProfilePoint(1.0, 85_000.0, 287.0, 0.009),),
            "thermal_profile_below_surface",
        ),
    ),
)
def test_thermal_strength_rejects_invalid_depth_flux_and_height_evidence(
    pbl_height: float,
    sensible: float,
    profile: tuple[HeightProfilePoint, ...],
    expected_reason: str,
) -> None:
    with pytest.raises(ThermodynamicError, match=expected_reason):
        thermal_strength_from_surface_fluxes(
            surface_pressure_pa=90_000.0,
            surface_temperature_k=290.0,
            surface_specific_humidity_kg_per_kg=0.009,
            sensible_heat_flux_upward_w_m2=sensible,
            latent_heat_flux_upward_w_m2=100.0,
            provider_boundary_layer_height_agl_m=pbl_height,
            profile=profile,
        )


def test_thermal_strength_refuses_an_unbracketed_boundary_layer() -> None:
    with pytest.raises(ThermodynamicError, match="boundary_layer_not_bracketed"):
        thermal_strength_from_surface_fluxes(
            surface_pressure_pa=90_000.0,
            surface_temperature_k=290.0,
            surface_specific_humidity_kg_per_kg=0.009,
            sensible_heat_flux_upward_w_m2=100.0,
            latent_heat_flux_upward_w_m2=100.0,
            provider_boundary_layer_height_agl_m=3_500.0,
            profile=_height_profile(),
        )
