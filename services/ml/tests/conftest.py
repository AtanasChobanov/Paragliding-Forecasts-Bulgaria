"""Shared synthetic inputs; never loads the user's local forecast data."""

import pytest

from paragliding_forecasts_ml.predictions.cloudbase.models import HourlyInput, ProfileLevel


@pytest.fixture
def cloudbase_column():
    return HourlyInput(
        run_key="11111111-1111-4111-8111-111111111111",
        site_id=1,
        site_slug="mountain",
        target_local_date="2024-06-29",
        valid_at_utc="2024-06-29T12:00:00Z",
        reference_at_utc="2024-06-28T06:00:00Z",
        issue_cutoff_utc="2024-06-28T13:00:00Z",
        source_ready_at_utc="2024-06-28T10:00:00Z",
        horizon_days=1,
        site_elevation_msl_m=1500,
        model_elevation_msl_m=500,
        surface_pressure_pa=95000,
        temperature_2m_k=300,
        specific_humidity_2m_kg_kg=0.010,
        pbl_model_agl_m=2500,
        low_cloud_percent=5,
        total_cloud_percent=10,
        sensible_heat_flux_w_m2=150,
        latent_heat_flux_w_m2=80,
        sensible_interval=("2024-06-29T11:00:00Z", "2024-06-29T12:00:00Z"),
        latent_interval=("2024-06-29T11:00:00Z", "2024-06-29T12:00:00Z"),
        profile=tuple(
            ProfileLevel(pressure_pa=p, height_msl_m=z, temperature_k=t, specific_humidity_kg_kg=q)
            for p, z, t, q in [
                (92500, 750, 297, 0.010),
                (90000, 1000, 294, 0.009),
                (85000, 1500, 289, 0.008),
                (80000, 2000, 285, 0.006),
                (70000, 3100, 275, 0.004),
                (60000, 4300, 267, 0.003),
                (50000, 5600, 255, 0.001),
            ]
        ),
    )
