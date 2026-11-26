"""Synthetic persisted GFS lineage and standalone prediction replay."""

import json
import socket
import sqlite3
from collections import defaultdict
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from sqlite3 import Row, connect
from types import SimpleNamespace

import pytest
from sklearn.linear_model import LogisticRegression

from paragliding_forecasts_ml.ingestion.atmosphere.contracts import RawManifest, StageManifest
from paragliding_forecasts_ml.ingestion.gfs.models import GFS_SOURCE_ID
from paragliding_forecasts_ml.ingestion.weather.artifacts import ArtifactError, WeatherArtifactStore
from paragliding_forecasts_ml.ingestion.weather.features.contracts import (
    DailyFeatureSnapshot,
    DailyFeatureSnapshotBatch,
    FeatureLayer,
    FeatureQualitySummary,
    FeatureValue,
    HourlyFeatureSnapshot,
    HourlyFeatureSnapshotBatch,
    MissingFeatureLocator,
)
from paragliding_forecasts_ml.ingestion.weather.features.policy import load_feature_policy
from paragliding_forecasts_ml.ingestion.weather.persistence_models import WeatherPersistenceReceipt
from paragliding_forecasts_ml.ingestion.weather.serialization import (
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)
from paragliding_forecasts_ml.ingestion.weather.state import RunStateLedger
from paragliding_forecasts_ml.predictions.cloudbase.calculation import aggregate_day
from paragliding_forecasts_ml.predictions.cloudbase.models import Height, HourlyResult
from paragliding_forecasts_ml.predictions.publication import store
from paragliding_forecasts_ml.predictions.publication.weather import read_weather
from paragliding_forecasts_ml.predictions.xc_probability import (
    cli,
    model_io,
    prediction,
    selection,
    trials,
)
from paragliding_forecasts_ml.predictions.xc_probability.models import (
    AvailableMetric,
    Confidence,
    ConversionSupport,
    ThresholdProbabilities,
)
from paragliding_forecasts_ml.predictions.xc_probability.policy import LAYER_BOUNDS, load_policy
from paragliding_forecasts_ml.predictions.xc_probability.retained import read_retained_inputs

DATABASE_URL = "file:./data/local/synthetic.db"
DB_IDENTITY = "data/local/synthetic.db"
STUDY_ID = "a" * 64


def make_retained(root, records, *, builder_version="weather-feature-builder/5"):
    first = records[0]
    key = first.run_key
    stamp = first.source_ready_at_utc
    store = WeatherArtifactStore.create_fresh(key, project_root=root)
    ledger = RunStateLedger(store)
    ledger.initialize(occurred_at_utc=stamp)

    def append(name, reference):
        ledger.append(
            invocation_mode="resume",
            stage=name,
            disposition="persisted" if name == "persisted" else "complete",
            occurred_at_utc=stamp,
            evidence=reference,
        )

    def stage(directory, name, event, version, inputs, outputs, configuration=None):
        manifest = StageManifest(
            run_key=key,
            stage=name,
            producer_version=version,
            input_fingerprint_sha256="a" * 64,
            inputs=tuple(inputs),
            outputs=tuple(outputs),
            configuration=configuration or {},
            disposition="complete",
            started_at_utc=stamp,
            completed_at_utc=stamp,
        )
        ref = store.write_stage_model(directory, "stage-manifest.json", "stage_manifest", manifest)
        append(event, ref)
        return ref

    raw_data = store.write_raw_bytes(
        "grib", "gone.grib2", b"synthetic", media_type="application/x-grib2"
    )
    request_ref = raw_data.model_copy(
        update={
            "artifact_key": "request_plan",
            "relative_path": f"data/raw/weather/{key}/request-plan.json",
        }
    )
    (root / request_ref.relative_path).write_bytes(b"synthetic")
    raw = store.write_raw_manifest(
        RawManifest(
            run_key=key,
            source_id=GFS_SOURCE_ID,
            source_kind="forecast",
            collector_version="synthetic/1",
            request_plan=request_ref,
            source_product_key="synthetic",
            source_url="https://example.invalid/gfs",
            permission_basis="synthetic",
            permission_reference="synthetic",
            reference_at_utc=first.cycle_reference_utc,
            retrieved_at_utc=stamp,
            valid_from_utc=first.valid_times_utc[0],
            valid_to_utc=first.valid_times_utc[-1],
            artifacts=(raw_data,),
            status="complete",
            completed_at_utc=stamp,
        )
    )
    append("raw_complete", raw)
    last = raw
    for name, event in (
        ("parser", "parsed"),
        ("normalizer", "normalized"),
        ("spatial", "spatially_aligned"),
        ("validator", "validated"),
    ):
        directory = store.begin_stage(name, "synthetic/1", "a" * 64)
        proof = store.write_stage_bytes(
            directory, "metadata.json", "synthetic", b"{}", media_type="application/json"
        )
        last = stage(directory, name, event, "synthetic/1", [last], [proof])

    policy, _ = load_policy()
    contract = policy.feature_contract_version
    hourly, daily = [], []
    for record in records:
        by_scope = defaultdict(list)
        locators = []
        counts = defaultdict(int)
        for spec, obs in zip(policy.required_features, record.observations, strict=True):
            by_scope[spec.scope].append(
                FeatureValue(
                    feature_key=spec.feature_key,
                    field_code=spec.field_code,
                    canonical_unit=spec.canonical_unit,
                    variant=spec.variant,
                    statistic=spec.statistic,
                    canonical_value=obs.value,
                    quality_state=obs.quality_state,
                    missing_reason=obs.missing_reason,
                    derivation_method=spec.derivation_method,
                    derivation_version=spec.derivation_method,
                    input_field_codes=(spec.field_code,),
                )
            )
            counts[obs.quality_state] += 1
            if obs.value is None:
                base, top = LAYER_BOUNDS.get(spec.scope, (None, None))
                locators.append(
                    MissingFeatureLocator(
                        feature_key=spec.feature_key,
                        layer_base_agl_m=base,
                        layer_top_agl_m=top,
                        missing_reason=obs.missing_reason,
                    )
                )
        site = record.site_id
        point = sha256_bytes(f"point{site}".encode())
        neighbourhood = sha256_bytes(f"neighbourhood{site}".encode())
        sample_keys = []
        for valid in record.valid_times_utc:
            sample_key = sha256_bytes(f"{key}/{site}/{valid}".encode())
            sample_keys.append(sample_key)
            hourly.append(
                HourlyFeatureSnapshot(
                    run_key=key,
                    sample_identity_key=sample_key,
                    site_id=site,
                    point_footprint_key=point,
                    neighbourhood_footprint_key=neighbourhood,
                    valid_at_utc=valid,
                    valid_local_date=record.target_local_date,
                    feature_contract_version=contract,
                    input_fingerprint_sha256="a" * 64,
                    fields=(by_scope["daily"][1],),
                    quality_summary=FeatureQualitySummary(
                        total_features=1, quality_counts={"derived": 1}
                    ),
                )
            )
        daily.append(
            DailyFeatureSnapshot(
                run_key=key,
                site_id=site,
                point_footprint_key=point,
                neighbourhood_footprint_key=neighbourhood,
                source_product_key="synthetic",
                local_date=record.target_local_date,
                feature_contract_version=contract,
                input_fingerprint_sha256="a" * 64,
                input_sample_identity_keys=tuple(sample_keys),
                daily_fields=tuple(by_scope["daily"]),
                missing_features=tuple(locators),
                profile_layers=tuple(
                    FeatureLayer(
                        layer_base_agl_m=base, layer_top_agl_m=top, fields=tuple(by_scope[scope])
                    )
                    for scope, (base, top) in LAYER_BOUNDS.items()
                ),
                quality_summary=FeatureQualitySummary(
                    total_features=67, quality_counts=dict(counts)
                ),
            )
        )
    feature_dir = store.begin_stage("feature_builder", builder_version, "a" * 64)
    daily_ref = store.write_stage_model(
        feature_dir,
        "daily.json",
        "daily_feature_snapshot_batch",
        DailyFeatureSnapshotBatch(run_key=key, snapshots=tuple(daily)),
    )
    hourly_ref = store.write_stage_model(
        feature_dir,
        "hourly.json",
        "hourly_feature_snapshot_batch",
        HourlyFeatureSnapshotBatch(run_key=key, snapshots=tuple(hourly)),
    )
    _, policy_sha = load_feature_policy(f"{policy.weather_policy_version}.json")
    feature = stage(
        feature_dir,
        "feature_builder",
        "features_built",
        builder_version,
        [last],
        [daily_ref, hourly_ref],
        {
            "feature_builder_version": builder_version,
            "feature_contract_version": contract,
            "policy_version": policy.weather_policy_version,
            "policy_sha256": policy_sha,
            "validator_manifest_sha256": last.sha256,
        },
    )
    version = "weather-persistence/3"
    pipeline = f"{builder_version}|{version}"
    receipt = WeatherPersistenceReceipt(
        run_key=key,
        source_id=GFS_SOURCE_ID,
        source_product_key="synthetic",
        target_local_date=first.target_local_date,
        database_identity=DB_IDENTITY,
        feature_manifest=feature,
        usage_policy_sha256="b" * 64,
        persistence_input_sha256="c" * 64,
        pipeline_version=pipeline,
        persistence_version=version,
        disposition="inserted",
        table_counts={"weather_daily_feature_snapshots": len(records)},
        persisted_graph_sha256="d" * 64,
        missing_quality_count=0,
        unsupported_quality_count=0,
        missing_reason_counts={},
        completed_at_utc=stamp,
    )
    persistence_dir = store.begin_stage("persistence", version, "a" * 64)
    receipt_ref = store.write_stage_model(
        persistence_dir, "receipt.json", "weather_persistence_receipt", receipt
    )
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
    (root / raw_data.relative_path).unlink()

    db = root / DB_IDENTITY
    db.parent.mkdir(parents=True)
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.executescript("""
            CREATE TABLE weather_sources(id INTEGER PRIMARY KEY, code TEXT, source_kind TEXT);
            CREATE TABLE weather_product_runs(id INTEGER PRIMARY KEY, source_id INTEGER, reference_at_utc TEXT, source_product_key TEXT);
            CREATE TABLE weather_ingestion_runs(id INTEGER PRIMARY KEY, run_key TEXT, product_run_id INTEGER, status TEXT,
                target_local_date TEXT, operational_use_allowed INTEGER, raw_manifest_path TEXT, raw_manifest_sha256 TEXT,
                feature_manifest_path TEXT, feature_manifest_sha256 TEXT, persistence_input_sha256 TEXT, pipeline_version TEXT);
            CREATE TABLE sites(id INTEGER PRIMARY KEY, slug TEXT);
            CREATE TABLE weather_sampling_footprints(id INTEGER PRIMARY KEY, site_id INTEGER, purpose TEXT);
            CREATE TABLE weather_daily_feature_snapshots(id INTEGER PRIMARY KEY, ingestion_run_id INTEGER,
                point_footprint_id INTEGER, feature_contract_version TEXT);
            CREATE TABLE weather_daily_feature_snapshot_inputs(daily_feature_snapshot_id INTEGER, weather_point_sample_id INTEGER);
            CREATE TABLE weather_point_samples(id INTEGER PRIMARY KEY, ingestion_run_id INTEGER, point_footprint_id INTEGER, product_valid_time_id INTEGER);
            CREATE TABLE weather_product_valid_times(id INTEGER PRIMARY KEY, product_run_id INTEGER, valid_at_utc TEXT,
                lead_hours REAL, required_inputs_last_modified_at_utc TEXT);
        """)
        connection.execute("INSERT INTO weather_sources VALUES(1,?,'forecast')", (GFS_SOURCE_ID,))
        connection.execute(
            "INSERT INTO weather_product_runs VALUES(1,1,?,'synthetic')",
            (first.cycle_reference_utc,),
        )
        connection.execute(
            "INSERT INTO weather_ingestion_runs VALUES(1,?,1,'succeeded',?,1,?,?,?,?,?,?)",
            (
                key,
                first.target_local_date,
                raw.relative_path,
                raw.sha256,
                feature.relative_path,
                feature.sha256,
                receipt.persistence_input_sha256,
                pipeline,
            ),
        )
        for hour, valid in enumerate(first.valid_times_utc, 1):
            lead = (
                datetime.fromisoformat(valid) - datetime.fromisoformat(first.cycle_reference_utc)
            ).total_seconds() / 3600
            connection.execute(
                "INSERT INTO weather_product_valid_times VALUES(?,1,?,?,?)",
                (hour, valid, lead, stamp),
            )
        for record in records:
            site = record.site_id
            connection.execute("INSERT INTO sites VALUES(?,?)", (site, record.site_slug))
            connection.execute(
                "INSERT INTO weather_sampling_footprints VALUES(?,?,'point')", (site, site)
            )
            connection.execute(
                "INSERT INTO weather_daily_feature_snapshots VALUES(?,1,?,?)",
                (site, site, contract),
            )
            for hour in range(1, 12):
                sample_id = site * 100 + hour
                connection.execute(
                    "INSERT INTO weather_point_samples VALUES(?,1,?,?)", (sample_id, site, hour)
                )
                connection.execute(
                    "INSERT INTO weather_daily_feature_snapshot_inputs VALUES(?,?)",
                    (site, sample_id),
                )
    return db, root / receipt_ref.relative_path, root / daily_ref.relative_path


@pytest.fixture
def forecasts(synthetic_study):
    first = synthetic_study.rows[0].inputs
    return tuple(row.inputs for row in synthetic_study.rows if row.inputs.run_key == first.run_key)


@pytest.mark.parametrize(
    "failure,match",
    [
        ("v4", "v5/contract 3"),
        ("receipt", "(SHA-256|byte count)"),
        ("daily", "(SHA-256|byte count)"),
        ("late", "ready by"),
        ("permission", "authorized"),
        ("short_window", "eleven matching hours"),
        ("other_run", "inconsistent forecast lineage"),
        ("wrong_feature", "SQLite lineage disagree"),
    ],
)
def test_prediction_source_rejects_incompatible_or_damaged_lineage(
    tmp_path, forecasts, failure, match
):
    db, receipt, daily = make_retained(
        tmp_path,
        forecasts[:1],
        builder_version=(
            "weather-feature-builder/4" if failure == "v4" else "weather-feature-builder/5"
        ),
    )
    if failure in {"receipt", "daily"}:
        (receipt if failure == "receipt" else daily).write_bytes(b"damaged")
    sql = {
        "late": "UPDATE weather_product_valid_times SET required_inputs_last_modified_at_utc='2021-09-30T18:00:00Z'",
        "permission": "UPDATE weather_ingestion_runs SET operational_use_allowed=0",
        "short_window": "DELETE FROM weather_daily_feature_snapshot_inputs WHERE weather_point_sample_id=101",
        "other_run": "UPDATE weather_point_samples SET ingestion_run_id=2",
        "wrong_feature": "UPDATE weather_ingestion_runs SET feature_manifest_sha256=raw_manifest_sha256",
    }
    if failure in sql:
        with closing(sqlite3.connect(db)) as connection, connection:
            connection.execute(sql[failure])
    before = sha256_file(db)
    with pytest.raises((ArtifactError, ValueError), match=match):
        read_retained_inputs(
            (forecasts[0].run_key,),
            project_root=tmp_path,
            policy=load_policy()[0],
            database_url=DATABASE_URL,
        )
    assert sha256_file(db) == before


def test_predict_cli_publishes_and_replays_exact_inputs(
    tmp_path, monkeypatch, capsys, forecasts, synthetic_study
):
    for module in (trials, selection, model_io):
        monkeypatch.setattr(module, "load_study", lambda **_: synthetic_study)
    trial_ids = [
        trials.train_trials(
            study_id=STUDY_ID, fold=fold, project_root=tmp_path, experiment_version=1
        )["trial_id"]
        for fold in (2023, 2024)
    ]
    selected = selection.select_recipe(
        study_id=STUDY_ID, trial_ids=trial_ids, project_root=tmp_path
    )
    model_id = model_io.train_final(
        study_id=STUDY_ID, selection_id=selected["selection_id"], project_root=tmp_path
    )["model_id"]
    model = model_io.load_model(model_id=model_id, project_root=tmp_path)
    first, second = forecasts[:2]
    absent = second.observations[0].model_copy(
        update={"value": None, "quality_state": "missing", "missing_reason": "synthetic_missing"}
    )
    incomplete = second.model_copy(update={"observations": (absent, *second.observations[1:])})
    database, _, _ = make_retained(tmp_path, (first, incomplete))
    before = sha256_file(database)

    def blocked(*_args, **_kwargs):
        pytest.fail(
            "Prediction attempted to train, access network, replay ingestion or read study data"
        )

    monkeypatch.setattr(LogisticRegression, "fit", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(model_io, "load_study", blocked)
    monkeypatch.setattr(model_io, "load_selection", blocked)
    monkeypatch.setattr(WeatherArtifactStore, "verify_boundary", blocked)
    args = [
        "predict",
        "--model-id",
        model_id,
        "--run-key",
        first.run_key,
        "--project-root",
        str(tmp_path),
        "--database-url",
        DATABASE_URL,
    ]
    assert cli.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    directory = Path(result["output_directory"])
    before_manifest = (directory / "manifest.json").read_bytes()
    assert result["row_count"] == 2 and result["missing_by_reason"] == {
        "required_inputs_missing": 3
    }
    assert result["conversion"]["k"] == 2 and result["conversion"]["n"] == 9
    assert {file.name for file in directory.iterdir()} == {
        "manifest.json",
        "policy.json",
        "inputs.jsonl",
        "predictions.jsonl",
        "prediction.json",
    }
    assert cli.main(args) == 0
    repeated = json.loads(capsys.readouterr().out)
    assert repeated["prediction_id"] == result["prediction_id"] and repeated["reused"]
    assert (directory / "manifest.json").read_bytes() == before_manifest and sha256_file(
        database
    ) == before

    with monkeypatch.context() as replay:
        replay.setattr(prediction, "read_retained_inputs", blocked)
        batch = prediction.load_prediction(
            prediction_id=result["prediction_id"], project_root=tmp_path
        )
    good, missing = batch.rows
    assert len(batch.inputs[0].observations) == 67 and len(batch.inputs[0].valid_times_utc) == 11
    assert good.input_sha256 == sha256_bytes(canonical_json_bytes(batch.inputs[0]))
    assert good.probabilities.p100.value == good.stage_drivers[0].probability
    assert (
        good.probabilities.p200.value
        == good.stage_drivers[0].probability * good.stage_drivers[1].probability
    )
    assert good.probabilities.p300.value == good.probabilities.p200.value * (2 / 9)
    for metric in (good.probabilities.p100, good.probabilities.p200, good.probabilities.p300):
        assert (
            metric.confidence.level == "low" and "not_calibrated" in metric.confidence.reason_codes
        )
    assert good.threshold_explanations["p200"].stages == ("p100", "q200")
    assert good.threshold_explanations["p300"].message.message_code == "empirical_300_method"
    assert all(
        len(stage.groups) == 15 and len(stage.top_group_ids) <= 3 for stage in good.stage_drivers
    )
    assert missing.probabilities.p100.missing_feature_ids == (absent.feature_id,)
    assert (
        missing.probabilities.p200.value is None and missing.probabilities.p300.confidence is None
    )
    assert not missing.stage_drivers and not missing.stage_messages

    sparse = model.model_copy(
        update={
            "conversion": model.conversion.model_copy(
                update={
                    "k": 0,
                    "ratio": 0.0,
                    "support_state": "insufficient_300_support",
                }
            )
        }
    )
    unsupported = prediction.predict_records(sparse, model_id, batch.inputs[:1], load_policy()[0])[
        0
    ]
    assert unsupported.probabilities.p100 == good.probabilities.p100
    assert (
        unsupported.probabilities.p300.value is None
        and unsupported.probabilities.p300.confidence is None
    )
    assert unsupported.threshold_explanations["p300"].stages == ()
    assert (
        unsupported.threshold_explanations["p300"].message.message_code
        == "insufficient_300_support"
    )

    (directory / "predictions.jsonl").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="payload changed"):
        prediction.load_prediction(prediction_id=result["prediction_id"], project_root=tmp_path)


def test_cli_rejects_an_unknown_command_before_prediction(monkeypatch, capsys):
    def unexpected_prediction(**_kwargs):
        pytest.fail("An unknown command must not reach prediction")

    monkeypatch.setattr(cli, "predict_runs", unexpected_prediction)
    with pytest.raises(SystemExit) as error:
        cli.main(["predcit", "--model-id", "a" * 64, "--run-key", "unused"])
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "invalid choice" in captured.err and "predcit" in captured.err


MODEL = "a" * 64
IDS = store.BundleIds("b" * 64, "c" * 64, "d" * 64)


@pytest.fixture
def weather_data(tmp_path, synthetic_study):
    first = synthetic_study.rows[0].inputs
    records = tuple(r.inputs for r in synthetic_study.rows if r.inputs.run_key == first.run_key)
    database, _, _ = make_retained(tmp_path, records)
    with closing(connect(database)) as db, db:
        db.executescript("""
            ALTER TABLE sites ADD is_active INTEGER NOT NULL DEFAULT 1;
            ALTER TABLE weather_ingestion_runs ADD request_purpose TEXT NOT NULL DEFAULT 'operational_forecast';
            CREATE TABLE weather_field_provenance (
                id INTEGER PRIMARY KEY, daily_feature_snapshot_id INTEGER, daily_feature_profile_layer_id INTEGER,
                weather_point_sample_id INTEGER, point_convection_measurement_id INTEGER,
                point_interval_measurement_id INTEGER, field_code TEXT, field_variant TEXT, statistic_type TEXT
            );
            CREATE TABLE weather_point_interval_measurements (
                id INTEGER PRIMARY KEY, weather_point_sample_id INTEGER, interval_start_utc TEXT, interval_end_utc TEXT
            );
        """)
        db.execute(
            "UPDATE weather_product_runs SET source_product_key = ?",
            ("gfs." + first.issue_local_date.replace("-", "") + "/06/atmos",),
        )
        migrations = Path(__file__).resolve().parents[3] / "packages/database/drizzle"
        [migration] = migrations.glob("*_create_prediction_publications/migration.sql")
        db.executescript(migration.read_text())
        db.row_factory = Row
        return database, records, read_weather(db, first.run_key)


def batch_for(records, weather, template):
    rows = []
    clouds = []
    all_hours = []
    inputs = []
    od = []
    policy, _ = load_policy()
    spec = policy.required_features[0]
    code = spec.feature_id
    confidence = Confidence(note="Synthetic baseline confidence.", reason_codes=("synthetic",))
    for record in records:
        messages = {
            "p100": (SimpleNamespace(text="Grouped P100 contribution."),),
            "q200": (SimpleNamespace(text="Grouped Q200 contribution."),),
        }
        row = SimpleNamespace(
            **record.model_dump(
                include={
                    "site_id",
                    "site_slug",
                    "target_local_date",
                    "run_key",
                    "cycle_reference_utc",
                    "horizon_days",
                }
            ),
            probabilities=ThresholdProbabilities(
                p100=AvailableMetric(value=0.5, confidence=confidence),
                p200=AvailableMetric(value=0.4, confidence=confidence),
                p300=AvailableMetric(value=0.03, confidence=confidence),
            ),
            stage_messages=messages,
            stage_drivers=tuple(
                SimpleNamespace(
                    stage=stage,
                    top_group_ids=(spec.group_id,),
                    groups=(
                        SimpleNamespace(
                            group_id=spec.group_id,
                            direction="raises",
                            contribution_logit=0.34,
                            source_feature_ids=(code,),
                        ),
                    ),
                )
                for stage in ("p100", "q200")
            ),
            threshold_explanations={
                "p100": SimpleNamespace(message=None),
                "p200": SimpleNamespace(message=None),
                "p300": SimpleNamespace(message=SimpleNamespace(text="Pooled conversion 3/42.")),
            },
            limitation=SimpleNamespace(text="Synthetic uncalibrated forecast."),
        )
        rows.append(row)
        hours = []
        for i, when in enumerate(weather.horizon.hours):
            regime, reason, potential, top = {
                0: ("cumulus", "heating_and_condensation_supported", 1200, 3500),
                1: ("indeterminate", "positive_heating_not_established", 1300, 3500),
                2: ("indeterminate", "potential_base_outside_profile", 3000, 2500),
                3: ("missing", "model_profile_missing", None, None),
            }.get(i, ("blue", "local_cumulus_formation_not_supported", 1100, 3500))
            if row.site_id == 2:
                regime, reason, potential, top = (
                    "blue",
                    "local_cumulus_formation_not_supported",
                    1100,
                    3500,
                )
            height = (
                Height(msl_m=potential, model_agl_m=potential - 500, site_agl_m=potential - 1500)
                if potential
                else None
            )
            identity = {
                "site_id": row.site_id,
                "site_slug": row.site_slug,
                "run_key": row.run_key,
                "target_local_date": row.target_local_date,
                "valid_at_utc": when,
                "reference_at_utc": row.cycle_reference_utc,
                "horizon_days": row.horizon_days,
            }
            inputs.append(
                template.model_copy(
                    update={
                        **identity,
                        "source_ready_at_utc": weather.ready_times[when],
                        "sensible_interval": None,
                        "latent_interval": None,
                    }
                )
            )
            hours.append(
                HourlyResult(
                    **identity,
                    valid_at_local=when,
                    data_status="missing" if regime == "missing" else "baseline",
                    regime=regime,
                    potential_base=height,
                    estimated_cloudbase=height if regime == "cumulus" else None,
                    confidence=None if regime == "missing" else "low",
                    reason_codes=(reason,),
                    limitations=("uncalibrated_baseline",),
                    diagnostics={"profile_top_msl_m": top},
                    input_sha256="e" * 64,
                )
            )
        clouds.append(aggregate_day(hours))
        all_hours.extend(hours)
        od.append(
            {
                **vars(row),
                "risk_level": "high",
                "score": None,
                "confidence": "low",
                "data_status": "baseline",
                "validation_status": "not_observationally_calibrated",
                "coverage": {"complete": False},
                "overrides": [{"code": "high_precipitation"}],
                "reasons": [
                    {
                        "code": "high_precipitation",
                        "message": "Rain in the first hour.",
                        "evidence": {
                            "key": "rain",
                            "valid_at_utc": hours[0].valid_at_utc,
                            "interval_end_utc": hours[1].valid_at_utc,
                        },
                    }
                ],
            }
        )
    references = [
        {"relative_path": path, "sha256": sha}
        for path, sha in (weather.raw_manifest, weather.feature_manifest)
    ]
    lineage = {
        "persistence_input_sha256": weather.persistence_input_sha256,
        "source_product_key": weather.source_product_key,
        "hourly_source_ready_at_utc": list(weather.ready_times.values()),
        "references": references,
    }
    conversion = ConversionSupport(
        k=3,
        n=42,
        ratio=3 / 42,
        support_state="supported",
        study_id="a" * 64,
        training_source_seasons=(2022, 2023, 2024),
    )
    xc = SimpleNamespace(
        rows=rows,
        inputs=tuple(record.model_copy(update={"source_lineage": lineage}) for record in records),
        metadata=SimpleNamespace(
            model_id=MODEL, run_keys=(weather.run_key,), conversion=conversion
        ),
    )
    source = {
        "run_key": weather.run_key,
        "source_id": "noaa_gfs_0p25_aws_grib2",
        "reference_at_utc": weather.horizon.cycle,
        "target_local_date": str(weather.horizon.target_date),
        "references": references,
    }
    cloud = store.CloudbaseBatch(
        "cloudbase/2", [source], tuple(inputs), tuple(all_hours), tuple(clouds)
    )
    od_source = SimpleNamespace(
        run_key=weather.run_key,
        persistence_input_sha256=weather.persistence_input_sha256,
        database_identity="data/local/synthetic.db",
        references=[SimpleNamespace(model_dump=lambda ref=ref, **_: ref) for ref in references],
    )
    manifest = SimpleNamespace(
        run_keys=(weather.run_key,), sources=(od_source,), policy_version="od/1"
    )
    return store.Batches(xc, cloud, manifest, od)


def test_atomic_publication_mapping_and_repeat(
    tmp_path, weather_data, cloudbase_column, monkeypatch
):
    database, records, weather = weather_data
    batch = batch_for(records, weather, cloudbase_column)
    spec = load_policy()[0].required_features[0]
    with closing(connect(database)) as db, db:
        db.execute(
            "INSERT INTO weather_field_provenance (id,daily_feature_snapshot_id,field_code,field_variant,statistic_type) VALUES (10,1,?,?,?)",
            (spec.field_code, spec.variant, spec.statistic),
        )
        db.execute(
            "INSERT INTO weather_point_interval_measurements VALUES (20,102,?,?)",
            weather.horizon.hours[:2],
        )
        db.execute(
            "INSERT INTO weather_field_provenance (id,point_interval_measurement_id,field_code,field_variant) VALUES (21,20,'precipitation_amount_mm','canonical')"
        )

    def publish(model=MODEL):
        return store.publish_date(
            project_root=tmp_path,
            database_url=DATABASE_URL,
            run_key=weather.run_key,
            model_id=model,
            ids=IDS,
            clock=lambda: datetime(2026, 11, 16, 14, tzinfo=UTC),
        )

    broken = replace(batch, cloudbase=replace(batch.cloudbase, hourly=batch.cloudbase.hourly[:-1]))
    monkeypatch.setattr(store, "_read_batches", lambda *_: broken)
    with pytest.raises(ValueError, match="eleven"):
        publish()
    with closing(connect(database)) as db:
        assert all(
            db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0 for table in store.TABLES
        )

    monkeypatch.setattr(store, "_read_batches", lambda *_: batch)
    first = publish()
    assert first.id == 1 and not first.reused
    second_id = "f" * 64
    batch.xc.metadata.model_id = second_id
    assert publish(second_id).id == 2
    monkeypatch.setattr(
        store, "_read_batches", lambda *_: pytest.fail("Recomputed an existing publication")
    )
    assert publish() == replace(first, reused=True)

    with closing(connect(database)) as db:
        assert db.execute("SELECT count(*) FROM predictions").fetchone() == (14,)
        assert db.execute("SELECT count(*) FROM prediction_cloudbase_hours").fetchone() == (154,)
        assert db.execute("SELECT count(*) FROM prediction_metric_details").fetchone() == (70,)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        hours = db.execute(
            """SELECT regime, estimated_cloudbase_msl_m, estimated_cloudbase_site_agl_m
               FROM prediction_cloudbase_hours WHERE prediction_id=1 ORDER BY valid_at_utc LIMIT 5"""
        ).fetchall()
        assert hours == [
            ("cumulus", 1200, -300),
            ("indeterminate", 1300, -200),
            ("indeterminate", None, None),
            ("missing", None, None),
            ("blue", None, None),
        ]
        assert db.execute(
            "SELECT data_status FROM prediction_metric_details WHERE prediction_id=2 AND metric_code='cloudbase'"
        ).fetchone() == ("baseline",)
        assert db.execute(
            """SELECT d.metric_code, d.xc_stage, i.input_key, i.weather_field_provenance_id
               FROM prediction_drivers AS d JOIN prediction_driver_inputs AS i
                 ON i.prediction_driver_id=d.id
               WHERE d.prediction_id=1 AND d.kind IN ('xc_contribution','od_override')
               ORDER BY d.metric_code"""
        ).fetchall() == [
            ("overdevelopment", None, "rain", 21),
            ("p100", "p100", spec.feature_id, 10),
            ("p200", "q200", spec.feature_id, 10),
        ]
        assert db.execute(
            """SELECT support_successes,support_total FROM prediction_drivers
               WHERE prediction_id=1 AND kind='pooled_conversion'"""
        ).fetchone() == (3, 42)
