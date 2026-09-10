"""Fail-closed S07 neighbourhood pressure-gradient and divergence calculations."""

from __future__ import annotations

from dataclasses import dataclass
from math import asin, atan2, cos, hypot, isfinite, pi, sin, sqrt

import numpy as np

EARTH_MEAN_RADIUS_KM = 6371.0088


class NeighbourhoodCoverageError(ValueError):
    """The exact S05 neighbourhood evidence cannot support a planar fit."""


@dataclass(frozen=True)
class NeighbourhoodObservation:
    """One finite S05 node value tuple for one site and valid instant."""

    node_key: str
    latitude_deg: float
    longitude_deg: float
    mean_sea_level_pressure_pa: float
    wind_u_m_s: float
    wind_v_m_s: float


@dataclass(frozen=True)
class LocalOffset:
    """One node's east/north displacement from the reviewed site, in kilometres."""

    east_km: float
    north_km: float


@dataclass(frozen=True)
class NeighbourhoodMetrics:
    """The retained S07 instantaneous planar-fit diagnostics."""

    pressure_gradient_pa_per_km: float
    low_level_divergence_s_inverse: float


def local_offset_km(
    site_latitude_deg: float,
    site_longitude_deg: float,
    node_latitude_deg: float,
    node_longitude_deg: float,
    *,
    earth_mean_radius_km: float = EARTH_MEAN_RADIUS_KM,
) -> LocalOffset:
    """Project one geodesic site-to-node offset to the local east/north tangent frame."""

    _require_coordinate(site_latitude_deg, site_longitude_deg, "Site")
    _require_coordinate(node_latitude_deg, node_longitude_deg, "Node")
    if not isfinite(earth_mean_radius_km) or earth_mean_radius_km <= 0:
        raise NeighbourhoodCoverageError("Earth mean radius must be finite and positive.")
    site_latitude = site_latitude_deg * pi / 180.0
    node_latitude = node_latitude_deg * pi / 180.0
    delta_latitude = node_latitude - site_latitude
    delta_longitude = (
        _normalize_longitude_delta(node_longitude_deg - site_longitude_deg) * pi / 180.0
    )
    haversine = (
        sin(delta_latitude / 2.0) ** 2
        + cos(site_latitude) * cos(node_latitude) * sin(delta_longitude / 2.0) ** 2
    )
    distance_km = 2.0 * earth_mean_radius_km * asin(sqrt(min(1.0, max(0.0, haversine))))
    bearing = atan2(
        sin(delta_longitude) * cos(node_latitude),
        cos(site_latitude) * sin(node_latitude)
        - sin(site_latitude) * cos(node_latitude) * cos(delta_longitude),
    )
    return LocalOffset(east_km=distance_km * sin(bearing), north_km=distance_km * cos(bearing))


def fit_neighbourhood_metrics(
    site_latitude_deg: float,
    site_longitude_deg: float,
    observations: tuple[NeighbourhoodObservation, ...],
    *,
    earth_mean_radius_km: float = EARTH_MEAN_RADIUS_KM,
) -> NeighbourhoodMetrics:
    """Fit unweighted local planes and return pressure gradient and surface divergence."""

    if len(observations) < 3:
        raise NeighbourhoodCoverageError("At least three neighbourhood nodes are required.")
    node_keys = [item.node_key for item in observations]
    if len(node_keys) != len(set(node_keys)) or any(not key for key in node_keys):
        raise NeighbourhoodCoverageError("Neighbourhood node keys must be non-empty and unique.")
    offsets = tuple(
        local_offset_km(
            site_latitude_deg,
            site_longitude_deg,
            item.latitude_deg,
            item.longitude_deg,
            earth_mean_radius_km=earth_mean_radius_km,
        )
        for item in observations
    )
    for item in observations:
        for label, value in (
            ("Mean sea-level pressure", item.mean_sea_level_pressure_pa),
            ("Wind U", item.wind_u_m_s),
            ("Wind V", item.wind_v_m_s),
        ):
            if not isfinite(value):
                raise NeighbourhoodCoverageError(f"{label} must be finite at every node.")
    matrix = np.asarray([[1.0, offset.east_km, offset.north_km] for offset in offsets], dtype=float)
    pressure = np.asarray([item.mean_sea_level_pressure_pa for item in observations], dtype=float)
    wind_u = np.asarray([item.wind_u_m_s for item in observations], dtype=float)
    wind_v = np.asarray([item.wind_v_m_s for item in observations], dtype=float)
    pressure_coefficients = _full_rank_coefficients(matrix, pressure, "Mean sea-level pressure")
    wind_u_coefficients = _full_rank_coefficients(matrix, wind_u, "Wind U")
    wind_v_coefficients = _full_rank_coefficients(matrix, wind_v, "Wind V")
    pressure_gradient = hypot(pressure_coefficients[1], pressure_coefficients[2])
    divergence = (wind_u_coefficients[1] + wind_v_coefficients[2]) / 1000.0
    if not isfinite(pressure_gradient) or not isfinite(divergence):
        raise NeighbourhoodCoverageError("Neighbourhood fit produced a non-finite diagnostic.")
    return NeighbourhoodMetrics(
        pressure_gradient_pa_per_km=float(pressure_gradient),
        low_level_divergence_s_inverse=float(divergence),
    )


def _full_rank_coefficients(matrix: np.ndarray, values: np.ndarray, label: str) -> np.ndarray:
    coefficients, _residuals, rank, _singular_values = np.linalg.lstsq(matrix, values, rcond=None)
    if rank != 3:
        raise NeighbourhoodCoverageError(f"{label} neighbourhood fit must have rank three.")
    if not np.all(np.isfinite(coefficients)):
        raise NeighbourhoodCoverageError(f"{label} neighbourhood fit coefficients must be finite.")
    return coefficients


def _normalize_longitude_delta(delta_longitude_deg: float) -> float:
    return (delta_longitude_deg + 180.0) % 360.0 - 180.0


def _require_coordinate(latitude_deg: float, longitude_deg: float, label: str) -> None:
    if not isfinite(latitude_deg) or not -90.0 <= latitude_deg <= 90.0:
        raise NeighbourhoodCoverageError(f"{label} latitude must be finite and within [-90, 90].")
    if not isfinite(longitude_deg) or not -180.0 <= longitude_deg <= 180.0:
        raise NeighbourhoodCoverageError(
            f"{label} longitude must be finite and within [-180, 180]."
        )
