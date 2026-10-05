"""Synthetic 06Z metadata checkpoints and bounded batch construction."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from paragliding_forecasts_ml.datasets import weather_full_backfill as full
from paragliding_forecasts_ml.ingestion.atmosphere.catalogue import load_catalogue
from paragliding_forecasts_ml.ingestion.atmosphere.contracts import RequestPlan
from paragliding_forecasts_ml.ingestion.gfs.models import sofia_window_instants
from paragliding_forecasts_ml.ingestion.weather.pipeline import WeatherPreflight


def _fixture(tmp_path, monkeypatch, *, late_index: bool = False):
    target = date(2022, 5, 1)
    jobs = []
    for horizon in (1, 2, 3):
        issue = target - timedelta(days=horizon)
        jobs.append(
            {
                "target_local_date": target.isoformat(),
                "issue_local_date": issue.isoformat(),
                "horizon_days": horizon,
                "split": "development",
                "site_ids": [1, 2],
                "issue_cutoff_utc": f"{issue}T13:00:00Z",
                "delivery_deadline_utc": f"{issue}T17:00:00Z",
                "valid_times_utc": list(sofia_window_instants(target.isoformat())),
                "candidate_cycles": [
                    {"cycle_reference_utc": f"{issue}T06:00:00Z", "lead_hours": []}
                ],
            }
        )
    monkeypatch.setattr(
        full,
        "_cohort",
        lambda *_: (
            {
                "schema_version": "weather-cohort-plan/2",
                "policy": {"cycle_hour_utc": 6, "source_ready_time_local": "16:00"},
            },
            jobs,
        ),
    )
    monkeypatch.setattr(
        full,
        "_preflight",
        lambda *_a, **_k: WeatherPreflight(
            database_url="file:data/local/test.db",
            site_config_sha256="a" * 64,
            sampling_policy_sha256="b" * 64,
            compact_selection_version="crop/1",
        ),
    )
    monkeypatch.setattr(full, "load_weather_usage_policy", lambda *_a, **_k: (None, "c" * 64))
    calls = []

    class FakePlanner:
        def __init__(self, _transport):
            pass

        def plan(self, request, *, created_at_utc):
            calls.append(request.explicit_run_at_utc)
            issue = request.explicit_run_at_utc[:10]
            index_time = f"{issue}T14:00:00Z" if late_index else f"{issue}T10:00:00Z"
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
                    "resolved_run_at_utc": request.explicit_run_at_utc,
                    "available_at_utc": index_time,
                    "ranges": [
                        {
                            "object_last_modified_utc": f"{issue}T09:00:00Z",
                            "index_last_modified_utc": index_time,
                            "byte_start": 0,
                            "byte_end": 1023,
                        }
                    ],
                },
                expected_artifact_keys=("gfs_grib",),
                created_at_utc=created_at_utc,
            )

    monkeypatch.setattr(full, "GfsPlanner", FakePlanner)
    args = SimpleNamespace(
        project_root=tmp_path,
        cohort_plan_id="d" * 64,
        split="development",
        max_new_jobs=2,
        maximum_total_mib=2048,
        allow_metadata_network=True,
        policy_file=None,
        database_url=None,
    )
    return args, calls


def test_metadata_resolution_resumes_and_freezes_06z_batch(tmp_path, monkeypatch) -> None:
    args, calls = _fixture(tmp_path, monkeypatch)
    first = full.resolve(args)
    assert first["states"] == {"ready": 2, "pending": 1}
    assert not first["finalized"]
    second = full.resolve(args)
    assert second["states"] == {"ready": 3}
    assert second["finalized"]
    assert len(calls) == 3
    assert full.resolve(args) == second
    assert len(calls) == 3
    batch = full.batch_create(
        SimpleNamespace(
            project_root=tmp_path,
            acquisition_id=second["acquisition_id"],
            max_target_dates=25,
            max_new_gib=10,
            minimum_free_gib=0,
        )
    )
    _directory, manifest = full._batch(tmp_path, batch["batch_id"])
    assert batch["job_count"] == 3
    assert {job["selected_cycle_utc"][11:13] for job in manifest["jobs"]} == {"06"}
    assert manifest["planned_selected_bytes"] == 3072


def test_index_metadata_after_16_local_is_not_acquired(tmp_path, monkeypatch) -> None:
    args, _calls = _fixture(tmp_path, monkeypatch, late_index=True)
    args.max_new_jobs = 3
    result = full.resolve(args)
    assert result["states"] == {"late_source": 3}
    assert result["finalized"]
    assert full.batch_create(
        SimpleNamespace(
            project_root=tmp_path,
            acquisition_id=result["acquisition_id"],
            max_target_dates=25,
            max_new_gib=10,
            minimum_free_gib=0,
        )
    )["complete"]
