from __future__ import annotations

import io
import json

import numpy as np
import pytest
from pydantic import ValidationError

from paragliding_forecasts_ml.ingestion.gfs.compact import (
    CompactGridDescriptor,
    CompactGridError,
    GridNodeIndex,
    MatrixSliceReference,
    PackedMaskReference,
    compact_node_value,
    global_to_local,
    load_matrix_slice,
    load_packed_missing_mask,
    local_to_global,
    plan_compact_grid,
    regular_latlon_geometry,
    write_float64_matrix,
    write_packed_missing_mask,
)
from paragliding_forecasts_ml.ingestion.weather.artifacts import WeatherArtifactStore
from paragliding_forecasts_ml.ingestion.weather.sampling_policy import load_sampling_policy
from paragliding_forecasts_ml.ingestion.weather.sites import SiteSamplingConfig


def _geometry():
    return regular_latlon_geometry(
        row_count=721,
        column_count=1440,
        first_latitude_deg=90.0,
        first_longitude_deg=0.0,
        last_latitude_deg=-90.0,
        last_longitude_deg=359.75,
        latitude_step_deg=-0.25,
        longitude_step_deg=0.25,
    )


def _sites() -> tuple[SiteSamplingConfig, ...]:
    rows = (
        (1, "sofia-vitosha-kominite", "Sofia - Vitosha (Kominite)", 42.6013, 23.2844, 1793.929),
        (2, "zlatitsa", "Zlatitsa", 42.7302, 24.0923, 1129.007),
        (3, "sopot", "Sopot", 42.68733, 24.749962, 1445.337),
        (4, "nevsha", "Nevsha", 43.2622, 27.2846, 307.87),
        (5, "shumen", "Shumen", 43.2575, 26.9258, 447.1),
        (6, "pastrina", "Pastrina", 43.4282, 23.3032, 522.765),
        (7, "dobrich-region", "Dobrich region", 43.746321, 28.074025, 190.402),
    )
    return tuple(
        SiteSamplingConfig(
            site_id=site_id,
            site_slug=slug,
            site_name=name,
            site_time_zone="Europe/Sofia",
            latitude_deg=latitude,
            longitude_deg=longitude,
            coordinate_reference=(
                "kardam_accepted_flight_centroid_v1"
                if site_id == 7
                else "canonical_site_coordinate_v1"
            ),
            reference_elevation_msl_m=elevation,
            elevation_reference="copernicus_dem_glo30_egm2008_orthometric_bilinear_v1",
        )
        for site_id, slug, name, latitude, longitude, elevation in rows
    )


def _descriptor() -> CompactGridDescriptor:
    policy, policy_sha256 = load_sampling_policy()
    return plan_compact_grid(_geometry(), _sites(), policy, policy_sha256)


def _store_and_directory(tmp_path):
    store = WeatherArtifactStore.create_fresh("compact-test", project_root=tmp_path)
    directory = store.begin_stage("parser", "gfs-parser/6", "a" * 64)
    return store, directory


def _npy_bytes(values: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    np.save(buffer, values, allow_pickle=False)
    return buffer.getvalue()


def test_reviewed_sites_select_deterministic_77_node_8_by_24_crop() -> None:
    descriptor = _descriptor()
    repeated = _descriptor()

    assert len(descriptor.required_nodes) == 77
    assert (
        descriptor.crop_min_row,
        descriptor.crop_max_row,
        descriptor.crop_min_column,
        descriptor.crop_max_column,
    ) == (184, 191, 91, 114)
    assert (descriptor.compact_row_count, descriptor.compact_column_count) == (8, 24)
    assert descriptor.selection_sha256 == repeated.selection_sha256
    assert descriptor.model_dump(mode="json") == repeated.model_dump(mode="json")
    assert min(node.row_index for node in descriptor.required_nodes) == descriptor.crop_min_row
    assert max(node.row_index for node in descriptor.required_nodes) == descriptor.crop_max_row
    assert (
        min(node.column_index for node in descriptor.required_nodes) == descriptor.crop_min_column
    )
    assert (
        max(node.column_index for node in descriptor.required_nodes) == descriptor.crop_max_column
    )


def test_geometry_and_index_translation_fail_closed_without_clamping() -> None:
    geometry = _geometry()
    assert geometry.first_latitude_deg > geometry.last_latitude_deg
    assert geometry.first_longitude_deg < geometry.last_longitude_deg
    node = GridNodeIndex(row_index=191, column_index=114)
    local = global_to_local(
        node,
        crop_min_row=184,
        crop_min_column=91,
        crop_row_count=8,
        crop_column_count=24,
    )
    assert local == GridNodeIndex(row_index=7, column_index=23)
    assert (
        local_to_global(
            local,
            crop_min_row=184,
            crop_min_column=91,
            crop_row_count=8,
            crop_column_count=24,
        )
        == node
    )
    with pytest.raises(CompactGridError, match="outside"):
        global_to_local(
            GridNodeIndex(row_index=183, column_index=91),
            crop_min_row=184,
            crop_min_column=91,
            crop_row_count=8,
            crop_column_count=24,
        )
    with pytest.raises(ValidationError):
        regular_latlon_geometry(
            row_count=721,
            column_count=1440,
            first_latitude_deg=90.0,
            first_longitude_deg=0.0,
            last_latitude_deg=-90.0,
            last_longitude_deg=359.75,
            latitude_step_deg=-0.25,
            longitude_step_deg=0.25,
            j_scans_positively=True,
        )


def test_compact_lookup_rejects_unselected_cells_without_nearest_fallback() -> None:
    descriptor = _descriptor()
    required = set(descriptor.required_nodes)
    absent = next(
        GridNodeIndex(row_index=row, column_index=column)
        for row in range(descriptor.crop_min_row, descriptor.crop_max_row + 1)
        for column in range(descriptor.crop_min_column, descriptor.crop_max_column + 1)
        if GridNodeIndex(row_index=row, column_index=column) not in required
    )
    values = np.zeros((descriptor.compact_row_count, descriptor.compact_column_count), dtype="<f8")

    with pytest.raises(CompactGridError, match="absent"):
        compact_node_value(values, descriptor, absent)


def test_descriptor_rejects_tampered_geometry_sites_nodes_and_selection() -> None:
    descriptor = _descriptor()
    for field, value in (
        ("compact_row_count", 9),
        ("site_config_sha256", "f" * 64),
        ("selection_sha256", "e" * 64),
    ):
        payload = descriptor.model_dump(mode="json")
        payload[field] = value
        with pytest.raises(ValidationError):
            CompactGridDescriptor.model_validate_json(json.dumps(payload))
    payload = descriptor.model_dump(mode="json")
    payload["required_nodes"] = payload["required_nodes"][:-1]
    with pytest.raises(ValidationError, match="footprint-node union"):
        CompactGridDescriptor.model_validate_json(json.dumps(payload))


def test_consolidated_matrix_slice_is_cached_and_validated(tmp_path) -> None:
    store, directory = _store_and_directory(tmp_path)
    selection = "b" * 64
    matrix = np.arange(24, dtype="<f8").reshape(2, 3, 4)
    artifact = write_float64_matrix(
        store, directory, "compact-values.npy", "compact_values", matrix
    )
    reference = MatrixSliceReference(
        artifact=artifact,
        matrix_row=1,
        expected_shape=(3, 4),
        selection_sha256=selection,
    )

    first = load_matrix_slice(store, reference, expected_selection_sha256=selection)
    second = load_matrix_slice(store, reference, expected_selection_sha256=selection)

    assert np.array_equal(first, matrix[1])
    assert first.flags.writeable is False
    assert second is not first
    assert store.verification.matrices_loaded == 1
    with pytest.raises(CompactGridError, match="another compact selection"):
        load_matrix_slice(store, reference, expected_selection_sha256="c" * 64)
    with pytest.raises(CompactGridError, match="row"):
        load_matrix_slice(
            store,
            reference.model_copy(update={"matrix_row": 2}),
            expected_selection_sha256=selection,
        )
    with pytest.raises(CompactGridError, match="shape"):
        load_matrix_slice(
            store,
            reference.model_copy(update={"expected_shape": (4, 3)}),
            expected_selection_sha256=selection,
        )


def test_matrix_reader_rejects_wrong_dtype_and_corrupt_npy(tmp_path) -> None:
    store, directory = _store_and_directory(tmp_path)
    selection = "d" * 64
    float32_artifact = store.write_stage_bytes(
        directory,
        "float32.npy",
        "float32_values",
        _npy_bytes(np.zeros((1, 2, 2), dtype="<f4")),
        media_type="application/x-npy",
    )
    corrupt_artifact = store.write_stage_bytes(
        directory,
        "corrupt.npy",
        "corrupt_values",
        b"not-a-numpy-file",
        media_type="application/x-npy",
    )
    for artifact, message in (
        (float32_artifact, "dtype"),
        (corrupt_artifact, "decoded safely"),
    ):
        reference = MatrixSliceReference(
            artifact=artifact,
            matrix_row=0,
            expected_shape=(2, 2),
            selection_sha256=selection,
        )
        with pytest.raises(CompactGridError, match=message):
            load_matrix_slice(store, reference, expected_selection_sha256=selection)


def test_packed_mask_round_trip_fixed_bit_order_and_padding_validation(tmp_path) -> None:
    store, directory = _store_and_directory(tmp_path)
    selection = "e" * 64
    mask = np.array([True, False, True, False, False, False, False, True, True]).reshape(1, 3, 3)
    reference = write_packed_missing_mask(
        store,
        directory,
        "compact-mask.npy",
        "compact_missing_mask",
        mask,
        selection_sha256=selection,
    )
    restored = load_packed_missing_mask(store, reference, expected_selection_sha256=selection)
    assert np.array_equal(restored, mask)
    assert restored.flags.writeable is False
    path = store.verify_reference(reference.artifact)
    assert np.load(path, allow_pickle=False).tolist() == [133, 1]

    malicious_artifact = store.write_stage_bytes(
        directory,
        "bad-padding.npy",
        "bad_padding_mask",
        _npy_bytes(np.array([0, 128], dtype="uint8")),
        media_type="application/x-npy",
    )
    malicious = PackedMaskReference(
        artifact=malicious_artifact,
        matrix_shape=(1, 3, 3),
        bit_count=9,
        selection_sha256=selection,
    )
    with pytest.raises(CompactGridError, match="padding"):
        load_packed_missing_mask(store, malicious, expected_selection_sha256=selection)
