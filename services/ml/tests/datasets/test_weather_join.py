"""A joined flight day must keep three distinct issue/run/lead identities."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from uuid import uuid4

import pytest

from paragliding_forecasts_ml.datasets import weather_join
from paragliding_forecasts_ml.datasets.weather_cohort import _encoded
from paragliding_forecasts_ml.ingestion.gfs.models import GFS_SOURCE_ID, sofia_window_instants


def _fixture(tmp_path, monkeypatch):
    target = date(2022, 5, 1)
    valid_times = sofia_window_instants(target.isoformat())
    label = {
        "local_date": target.isoformat(),
        "site_id": 1,
        "labels": {
            "100": {"state": "positive"},
            "200": {"state": "negative"},
            "300": {"state": "negative"},
        },
        "flight_count": 1,
        "max_distance_km": 120.0,
        "coverage": {"mature": True},
    }
    label_hash = weather_join._sha(_encoded(label))
    selected = {
        "target_local_date": target.isoformat(),
        "site_id": 1,
        "site_slug": "fixture",
        "split": "development",
        "sampling_weight": 1.0,
        "inclusion_probability": {"numerator": 1, "denominator": 1},
        "label_row_sha256": label_hash,
    }
    cohort_dir = tmp_path / "data/processed/weather-cohorts" / ("a" * 64)
    cohort_dir.mkdir(parents=True)
    (cohort_dir / "selected_site_days.jsonl").write_bytes(_encoded(selected))
    acquisition_dir = tmp_path / "data/processed/weather-acquisitions" / ("b" * 64)
    acquisition_dir.mkdir(parents=True)
    (acquisition_dir / "manifest.json").write_bytes(b"synthetic manifest")
    jobs = []
    receipts = []
    database = tmp_path / "data/local/paragliding.db"
    database.parent.mkdir(parents=True)
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE weather_sources (id INTEGER, code TEXT, source_kind TEXT);
        CREATE TABLE weather_product_runs (id INTEGER, source_id INTEGER, reference_at_utc TEXT, available_at_utc TEXT);
        CREATE TABLE weather_ingestion_runs (id INTEGER, run_key TEXT, status TEXT, target_local_date TEXT, request_purpose TEXT, model_training_allowed INTEGER, raw_manifest_sha256 TEXT, feature_manifest_sha256 TEXT, persistence_input_sha256 TEXT, product_run_id INTEGER);
        CREATE TABLE weather_sampling_footprints (id INTEGER, site_id INTEGER);
        CREATE TABLE weather_daily_feature_snapshots (id INTEGER, ingestion_run_id INTEGER, point_footprint_id INTEGER, neighbourhood_footprint_id INTEGER, feature_contract_version TEXT, air_temperature_2m_mean_k REAL);
        CREATE TABLE weather_product_valid_times (id INTEGER, product_run_id INTEGER, valid_at_utc TEXT, lead_hours REAL);
        CREATE TABLE weather_point_samples (id INTEGER, ingestion_run_id INTEGER, product_valid_time_id INTEGER, point_footprint_id INTEGER);
        CREATE TABLE weather_daily_feature_snapshot_inputs (daily_feature_snapshot_id INTEGER, weather_point_sample_id INTEGER);
        CREATE TABLE weather_daily_feature_profile_layers (id INTEGER, daily_feature_snapshot_id INTEGER, layer_base_agl_m REAL, layer_top_agl_m REAL);
        CREATE TABLE weather_field_provenance (daily_feature_snapshot_id INTEGER, daily_feature_profile_layer_id INTEGER, field_code TEXT, field_variant TEXT, statistic_type TEXT, quality_state TEXT, missing_reason_code TEXT, source_reference_at_utc TEXT, native_field_name TEXT, native_unit TEXT, native_sign_convention TEXT, native_step_type TEXT, step_start_hours REAL, step_end_hours REAL, normalization_method TEXT, normalization_version TEXT, derivation_method TEXT, derivation_version TEXT, raw_artifact_key TEXT, native_message_reference TEXT);
        """
    )
    connection.execute("INSERT INTO weather_sources VALUES (1, ?, 'forecast')", (GFS_SOURCE_ID,))
    connection.execute("INSERT INTO weather_sampling_footprints VALUES (1, 1)")
    for horizon in (1, 2, 3):
        issue = target - timedelta(days=horizon)
        cycle = f"{issue}T06:00:00Z"
        available = f"{issue}T10:00:00Z"
        run_key = str(uuid4())
        leads = list(range(25 + 24 * (horizon - 1), 36 + 24 * (horizon - 1)))
        jobs.append(
            {
                "target_local_date": target.isoformat(),
                "horizon_days": horizon,
                "issue_local_date": issue.isoformat(),
                "valid_times_utc": list(valid_times),
                "candidate_cycles": [{"cycle_reference_utc": cycle, "lead_hours": leads}],
            }
        )
        receipts.append(
            {
                "job_key": f"{target}-D{horizon}",
                "state": "ready",
                "run_key": run_key,
                "target_local_date": target.isoformat(),
                "issue_local_date": issue.isoformat(),
                "site_ids": [1],
                "cycle_reference_utc": cycle,
                "available_at_utc": available,
                "issue_cutoff_utc": f"{issue}T13:00:00Z",
            }
        )
        connection.execute(
            "INSERT INTO weather_product_runs VALUES (?, 1, ?, ?)", (horizon, cycle, available)
        )
        connection.execute(
            "INSERT INTO weather_ingestion_runs VALUES (?, ?, 'succeeded', ?, 'historical_forecast', 1, ?, ?, ?, ?)",
            (horizon, run_key, target.isoformat(), "a" * 64, "b" * 64, "c" * 64, horizon),
        )
        connection.execute(
            "INSERT INTO weather_daily_feature_snapshots VALUES (?, ?, 1, 2, 'features/1', ?)",
            (horizon, horizon, 280.0 + horizon),
        )
        connection.execute(
            """INSERT INTO weather_field_provenance
               (daily_feature_snapshot_id, field_code, field_variant, statistic_type,
                quality_state, native_unit, normalization_version)
               VALUES (?, 'air_temperature_2m_mean_k', 'canonical', 'mean',
                       'real', 'K', 'normalization/1')""",
            (horizon,),
        )
        for index, (valid, lead) in enumerate(zip(valid_times, leads, strict=True), start=1):
            identity = 100 * horizon + index
            connection.execute(
                "INSERT INTO weather_product_valid_times VALUES (?, ?, ?, ?)",
                (identity, horizon, valid, lead),
            )
            connection.execute(
                "INSERT INTO weather_point_samples VALUES (?, ?, ?, 1)",
                (identity, horizon, identity),
            )
            connection.execute(
                "INSERT INTO weather_daily_feature_snapshot_inputs VALUES (?, ?)",
                (horizon, identity),
            )
    connection.commit()
    connection.close()
    session = {"cohort_plan_id": "a" * 64, "split": "development"}
    monkeypatch.setattr(weather_join, "_resolution", lambda *_: (acquisition_dir, session, jobs))
    monkeypatch.setattr(
        weather_join,
        "resolution_status",
        lambda *_: {"finalized": True, "states": {"ready": 3}},
    )
    monkeypatch.setattr(
        weather_join,
        "_verified_json",
        lambda *_: {"acquisition_id": "b" * 64, "split": "development", "jobs": receipts},
    )
    monkeypatch.setattr(weather_join, "_cohort", lambda *_: ({"source_audit_id": "d" * 64}, jobs))
    monkeypatch.setattr(weather_join, "_load_audit", lambda *_: ({}, [label], "e" * 64))
    return database


def test_join_keeps_three_horizons_distinct_and_rejects_bad_lead(tmp_path, monkeypatch) -> None:
    database = _fixture(tmp_path, monkeypatch)
    result = weather_join.build_joined_dataset(acquisition_id="b" * 64, project_root=tmp_path)
    examples = [
        json.loads(line)
        for line in (
            tmp_path
            / "data/processed/joined-weather"
            / result["dataset_id"]
            / "training_examples.jsonl"
        )
        .read_text()
        .splitlines()
    ]
    assert result["examples"] == 3
    assert len({item["weather"]["run_key"] for item in examples}) == 3
    assert [item["horizon_days"] for item in examples] == [1, 2, 3]
    assert examples[0]["weather"]["feature_quality"][0]["statistic_type"] == "mean"
    connection = sqlite3.connect(database)
    connection.execute("UPDATE weather_product_valid_times SET lead_hours = 24 WHERE id = 101")
    connection.commit()
    connection.close()
    with pytest.raises(weather_join.WeatherJoinError, match="mixes runs, footprints, leads"):
        weather_join.build_joined_dataset(acquisition_id="b" * 64, project_root=tmp_path)
