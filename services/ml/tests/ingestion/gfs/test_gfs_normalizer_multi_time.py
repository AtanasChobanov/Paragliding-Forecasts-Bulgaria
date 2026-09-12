from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest

from paragliding_forecasts_ml.ingestion.atmosphere.contracts import ArtifactReference, StageManifest
from paragliding_forecasts_ml.ingestion.gfs.normalizer import (
    GfsCanonicalGridBatch,
    _resolve_adjacent_intervals,
    normalize,
)
from paragliding_forecasts_ml.ingestion.gfs.parser import (
    GfsNativeGridBatch,
    GfsNativeGridMessage,
    load_array,
)
from paragliding_forecasts_ml.ingestion.weather.artifacts import WeatherArtifactStore

RUN_KEY = "88888888-8888-4888-8888-888888888888"


def _array(
    store: WeatherArtifactStore, directory: Path, key: str, values: np.ndarray
) -> ArtifactReference:
    output = io.BytesIO()
    np.save(output, values.astype("<f8"), allow_pickle=False)
    return store.write_stage_bytes(
        directory,
        f"{key}.npy",
        key,
        output.getvalue(),
        media_type="application/x-npy",
        record_count=values.size,
    )


def _message(
    store: WeatherArtifactStore,
    directory: Path,
    *,
    selector: str,
    valid_at_utc: str,
    lead_hours: int,
    value: float,
    step_start_hours: int | None = None,
) -> GfsNativeGridMessage:
    key = f"{valid_at_utc.replace(':', '').replace('-', '')}-{selector}"
    values = _array(store, directory, f"{key}-values", np.full(12, value))
    missing = _array(store, directory, f"{key}-mask", np.zeros(12, dtype=bool))
    return GfsNativeGridMessage(
        selector_key=selector,
        message_number=1,
        raw_artifact_key=f"raw-{key}",
        native_message_reference=f"raw-{key}:message-1",
        reference_at_utc="2026-08-24T00:00:00Z",
        valid_at_utc=valid_at_utc,
        lead_hours=lead_hours,
        discipline=0,
        parameter_category=2,
        parameter_number=2,
        centre="kwbc",
        sub_centre=0,
        tables_version=2,
        local_tables_version=1,
        type_of_level="surface" if selector == "orog" else "heightAboveGround",
        level=0 if selector == "orog" else 10,
        native_field_name=selector,
        native_unit="m" if selector == "orog" else "m s**-1",
        step_type=(
            "accum"
            if selector == "apcp"
            else "avg"
            if selector in {"dswrf", "shtfl", "lhtfl"}
            else "instant"
        ),
        step_start_hours=(
            lead_hours
            if selector not in {"apcp", "dswrf", "shtfl", "lhtfl"}
            else step_start_hours
            if step_start_hours is not None
            else lead_hours - 1
        ),
        step_end_hours=lead_hours,
        statistic_type=(
            "1" if selector == "apcp" else "0" if selector in {"dswrf", "shtfl", "lhtfl"} else None
        ),
        quantization_step=0.0625 if selector == "apcp" else None,
        grid_type="regular_ll",
        ni=4,
        nj=3,
        latitude_of_first_grid_point_deg=1,
        longitude_of_first_grid_point_deg=0,
        latitude_of_last_grid_point_deg=-1,
        longitude_of_last_grid_point_deg=270,
        i_direction_increment_deg=90,
        j_direction_increment_deg=1,
        i_scans_negatively=False,
        j_scans_positively=False,
        j_points_are_consecutive=False,
        alternative_row_scanning=False,
        values=values,
        missing_mask=missing,
        quality_state="real",
    )


def test_normalizer_keeps_multi_valid_time_arrays_unique_and_promotes_orography(
    tmp_path, monkeypatch
) -> None:
    store = WeatherArtifactStore.create_fresh(RUN_KEY, project_root=tmp_path)
    directory = store.begin_stage("parser", "gfs-parser/4", "c" * 64)
    parser_manifest = store.write_stage_bytes(
        directory,
        "parser-stage-manifest.json",
        "stage_manifest",
        b"{}\n",
        media_type="application/json",
    )
    messages = tuple(
        _message(
            store,
            directory,
            selector=selector,
            valid_at_utc=valid_at_utc,
            lead_hours=lead_hours,
            value=value,
        )
        for valid_at_utc, lead_hours, u_value in (
            ("2026-08-24T06:00:00Z", 6, 1.0),
            ("2026-08-24T09:00:00Z", 9, -1.0),
        )
        for selector, value in (("orog", 150.0), ("ugrd_10m", u_value), ("vgrd_10m", 0.0))
    )
    native = GfsNativeGridBatch(
        run_key=RUN_KEY,
        raw_manifest=parser_manifest,
        eccodes_version="2.47.0",
        messages=messages,
    )
    monkeypatch.setattr(
        "paragliding_forecasts_ml.ingestion.gfs.normalizer.load_batch",
        lambda _store, _reference: native,
    )

    normalizer_manifest = normalize(store, parser_manifest, occurred_at_utc="2026-08-24T12:00:00Z")

    stage = StageManifest.model_validate_json(
        store.verify_reference(normalizer_manifest).read_bytes(), strict=True
    )
    batch_reference = next(
        item for item in stage.outputs if item.artifact_key == "gfs_canonical_grid_batch"
    )
    batch = GfsCanonicalGridBatch.model_validate_json(
        store.verify_reference(batch_reference).read_bytes(), strict=True
    )
    assert batch.grid.model_elevation_source_selector_keys == ("orog",)
    assert len(batch.surface_grains) == 8
    assert {grain.valid_at_utc for grain in batch.surface_grains} == {
        "2026-08-24T06:00:00Z",
        "2026-08-24T09:00:00Z",
    }
    artifact_keys = [grain.values.artifact_key for grain in batch.surface_grains]
    assert len(artifact_keys) == len(set(artifact_keys))
    assert batch.grid.values_order == "row_major_north_to_south_west_to_east"
    assert (
        next(
            item.dimension
            for item in batch.surface_grains
            if item.field_code == "wind_u_m_s" and item.source_selector_keys == ("ugrd_10m",)
        )
        == "10m_above_ground"
    )
    assert (
        next(item.dimension for item in batch.surface_grains if item.field_code == "wind_speed_m_s")
        == "10m_above_ground"
    )


def test_normalizer_retains_specific_humidity_and_upward_interval_fluxes(
    tmp_path, monkeypatch
) -> None:
    store = WeatherArtifactStore.create_fresh(RUN_KEY, project_root=tmp_path)
    directory = store.begin_stage("parser", "gfs-parser/4", "d" * 64)
    parser_manifest = store.write_stage_bytes(
        directory,
        "parser-stage-manifest.json",
        "stage_manifest",
        b"{}\n",
        media_type="application/json",
    )
    messages = tuple(
        _message(
            store,
            directory,
            selector=selector,
            valid_at_utc="2026-08-24T06:00:00Z",
            lead_hours=6,
            value=value,
        )
        for selector, value in (
            ("orog", 150.0),
            ("spfh_2m", 0.006),
            ("spfh_850", 0.005),
            ("shtfl", 25.0),
            ("lhtfl", 50.0),
        )
    )
    native = GfsNativeGridBatch(
        run_key=RUN_KEY,
        raw_manifest=parser_manifest,
        eccodes_version="2.47.0",
        messages=messages,
    )
    monkeypatch.setattr(
        "paragliding_forecasts_ml.ingestion.gfs.normalizer.load_batch",
        lambda _store, _reference: native,
    )

    normalizer_manifest = normalize(store, parser_manifest, occurred_at_utc="2026-08-24T12:00:00Z")
    stage = StageManifest.model_validate_json(
        store.verify_reference(normalizer_manifest).read_bytes(), strict=True
    )
    batch_reference = next(
        item for item in stage.outputs if item.artifact_key == "gfs_canonical_grid_batch"
    )
    batch = GfsCanonicalGridBatch.model_validate_json(
        store.verify_reference(batch_reference).read_bytes(), strict=True
    )
    surface_by_selector = {item.source_selector_keys[0]: item for item in batch.surface_grains}
    pressure_by_selector = {
        item.source_selector_keys[0]: item for item in batch.pressure_level_grains
    }

    assert surface_by_selector["spfh_2m"].field_code == "specific_humidity_kg_per_kg"
    assert surface_by_selector["spfh_2m"].dimension == "2m_above_ground"
    assert pressure_by_selector["spfh_850"].field_code == "specific_humidity_kg_per_kg"
    assert pressure_by_selector["spfh_850"].pressure_pa == 85_000
    for selector in ("shtfl", "lhtfl"):
        grain = surface_by_selector[selector]
        assert grain.statistic_type == "interval_average"
        assert grain.native_sign_convention == "upward_positive"
        assert grain.normalization_method == "gfs_native_adjacent_hour_interval_average"


def _reset_block_messages(
    store: WeatherArtifactStore,
    directory: Path,
    *,
    selector: str,
    values: tuple[float, ...],
) -> tuple[GfsNativeGridMessage, ...]:
    return tuple(
        _message(
            store,
            directory,
            selector=selector,
            valid_at_utc=f"2026-08-25T{lead - 24:02d}:00:00Z",
            lead_hours=lead,
            value=value,
            step_start_hours=30 if lead <= 36 else 36,
        )
        for lead, value in zip(range(31, 42), values, strict=True)
    )


def test_normalizer_resolves_exact_adjacent_intervals_across_reset_blocks(tmp_path) -> None:
    store = WeatherArtifactStore.create_fresh(RUN_KEY, project_root=tmp_path)
    directory = store.begin_stage("normalizer", "gfs-normalizer/5", "e" * 64)
    precipitation = _resolve_adjacent_intervals(
        store,
        directory,
        _reset_block_messages(
            store,
            directory,
            selector="apcp",
            values=(1, 3, 6, 10, 15, 21, 7, 15, 24, 34, 45),
        ),
        ("precipitation_amount_mm", "accumulation", None),
    )
    sensible = _resolve_adjacent_intervals(
        store,
        directory,
        _reset_block_messages(
            store,
            directory,
            selector="shtfl",
            values=(10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110),
        ),
        ("surface_sensible_heat_flux_upward_w_m2", "interval_average", "upward_positive"),
    )

    precipitation_by_lead = {item.lead_hours: item for item in precipitation}
    sensible_by_lead = {item.lead_hours: item for item in sensible}
    assert np.allclose(load_array(store, precipitation_by_lead[32].values), 2.0)
    assert np.allclose(load_array(store, precipitation_by_lead[37].values), 7.0)
    assert np.allclose(load_array(store, precipitation_by_lead[38].values), 8.0)
    assert precipitation_by_lead[32].interval_start_utc == "2026-08-25T07:00:00Z"
    assert precipitation_by_lead[32].interval_end_utc == "2026-08-25T08:00:00Z"
    assert len(precipitation_by_lead[32].source_native_message_references) == 2
    assert precipitation_by_lead[32].normalization_method == "gfs_kg_m2_to_mm_adjacent_difference"
    assert np.allclose(load_array(store, sensible_by_lead[32].values), 30.0)
    assert sensible_by_lead[32].native_sign_convention == "upward_positive"
    assert sensible_by_lead[32].derivation_method == "gfs_interval_average_adjacent_deaverage"


def test_normalizer_keeps_an_unresolved_interval_explicitly_missing(tmp_path) -> None:
    store = WeatherArtifactStore.create_fresh(RUN_KEY, project_root=tmp_path)
    directory = store.begin_stage("normalizer", "gfs-normalizer/5", "f" * 64)
    missing = _resolve_adjacent_intervals(
        store,
        directory,
        (
            _message(
                store,
                directory,
                selector="apcp",
                valid_at_utc="2026-08-25T08:00:00Z",
                lead_hours=32,
                value=3.0,
                step_start_hours=30,
            ),
        ),
        ("precipitation_amount_mm", "accumulation", None),
    )[0]

    assert missing.quality_state == "missing"
    assert missing.derivation_method == "gfs_adjacent_interval_predecessor_missing"
    assert np.isnan(load_array(store, missing.values)).all()


def test_normalizer_rejects_ambiguous_or_materially_decreasing_precipitation(tmp_path) -> None:
    store = WeatherArtifactStore.create_fresh(RUN_KEY, project_root=tmp_path)
    directory = store.begin_stage("normalizer", "gfs-normalizer/5", "a" * 64)
    duplicate = _message(
        store,
        directory,
        selector="apcp",
        valid_at_utc="2026-08-25T07:00:00Z",
        lead_hours=31,
        value=1.0,
        step_start_hours=30,
    )
    with pytest.raises(ValueError, match="ambiguous native interval"):
        _resolve_adjacent_intervals(
            store,
            directory,
            (duplicate, duplicate.model_copy(update={"message_number": 2})),
            ("precipitation_amount_mm", "accumulation", None),
        )

    directory = store.begin_stage("normalizer", "gfs-normalizer/5", "c" * 64)
    previous = _message(
        store,
        directory,
        selector="apcp",
        valid_at_utc="2026-08-25T07:00:00Z",
        lead_hours=31,
        value=0.125,
        step_start_hours=30,
    )
    current = _message(
        store,
        directory,
        selector="apcp",
        valid_at_utc="2026-08-25T08:00:00Z",
        lead_hours=32,
        value=0.0,
        step_start_hours=30,
    )
    with pytest.raises(ValueError, match="decreases beyond packing tolerance"):
        _resolve_adjacent_intervals(
            store,
            directory,
            (previous, current),
            ("precipitation_amount_mm", "accumulation", None),
        )


def test_normalizer_clamps_only_a_packing_sized_precipitation_decrease(tmp_path) -> None:
    store = WeatherArtifactStore.create_fresh(RUN_KEY, project_root=tmp_path)
    directory = store.begin_stage("normalizer", "gfs-normalizer/5", "b" * 64)
    previous = _message(
        store,
        directory,
        selector="apcp",
        valid_at_utc="2026-08-25T07:00:00Z",
        lead_hours=31,
        value=0.0625,
        step_start_hours=30,
    )
    current = _message(
        store,
        directory,
        selector="apcp",
        valid_at_utc="2026-08-25T08:00:00Z",
        lead_hours=32,
        value=0.0,
        step_start_hours=30,
    )

    resolved = _resolve_adjacent_intervals(
        store,
        directory,
        (previous, current),
        ("precipitation_amount_mm", "accumulation", None),
    )[1]

    assert np.allclose(load_array(store, resolved.values), 0.0)
    assert resolved.derivation_method == "gfs_precipitation_quantization_clamp"
    assert resolved.quality_state == "derived"
