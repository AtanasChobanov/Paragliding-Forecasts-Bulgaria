from __future__ import annotations

import hashlib
import io
import sqlite3
from pathlib import Path

import numpy as np

from paragliding_forecasts_ml.ingestion.atmosphere.contracts import (
    ArtifactReference,
    StageManifest,
)
from paragliding_forecasts_ml.ingestion.gfs.compact import (
    MatrixSliceReference,
    plan_compact_grid,
    regular_latlon_geometry,
    write_float64_matrix,
)
from paragliding_forecasts_ml.ingestion.gfs.normalizer import (
    GfsCanonicalGridBatch,
    GfsCanonicalGridDefinition,
    GfsCanonicalGridMessage,
    GfsCompactCanonicalGridBatch,
    GfsCompactCanonicalGridDefinition,
)
from paragliding_forecasts_ml.ingestion.gfs.parser import load_array
from paragliding_forecasts_ml.ingestion.weather.artifacts import WeatherArtifactStore
from paragliding_forecasts_ml.ingestion.weather.sampling_policy import load_sampling_policy
from paragliding_forecasts_ml.ingestion.weather.sites import SiteSamplingConfig
from paragliding_forecasts_ml.ingestion.weather.spatial import (
    CanonicalSiteSampleBatch,
    NeighbourhoodNodeBatch,
    _sampled_field,
    sample_canonical_sites,
)

RUN_KEY = "99999999-9999-4999-8999-999999999999"


def _database(root: Path) -> None:
    path = root / "data" / "local" / "weather.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE sites (
          id INTEGER PRIMARY KEY,
          slug TEXT NOT NULL,
          name TEXT NOT NULL,
          time_zone TEXT NOT NULL,
          is_active INTEGER NOT NULL
        );
        CREATE TABLE weather_site_sampling_configs (
          site_id INTEGER PRIMARY KEY,
          latitude_deg REAL NOT NULL,
          longitude_deg REAL NOT NULL,
          coordinate_reference TEXT NOT NULL,
          reference_elevation_msl_m REAL,
          elevation_reference TEXT
        );
        INSERT INTO sites VALUES (1, 'test-site', 'Test site', 'Europe/Sofia', 1);
        INSERT INTO weather_site_sampling_configs VALUES
          (1, 0, 0, 'test-coordinate-v1', 100, 'test-elevation-v1');
        """
    )
    connection.commit()
    connection.close()


def _array_reference(
    store: WeatherArtifactStore,
    directory: Path,
    artifact_key: str,
    values: np.ndarray,
) -> ArtifactReference:
    output = io.BytesIO()
    np.save(output, values.astype("<f8"), allow_pickle=False)
    return store.write_stage_bytes(
        directory,
        f"{artifact_key}.npy",
        artifact_key,
        output.getvalue(),
        media_type="application/x-npy",
        record_count=values.size,
    )


def _grain(
    values: ArtifactReference,
    *,
    selector: str,
    field_code: str,
    unit: str,
    valid_at_utc: str,
    lead_hours: int,
    grain: str,
    dimension: str | None = None,
    pressure_pa: float | None = None,
) -> GfsCanonicalGridMessage:
    return GfsCanonicalGridMessage(
        field_code=field_code,
        grain=grain,
        source_selector_keys=(selector,),
        source_raw_artifact_keys=(f"raw-{valid_at_utc}-{selector}",),
        source_native_message_references=(f"message-{valid_at_utc}-{selector}",),
        canonical_unit=unit,
        values=values,
        quality_state="real",
        valid_at_utc=valid_at_utc,
        reference_at_utc="2026-08-24T00:00:00Z",
        lead_hours=lead_hours,
        pressure_pa=pressure_pa,
        dimension=dimension,
        normalization_method="test_identity",
        normalization_version="test-normalization/1",
    )


def _fixture(root: Path) -> tuple[WeatherArtifactStore, ArtifactReference, GfsCanonicalGridBatch]:
    _database(root)
    store = WeatherArtifactStore.create_fresh(RUN_KEY, project_root=root)
    directory = store.begin_stage("normalizer", "gfs-normalizer/2", "d" * 64)
    input_manifest = store.write_stage_bytes(
        directory,
        "input-stage-manifest.json",
        "stage_manifest",
        b"{}\n",
        media_type="application/json",
    )
    model_elevation = _array_reference(store, directory, "model-elevation", np.full(12, 150.0))
    grid = GfsCanonicalGridDefinition(
        row_count=3,
        column_count=4,
        first_latitude_deg=1,
        first_longitude_deg=0,
        latitude_step_deg=-1,
        longitude_step_deg=90,
        geometry_sha256="b" * 64,
        model_elevation_msl_m=model_elevation,
        model_elevation_source_selector_keys=("orog",),
    )
    surface: list[GfsCanonicalGridMessage] = []
    pressure: list[GfsCanonicalGridMessage] = []
    for valid_at_utc, lead_hours, u_value in (
        ("2026-08-24T06:00:00Z", 6, 1.0),
        ("2026-08-24T09:00:00Z", 9, -1.0),
    ):
        stamp = valid_at_utc.replace(":", "").replace("-", "")

        def values(name: str, value: float, *, stamp_value: str = stamp) -> ArtifactReference:
            return _array_reference(store, directory, f"{stamp_value}-{name}", np.full(12, value))

        surface.extend(
            (
                _grain(
                    values("prmsl", 101325),
                    selector="prmsl",
                    field_code="air_pressure_pa",
                    unit="Pa",
                    valid_at_utc=valid_at_utc,
                    lead_hours=lead_hours,
                    grain="surface",
                    dimension="mean_sea_level",
                ),
                _grain(
                    values("ugrd-10m", u_value),
                    selector="ugrd_10m",
                    field_code="wind_u_m_s",
                    unit="m/s",
                    valid_at_utc=valid_at_utc,
                    lead_hours=lead_hours,
                    grain="surface",
                    dimension="10m_above_ground",
                ),
                _grain(
                    values("vgrd-10m", 0),
                    selector="vgrd_10m",
                    field_code="wind_v_m_s",
                    unit="m/s",
                    valid_at_utc=valid_at_utc,
                    lead_hours=lead_hours,
                    grain="surface",
                    dimension="10m_above_ground",
                ),
            )
        )
        for level, height in ((925, 1000.0), (850, 50.0)):
            pressure.extend(
                (
                    _grain(
                        values(f"hgt-{level}", height),
                        selector=f"hgt_{level}",
                        field_code="geopotential_height_msl_m",
                        unit="m",
                        valid_at_utc=valid_at_utc,
                        lead_hours=lead_hours,
                        grain="pressure_level",
                        pressure_pa=level * 100,
                    ),
                    _grain(
                        values(f"ugrd-{level}", u_value),
                        selector=f"ugrd_{level}",
                        field_code="wind_u_m_s",
                        unit="m/s",
                        valid_at_utc=valid_at_utc,
                        lead_hours=lead_hours,
                        grain="pressure_level",
                        pressure_pa=level * 100,
                    ),
                    _grain(
                        values(f"vgrd-{level}", 0),
                        selector=f"vgrd_{level}",
                        field_code="wind_v_m_s",
                        unit="m/s",
                        valid_at_utc=valid_at_utc,
                        lead_hours=lead_hours,
                        grain="pressure_level",
                        pressure_pa=level * 100,
                    ),
                )
            )
    return (
        store,
        input_manifest,
        GfsCanonicalGridBatch(
            run_key=RUN_KEY,
            parser_stage_manifest=input_manifest,
            grid=grid,
            surface_grains=tuple(surface),
            pressure_level_grains=tuple(pressure),
        ),
    )


def _run(root: Path, monkeypatch):
    store, input_manifest, batch = _fixture(root)
    monkeypatch.setattr(
        store, "verify_boundary", lambda reference: store.verify_reference(reference)
    )
    monkeypatch.setattr(
        "paragliding_forecasts_ml.ingestion.weather.spatial.load_canonical_batch",
        lambda _store, _reference: batch,
    )
    database_path = root / "data" / "local" / "weather.db"
    database_sha256 = hashlib.sha256(database_path.read_bytes()).hexdigest()
    stage_reference = sample_canonical_sites(
        store,
        input_manifest,
        database_url="file:./data/local/weather.db",
        occurred_at_utc="2026-08-24T12:00:00Z",
        project_root=root,
    )
    assert hashlib.sha256(database_path.read_bytes()).hexdigest() == database_sha256
    stage_path = store.verify_reference(stage_reference)
    stage = StageManifest.model_validate_json(stage_path.read_bytes(), strict=True)
    sample_reference = next(
        item for item in stage.outputs if item.artifact_key == "canonical_site_sample_batch"
    )
    neighbourhood_reference = next(
        item for item in stage.outputs if item.artifact_key == "neighbourhood_node_batch"
    )
    samples = CanonicalSiteSampleBatch.model_validate_json(
        store.verify_reference(sample_reference).read_bytes(), strict=True
    )
    neighbourhoods = NeighbourhoodNodeBatch.model_validate_json(
        store.verify_reference(neighbourhood_reference).read_bytes(), strict=True
    )
    return sample_reference, neighbourhood_reference, samples, neighbourhoods


def _compact_run(root: Path, monkeypatch):
    store, input_manifest, legacy = _fixture(root)
    geometry = regular_latlon_geometry(
        row_count=3,
        column_count=4,
        first_latitude_deg=1.0,
        first_longitude_deg=0.0,
        last_latitude_deg=-1.0,
        last_longitude_deg=270.0,
        latitude_step_deg=-1.0,
        longitude_step_deg=90.0,
    )
    site = SiteSamplingConfig(
        site_id=1,
        site_slug="test-site",
        site_name="Test site",
        site_time_zone="Europe/Sofia",
        latitude_deg=0.0,
        longitude_deg=0.0,
        coordinate_reference="test-coordinate-v1",
        reference_elevation_msl_m=100.0,
        elevation_reference="test-elevation-v1",
    )
    policy, policy_sha256 = load_sampling_policy()
    descriptor = plan_compact_grid(geometry, (site,), policy, policy_sha256)
    legacy_grains = (*legacy.surface_grains, *legacy.pressure_level_grains)
    full_references = (legacy.grid.model_elevation_msl_m,) + tuple(
        item.values for item in legacy_grains
    )
    compact_values = np.stack(
        [load_array(store, reference).reshape(3, 4)[1:2, 0:1] for reference in full_references]
    ).astype("<f8", copy=False)
    directory = store.verify_reference(input_manifest).parent
    matrix = write_float64_matrix(
        store,
        directory,
        "compact-canonical-fixture.npy",
        "gfs_compact_parser_values_fixture",
        compact_values,
    )

    def matrix_slice(row: int) -> MatrixSliceReference:
        return MatrixSliceReference(
            artifact=matrix,
            matrix_row=row,
            expected_shape=(1, 1),
            selection_sha256=descriptor.selection_sha256,
        )

    compact_grains = tuple(
        grain.model_copy(update={"values": matrix_slice(row)})
        for row, grain in enumerate(legacy_grains, start=1)
    )
    compact = GfsCompactCanonicalGridBatch(
        run_key=RUN_KEY,
        parser_stage_manifest=input_manifest,
        grid=GfsCompactCanonicalGridDefinition(
            descriptor=descriptor,
            model_elevation_msl_m=matrix_slice(0),
            model_elevation_source_selector_keys=("orog",),
        ),
        reused_parser_values_matrix=matrix,
        surface_grains=compact_grains[: len(legacy.surface_grains)],
        pressure_level_grains=compact_grains[len(legacy.surface_grains) :],
    )
    monkeypatch.setattr(
        store, "verify_boundary", lambda reference: store.verify_reference(reference)
    )
    monkeypatch.setattr(
        "paragliding_forecasts_ml.ingestion.weather.spatial.load_canonical_batch",
        lambda _store, _reference: compact,
    )
    stage_reference = sample_canonical_sites(
        store,
        input_manifest,
        database_url="file:./data/local/weather.db",
        occurred_at_utc="2026-08-24T12:00:00Z",
        project_root=root,
    )
    stage = StageManifest.model_validate_json(
        store.verify_reference(stage_reference).read_bytes(), strict=True
    )
    sample_reference = next(
        item for item in stage.outputs if item.artifact_key == "canonical_site_sample_batch"
    )
    neighbourhood_reference = next(
        item for item in stage.outputs if item.artifact_key == "neighbourhood_node_batch"
    )
    samples = CanonicalSiteSampleBatch.model_validate_json(
        store.verify_reference(sample_reference).read_bytes(), strict=True
    )
    neighbourhoods = NeighbourhoodNodeBatch.model_validate_json(
        store.verify_reference(neighbourhood_reference).read_bytes(), strict=True
    )
    return samples, neighbourhoods, store


def test_spatial_sampler_preserves_unsupported_as_null_evidence(tmp_path) -> None:
    _store, _input_manifest, batch = _fixture(tmp_path)
    unsupported_grain = batch.surface_grains[0].model_copy(update={"quality_state": "unsupported"})

    sampled = _sampled_field(unsupported_grain, 101_325.0)

    assert sampled.quality_state == "unsupported"
    assert sampled.canonical_value is None


def test_spatial_stage_handles_multi_time_terrain_agl_exclusions_and_fingerprints(
    tmp_path, monkeypatch
) -> None:
    first = _run(tmp_path / "first", monkeypatch)
    second = _run(tmp_path / "second", monkeypatch)
    first_samples, first_neighbourhoods = first[2], first[3]

    assert len(first_samples.samples) == 2
    assert len(first_samples.pressure_level_exclusions) == 2
    assert {item.code for item in first_samples.pressure_level_exclusions} == {
        "below_site_or_model_terrain"
    }
    assert [sample.lead_hours for sample in first_samples.samples] == [6, 9]
    assert all(
        sample.terrain.model_minus_site_elevation_m == 50 for sample in first_samples.samples
    )
    assert all(len(sample.profile_levels) == 1 for sample in first_samples.samples)
    assert all(
        sample.profile_levels[0].level_height_agl_m == 900 for sample in first_samples.samples
    )
    assert all(
        sample.profile_levels[0].model_level_height_agl_m == 850 for sample in first_samples.samples
    )
    directions = [
        next(
            field.canonical_value
            for field in sample.fields
            if field.field_code == "wind_direction_degrees_from_north"
        )
        for sample in first_samples.samples
    ]
    assert directions == [270, 90]
    assert len(first_neighbourhoods.records) == 2
    assert all(len(record.fields) == 5 for record in first_neighbourhoods.records)
    assert len(first_samples.point_footprints[0].nodes) == 1
    assert len(first_samples.neighbourhood_footprints[0].nodes) == 1

    assert first[0].sha256 == second[0].sha256
    assert first[1].sha256 == second[1].sha256
    assert first_samples.sampling_fingerprint_sha256 == second[2].sampling_fingerprint_sha256


def test_compact_spatial_sampling_matches_full_grid_domain_outputs(tmp_path, monkeypatch) -> None:
    legacy_samples, legacy_neighbourhoods = _run(tmp_path / "legacy", monkeypatch)[2:]
    compact_samples, compact_neighbourhoods, compact_store = _compact_run(
        tmp_path / "compact", monkeypatch
    )

    assert len(compact_samples.samples) == len(legacy_samples.samples)
    for compact, legacy in zip(compact_samples.samples, legacy_samples.samples, strict=True):
        assert compact.valid_at_utc == legacy.valid_at_utc
        assert compact.lead_hours == legacy.lead_hours
        assert compact.terrain == legacy.terrain
        assert compact.fields == legacy.fields
        assert compact.profile_levels == legacy.profile_levels
    assert compact_samples.pressure_level_exclusions == legacy_samples.pressure_level_exclusions
    assert len(compact_neighbourhoods.records) == len(legacy_neighbourhoods.records)
    for compact, legacy in zip(
        compact_neighbourhoods.records, legacy_neighbourhoods.records, strict=True
    ):
        assert compact.site_id == legacy.site_id
        assert compact.valid_at_utc == legacy.valid_at_utc
        assert compact.fields == legacy.fields
    assert compact_samples.point_footprints[0].nodes == legacy_samples.point_footprints[0].nodes
    assert (
        compact_samples.neighbourhood_footprints[0].nodes
        == legacy_samples.neighbourhood_footprints[0].nodes
    )
    assert compact_store.verification.matrices_loaded == 1
