"""Synthetic S06 evidence and persisted readiness for OD prediction."""

import json
import shutil
import socket
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import pytest

from paragliding_forecasts_ml.ingestion.atmosphere.contracts import RawManifest, StageManifest
from paragliding_forecasts_ml.ingestion.gfs.models import GFS_SOURCE_ID
from paragliding_forecasts_ml.ingestion.weather.artifacts import ArtifactError, WeatherArtifactStore
from paragliding_forecasts_ml.ingestion.weather.features.aggregation import sofia_flying_window
from paragliding_forecasts_ml.ingestion.weather.features.contracts import (
    DailyFeatureSnapshot,
    DailyFeatureSnapshotBatch,
    FeatureLayer,
    FeatureQualitySummary,
    FeatureValue,
)
from paragliding_forecasts_ml.ingestion.weather.features.policy import load_feature_policy
from paragliding_forecasts_ml.ingestion.weather.persistence_models import WeatherPersistenceReceipt
from paragliding_forecasts_ml.ingestion.weather.serialization import sha256_bytes
from paragliding_forecasts_ml.ingestion.weather.spatial import SampledField, SiteAlignedSample
from paragliding_forecasts_ml.ingestion.weather.state import RunStateLedger
from paragliding_forecasts_ml.ingestion.weather.validation import (
    AcceptedWeatherSamples,
    ValidationSnapshot,
)
from paragliding_forecasts_ml.predictions.overdevelopment import cli, retained
from paragliding_forecasts_ml.predictions.overdevelopment.artifacts import load_prediction
from paragliding_forecasts_ml.predictions.overdevelopment.models import FIELD_UNITS
from paragliding_forecasts_ml.predictions.overdevelopment.retained import (
    SELECTORS,
    _sample_fields,
    read_inputs,
)

RUN = "11111111-1111-4111-8111-111111111111"
CYCLE = "2024-06-01T06:00:00Z"
READY = "2024-06-01T13:00:00Z"
TARGET = "2024-06-02"
WINDOW = sofia_flying_window(date.fromisoformat(TARGET))
DB = "data/local/synthetic.db"


def make_samples():
    samples = []
    for index, valid in enumerate(WINDOW.expected_instants_utc):
        fields = []
        for (code, grain, dimension), (key, selectors) in SELECTORS.items():
            precipitation = key == "rain"
            fields.append(
                SampledField(
                    field_code=code,
                    grain=grain,
                    dimension=dimension,
                    canonical_unit=FIELD_UNITS[key],
                    canonical_value=100.0 if precipitation and index == 0 else 1.0,
                    quality_state="real",
                    interval_start_utc=(
                        (datetime.fromisoformat(valid) - timedelta(hours=1)).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"
                        )
                        if precipitation
                        else None
                    ),
                    interval_end_utc=valid if precipitation else None,
                    statistic_type="accumulation" if precipitation else None,
                    source_selector_keys=tuple(sorted(selectors)),
                    source_raw_artifact_keys=("synthetic",),
                    source_native_message_references=("synthetic:message-1",),
                )
            )
        samples.append(
            SiteAlignedSample.model_validate(
                {
                    "sample_identity_key": sha256_bytes(valid.encode()),
                    "site_id": 1,
                    "point_footprint_key": "a" * 64,
                    "neighbourhood_footprint_key": "b" * 64,
                    "reference_at_utc": CYCLE,
                    "valid_at_utc": valid,
                    "valid_local_date": TARGET,
                    "lead_hours": 25 + index,
                    "terrain": {
                        "site_elevation_msl_m": 300.0,
                        "model_elevation_msl_m": 300.0,
                        "model_minus_site_elevation_m": 0.0,
                        "absolute_mismatch_m": 0.0,
                    },
                    "fields": tuple(fields),
                    "profile_levels": (),
                }
            )
        )
    return tuple(samples)


@pytest.fixture
def od_source(tmp_path):
    store = WeatherArtifactStore.create_fresh(RUN, project_root=tmp_path)
    ledger = RunStateLedger(store)
    ledger.initialize(occurred_at_utc=READY)

    def append(event, ref):
        ledger.append(
            invocation_mode="resume",
            stage=event,
            evidence=ref,
            occurred_at_utc=READY,
            disposition="persisted" if event == "persisted" else "complete",
        )

    def output(directory, key, value):
        return store.write_stage_model(directory, f"{key}.json", key, value)

    def stage(directory, name, event, version, inputs, outputs, config=None):
        manifest = StageManifest(
            run_key=RUN,
            stage=name,
            producer_version=version,
            input_fingerprint_sha256="a" * 64,
            inputs=tuple(inputs),
            outputs=tuple(outputs),
            configuration=config or {},
            disposition="complete",
            started_at_utc=READY,
            completed_at_utc=READY,
        )
        ref = store.write_stage_model(directory, "stage-manifest.json", "stage_manifest", manifest)
        append(event, ref)
        return ref

    fake_grib = store.write_raw_bytes("grib", "gone.grib2", b"x", media_type="application/x-grib2")
    plan = fake_grib.model_copy(
        update={
            "artifact_key": "request_plan",
            "relative_path": f"data/raw/weather/{RUN}/request-plan.json",
        }
    )
    (tmp_path / plan.relative_path).write_bytes(b"x")
    raw = store.write_raw_manifest(
        RawManifest(
            run_key=RUN,
            source_id=GFS_SOURCE_ID,
            source_kind="forecast",
            collector_version="synthetic/1",
            request_plan=plan,
            source_product_key="synthetic",
            source_url="https://example.invalid/gfs",
            permission_basis="synthetic",
            permission_reference="synthetic",
            reference_at_utc=CYCLE,
            retrieved_at_utc=READY,
            valid_from_utc=WINDOW.interval_start_utc,
            valid_to_utc=WINDOW.interval_end_utc,
            artifacts=(fake_grib,),
            status="complete",
            completed_at_utc=READY,
        )
    )
    append("raw_complete", raw)
    previous = raw
    for name, event in (("parser", "parsed"), ("normalizer", "normalized")):
        directory = store.begin_stage(name, "synthetic/1", "a" * 64)
        proof = store.write_stage_bytes(
            directory, "metadata.json", "synthetic", b"{}", media_type="application/json"
        )
        previous = stage(directory, name, event, "synthetic/1", [previous], [proof])

    spatial_dir = store.begin_stage("spatial", "synthetic/1", "a" * 64)
    spatial_payload = store.write_stage_bytes(
        spatial_dir,
        "canonical.json",
        "canonical_site_sample_batch",
        b"{}",
        media_type="application/json",
    )
    spatial = stage(
        spatial_dir, "spatial", "spatially_aligned", "synthetic/1", [previous], [spatial_payload]
    )

    validator_dir = store.begin_stage("validator", "synthetic/1", "a" * 64)
    samples = make_samples()
    accepted = output(
        validator_dir,
        "accepted_weather_samples",
        AcceptedWeatherSamples(
            run_key=RUN,
            input_samples=spatial_payload,
            samples=samples,
        ),
    )
    validation = output(
        validator_dir,
        "validation_snapshot",
        ValidationSnapshot.model_validate(
            {
                "run_key": RUN,
                "validator_version": "synthetic/1",
                "policy_version": "synthetic/1",
                "policy_sha256": "a" * 64,
                "upstream_boundary": spatial,
                "raw_manifest": raw,
                "exact_upstream_hashes": (spatial.sha256,),
                "source": {
                    "code": GFS_SOURCE_ID,
                    "provider_name": "NOAA",
                    "dataset_name": "Synthetic",
                    "source_kind": "forecast",
                    "base_url": "https://example.invalid/gfs",
                    "is_active": True,
                    "sha256": "a" * 64,
                },
            }
        ),
    )
    validator = stage(
        validator_dir, "validator", "validated", "synthetic/1", [spatial], [accepted, validation]
    )

    policy, policy_sha = load_feature_policy("weather-feature-policy-v5.json")
    feature_version = policy.feature_builder_version
    contract = policy.feature_contract_version
    feature_dir = store.begin_stage("feature_builder", feature_version, "a" * 64)
    field = FeatureValue(
        feature_key="surface_pressure_mean_pa",
        field_code="air_pressure_pa",
        canonical_unit="Pa",
        canonical_value=95000,
        quality_state="derived",
        statistic="mean",
        derivation_method="synthetic/1",
        derivation_version="synthetic/1",
        input_field_codes=("air_pressure_pa",),
    )
    daily = output(
        feature_dir,
        "daily_feature_snapshot_batch",
        DailyFeatureSnapshotBatch(
            run_key=RUN,
            snapshots=(
                DailyFeatureSnapshot(
                    run_key=RUN,
                    site_id=1,
                    point_footprint_key="a" * 64,
                    neighbourhood_footprint_key="b" * 64,
                    source_product_key="synthetic",
                    local_date=TARGET,
                    feature_contract_version=contract,
                    input_fingerprint_sha256="a" * 64,
                    input_sample_identity_keys=tuple(
                        sample.sample_identity_key for sample in samples
                    ),
                    daily_fields=(field,),
                    profile_layers=(
                        FeatureLayer(layer_base_agl_m=0, layer_top_agl_m=500, fields=(field,)),
                    ),
                    quality_summary=FeatureQualitySummary(
                        total_features=2, quality_counts={"derived": 2}
                    ),
                ),
            ),
        ),
    )
    feature = stage(
        feature_dir,
        "feature_builder",
        "features_built",
        feature_version,
        [validator, accepted],
        [daily],
        {
            "feature_builder_version": feature_version,
            "feature_contract_version": contract,
            "policy_version": policy.policy_version,
            "policy_sha256": policy_sha,
            "validator_manifest_sha256": validator.sha256,
        },
    )
    version = "weather-persistence/3"
    pipeline = f"{feature_version}|{version}"
    receipt = WeatherPersistenceReceipt(
        run_key=RUN,
        source_id=GFS_SOURCE_ID,
        source_product_key="synthetic",
        target_local_date=TARGET,
        database_identity=DB,
        feature_manifest=feature,
        usage_policy_sha256="b" * 64,
        persistence_input_sha256="c" * 64,
        pipeline_version=pipeline,
        persistence_version=version,
        disposition="inserted",
        table_counts={"weather_daily_feature_snapshots": 1},
        persisted_graph_sha256="d" * 64,
        missing_quality_count=0,
        unsupported_quality_count=0,
        missing_reason_counts={},
        completed_at_utc=READY,
    )
    persistence_dir = store.begin_stage("persistence", version, "a" * 64)
    receipt_ref = output(persistence_dir, "weather_persistence_receipt", receipt)
    stage(
        persistence_dir,
        "persistence",
        "persisted",
        version,
        [feature],
        [receipt_ref],
        {
            "usage_policy_sha256": receipt.usage_policy_sha256,
            "persistence_input_sha256": receipt.persistence_input_sha256,
        },
    )
    (tmp_path / fake_grib.relative_path).unlink()

    database = tmp_path / DB
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.executescript("""
            CREATE TABLE weather_sources(id INTEGER PRIMARY KEY, code TEXT, source_kind TEXT);
            CREATE TABLE weather_product_runs(id INTEGER PRIMARY KEY, source_id INTEGER,
                reference_at_utc TEXT, source_product_key TEXT);
            CREATE TABLE weather_ingestion_runs(id INTEGER PRIMARY KEY, run_key TEXT,
                product_run_id INTEGER, status TEXT, target_local_date TEXT, operational_use_allowed INTEGER,
                raw_manifest_path TEXT, raw_manifest_sha256 TEXT, feature_manifest_path TEXT,
                feature_manifest_sha256 TEXT, persistence_input_sha256 TEXT, pipeline_version TEXT);
            CREATE TABLE sites(id INTEGER PRIMARY KEY, slug TEXT);
            CREATE TABLE weather_sampling_footprints(id INTEGER PRIMARY KEY, site_id INTEGER, purpose TEXT);
            CREATE TABLE weather_daily_feature_snapshots(id INTEGER PRIMARY KEY, ingestion_run_id INTEGER,
                point_footprint_id INTEGER, feature_contract_version TEXT);
            CREATE TABLE weather_daily_feature_snapshot_inputs(daily_feature_snapshot_id INTEGER,
                weather_point_sample_id INTEGER);
            CREATE TABLE weather_point_samples(id INTEGER PRIMARY KEY, ingestion_run_id INTEGER,
                point_footprint_id INTEGER, product_valid_time_id INTEGER);
            CREATE TABLE weather_product_valid_times(id INTEGER PRIMARY KEY, product_run_id INTEGER,
                valid_at_utc TEXT, lead_hours INTEGER, required_inputs_last_modified_at_utc TEXT);
            INSERT INTO sites VALUES(1,'synthetic');
            INSERT INTO weather_sampling_footprints VALUES(1,1,'point');
            INSERT INTO weather_daily_feature_snapshots VALUES(1,1,1,'weather-feature-contract/3');
        """)
        connection.execute("INSERT INTO weather_sources VALUES(1,?,'forecast')", (GFS_SOURCE_ID,))
        connection.execute("INSERT INTO weather_product_runs VALUES(1,1,?,'synthetic')", (CYCLE,))
        connection.execute(
            "INSERT INTO weather_ingestion_runs VALUES(1,?,1,'succeeded',?,1,?,?,?,?,?,?)",
            (
                RUN,
                TARGET,
                raw.relative_path,
                raw.sha256,
                feature.relative_path,
                feature.sha256,
                receipt.persistence_input_sha256,
                pipeline,
            ),
        )
        for index, sample in enumerate(samples, 1):
            connection.execute(
                "INSERT INTO weather_product_valid_times VALUES(?,1,?,?,?)",
                (index, sample.valid_at_utc, sample.lead_hours, READY),
            )
            connection.execute("INSERT INTO weather_point_samples VALUES(?,1,1,?)", (index, index))
            connection.execute(
                "INSERT INTO weather_daily_feature_snapshot_inputs VALUES(1,?)", (index,)
            )
    connection.close()
    return SimpleNamespace(
        root=tmp_path, database=database, accepted=tmp_path / accepted.relative_path
    )


def read(source):
    return read_inputs([RUN], project_root=source.root, database_url=f"file:./{DB}")


def test_retained_reader_needs_only_verified_evidence(od_source):
    records, sources = read(od_source)
    assert len(records) == len(sources) == 1
    day = records[0]
    assert day.source_ready_at_utc == READY
    rain = [item for item in day.observations if item.key == "rain"]
    assert len(rain) == 10 and sum(item.value for item in rain) == 10
    assert rain[0].valid_at_utc == WINDOW.interval_start_utc
    assert rain[-1].interval_end_utc == WINDOW.interval_end_utc
    assert len([item for item in day.observations if item.key == "wind"]) == 11
    assert od_source.database.is_file()


@pytest.mark.parametrize(
    ("statement", "message"),
    [
        ("UPDATE weather_ingestion_runs SET operational_use_allowed=0", "authorized"),
        ("UPDATE weather_sources SET source_kind='reanalysis'", "authorized"),
        ("UPDATE weather_ingestion_runs SET target_local_date='2024-06-05'", r"D\+1"),
        ("UPDATE weather_product_runs SET reference_at_utc='2024-06-01T12:00:00Z'", "06Z"),
        (
            "UPDATE weather_product_valid_times SET required_inputs_last_modified_at_utc=NULL WHERE id=1",
            "lacks source readiness",
        ),
        (
            "UPDATE weather_product_valid_times SET required_inputs_last_modified_at_utc='2024-06-01T13:00:01Z' WHERE id=1",
            "readiness",
        ),
        ("UPDATE weather_point_samples SET point_footprint_id=99 WHERE id=1", "lineage"),
    ],
)
def test_ineligible_persisted_evidence_fails(od_source, statement, message):
    with sqlite3.connect(od_source.database) as connection:
        connection.execute(statement)
    connection.close()
    with pytest.raises(ValueError, match=message):
        read(od_source)


def test_tampered_accepted_samples_fail(od_source):
    od_source.accepted.write_bytes(od_source.accepted.read_bytes() + b" ")
    with pytest.raises(ArtifactError):
        read(od_source)


def test_slot_selector_and_invalid_values():
    samples = list(make_samples())
    rain = samples[1].fields[0]
    samples[1] = samples[1].model_copy(
        update={
            "fields": (rain.model_copy(update={"interval_start_utc": "2024-06-02T06:00:00Z"}),)
            + samples[1].fields[1:],
        }
    )
    humidity = samples[0].fields[4]
    fields = samples[0].fields
    samples[0] = samples[0].model_copy(
        update={
            "fields": (
                *fields[:4],
                humidity.model_copy(update={"canonical_value": 101}),
                *fields[5:],
            ),
        }
    )
    observations = _sample_fields(tuple(samples), WINDOW)
    assert observations[0].value is None and observations[0].missing_reason == "interval_unresolved"
    assert observations[4].value is None and observations[4].missing_reason == "invalid_value"
    for added, message in [
        (rain, "Duplicate"),
        (rain.model_copy(update={"canonical_unit": "in"}), "unit"),
    ]:
        duplicate = make_samples()
        broken = duplicate[1].model_copy(update={"fields": (*duplicate[1].fields, added)})
        with pytest.raises(ValueError, match=message):
            _sample_fields((duplicate[0], broken, *duplicate[2:]), WINDOW)


def test_sofia_windows_keep_same_local_hours_in_both_seasons():
    winter = sofia_flying_window(date(2024, 1, 1))
    assert winter.interval_start_utc == "2024-01-01T08:00:00Z"
    assert WINDOW.interval_start_utc == "2024-06-02T07:00:00Z"
    assert len(winter.expected_instants_utc) == len(WINDOW.expected_instants_utc) == 11


def _cli_args(source, *keys):
    return [
        "--project-root",
        str(source.root),
        "--database-url",
        f"file:./{DB}",
        *(argument for key in keys for argument in ("--run-key", key)),
    ]


def test_real_console_entry_point(od_source):
    executable = shutil.which("overdevelopment-predict")
    assert executable is not None, "Install the project entry point with uv sync."
    result = subprocess.run(
        [executable, *_cli_args(od_source, RUN)], check=True, capture_output=True, text=True
    )
    summary = json.loads(result.stdout)
    assert summary["daily_count"] == 1
    assert summary["risk_counts"] == {"low": 0, "medium": 0, "high": 1}
    assert summary["reused"] is False


@pytest.mark.parametrize(
    "args", [[], ["--run-key", "unknown"], ["--run-key", RUN, "--run-key", RUN]]
)
def test_invalid_arguments_exit_two(args):
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2


def test_cli_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["--help"])
    assert error.value.code == 0
    assert "--run-key" in capsys.readouterr().out


def test_cli_reuse_and_standalone_replay(od_source, capsys, monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Unexpected access outside the saved OD bundle.")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    original_database = od_source.database.read_bytes()
    args = _cli_args(od_source, RUN)
    assert cli.main(args) == 0
    first = json.loads(capsys.readouterr().out)
    directory = Path(first["output_directory"])
    manifest_bytes = (directory / "manifest.json").read_bytes()
    assert cli.main(args) == 0
    second = json.loads(capsys.readouterr().out)
    assert first["prediction_id"] == second["prediction_id"]
    assert second["reused"]
    assert manifest_bytes == (directory / "manifest.json").read_bytes()
    assert original_database == od_source.database.read_bytes()

    monkeypatch.setattr(sqlite3, "connect", denied)
    monkeypatch.setattr(WeatherArtifactStore, "verify_reference", denied)
    saved = load_prediction(first["prediction_id"], project_root=od_source.root)
    assert saved.daily_count == 1
    (directory / "predictions.jsonl").write_bytes(b"modified\n")
    with pytest.raises(ValueError, match="payload changed"):
        load_prediction(first["prediction_id"], project_root=od_source.root)


def test_cli_validation_is_all_or_nothing(od_source, capsys):
    unknown = "22222222-2222-4222-8222-222222222222"
    assert cli.main(_cli_args(od_source, RUN, unknown)) == 1
    captured = capsys.readouterr()
    assert not captured.out and "Unknown persisted OD run" in captured.err
    assert not (od_source.root / "data/processed/overdevelopment").exists()


def test_reader_resolves_run_keys_in_stable_order(od_source, monkeypatch):
    second = "22222222-2222-4222-8222-222222222222"
    calls = []

    def record(connection, root, database_identity, key):
        calls.append(key)
        return [], {"run_key": key}

    monkeypatch.setattr(retained, "_read_run", record)
    _, sources = read_inputs(
        [second, RUN], project_root=od_source.root, database_url=f"file:./{DB}"
    )
    assert calls == [RUN, second]
    assert sources == [{"run_key": RUN}, {"run_key": second}]


def test_concurrent_publication_reuses_one_valid_bundle(od_source, monkeypatch):
    from paragliding_forecasts_ml.predictions.overdevelopment.artifacts import publish_prediction
    from paragliding_forecasts_ml.predictions.overdevelopment.policy import load_policy

    days, sources = read(od_source)
    policy, policy_bytes = load_policy()
    rename = Path.rename
    barrier = Barrier(2, timeout=5)

    def race(path, destination):
        if path.name == "bundle":
            barrier.wait()
        return rename(path, destination)

    monkeypatch.setattr(Path, "rename", race)

    def publish():
        return publish_prediction(od_source.root, days, sources, policy, policy_bytes)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(publish), pool.submit(publish)
        a, b = first.result(timeout=10), second.result(timeout=10)
    assert a[:2] == b[:2]
    assert {a[2], b[2]} == {True, False}
