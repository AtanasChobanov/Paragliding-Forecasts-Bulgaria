"""Cohort split, as-of requests, replay, and audit-integrity gates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from paragliding_forecasts_ml.datasets.weather_cohort import (
    CohortPlanError,
    _encoded,
    _stratified_fill,
    plan_weather_cohort,
)


def _row(site_id: int, day: str, season: int, pattern: str) -> dict:
    return {
        "schema_version": "site-day-flight-label-audit/2",
        "site_id": site_id,
        "site_slug": f"site-{site_id}",
        "local_date": day,
        "source_season": season,
        "timezone": "Europe/Sofia",
        "all_labels_known": True,
        "labels": {
            str(threshold): {"state": "positive" if digit == "1" else "negative"}
            for threshold, digit in zip((100, 200, 300), pattern, strict=True)
        },
    }


def _fixture(root: Path) -> tuple[str, Path]:
    rows = [
        _row(1, "2022-05-01", 2022, "111"),
        _row(2, "2022-05-01", 2022, "000"),
        _row(1, "2023-03-26", 2023, "100"),
        _row(2, "2023-03-26", 2023, "000"),
        _row(1, "2023-10-29", 2024, "111"),
    ]
    known = b"".join(_encoded(row) for row in rows)
    manifest = {
        "schema_version": "site-day-flight-label-audit/2",
        "timezone": "Europe/Sofia",
        "source_seasons": [2022, 2023, 2024],
        "outputs": {
            "known_site_day_labels.jsonl": {
                "sha256": hashlib.sha256(known).hexdigest(),
                "bytes": len(known),
            }
        },
    }
    audit_id = hashlib.sha256(_encoded(manifest)).hexdigest()
    audit = root / "data/processed/flight-label-audits" / audit_id
    audit.mkdir(parents=True)
    (audit / "manifest.json").write_bytes(_encoded({**manifest, "audit_id": audit_id}))
    (audit / "known_site_day_labels.jsonl").write_bytes(known)
    policy = {
        "schema_version": 2,
        "policy_version": "test/2",
        "source_audit_id": audit_id,
        "development_seasons": [2022, 2023],
        "backtest_seasons": [2024],
        "development_positive_100_quota": 2,
        "development_negative_100_quota": 2,
        "mandatory_positive_threshold_km": 200,
        "rare_site_positive_100_max": 0,
        "selection_seed": "synthetic-fixture",
        "technical_sample_target_dates": ["2022-05-01", "2023-10-29"],
        "source_ready_time_local": "16:00",
        "delivery_time_local": "20:00",
        "cycle_hour_utc": 6,
        "timezone": "Europe/Sofia",
        "flying_window_version": "sofia-flying-window/1",
        "horizons_days": [1, 2, 3],
    }
    policy_path = root / "policy.json"
    policy_path.write_bytes(_encoded(policy))
    return audit_id, policy_path


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_cohort_is_site_day_sample_with_three_horizon_jobs_and_stable_replay(
    tmp_path: Path,
) -> None:
    audit_id, policy_path = _fixture(tmp_path)
    first = plan_weather_cohort(audit_id=audit_id, policy_file=policy_path, project_root=tmp_path)
    second = plan_weather_cohort(audit_id=audit_id, policy_file=policy_path, project_root=tmp_path)
    assert first == second
    output = Path(first["output_directory"])
    selected = _jsonl(output / "selected_site_days.jsonl")
    jobs = _jsonl(output / "acquisition_jobs.jsonl")
    assert len(selected) == 5
    assert len(jobs) == 9
    assert [j["horizon_days"] for j in jobs] == [1, 2, 3] * 3
    assert all(j["site_ids"] == [1, 2] for j in jobs[:3])
    assert all(j["site_ids"] == [1, 2] for j in jobs[3:6])
    assert all(j["site_ids"] == [1] for j in jobs[6:])
    assert all(j["cycle_selection_status"] == "unresolved_metadata_probe" for j in jobs)
    assert jobs[0]["issue_local_date"] == "2022-04-30"
    assert jobs[0]["issue_cutoff_utc"] == "2022-04-30T13:00:00Z"
    assert jobs[0]["delivery_deadline_utc"] == "2022-04-30T17:00:00Z"
    assert jobs[0]["candidate_cycles"][0]["cycle_reference_utc"] == "2022-04-30T06:00:00Z"
    assert jobs[0]["candidate_cycles"][0]["lead_hours"] == list(range(25, 36))
    assert len(jobs[0]["candidate_cycles"]) == 1
    assert jobs[6]["issue_local_date"] == "2023-10-28"
    assert jobs[6]["issue_cutoff_utc"] == "2023-10-28T13:00:00Z"
    assert jobs[6]["candidate_cycles"][0]["lead_hours"] == list(range(26, 37))
    assert jobs[7]["issue_local_date"] == "2023-10-27"
    assert jobs[7]["candidate_cycles"][0]["lead_hours"] == list(range(50, 61))
    assert {r["split"] for r in selected if r["source_season"] == 2024} == {"backtest"}


def test_cohort_fails_closed_on_modified_audit_and_cannot_overwrite(tmp_path: Path) -> None:
    audit_id, policy_path = _fixture(tmp_path)
    audit = tmp_path / "data/processed/flight-label-audits" / audit_id
    output = plan_weather_cohort(audit_id=audit_id, policy_file=policy_path, project_root=tmp_path)
    destination = Path(output["output_directory"])
    (destination / "summary.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(CohortPlanError, match="Existing cohort plan differs"):
        plan_weather_cohort(audit_id=audit_id, policy_file=policy_path, project_root=tmp_path)
    (audit / "known_site_day_labels.jsonl").write_bytes(b"{}\n")
    with pytest.raises(CohortPlanError, match="Known-label output disagrees"):
        plan_weather_cohort(audit_id=audit_id, policy_file=policy_path, project_root=tmp_path)


def test_cohort_rejects_ambiguous_season_split(tmp_path: Path) -> None:
    audit_id, policy_path = _fixture(tmp_path)
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["backtest_seasons"] = [2023, 2024]
    policy_path.write_bytes(_encoded(policy))
    with pytest.raises(CohortPlanError, match="unique and chronological"):
        plan_weather_cohort(audit_id=audit_id, policy_file=policy_path, project_root=tmp_path)


def test_stratum_records_exact_conditional_inclusion_fraction() -> None:
    rows = [_row(2, f"2022-05-0{day}", 2022, "000") for day in (1, 2, 3)]
    chosen, fractions = _stratified_fill(rows, set(), 2, "fixture")
    assert len(chosen) == 2
    assert set(fractions.values()) == {(2, 3)}
