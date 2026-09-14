from __future__ import annotations

from dataclasses import replace

import pytest

from paragliding_forecasts_ml.ingestion.weather.features.neighbourhood import (
    NeighbourhoodCoverageError,
    NeighbourhoodObservation,
    fit_neighbourhood_metrics,
    local_offset_km,
)

_SITE_LATITUDE = 42.0
_SITE_LONGITUDE = 23.0


def _locations() -> tuple[NeighbourhoodObservation, ...]:
    return (
        NeighbourhoodObservation("west", 42.0, 22.8, 0.0, 0.0, 0.0),
        NeighbourhoodObservation("east", 42.0, 23.2, 0.0, 0.0, 0.0),
        NeighbourhoodObservation("south", 41.8, 23.0, 0.0, 0.0, 0.0),
        NeighbourhoodObservation("north", 42.2, 23.0, 0.0, 0.0, 0.0),
    )


def _analytic_plane_observations() -> tuple[NeighbourhoodObservation, ...]:
    observations = []
    for location in _locations():
        offset = local_offset_km(
            _SITE_LATITUDE, _SITE_LONGITUDE, location.latitude_deg, location.longitude_deg
        )
        observations.append(
            replace(
                location,
                mean_sea_level_pressure_pa=100_000.0 + 2.0 * offset.east_km - 3.0 * offset.north_km,
                wind_u_m_s=4.0 + 0.5 * offset.east_km + 0.2 * offset.north_km,
                wind_v_m_s=-1.0 - 0.1 * offset.east_km + 0.25 * offset.north_km,
            )
        )
    return tuple(observations)


def test_planar_fit_recovers_gradient_and_surface_divergence_with_km_conversion() -> None:
    metrics = fit_neighbourhood_metrics(
        _SITE_LATITUDE, _SITE_LONGITUDE, _analytic_plane_observations()
    )

    assert metrics.pressure_gradient_pa_per_km == pytest.approx((2.0**2 + (-3.0) ** 2) ** 0.5)
    assert metrics.low_level_divergence_s_inverse == pytest.approx((0.5 + 0.25) / 1000.0)


def test_local_offset_normalizes_antimeridian_longitudes() -> None:
    east = local_offset_km(0.0, 179.9, 0.0, -179.9)
    west = local_offset_km(0.0, -179.9, 0.0, 179.9)

    assert east.east_km > 0
    assert west.east_km < 0
    assert abs(east.east_km) == pytest.approx(abs(west.east_km), rel=1e-12)


def test_planar_fit_rejects_duplicate_nodes_rank_deficiency_and_non_finite_evidence() -> None:
    observations = _analytic_plane_observations()

    with pytest.raises(NeighbourhoodCoverageError, match="unique"):
        fit_neighbourhood_metrics(
            _SITE_LATITUDE,
            _SITE_LONGITUDE,
            (
                observations[0],
                replace(observations[0], mean_sea_level_pressure_pa=100001.0),
                observations[1],
            ),
        )
    with pytest.raises(NeighbourhoodCoverageError, match="rank three"):
        fit_neighbourhood_metrics(
            _SITE_LATITUDE,
            _SITE_LONGITUDE,
            (
                observations[0],
                observations[1],
                replace(observations[0], node_key="west-two"),
            ),
        )
    with pytest.raises(NeighbourhoodCoverageError, match="finite"):
        fit_neighbourhood_metrics(
            _SITE_LATITUDE,
            _SITE_LONGITUDE,
            (replace(observations[0], wind_u_m_s=float("nan")), *observations[1:]),
        )
