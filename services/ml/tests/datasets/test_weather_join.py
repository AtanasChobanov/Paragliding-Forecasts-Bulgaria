"""A joined flight day must keep three distinct issue/run/lead identities."""

from __future__ import annotations

import copy
import json
import sqlite3
from datetime import date, timedelta
from uuid import uuid4

import pytest

from paragliding_forecasts_ml.datasets import weather_join, weather_join_verify
from paragliding_forecasts_ml.datasets.weather_cohort import _encoded
from paragliding_forecasts_ml.ingestion.atmosphere.catalogue import load_catalogue
from paragliding_forecasts_ml.ingestion.gfs.models import GFS_SOURCE_ID, sofia_window_instants
from paragliding_forecasts_ml.ingestion.weather.features.policy import load_feature_policy
from paragliding_forecasts_ml.ingestion.weather.persistence import DAILY_COLUMNS, LAYER_COLUMNS


def _fixture(tmp_path, monkeypatch):
    target = date(2022, 5, 1)
    valid_times = sofia_window_instants(target.isoformat())
    label = {
        "local_date": target.isoformat(),
        "site_id": 1,
        "labels": {
            "100": {
                "state": "positive",
                "reason": "accepted_threshold_flight",
                "positive_source_flight_ids": ["fixture-flight"],
            },
            "200": {
                "state": "negative",
                "reason": "accepted_activity_and_complete_mature_coverage",
                "positive_source_flight_ids": [],
            },
            "300": {
                "state": "negative",
                "reason": "accepted_activity_and_complete_mature_coverage",
                "positive_source_flight_ids": [],
            },
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
    policy, _ = load_feature_policy()
    catalogue = load_catalogue()
    connection.executescript(
        f"""
        CREATE TABLE weather_sources (id INTEGER, code TEXT, source_kind TEXT);
        CREATE TABLE weather_product_runs (id INTEGER, source_id INTEGER, reference_at_utc TEXT, available_at_utc TEXT);
        CREATE TABLE weather_ingestion_runs (id INTEGER, run_key TEXT, status TEXT, target_local_date TEXT, request_purpose TEXT, model_training_allowed INTEGER, raw_manifest_sha256 TEXT, feature_manifest_sha256 TEXT, persistence_input_sha256 TEXT, product_run_id INTEGER);
        CREATE TABLE weather_sampling_footprints (id INTEGER, site_id INTEGER);
        CREATE TABLE weather_daily_feature_snapshots (id INTEGER, ingestion_run_id INTEGER, point_footprint_id INTEGER, neighbourhood_footprint_id INTEGER, feature_contract_version TEXT, {", ".join(f"{column} REAL" for column in DAILY_COLUMNS.values())});
        CREATE TABLE weather_product_valid_times (id INTEGER, product_run_id INTEGER, valid_at_utc TEXT, lead_hours REAL, required_inputs_last_modified_at_utc TEXT);
        CREATE TABLE weather_point_samples (id INTEGER, ingestion_run_id INTEGER, product_valid_time_id INTEGER, point_footprint_id INTEGER);
        CREATE TABLE weather_daily_feature_snapshot_inputs (daily_feature_snapshot_id INTEGER, weather_point_sample_id INTEGER);
        CREATE TABLE weather_daily_feature_profile_layers (id INTEGER, daily_feature_snapshot_id INTEGER, layer_base_agl_m REAL, layer_top_agl_m REAL, {", ".join(f"{column} REAL" for column in LAYER_COLUMNS.values())});
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
                "issue_cutoff_utc": f"{issue}T13:00:00Z",
                "delivery_deadline_utc": f"{issue}T17:00:00Z",
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
                "delivery_deadline_utc": f"{issue}T17:00:00Z",
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
            f"INSERT INTO weather_daily_feature_snapshots VALUES ({','.join('?' for _ in range(5 + len(DAILY_COLUMNS)))})",
            (
                horizon,
                horizon,
                1,
                2,
                policy.feature_contract_version,
                *(1.0 for _ in DAILY_COLUMNS),
            ),
        )
        for entry in policy.daily_fields:
            connection.execute(
                """INSERT INTO weather_field_provenance
                   (daily_feature_snapshot_id, field_code, field_variant, statistic_type,
                    quality_state, native_unit, derivation_version)
                   VALUES (?, ?, ?, ?, 'derived', ?, 'fixture/1')""",
                (
                    horizon,
                    entry.field_code,
                    entry.variant or "canonical",
                    entry.statistic,
                    catalogue.field_unit(entry.field_code),
                ),
            )
        for layer_index, spec in enumerate(policy.profile_layers):
            layer_id = 10 * horizon + layer_index
            applicable = {entry.feature_key for entry in policy.entries_for_layer(spec)}
            connection.execute(
                f"INSERT INTO weather_daily_feature_profile_layers VALUES ({','.join('?' for _ in range(4 + len(LAYER_COLUMNS)))})",
                (
                    layer_id,
                    horizon,
                    spec.layer_base_agl_m,
                    spec.layer_top_agl_m,
                    *(1.0 if key in applicable else None for key in LAYER_COLUMNS),
                ),
            )
            for entry in policy.entries_for_layer(spec):
                connection.execute(
                    """INSERT INTO weather_field_provenance
                       (daily_feature_profile_layer_id, field_code, field_variant, statistic_type,
                        quality_state, native_unit, derivation_version)
                       VALUES (?, ?, ?, ?, 'derived', ?, 'fixture/1')""",
                    (
                        layer_id,
                        entry.field_code,
                        entry.variant or "canonical",
                        entry.statistic,
                        catalogue.field_unit(entry.field_code),
                    ),
                )
        for index, (valid, lead) in enumerate(zip(valid_times, leads, strict=True), start=1):
            identity = 100 * horizon + index
            connection.execute(
                "INSERT INTO weather_product_valid_times VALUES (?, ?, ?, ?, ?)",
                (identity, horizon, valid, lead, available),
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
    target = date(2022, 5, 1)
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
    assert [item["issue_cutoff_utc"] for item in examples] == [
        f"{target - timedelta(days=horizon)}T13:00:00Z" for horizon in (1, 2, 3)
    ]
    assert [item["delivery_deadline_utc"] for item in examples] == [
        f"{target - timedelta(days=horizon)}T17:00:00Z" for horizon in (1, 2, 3)
    ]
    assert examples[0]["weather"]["required_inputs_last_modified_at_utc"].endswith("T10:00:00Z")
    assert any(
        item["statistic_type"] == "mean" for item in examples[0]["weather"]["feature_quality"]
    )
    connection = sqlite3.connect(database)
    connection.execute("UPDATE weather_product_valid_times SET lead_hours = 24 WHERE id = 101")
    connection.commit()
    connection.close()
    with pytest.raises(weather_join.WeatherJoinError, match="mixes runs, footprints, leads"):
        weather_join.build_joined_dataset(acquisition_id="b" * 64, project_root=tmp_path)


def test_join_rejects_missing_or_wrong_hourly_source_timing(tmp_path, monkeypatch) -> None:
    database = _fixture(tmp_path, monkeypatch)
    connection = sqlite3.connect(database)
    connection.execute(
        "UPDATE weather_product_valid_times SET required_inputs_last_modified_at_utc = NULL "
        "WHERE id = 101"
    )
    connection.commit()
    with pytest.raises(weather_join.WeatherJoinError, match="mixes runs, footprints, leads"):
        weather_join.build_joined_dataset(acquisition_id="b" * 64, project_root=tmp_path)
    connection.execute(
        "UPDATE weather_product_valid_times SET required_inputs_last_modified_at_utc = ? "
        "WHERE id = 101",
        ("2022-04-30T12:00:00Z",),
    )
    connection.commit()
    connection.close()
    with pytest.raises(weather_join.WeatherJoinError, match="mixes runs, footprints, leads"):
        weather_join.build_joined_dataset(acquisition_id="b" * 64, project_root=tmp_path)


def _verify_fixture(tmp_path, monkeypatch, *, unavailable_state: str | None = None):
    _fixture(tmp_path, monkeypatch)
    if unavailable_state is not None:
        receipts = weather_join._verified_json(None)["jobs"]
        receipts[1]["state"] = unavailable_state
        if unavailable_state == "late_source":
            receipts[1]["available_at_utc"] = receipts[1]["issue_local_date"] + "T14:00:00Z"
    for name in ("_resolution", "resolution_status", "_verified_json", "_cohort"):
        monkeypatch.setattr(weather_join_verify, name, getattr(weather_join, name))
    result = weather_join.build_joined_dataset(acquisition_id="b" * 64, project_root=tmp_path)
    return result


def test_artifact_verifier_checks_complete_three_horizon_output_and_hashes(
    tmp_path, monkeypatch
) -> None:
    result = _verify_fixture(tmp_path, monkeypatch)
    verified = weather_join_verify.verify_joined_dataset(
        dataset_id=result["dataset_id"], project_root=tmp_path
    )
    assert verified["verified"] is True
    assert verified["examples_by_horizon"] == {"D+1": 1, "D+2": 1, "D+3": 1}
    output = (
        tmp_path
        / "data/processed/joined-weather"
        / result["dataset_id"]
        / "training_examples.jsonl"
    )
    output.write_bytes(output.read_bytes() + b"\n")
    with pytest.raises(weather_join.WeatherJoinError, match="Joined output changed"):
        weather_join_verify.verify_joined_dataset(
            dataset_id=result["dataset_id"], project_root=tmp_path
        )


@pytest.mark.parametrize("state", ["missing_weather", "late_source"])
def test_artifact_verifier_accepts_explicit_unavailable_horizon(
    tmp_path, monkeypatch, state
) -> None:
    result = _verify_fixture(tmp_path, monkeypatch, unavailable_state=state)
    verified = weather_join_verify.verify_joined_dataset(
        dataset_id=result["dataset_id"], project_root=tmp_path
    )
    assert verified["examples"] == 2
    assert verified["excluded"] == 1
    assert verified["excluded_reasons"] == {state: 1}
    assert verified["examples_by_horizon"] == {"D+1": 1, "D+3": 1}


def test_artifact_verifier_rejects_unknown_and_non_nested_labels() -> None:
    evidence = {
        "labels": {
            "100": {"state": "positive", "reason": "accepted", "positive_source_flight_ids": ["f"]},
            "200": {"state": "negative", "reason": "covered", "positive_source_flight_ids": []},
            "300": {"state": "negative", "reason": "covered", "positive_source_flight_ids": []},
        },
        "flight_count": 1,
        "max_distance_km": 120.0,
        "coverage": {"mature": True},
        "label_row_sha256": "a" * 64,
    }
    weather_join_verify._labels(evidence)
    unknown = copy.deepcopy(evidence)
    unknown["labels"]["200"]["state"] = "unknown"
    with pytest.raises(weather_join.WeatherJoinError, match="Unknown label"):
        weather_join_verify._labels(unknown)
    not_nested = copy.deepcopy(evidence)
    not_nested["labels"]["200"] = {
        "state": "positive",
        "reason": "accepted",
        "positive_source_flight_ids": ["f"],
    }
    not_nested["labels"]["100"]["state"] = "negative"
    not_nested["labels"]["100"]["positive_source_flight_ids"] = []
    with pytest.raises(weather_join.WeatherJoinError, match="Negative label disagrees|not nested"):
        weather_join_verify._labels(not_nested)


def test_artifact_verifier_rejects_bad_unit_and_unexplained_null() -> None:
    policy, _ = load_feature_policy()
    entry = policy.daily_fields[0]
    provenance = {
        "field_code": entry.field_code,
        "field_variant": entry.variant or "canonical",
        "statistic_type": entry.statistic,
        "quality_state": "derived",
        "native_unit": load_catalogue().field_unit(entry.field_code),
        "missing_reason_code": None,
        "derivation_version": "fixture/1",
    }
    weather_join_verify._feature_scope({entry.feature_key: 1.0}, [provenance], (entry,))
    wrong_unit = {**provenance, "native_unit": "wrong"}
    with pytest.raises(weather_join.WeatherJoinError, match="unit differs"):
        weather_join_verify._feature_scope({entry.feature_key: 1.0}, [wrong_unit], (entry,))
    unexplained_null = {**provenance, "quality_state": "missing"}
    with pytest.raises(weather_join.WeatherJoinError, match="lacks null value or reason"):
        weather_join_verify._feature_scope({entry.feature_key: None}, [unexplained_null], (entry,))
