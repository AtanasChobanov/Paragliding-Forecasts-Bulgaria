from __future__ import annotations

import io
from pathlib import Path

import numpy as np

from paragliding_forecasts_ml.ingestion.atmosphere.contracts import ArtifactReference, StageManifest
from paragliding_forecasts_ml.ingestion.gfs.normalizer import (
    GfsCanonicalGridBatch,
    normalize,
)
from paragliding_forecasts_ml.ingestion.gfs.parser import (
    GfsNativeGridBatch,
    GfsNativeGridMessage,
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
        step_type="instant",
        step_start_hours=lead_hours,
        step_end_hours=lead_hours,
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
    directory = store.begin_stage("parser", "gfs-parser/3", "c" * 64)
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
    assert batch.source_unsupported_selectors == ()
    assert len(batch.surface_grains) == 8
    assert {grain.valid_at_utc for grain in batch.surface_grains} == {
        "2026-08-24T06:00:00Z",
        "2026-08-24T09:00:00Z",
    }
    artifact_keys = [grain.values.artifact_key for grain in batch.surface_grains]
    assert len(artifact_keys) == len(set(artifact_keys))
    assert batch.grid.values_order == "row_major_north_to_south_west_to_east"
