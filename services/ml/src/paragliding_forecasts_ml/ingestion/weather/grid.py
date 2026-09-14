"""Source-neutral regular-grid geometry and canonical site-footprint helpers."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal, Protocol

import numpy as np
from pydantic import Field

from ..atmosphere.contracts import AtmosphericContract
from .serialization import canonical_json_bytes, sha256_bytes
from .sites import SiteSamplingConfig


class RegularGrid(Protocol):
    row_count: int
    column_count: int
    first_latitude_deg: float
    first_longitude_deg: float
    latitude_step_deg: float
    longitude_step_deg: float
    geometry_sha256: str


class GridGeometryError(RuntimeError):
    """A regular grid cannot represent the required canonical site footprint."""


class SamplingNode(AtmosphericContract):
    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)
    latitude_deg: float = Field(ge=-90, le=90)
    longitude_deg: float = Field(ge=-180, le=180)
    distance_km: float = Field(ge=0)
    interpolation_weight: float | None = Field(default=None, ge=0, le=1)


class SamplingFootprint(AtmosphericContract):
    footprint_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    site_id: int = Field(gt=0)
    purpose: Literal["point", "neighbourhood"]
    sampling_method: Literal["bilinear", "radius"]
    sampling_method_version: str
    radius_km: float | None = Field(default=None, gt=0)
    definition_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    nodes: tuple[SamplingNode, ...] = Field(min_length=1)


class SiteConfigSnapshot(AtmosphericContract):
    site_id: int = Field(gt=0)
    site_slug: str
    site_name: str
    site_time_zone: str
    latitude_deg: float = Field(ge=-90, le=90)
    longitude_deg: float = Field(ge=-180, le=180)
    coordinate_reference: str
    reference_elevation_msl_m: float
    elevation_reference: str


def snapshot_site_configs(
    sites: Sequence[SiteSamplingConfig],
) -> tuple[SiteConfigSnapshot, ...]:
    snapshots: list[SiteConfigSnapshot] = []
    for site in sites:
        if site.reference_elevation_msl_m is None or site.elevation_reference is None:
            raise GridGeometryError(f"Site {site.site_slug} lacks a reviewed elevation.")
        snapshots.append(
            SiteConfigSnapshot(
                site_id=site.site_id,
                site_slug=site.site_slug,
                site_name=site.site_name,
                site_time_zone=site.site_time_zone,
                latitude_deg=site.latitude_deg,
                longitude_deg=site.longitude_deg,
                coordinate_reference=site.coordinate_reference,
                reference_elevation_msl_m=site.reference_elevation_msl_m,
                elevation_reference=site.elevation_reference,
            )
        )
    return tuple(snapshots)


def site_config_fingerprint(snapshots: Sequence[SiteConfigSnapshot]) -> str:
    return sha256_bytes(
        canonical_json_bytes({"site_configs": [item.model_dump(mode="json") for item in snapshots]})
    )


def _longitude_for_storage(longitude_deg: float) -> float:
    value = (longitude_deg + 180.0) % 360.0 - 180.0
    return 180.0 if math.isclose(value, -180.0) and longitude_deg > 0 else value


def _haversine_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
    earth_radius_km: float,
) -> float:
    lat_a, lat_b = math.radians(latitude_a), math.radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = math.radians((longitude_b - longitude_a + 180.0) % 360.0 - 180.0)
    value = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2.0) ** 2
    )
    return earth_radius_km * 2.0 * math.asin(min(1.0, math.sqrt(value)))


def bilinear_footprint(
    grid: RegularGrid,
    site: SiteSamplingConfig,
    *,
    method_version: str,
    earth_radius_km: float,
) -> SamplingFootprint:
    row_position = (site.latitude_deg - grid.first_latitude_deg) / grid.latitude_step_deg
    if row_position < -1e-12 or row_position > grid.row_count - 1 + 1e-12:
        raise GridGeometryError(f"Site {site.site_slug} falls outside the grid latitude range.")
    row_position = min(max(row_position, 0.0), grid.row_count - 1)
    row_floor = math.floor(row_position)
    row_fraction = row_position - row_floor
    if math.isclose(row_fraction, 0.0, abs_tol=1e-12):
        row_fraction = 0.0
    row_ceil = min(row_floor + 1, grid.row_count - 1)

    longitude = site.longitude_deg % 360.0
    column_position = ((longitude - grid.first_longitude_deg) % 360.0) / (grid.longitude_step_deg)
    column_position %= grid.column_count
    column_floor = math.floor(column_position)
    column_fraction = column_position - column_floor
    if math.isclose(column_fraction, 0.0, abs_tol=1e-12):
        column_fraction = 0.0
    column_ceil = (column_floor + 1) % grid.column_count

    weighted_indices = (
        (row_floor, column_floor, (1.0 - row_fraction) * (1.0 - column_fraction)),
        (row_floor, column_ceil, (1.0 - row_fraction) * column_fraction),
        (row_ceil, column_floor, row_fraction * (1.0 - column_fraction)),
        (row_ceil, column_ceil, row_fraction * column_fraction),
    )
    combined: dict[tuple[int, int], float] = {}
    for row_index, column_index, weight in weighted_indices:
        if weight > 0:
            combined[(row_index, column_index)] = (
                combined.get((row_index, column_index), 0.0) + weight
            )
    nodes = tuple(
        SamplingNode(
            row_index=row_index,
            column_index=column_index,
            latitude_deg=grid.first_latitude_deg + row_index * grid.latitude_step_deg,
            longitude_deg=_longitude_for_storage(
                grid.first_longitude_deg + column_index * grid.longitude_step_deg
            ),
            distance_km=_haversine_km(
                site.latitude_deg,
                site.longitude_deg,
                grid.first_latitude_deg + row_index * grid.latitude_step_deg,
                grid.first_longitude_deg + column_index * grid.longitude_step_deg,
                earth_radius_km,
            ),
            interpolation_weight=weight,
        )
        for (row_index, column_index), weight in sorted(combined.items())
    )
    if not math.isclose(
        sum(node.interpolation_weight or 0.0 for node in nodes), 1.0, abs_tol=1e-12
    ):
        raise GridGeometryError("Bilinear footprint weights do not sum to one.")
    definition = {
        "site_id": site.site_id,
        "latitude_deg": site.latitude_deg,
        "longitude_deg": site.longitude_deg,
        "grid_geometry_sha256": grid.geometry_sha256,
        "method": "bilinear",
        "method_version": method_version,
        "nodes": [node.model_dump(mode="json") for node in nodes],
    }
    definition_sha256 = sha256_bytes(canonical_json_bytes(definition))
    return SamplingFootprint(
        footprint_key=definition_sha256,
        site_id=site.site_id,
        purpose="point",
        sampling_method="bilinear",
        sampling_method_version=method_version,
        definition_sha256=definition_sha256,
        nodes=nodes,
    )


def radius_footprint(
    grid: RegularGrid,
    site: SiteSamplingConfig,
    *,
    radius_km: float,
    method_version: str,
    earth_radius_km: float,
) -> SamplingFootprint:
    latitude_delta = math.degrees(radius_km / earth_radius_km)
    candidate_rows = [
        row
        for row in range(grid.row_count)
        if abs(grid.first_latitude_deg + row * grid.latitude_step_deg - site.latitude_deg)
        <= latitude_delta + abs(grid.latitude_step_deg)
    ]
    nodes: list[SamplingNode] = []
    for row_index in candidate_rows:
        latitude = grid.first_latitude_deg + row_index * grid.latitude_step_deg
        cosine = max(1e-12, abs(math.cos(math.radians(latitude))))
        longitude_delta = min(180.0, latitude_delta / cosine + grid.longitude_step_deg)
        for column_index in range(grid.column_count):
            longitude = grid.first_longitude_deg + column_index * grid.longitude_step_deg
            wrapped_delta = abs((longitude - site.longitude_deg + 180.0) % 360.0 - 180.0)
            if wrapped_delta > longitude_delta:
                continue
            distance = _haversine_km(
                site.latitude_deg,
                site.longitude_deg,
                latitude,
                longitude,
                earth_radius_km,
            )
            if distance <= radius_km + 1e-9:
                nodes.append(
                    SamplingNode(
                        row_index=row_index,
                        column_index=column_index,
                        latitude_deg=latitude,
                        longitude_deg=_longitude_for_storage(longitude),
                        distance_km=distance,
                    )
                )
    nodes.sort(key=lambda item: (item.row_index, item.column_index))
    if not nodes:
        raise GridGeometryError(f"Radius footprint for {site.site_slug} contains no nodes.")
    definition = {
        "site_id": site.site_id,
        "latitude_deg": site.latitude_deg,
        "longitude_deg": site.longitude_deg,
        "grid_geometry_sha256": grid.geometry_sha256,
        "method": "radius",
        "method_version": method_version,
        "radius_km": radius_km,
        "earth_radius_km": earth_radius_km,
        "nodes": [node.model_dump(mode="json") for node in nodes],
    }
    definition_sha256 = sha256_bytes(canonical_json_bytes(definition))
    return SamplingFootprint(
        footprint_key=definition_sha256,
        site_id=site.site_id,
        purpose="neighbourhood",
        sampling_method="radius",
        sampling_method_version=method_version,
        radius_km=radius_km,
        definition_sha256=definition_sha256,
        nodes=tuple(nodes),
    )


def strict_bilinear_value(
    values: np.ndarray,
    grid: RegularGrid,
    footprint: SamplingFootprint,
) -> float | None:
    flat = np.asarray(values).reshape(-1)
    if flat.size != grid.row_count * grid.column_count:
        raise GridGeometryError("Canonical value array does not match grid geometry.")
    weighted = 0.0
    for node in footprint.nodes:
        weight = node.interpolation_weight
        if weight is None:
            raise GridGeometryError("Point footprint node omits interpolation weight.")
        value = float(flat[node.row_index * grid.column_count + node.column_index])
        if not math.isfinite(value):
            return None
        weighted += weight * value
    return weighted
