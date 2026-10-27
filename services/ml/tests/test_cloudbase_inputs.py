from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from paragliding_forecasts_ml.ingestion.atmosphere.contracts import ArtifactReference
from paragliding_forecasts_ml.ingestion.gfs.compact import (
    MatrixSliceReference,
    plan_compact_grid,
    regular_latlon_geometry,
    write_float64_matrix,
)
from paragliding_forecasts_ml.ingestion.gfs.normalizer import GfsCanonicalGridMessage
from paragliding_forecasts_ml.ingestion.gfs.profile import GFS_FEATURE_PROFILE_PRESSURES_HPA
from paragliding_forecasts_ml.ingestion.weather.artifacts import ArtifactError, WeatherArtifactStore
from paragliding_forecasts_ml.ingestion.weather.features.aggregation import sofia_flying_window
from paragliding_forecasts_ml.ingestion.weather.sampling_policy import load_sampling_policy
from paragliding_forecasts_ml.ingestion.weather.sites import SiteSamplingConfig
from paragliding_forecasts_ml.predictions.cloudbase.inputs import (
    CloudbaseInputError,
    RetainedReader,
    run_identity,
)

RUN = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def retained(tmp_path, cloudbase_column, monkeypatch):
    hour = cloudbase_column
    geometry = regular_latlon_geometry(
        row_count=721,
        column_count=1440,
        first_latitude_deg=90.0,
        first_longitude_deg=0.0,
        last_latitude_deg=-90.0,
        last_longitude_deg=359.75,
        latitude_step_deg=-0.25,
        longitude_step_deg=0.25,
    )
    policy, digest = load_sampling_policy()
    site = SiteSamplingConfig(
        1, "mountain", "Mountain", "Europe/Sofia", 42.6, 23.2, "synthetic", 1500, "synthetic_dem"
    )
    descriptor = plan_compact_grid(geometry, (site,), policy, digest)
    shape = (descriptor.compact_row_count, descriptor.compact_column_count)
    store = WeatherArtifactStore.create_fresh(RUN, project_root=tmp_path)
    directory = store.begin_stage("parser", "gfs-parser/6", "a" * 64)
    raw = []
    rows = [np.full(shape, 500.0)]
    units_by_code = {
        "air_pressure_pa": "Pa",
        "air_temperature_k": "K",
        "specific_humidity_kg_per_kg": "kg/kg",
        "geopotential_height_msl_m": "m",
        "provider_boundary_layer_height_agl_m": "m",
        "cloud_cover_percent": "%",
        "surface_sensible_heat_flux_upward_w_m2": "W/m2",
        "surface_latent_heat_flux_upward_w_m2": "W/m2",
    }
    times = sofia_flying_window(
        datetime.fromisoformat(hour.target_local_date).date()
    ).expected_instants_utc
    for valid in times:
        for code, dim, value in [
            ("air_pressure_pa", "surface", 95000),
            ("air_temperature_k", "2m_above_ground", 300),
            ("specific_humidity_kg_per_kg", "2m_above_ground", 0.010),
            ("provider_boundary_layer_height_agl_m", None, 2500),
            ("cloud_cover_percent", "low", 5),
            ("cloud_cover_percent", "total", 10),
            ("surface_sensible_heat_flux_upward_w_m2", None, 150),
            ("surface_latent_heat_flux_upward_w_m2", None, 80),
        ]:
            raw.append((valid, code, dim, None, len(rows)))
            rows.append(np.full(shape, value, dtype="<f8"))
        for hpa in GFS_FEATURE_PROFILE_PRESSURES_HPA:
            z = 500 + 8000 * np.log(950 / hpa)
            for code, value in [
                ("geopotential_height_msl_m", z),
                ("air_temperature_k", 300 - 0.008 * (z - 500)),
                ("specific_humidity_kg_per_kg", 0.009),
            ]:
                raw.append((valid, code, None, hpa * 100.0, len(rows)))
                rows.append(np.full(shape, value, dtype="<f8"))
    reference = write_float64_matrix(
        store, directory, "values.npy", "gfs_compact_native_values", np.stack(rows)
    )

    def matrix_slice(index):
        return MatrixSliceReference(
            artifact=reference,
            matrix_row=index,
            expected_shape=shape,
            selection_sha256=descriptor.selection_sha256,
        )

    surface, levels = [], []
    for valid, code, dim, pressure, index in raw:
        is_flux = code.startswith("surface_")
        start = (datetime.fromisoformat(valid) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        grain = GfsCanonicalGridMessage(
            field_code=code,
            grain="pressure_level" if pressure else "interval" if is_flux else "surface",
            source_selector_keys=(code,),
            source_raw_artifact_keys=("synthetic",),
            source_native_message_references=("synthetic",),
            canonical_unit=units_by_code[code],
            values=matrix_slice(index),
            quality_state="real",
            valid_at_utc=valid,
            reference_at_utc=hour.reference_at_utc,
            lead_hours=int(
                (
                    datetime.fromisoformat(valid) - datetime.fromisoformat(hour.reference_at_utc)
                ).total_seconds()
                / 3600
            ),
            pressure_pa=pressure,
            dimension=dim,
            interval_start_utc=start if is_flux else None,
            interval_end_utc=valid if is_flux else None,
        )
        (levels if pressure else surface).append(grain)
    batch = SimpleNamespace(
        grid=SimpleNamespace(descriptor=descriptor, model_elevation_msl_m=matrix_slice(0)),
        surface_grains=surface,
        pressure_level_grains=levels,
    )
    samples = SimpleNamespace(
        site_configs=descriptor.site_configs, point_footprints=descriptor.point_footprints
    )
    run = {
        "run_key": RUN,
        "status": "succeeded",
        "source_code": "noaa_gfs_0p25_aws_grib2",
        "source_kind": "forecast",
        "reference_at_utc": hour.reference_at_utc,
        "target_local_date": hour.target_local_date,
    }
    reader = RetainedReader(tmp_path, run)
    monkeypatch.setattr(reader, "load", lambda: (batch, samples))
    points = [
        {
            "site_id": 1,
            "valid_at_utc": t,
            "reference_at_utc": hour.reference_at_utc,
            "lead_hours": (
                datetime.fromisoformat(t) - datetime.fromisoformat(hour.reference_at_utc)
            ).total_seconds()
            / 3600,
            "required_inputs_last_modified_at_utc": hour.source_ready_at_utc,
            "mixed_layer_lcl_agl_m": 1200,
        }
        for t in times
    ]
    return SimpleNamespace(
        reader=reader, points=points, batch=batch, reference=reference, root=tmp_path
    )


def test_reader_keeps_model_levels_below_site_and_builds_eleven_hours(retained):
    rows = retained.reader.hours(retained.points)
    assert len(rows) == 11
    assert rows[0].profile[0].height_msl_m < rows[0].site_elevation_msl_m
    assert rows[0].profile[0].height_msl_m > rows[0].model_elevation_msl_m
    assert rows[0].surface_pressure_pa == 95000
    assert rows[0].sensible_interval[1] == rows[0].valid_at_utc
    assert not rows[0].input_issues


def test_missing_and_late_persisted_hours_remain_explicit(retained):
    rows = retained.reader.hours(retained.points[1:])
    assert len(rows) == 11 and rows[0].input_issues == ("unavailable:source_not_ready_by_cutoff",)
    retained.points[0]["required_inputs_last_modified_at_utc"] = "2024-06-28T14:00:00Z"
    assert retained.reader.hours(retained.points)[0].input_issues


def test_duplicate_hours_cycles_and_units_fail_before_results(retained):
    with pytest.raises(CloudbaseInputError, match="Duplicate persisted"):
        retained.reader.hours([*retained.points, retained.points[0]])
    original = retained.batch.surface_grains[0]
    retained.batch.surface_grains[0] = original.model_copy(update={"canonical_unit": "hPa"})
    with pytest.raises(CloudbaseInputError, match="units"):
        retained.reader.hours(retained.points)
    retained.batch.surface_grains[0] = original.model_copy(
        update={"reference_at_utc": "2024-06-28T12:00:00Z"}
    )
    with pytest.raises(CloudbaseInputError, match="cycles"):
        retained.reader.hours(retained.points)


def test_compact_array_tampering_is_detected_without_raw_payloads(retained):
    path = retained.root / retained.reference.relative_path
    content = bytearray(path.read_bytes())
    content[-1] ^= 1
    path.write_bytes(content)
    with pytest.raises(ArtifactError, match="SHA-256"):
        retained.reader.hours(retained.points)


def test_strict_missing_node_is_not_renormalized(retained):
    # A separate valid-hashed fixture with NaN tests sampling, not integrity failure.
    array = np.load(retained.root / retained.reference.relative_path, allow_pickle=False)
    array[0] = np.nan
    from paragliding_forecasts_ml.ingestion.weather.serialization import sha256_file

    with (retained.root / retained.reference.relative_path).open("wb") as output:
        np.save(output, array, allow_pickle=False)
    changed = retained.reference.model_copy(
        update={"sha256": sha256_file(retained.root / retained.reference.relative_path)}
    )
    retained.batch.grid.model_elevation_msl_m = (
        retained.batch.grid.model_elevation_msl_m.model_copy(update={"artifact": changed})
    )
    # Other slices are not read after terrain sampling alone.
    value = retained.reader.value(
        retained.batch,
        retained.batch.grid.model_elevation_msl_m,
        retained.reader.load()[1].point_footprints[0],
    )
    assert value is None


@pytest.mark.parametrize(
    "changes",
    [
        {"reference_at_utc": "2024-06-28T12:00:00Z"},
        {"target_local_date": "2024-07-02"},
        {"source_kind": "reanalysis"},
        {"status": "failed"},
    ],
)
def test_issue_identity_rejects_inadmissible_sources(retained, changes):
    with pytest.raises(CloudbaseInputError):
        run_identity({**retained.reader.run, **changes})


def test_reference_cannot_escape_this_run(retained):
    reference = ArtifactReference(
        artifact_key="stage_manifest",
        relative_path="data/interim/other.json",
        sha256="a" * 64,
        byte_count=1,
        media_type="application/json",
    )
    with pytest.raises(ArtifactError):
        retained.reader.read(reference)


def test_complete_retained_boundary_and_sqlite_read_without_raw_grib(retained, monkeypatch):
    """Exercise real contracts/SQL/array reads; every byte is synthetic test data."""
    import sqlite3

    from paragliding_forecasts_ml.ingestion.atmosphere.contracts import RawManifest, StageManifest
    from paragliding_forecasts_ml.ingestion.gfs.normalizer import (
        GfsCompactCanonicalGridBatch,
        GfsCompactCanonicalGridDefinition,
    )
    from paragliding_forecasts_ml.ingestion.weather.persistence_models import (
        WeatherPersistenceReceipt,
    )
    from paragliding_forecasts_ml.ingestion.weather.serialization import (
        canonical_json_bytes,
        sha256_file,
    )
    from paragliding_forecasts_ml.ingestion.weather.spatial import (
        CanonicalSiteSampleBatch,
        SampledField,
        SiteAlignedSample,
        TerrainDiagnostic,
    )
    from paragliding_forecasts_ml.ingestion.weather.state import RunStateLedger
    from paragliding_forecasts_ml.predictions.cloudbase.inputs import read_inputs

    reader = retained.reader
    store = reader.store
    timestamp = "2024-06-28T10:00:00Z"
    payload = store.write_raw_bytes(
        "synthetic_grib", "deleted.grib2", b"synthetic", media_type="application/x-grib2"
    )
    (store.raw_dir / "request-plan.json").write_bytes(b"synthetic")
    raw = store.write_raw_manifest(
        RawManifest(
            run_key=RUN,
            source_id="noaa_gfs_0p25_aws_grib2",
            source_kind="forecast",
            collector_version="gfs-collector/1",
            request_plan=payload.model_copy(
                update={
                    "relative_path": f"data/raw/weather/{RUN}/request-plan.json",
                    "artifact_key": "request_plan",
                }
            ),
            source_product_key="synthetic",
            source_url="https://example.invalid/gfs",
            permission_basis="synthetic",
            permission_reference="synthetic",
            retrieved_at_utc=timestamp,
            valid_from_utc=timestamp,
            valid_to_utc=timestamp,
            completed_at_utc=timestamp,
            artifacts=(payload,),
            status="complete",
        )
    )
    events = {"raw_complete": raw}

    def stage(name, event, inputs, outputs):
        directory = store.begin_stage(name, f"synthetic-{name}/1", "c" * 64)
        manifest = StageManifest(
            run_key=RUN,
            stage=name,
            producer_version=f"synthetic-{name}/1",
            input_fingerprint_sha256="c" * 64,
            inputs=tuple(inputs),
            outputs=tuple(outputs),
            disposition="complete",
            started_at_utc=timestamp,
            completed_at_utc=timestamp,
        )
        reference = store.write_stage_bytes(
            directory,
            "stage-manifest.json",
            "stage_manifest",
            canonical_json_bytes(manifest),
            media_type="application/json",
        )
        events[event] = reference
        return reference

    parser = stage("parser", "parsed", [raw], [retained.reference])
    batch = retained.batch
    full = GfsCompactCanonicalGridBatch(
        run_key=RUN,
        parser_stage_manifest=parser,
        reused_parser_values_matrix=retained.reference,
        grid=GfsCompactCanonicalGridDefinition(
            descriptor=batch.grid.descriptor,
            model_elevation_msl_m=batch.grid.model_elevation_msl_m,
            model_elevation_source_selector_keys=("orog",),
        ),
        surface_grains=tuple(batch.surface_grains),
        pressure_level_grains=tuple(batch.pressure_level_grains),
    )
    directory = store.begin_stage("normalizer", "synthetic-normalizer/1", "b" * 64)
    canonical = store.write_stage_bytes(
        directory,
        "batch.json",
        "gfs_compact_canonical_grid_batch",
        canonical_json_bytes(full),
        media_type="application/json",
    )
    normalizer = stage("normalizer", "normalized", [parser, retained.reference], [canonical])
    descriptor = batch.grid.descriptor
    sample = SiteAlignedSample(
        sample_identity_key="c" * 64,
        site_id=1,
        point_footprint_key=descriptor.point_footprints[0].footprint_key,
        neighbourhood_footprint_key=descriptor.neighbourhood_footprints[0].footprint_key,
        reference_at_utc=reader.run["reference_at_utc"],
        valid_at_utc=retained.points[0]["valid_at_utc"],
        valid_local_date=reader.run["target_local_date"],
        lead_hours=int(retained.points[0]["lead_hours"]),
        terrain=TerrainDiagnostic(
            site_elevation_msl_m=1500,
            model_elevation_msl_m=500,
            model_minus_site_elevation_m=-1000,
            absolute_mismatch_m=1000,
        ),
        fields=(
            SampledField(
                field_code="air_temperature_k",
                grain="surface",
                canonical_unit="K",
                canonical_value=300,
                quality_state="real",
                source_selector_keys=("tmp",),
                source_raw_artifact_keys=("synthetic",),
                source_native_message_references=("synthetic",),
            ),
        ),
        profile_levels=(),
    )
    samples = CanonicalSiteSampleBatch(
        run_key=RUN,
        normalizer_stage_manifest=normalizer,
        grid_key="gfs_0p25_global",
        policy_version="synthetic/1",
        policy_sha256="d" * 64,
        site_config_sha256=descriptor.site_config_sha256,
        sampling_fingerprint_sha256="e" * 64,
        grid_geometry_sha256=descriptor.native_geometry.geometry_sha256,
        site_configs=descriptor.site_configs,
        point_footprints=descriptor.point_footprints,
        neighbourhood_footprints=descriptor.neighbourhood_footprints,
        samples=(sample,),
        pressure_level_exclusions=(),
    )
    directory = store.begin_stage("spatial", "synthetic-spatial/1", "b" * 64)
    sampled = store.write_stage_bytes(
        directory,
        "samples.json",
        "canonical_site_sample_batch",
        canonical_json_bytes(samples),
        media_type="application/json",
    )
    spatial = stage("spatial", "spatially_aligned", [normalizer], [sampled])
    validation = stage("validator", "validated", [spatial], [sampled])
    feature = stage("feature_builder", "features_built", [validation], [sampled])
    receipt = WeatherPersistenceReceipt(
        run_key=RUN,
        source_id="noaa_gfs_0p25_aws_grib2",
        source_product_key="synthetic",
        target_local_date=reader.run["target_local_date"],
        database_identity="data/local/synthetic.db",
        feature_manifest=feature,
        usage_policy_sha256="f" * 64,
        persistence_input_sha256="a" * 64,
        pipeline_version="synthetic/1",
        disposition="inserted",
        table_counts={},
        persisted_graph_sha256="a" * 64,
        missing_quality_count=0,
        unsupported_quality_count=0,
        missing_reason_counts={},
        completed_at_utc=timestamp,
    )
    directory = store.begin_stage("persistence", "weather-persistence/3", "b" * 64)
    events["persisted"] = store.write_stage_bytes(
        directory,
        "receipt.json",
        "weather_persistence_receipt",
        canonical_json_bytes(receipt),
        media_type="application/json",
    )
    snapshot = SimpleNamespace(
        effective_event=lambda event: SimpleNamespace(evidence=events[event])
    )
    monkeypatch.setattr(RunStateLedger, "load_state", lambda _: snapshot)
    # The original bytes are deliberately gone. The retained boundary still works.
    (retained.root / payload.relative_path).unlink()
    db = retained.root / "data/local/synthetic.db"
    db.parent.mkdir(parents=True)
    connection = sqlite3.connect(db)
    connection.executescript("""
        CREATE TABLE weather_sources(id INTEGER PRIMARY KEY,code TEXT,source_kind TEXT);
        CREATE TABLE weather_product_runs(id INTEGER PRIMARY KEY,source_id INTEGER,reference_at_utc TEXT);
        CREATE TABLE weather_ingestion_runs(id INTEGER PRIMARY KEY,run_key TEXT,product_run_id INTEGER,status TEXT,target_local_date TEXT,raw_manifest_sha256 TEXT,feature_manifest_sha256 TEXT,persistence_input_sha256 TEXT);
        CREATE TABLE weather_sampling_footprints(id INTEGER PRIMARY KEY,site_id INTEGER,purpose TEXT);
        CREATE TABLE weather_product_valid_times(id INTEGER PRIMARY KEY,product_run_id INTEGER,valid_at_utc TEXT,lead_hours REAL,required_inputs_last_modified_at_utc TEXT);
        CREATE TABLE weather_point_samples(id INTEGER PRIMARY KEY,ingestion_run_id INTEGER,point_footprint_id INTEGER,product_valid_time_id INTEGER,mixed_layer_lcl_agl_m REAL);
    """)
    connection.execute(
        "INSERT INTO weather_sources VALUES(1,?,?)", ("noaa_gfs_0p25_aws_grib2", "forecast")
    )
    connection.execute(
        "INSERT INTO weather_product_runs VALUES(1,1,?)", (reader.run["reference_at_utc"],)
    )
    connection.execute(
        "INSERT INTO weather_ingestion_runs VALUES(1,?,1,'succeeded',?,?,?,?)",
        (RUN, reader.run["target_local_date"], raw.sha256, feature.sha256, "a" * 64),
    )
    connection.execute("INSERT INTO weather_sampling_footprints VALUES(1,1,'point')")
    for index, point in enumerate(retained.points, 1):
        connection.execute(
            "INSERT INTO weather_product_valid_times VALUES(?,1,?,?,?)",
            (
                index,
                point["valid_at_utc"],
                point["lead_hours"],
                point["required_inputs_last_modified_at_utc"],
            ),
        )
        connection.execute("INSERT INTO weather_point_samples VALUES(?,1,1,?,1200)", (index, index))
    connection.commit()
    connection.close()
    digest = sha256_file(db)
    rows, evidence = read_inputs(
        RUN, project_root=retained.root, database_url="file:./data/local/synthetic.db"
    )
    assert len(rows) == 11 and not rows[0].input_issues
    assert sha256_file(db) == digest
    assert evidence["verification_scope"] == "retained_compact_values_and_metadata_not_raw_grib"
    assert len(evidence["references"]) >= 8
