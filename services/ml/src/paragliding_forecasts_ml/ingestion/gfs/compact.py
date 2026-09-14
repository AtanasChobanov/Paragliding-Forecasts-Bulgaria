"""Versioned lossless compact-grid contracts and consolidated NumPy storage."""

from __future__ import annotations

import io
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import Field, model_validator

from ..atmosphere.contracts import ArtifactReference, AtmosphericContract
from ..weather.artifacts import WeatherArtifactStore
from ..weather.grid import (
    SamplingFootprint,
    SiteConfigSnapshot,
    bilinear_footprint,
    radius_footprint,
    site_config_fingerprint,
    snapshot_site_configs,
)
from ..weather.sampling_policy import SamplingPolicy
from ..weather.serialization import canonical_json_bytes, sha256_bytes
from ..weather.sites import SiteSamplingConfig
from .models import GFS_GRID_KEY

COMPACT_DESCRIPTOR_SCHEMA_VERSION = 1
COMPACT_MATRIX_SLICE_SCHEMA_VERSION = 1
COMPACT_PACKED_MASK_SCHEMA_VERSION = 1
COMPACT_SELECTION_VERSION = "regular-grid-footprint-crop/1"
COMPACT_FLOAT_DTYPE = "<f8"
COMPACT_MASK_BIT_ORDER = "little"


class CompactGridError(RuntimeError):
    """Compact GFS evidence does not satisfy its immutable geometry contract."""


class GridNodeIndex(AtmosphericContract):
    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)


def _geometry_payload(
    *,
    row_count: int,
    column_count: int,
    first_latitude_deg: float,
    first_longitude_deg: float,
    last_latitude_deg: float,
    last_longitude_deg: float,
    latitude_step_deg: float,
    longitude_step_deg: float,
    i_scans_negatively: bool,
    j_scans_positively: bool,
    j_points_are_consecutive: bool,
    alternative_row_scanning: bool,
) -> dict[str, object]:
    return {
        "grid_key": GFS_GRID_KEY,
        "grid_type": "regular_ll",
        "row_count": row_count,
        "column_count": column_count,
        "first_latitude_deg": first_latitude_deg,
        "first_longitude_deg": first_longitude_deg,
        "last_latitude_deg": last_latitude_deg,
        "last_longitude_deg": last_longitude_deg,
        "latitude_step_deg": latitude_step_deg,
        "longitude_step_deg": longitude_step_deg,
        "longitude_wrap": True,
        "i_scans_negatively": i_scans_negatively,
        "j_scans_positively": j_scans_positively,
        "j_points_are_consecutive": j_points_are_consecutive,
        "alternative_row_scanning": alternative_row_scanning,
        "values_order": "row_major_north_to_south_west_to_east",
    }


class RegularLatLonGridGeometry(AtmosphericContract):
    """Verified native regular-LL geometry before any storage crop is applied."""

    geometry_schema_version: Literal[1] = 1
    grid_key: Literal["gfs_0p25_global"] = GFS_GRID_KEY
    grid_type: Literal["regular_ll"] = "regular_ll"
    row_count: int = Field(gt=0)
    column_count: int = Field(gt=0)
    first_latitude_deg: float = Field(ge=-90, le=90)
    first_longitude_deg: float = Field(ge=0, lt=360)
    last_latitude_deg: float = Field(ge=-90, le=90)
    last_longitude_deg: float = Field(ge=0, lt=360)
    latitude_step_deg: float = Field(lt=0)
    longitude_step_deg: float = Field(gt=0)
    longitude_wrap: Literal[True] = True
    i_scans_negatively: Literal[False] = False
    j_scans_positively: Literal[False] = False
    j_points_are_consecutive: Literal[False] = False
    alternative_row_scanning: Literal[False] = False
    values_order: Literal["row_major_north_to_south_west_to_east"] = (
        "row_major_north_to_south_west_to_east"
    )
    geometry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def geometry_must_be_exact(self) -> RegularLatLonGridGeometry:
        expected_last_latitude = (
            self.first_latitude_deg + (self.row_count - 1) * self.latitude_step_deg
        )
        expected_last_longitude = (
            self.first_longitude_deg + (self.column_count - 1) * self.longitude_step_deg
        ) % 360.0
        if not math.isclose(
            self.last_latitude_deg, expected_last_latitude, abs_tol=1e-9
        ) or not math.isclose(self.last_longitude_deg, expected_last_longitude, abs_tol=1e-9):
            raise ValueError("Regular-grid endpoints do not match dimensions and increments.")
        expected_hash = sha256_bytes(
            canonical_json_bytes(
                _geometry_payload(
                    row_count=self.row_count,
                    column_count=self.column_count,
                    first_latitude_deg=self.first_latitude_deg,
                    first_longitude_deg=self.first_longitude_deg,
                    last_latitude_deg=self.last_latitude_deg,
                    last_longitude_deg=self.last_longitude_deg,
                    latitude_step_deg=self.latitude_step_deg,
                    longitude_step_deg=self.longitude_step_deg,
                    i_scans_negatively=self.i_scans_negatively,
                    j_scans_positively=self.j_scans_positively,
                    j_points_are_consecutive=self.j_points_are_consecutive,
                    alternative_row_scanning=self.alternative_row_scanning,
                )
            )
        )
        if self.geometry_sha256 != expected_hash:
            raise ValueError("Native grid geometry fingerprint does not match its fields.")
        return self


def regular_latlon_geometry(
    *,
    row_count: int,
    column_count: int,
    first_latitude_deg: float,
    first_longitude_deg: float,
    last_latitude_deg: float,
    last_longitude_deg: float,
    latitude_step_deg: float,
    longitude_step_deg: float,
    i_scans_negatively: bool = False,
    j_scans_positively: bool = False,
    j_points_are_consecutive: bool = False,
    alternative_row_scanning: bool = False,
) -> RegularLatLonGridGeometry:
    payload = _geometry_payload(
        row_count=row_count,
        column_count=column_count,
        first_latitude_deg=first_latitude_deg,
        first_longitude_deg=first_longitude_deg,
        last_latitude_deg=last_latitude_deg,
        last_longitude_deg=last_longitude_deg,
        latitude_step_deg=latitude_step_deg,
        longitude_step_deg=longitude_step_deg,
        i_scans_negatively=i_scans_negatively,
        j_scans_positively=j_scans_positively,
        j_points_are_consecutive=j_points_are_consecutive,
        alternative_row_scanning=alternative_row_scanning,
    )
    return RegularLatLonGridGeometry(
        **payload,
        geometry_sha256=sha256_bytes(canonical_json_bytes(payload)),
    )


def global_to_local(
    node: GridNodeIndex,
    *,
    crop_min_row: int,
    crop_min_column: int,
    crop_row_count: int,
    crop_column_count: int,
) -> GridNodeIndex:
    row = node.row_index - crop_min_row
    column = node.column_index - crop_min_column
    if not 0 <= row < crop_row_count or not 0 <= column < crop_column_count:
        raise CompactGridError("Global node falls outside the compact crop.")
    return GridNodeIndex(row_index=row, column_index=column)


def local_to_global(
    node: GridNodeIndex,
    *,
    crop_min_row: int,
    crop_min_column: int,
    crop_row_count: int,
    crop_column_count: int,
) -> GridNodeIndex:
    if not 0 <= node.row_index < crop_row_count or not 0 <= node.column_index < crop_column_count:
        raise CompactGridError("Local node falls outside the compact crop.")
    return GridNodeIndex(
        row_index=node.row_index + crop_min_row,
        column_index=node.column_index + crop_min_column,
    )


def _descriptor_payload(descriptor: CompactGridDescriptor) -> dict[str, object]:
    payload = descriptor.model_dump(mode="json")
    payload.pop("selection_sha256", None)
    return payload


class CompactGridDescriptor(AtmosphericContract):
    """Complete selection identity and global-to-compact coordinate mapping."""

    descriptor_schema_version: Literal[1] = COMPACT_DESCRIPTOR_SCHEMA_VERSION
    selection_algorithm_version: Literal["regular-grid-footprint-crop/1"] = (
        COMPACT_SELECTION_VERSION
    )
    native_geometry: RegularLatLonGridGeometry
    crop_min_row: int = Field(ge=0)
    crop_max_row: int = Field(ge=0)
    crop_min_column: int = Field(ge=0)
    crop_max_column: int = Field(ge=0)
    compact_row_count: int = Field(gt=0)
    compact_column_count: int = Field(gt=0)
    compact_first_latitude_deg: float = Field(ge=-90, le=90)
    compact_last_latitude_deg: float = Field(ge=-90, le=90)
    compact_first_longitude_deg: float = Field(ge=0, lt=360)
    compact_last_longitude_deg: float = Field(ge=0, lt=360)
    values_order: Literal["row_major_north_to_south_west_to_east"] = (
        "row_major_north_to_south_west_to_east"
    )
    required_nodes: tuple[GridNodeIndex, ...] = Field(min_length=1)
    point_footprints: tuple[SamplingFootprint, ...] = Field(min_length=1)
    neighbourhood_footprints: tuple[SamplingFootprint, ...] = Field(min_length=1)
    site_configs: tuple[SiteConfigSnapshot, ...] = Field(min_length=1)
    site_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sampling_policy_version: str
    sampling_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def selection_must_be_self_consistent(self) -> CompactGridDescriptor:
        geometry = self.native_geometry
        if self.crop_max_row >= geometry.row_count or self.crop_max_column >= geometry.column_count:
            raise ValueError("Compact crop exceeds native grid dimensions.")
        if self.compact_row_count != self.crop_max_row - self.crop_min_row + 1 or (
            self.compact_column_count != self.crop_max_column - self.crop_min_column + 1
        ):
            raise ValueError("Compact shape does not match inclusive crop bounds.")
        expected_coordinates = (
            geometry.first_latitude_deg + self.crop_min_row * geometry.latitude_step_deg,
            geometry.first_latitude_deg + self.crop_max_row * geometry.latitude_step_deg,
            (geometry.first_longitude_deg + self.crop_min_column * geometry.longitude_step_deg)
            % 360,
            (geometry.first_longitude_deg + self.crop_max_column * geometry.longitude_step_deg)
            % 360,
        )
        actual_coordinates = (
            self.compact_first_latitude_deg,
            self.compact_last_latitude_deg,
            self.compact_first_longitude_deg,
            self.compact_last_longitude_deg,
        )
        if any(
            not math.isclose(actual, expected, abs_tol=1e-9)
            for actual, expected in zip(actual_coordinates, expected_coordinates, strict=True)
        ):
            raise ValueError("Compact coordinates do not match native geometry and bounds.")
        nodes = tuple(
            sorted(self.required_nodes, key=lambda item: (item.row_index, item.column_index))
        )
        if nodes != self.required_nodes or len(set(nodes)) != len(nodes):
            raise ValueError("Required nodes must be unique and globally row-major ordered.")
        footprint_nodes = {
            GridNodeIndex(row_index=node.row_index, column_index=node.column_index)
            for footprint in (*self.point_footprints, *self.neighbourhood_footprints)
            for node in footprint.nodes
        }
        if set(nodes) != footprint_nodes:
            raise ValueError("Required nodes must equal the complete footprint-node union.")
        for node in nodes:
            local = global_to_local(
                node,
                crop_min_row=self.crop_min_row,
                crop_min_column=self.crop_min_column,
                crop_row_count=self.compact_row_count,
                crop_column_count=self.compact_column_count,
            )
            if (
                local_to_global(
                    local,
                    crop_min_row=self.crop_min_row,
                    crop_min_column=self.crop_min_column,
                    crop_row_count=self.compact_row_count,
                    crop_column_count=self.compact_column_count,
                )
                != node
            ):
                raise ValueError("Compact node translation is not reversible.")
        site_ids = tuple(item.site_id for item in self.site_configs)
        if site_ids != tuple(sorted(site_ids)) or len(set(site_ids)) != len(site_ids):
            raise ValueError("Site snapshots must be unique and ordered by site id.")
        expected_footprint_ids = set(site_ids)
        if {item.site_id for item in self.point_footprints} != expected_footprint_ids or {
            item.site_id for item in self.neighbourhood_footprints
        } != expected_footprint_ids:
            raise ValueError("Every selected site requires point and neighbourhood footprints.")
        if self.site_config_sha256 != site_config_fingerprint(self.site_configs):
            raise ValueError("Site-config fingerprint does not match selected site rows.")
        if self.selection_sha256 != sha256_bytes(canonical_json_bytes(_descriptor_payload(self))):
            raise ValueError("Compact selection fingerprint does not match its descriptor.")
        return self


def plan_compact_grid(
    geometry: RegularLatLonGridGeometry,
    sites: Sequence[SiteSamplingConfig],
    policy: SamplingPolicy,
    policy_sha256: str,
) -> CompactGridDescriptor:
    ordered_sites = tuple(sorted(sites, key=lambda item: item.site_id))
    snapshots = snapshot_site_configs(ordered_sites)
    points = tuple(
        bilinear_footprint(
            geometry,
            site,
            method_version=policy.point_sampling.method_version,
            earth_radius_km=policy.neighbourhood_sampling.earth_mean_radius_km,
        )
        for site in ordered_sites
    )
    neighbourhoods = tuple(
        radius_footprint(
            geometry,
            site,
            radius_km=policy.neighbourhood_sampling.radius_km,
            method_version=policy.neighbourhood_sampling.method_version,
            earth_radius_km=policy.neighbourhood_sampling.earth_mean_radius_km,
        )
        for site in ordered_sites
    )
    required_nodes = tuple(
        GridNodeIndex(row_index=row, column_index=column)
        for row, column in sorted(
            {
                (node.row_index, node.column_index)
                for footprint in (*points, *neighbourhoods)
                for node in footprint.nodes
            }
        )
    )
    min_row = min(item.row_index for item in required_nodes)
    max_row = max(item.row_index for item in required_nodes)
    min_column = min(item.column_index for item in required_nodes)
    max_column = max(item.column_index for item in required_nodes)
    payload = {
        "native_geometry": geometry,
        "crop_min_row": min_row,
        "crop_max_row": max_row,
        "crop_min_column": min_column,
        "crop_max_column": max_column,
        "compact_row_count": max_row - min_row + 1,
        "compact_column_count": max_column - min_column + 1,
        "compact_first_latitude_deg": geometry.first_latitude_deg
        + min_row * geometry.latitude_step_deg,
        "compact_last_latitude_deg": geometry.first_latitude_deg
        + max_row * geometry.latitude_step_deg,
        "compact_first_longitude_deg": (
            geometry.first_longitude_deg + min_column * geometry.longitude_step_deg
        )
        % 360,
        "compact_last_longitude_deg": (
            geometry.first_longitude_deg + max_column * geometry.longitude_step_deg
        )
        % 360,
        "required_nodes": required_nodes,
        "point_footprints": points,
        "neighbourhood_footprints": neighbourhoods,
        "site_configs": snapshots,
        "site_config_sha256": site_config_fingerprint(snapshots),
        "sampling_policy_version": policy.policy_version,
        "sampling_policy_sha256": policy_sha256,
    }
    unhashed = CompactGridDescriptor.model_construct(
        **payload,
        selection_sha256="0" * 64,
    )
    return CompactGridDescriptor(
        **payload,
        selection_sha256=sha256_bytes(canonical_json_bytes(_descriptor_payload(unhashed))),
    )


class MatrixSliceReference(AtmosphericContract):
    matrix_slice_schema_version: Literal[1] = COMPACT_MATRIX_SLICE_SCHEMA_VERSION
    artifact: ArtifactReference
    matrix_row: int = Field(ge=0)
    expected_shape: tuple[int, int]
    expected_dtype: Literal["<f8"] = COMPACT_FLOAT_DTYPE
    selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def shape_must_be_positive(self) -> MatrixSliceReference:
        if any(item <= 0 for item in self.expected_shape):
            raise ValueError("Compact matrix slice shape must be positive.")
        return self


class PackedMaskReference(AtmosphericContract):
    packed_mask_schema_version: Literal[1] = COMPACT_PACKED_MASK_SCHEMA_VERSION
    artifact: ArtifactReference
    matrix_shape: tuple[int, int, int]
    bit_count: int = Field(gt=0)
    bit_order: Literal["little"] = COMPACT_MASK_BIT_ORDER
    selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def shape_must_match_bits(self) -> PackedMaskReference:
        if (
            any(item <= 0 for item in self.matrix_shape)
            or math.prod(self.matrix_shape) != self.bit_count
        ):
            raise ValueError("Packed-mask shape does not match its original bit count.")
        return self


def write_float64_matrix(
    store: WeatherArtifactStore,
    directory: Path,
    filename: str,
    artifact_key: str,
    matrix: np.ndarray,
) -> ArtifactReference:
    values = np.asarray(matrix)
    if values.ndim != 3 or values.dtype != np.dtype(COMPACT_FLOAT_DTYPE):
        raise CompactGridError(
            "Compact value matrix must have shape [message,row,column] and dtype <f8."
        )
    values = np.ascontiguousarray(values)
    buffer = io.BytesIO()
    np.save(buffer, values, allow_pickle=False)
    return store.write_stage_bytes(
        directory,
        filename,
        artifact_key,
        buffer.getvalue(),
        media_type="application/x-npy",
        record_count=int(values.size),
    )


def write_packed_missing_mask(
    store: WeatherArtifactStore,
    directory: Path,
    filename: str,
    artifact_key: str,
    mask: np.ndarray,
    *,
    selection_sha256: str,
) -> PackedMaskReference:
    values = np.asarray(mask)
    if values.ndim != 3 or values.dtype != np.dtype("bool"):
        raise CompactGridError("Compact missing mask must be a three-dimensional boolean matrix.")
    packed = np.packbits(np.ascontiguousarray(values).reshape(-1), bitorder=COMPACT_MASK_BIT_ORDER)
    buffer = io.BytesIO()
    np.save(buffer, packed, allow_pickle=False)
    artifact = store.write_stage_bytes(
        directory,
        filename,
        artifact_key,
        buffer.getvalue(),
        media_type="application/x-npy",
        record_count=int(values.size),
    )
    return PackedMaskReference(
        artifact=artifact,
        matrix_shape=values.shape,
        bit_count=int(values.size),
        selection_sha256=selection_sha256,
    )


def _load_matrix(store: WeatherArtifactStore, reference: ArtifactReference) -> np.ndarray:
    path = store.verify_reference(reference, expected_root=store.interim_dir)
    cached = store.verification.cached_matrix(reference, path)
    if cached is not None:
        return cached
    try:
        matrix = np.load(path, allow_pickle=False)
    except (OSError, ValueError) as error:
        raise CompactGridError("Compact NumPy artifact cannot be decoded safely.") from error
    if not isinstance(matrix, np.ndarray):
        raise CompactGridError("Compact NumPy artifact is not an array.")
    store.verification.register_matrix(reference, path, matrix)
    return matrix


def load_matrix_slice(
    store: WeatherArtifactStore,
    reference: MatrixSliceReference,
    *,
    expected_selection_sha256: str,
) -> np.ndarray:
    if reference.selection_sha256 != expected_selection_sha256:
        raise CompactGridError("Matrix slice belongs to another compact selection.")
    matrix = _load_matrix(store, reference.artifact)
    if matrix.ndim != 3 or matrix.dtype != np.dtype(reference.expected_dtype):
        raise CompactGridError("Compact matrix rank or dtype differs from its slice contract.")
    if tuple(matrix.shape[1:]) != reference.expected_shape:
        raise CompactGridError("Compact matrix shape differs from its slice contract.")
    if reference.matrix_row >= matrix.shape[0]:
        raise CompactGridError("Compact matrix row is outside the stored matrix.")
    result = matrix[reference.matrix_row]
    result.setflags(write=False)
    return result


def load_packed_missing_mask(
    store: WeatherArtifactStore,
    reference: PackedMaskReference,
    *,
    expected_selection_sha256: str,
) -> np.ndarray:
    if reference.selection_sha256 != expected_selection_sha256:
        raise CompactGridError("Packed mask belongs to another compact selection.")
    packed = _load_matrix(store, reference.artifact)
    expected_bytes = math.ceil(reference.bit_count / 8)
    if packed.ndim != 1 or packed.dtype != np.dtype("uint8") or packed.size != expected_bytes:
        raise CompactGridError("Packed mask storage differs from its contract.")
    bits = np.unpackbits(packed, bitorder=reference.bit_order)
    if bits[reference.bit_count :].any():
        raise CompactGridError("Packed mask contains non-zero padding bits.")
    result = bits[: reference.bit_count].astype(bool, copy=False).reshape(reference.matrix_shape)
    result.setflags(write=False)
    return result
