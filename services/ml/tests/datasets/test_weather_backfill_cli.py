"""Offline tests for the bounded technical GFS sample boundary."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from paragliding_forecasts_ml.datasets import weather_backfill_cli as sample
from paragliding_forecasts_ml.ingestion.atmosphere.catalogue import load_catalogue
from paragliding_forecasts_ml.ingestion.atmosphere.contracts import RequestPlan
from paragliding_forecasts_ml.ingestion.gfs.models import sofia_window_instants
from paragliding_forecasts_ml.ingestion.weather.pipeline import WeatherPreflight
from paragliding_forecasts_ml.ingestion.weather.serialization import canonical_json_bytes


def _cohort_fixture(root):
    target = date(2025, 8, 2)
    jobs = []
    for horizon in (1, 2, 3):
        issue = target - timedelta(days=horizon)
        jobs.append(
            {
                "target_local_date": target.isoformat(),
                "horizon_days": horizon,
                "issue_local_date": issue.isoformat(),
                "issue_cutoff_utc": f"{issue}T17:00:00Z",
                "site_ids": [1, 2],
                "valid_times_utc": list(sofia_window_instants(target.isoformat())),
            }
        )
    content = b"".join(canonical_json_bytes(job) for job in jobs)
    body = {
        "policy": {"technical_sample_target_dates": [target.isoformat()]},
        "outputs": {
            "acquisition_jobs.jsonl": {
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        },
    }
    cohort_id = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
    directory = root / "data/processed/weather-cohorts" / cohort_id
    directory.mkdir(parents=True)
    (directory / "acquisition_jobs.jsonl").write_bytes(content)
    (directory / "manifest.json").write_bytes(canonical_json_bytes({**body, "plan_id": cohort_id}))
    return cohort_id


def test_probe_freezes_three_horizons_without_grib_download(tmp_path, monkeypatch) -> None:
    cohort_id = _cohort_fixture(tmp_path)
    monkeypatch.setattr(
        sample,
        "_preflight",
        lambda *_a, **_k: WeatherPreflight(
            database_url="file:data/local/test.db",
            site_config_sha256="a" * 64,
            sampling_policy_sha256="b" * 64,
            compact_selection_version="crop/1",
        ),
    )
    monkeypatch.setattr(sample, "load_weather_usage_policy", lambda *_a, **_k: (None, "c" * 64))

    class FakePlanner:
        def __init__(self, _transport):
            pass

        def plan(self, request, *, created_at_utc):
            catalogue = load_catalogue()
            return RequestPlan(
                run_key=request.run_key,
                source_id="noaa_gfs_0p25_aws_grib2",
                source_kind="forecast",
                ingestion_method="public_object_archive",
                request_purpose="historical_forecast",
                catalogue_version=catalogue.version,
                catalogue_sha256=catalogue.sha256,
                adapter_request_schema_version=2,
                adapter_request={
                    "available_at_utc": request.explicit_run_at_utc,
                    "ranges": [{"byte_start": 0, "byte_end": 1023}],
                },
                expected_artifact_keys=("gfs_grib",),
                created_at_utc=created_at_utc,
            )

    monkeypatch.setattr(sample, "GfsPlanner", FakePlanner)
    args = SimpleNamespace(
        project_root=tmp_path,
        cohort_plan_id=cohort_id,
        target_date=["2025-08-02"],
        cycle=12,
        max_jobs=3,
        maximum_total_mib=2048,
        maximum_sample_gib=1,
        allow_metadata_network=True,
        policy_file=None,
        database_url=None,
    )
    output = sample.probe(args)
    assert output["job_count"] == 3
    assert output["total_selected_bytes"] == 3072
    assert [job["horizon_days"] for job in output["jobs"]] == [1, 2, 3]
    assert len({job["run_key"] for job in output["jobs"]}) == 3
    state = sample.status(SimpleNamespace(project_root=tmp_path, sample_id=output["sample_id"]))
    assert {job["state"] for job in state["jobs"]} == {"pending"}
    assert output["jobs"][0]["site_ids"] == [1, 2]

    manifest_path = (
        tmp_path / "data/processed/weather-samples" / output["sample_id"] / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_bytes())
    assert manifest["purpose"] == "technical_timing_only_not_training_as_of_policy"
    manifest["purpose"] = "tampered"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(sample.BackfillError, match="Sample manifest identity"):
        sample.status(SimpleNamespace(project_root=tmp_path, sample_id=output["sample_id"]))


def test_probe_requires_explicit_metadata_permission(tmp_path) -> None:
    args = SimpleNamespace(allow_metadata_network=False)
    with pytest.raises(sample.BackfillError, match="allow-metadata-network"):
        sample.probe(args)
