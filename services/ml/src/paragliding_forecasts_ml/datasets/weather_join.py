"""Database-first, horizon-matched weather and audited-flight dataset join."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from paragliding_forecasts_ml.ingestion.gfs.models import GFS_SOURCE_ID
from paragliding_forecasts_ml.storage.sqlite import (
    configured_database_url,
    open_read_only_database,
    repository_root,
)

from .weather_backfill_cli import _cohort
from .weather_cohort import _encoded, _load_audit
from .weather_full_backfill import _resolution, _verified_json, resolution_status

VERSION = "weather-flight-joined-dataset/1"


class WeatherJoinError(RuntimeError):
    """A source row cannot be joined without leakage or ambiguity."""


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _rows(connection: sqlite3.Connection, query: str, parameters: tuple = ()) -> list[dict]:
    return [dict(row) for row in connection.execute(query, parameters)]


def _weather_record(connection: sqlite3.Connection, job: dict, site_id: int) -> dict:
    run_rows = _rows(
        connection,
        """SELECT run.id AS ingestion_run_id, run.run_key, run.status,
                  run.target_local_date, run.request_purpose, run.model_training_allowed,
                  run.raw_manifest_sha256, run.feature_manifest_sha256,
                  run.persistence_input_sha256, product.id AS product_run_id,
                  product.reference_at_utc, product.available_at_utc,
                  source.code AS source_code, source.source_kind
           FROM weather_ingestion_runs AS run
           JOIN weather_product_runs AS product ON product.id = run.product_run_id
           JOIN weather_sources AS source ON source.id = product.source_id
           WHERE run.run_key = ?""",
        (job["run_key"],),
    )
    if len(run_rows) != 1:
        raise WeatherJoinError(f"Weather run is missing or duplicated: {job['run_key']}.")
    run = run_rows[0]
    if (
        run["status"] != "succeeded"
        or run["target_local_date"] != job["target_local_date"]
        or run["request_purpose"] != "historical_forecast"
        or run["model_training_allowed"] != 1
        or run["source_code"] != GFS_SOURCE_ID
        or run["source_kind"] != "forecast"
        or run["reference_at_utc"] != job["cycle_reference_utc"]
        or run["available_at_utc"] != job["available_at_utc"]
        or run["available_at_utc"] > job["issue_cutoff_utc"]
    ):
        raise WeatherJoinError("Persisted weather run violates the fixed 06Z as-of identity.")
    snapshots = _rows(
        connection,
        """SELECT daily.*, footprint.site_id
           FROM weather_daily_feature_snapshots AS daily
           JOIN weather_sampling_footprints AS footprint ON footprint.id = daily.point_footprint_id
           WHERE daily.ingestion_run_id = ? AND footprint.site_id = ?""",
        (run["ingestion_run_id"], site_id),
    )
    if len(snapshots) != 1:
        raise WeatherJoinError("Expected exactly one daily snapshot for the run and site.")
    snapshot = snapshots[0]
    inputs = _rows(
        connection,
        """SELECT valid.valid_at_utc, valid.lead_hours, point.ingestion_run_id,
                  point.point_footprint_id
           FROM weather_daily_feature_snapshot_inputs AS link
           JOIN weather_point_samples AS point ON point.id = link.weather_point_sample_id
           JOIN weather_product_valid_times AS valid ON valid.id = point.product_valid_time_id
           WHERE link.daily_feature_snapshot_id = ?
           ORDER BY valid.valid_at_utc""",
        (snapshot["id"],),
    )
    expected = list(zip(job["valid_times_utc"], job["lead_hours"], strict=True))
    actual = [(item["valid_at_utc"], item["lead_hours"]) for item in inputs]
    if (
        len(inputs) != 11
        or actual != expected
        or any(
            item["ingestion_run_id"] != run["ingestion_run_id"]
            or item["point_footprint_id"] != snapshot["point_footprint_id"]
            for item in inputs
        )
    ):
        raise WeatherJoinError("Daily snapshot mixes runs, footprints, leads, or valid hours.")
    layers = _rows(
        connection,
        """SELECT * FROM weather_daily_feature_profile_layers
           WHERE daily_feature_snapshot_id = ?
           ORDER BY layer_base_agl_m, layer_top_agl_m""",
        (snapshot["id"],),
    )
    provenance = _rows(
        connection,
        """SELECT field_code, field_variant, statistic_type, quality_state,
                  missing_reason_code, source_reference_at_utc,
                  native_field_name, native_unit, native_sign_convention,
                  native_step_type, step_start_hours, step_end_hours,
                  normalization_method, normalization_version,
                  derivation_method, derivation_version, raw_artifact_key,
                  native_message_reference
           FROM weather_field_provenance
           WHERE daily_feature_snapshot_id = ?
           ORDER BY field_code, field_variant, statistic_type""",
        (snapshot["id"],),
    )
    layer_ids = [item["id"] for item in layers]
    layer_provenance = (
        _rows(
            connection,
            """SELECT daily_feature_profile_layer_id, field_code, field_variant,
                      statistic_type, quality_state, missing_reason_code,
                      source_reference_at_utc, native_field_name, native_unit,
                      native_sign_convention, native_step_type, step_start_hours,
                      step_end_hours, normalization_method, normalization_version,
                      derivation_method, derivation_version, raw_artifact_key,
                      native_message_reference
               FROM weather_field_provenance
               WHERE daily_feature_profile_layer_id IN ("""
            + ",".join("?" for _ in layer_ids)
            + ") ORDER BY daily_feature_profile_layer_id, field_code, field_variant, statistic_type",
            tuple(layer_ids),
        )
        if layer_ids
        else []
    )
    feature_values = {
        key: value
        for key, value in snapshot.items()
        if key
        not in {
            "id",
            "ingestion_run_id",
            "point_footprint_id",
            "neighbourhood_footprint_id",
            "site_id",
        }
    }
    return {
        "run_key": run["run_key"],
        "product_reference_at_utc": run["reference_at_utc"],
        "product_available_at_utc": run["available_at_utc"],
        "raw_manifest_sha256": run["raw_manifest_sha256"],
        "feature_manifest_sha256": run["feature_manifest_sha256"],
        "persistence_input_sha256": run["persistence_input_sha256"],
        "feature_contract_version": snapshot["feature_contract_version"],
        "features": feature_values,
        "profile_layers": [
            {
                key: value
                for key, value in item.items()
                if key not in {"id", "daily_feature_snapshot_id"}
            }
            for item in layers
        ],
        "feature_quality": provenance,
        "profile_layer_quality": [
            {
                **{
                    key: value
                    for key, value in item.items()
                    if key != "daily_feature_profile_layer_id"
                },
                "layer_index": layer_ids.index(item["daily_feature_profile_layer_id"]),
            }
            for item in layer_provenance
        ],
    }


def build_joined_dataset(
    *, acquisition_id: str, project_root: Path | None = None, database_url: str | None = None
) -> dict[str, Any]:
    root = (project_root or repository_root()).resolve()
    acquisition_dir, session, cohort_jobs = _resolution(root, acquisition_id)
    resolution = resolution_status(
        SimpleNamespace(project_root=root, acquisition_id=acquisition_id)
    )
    if not resolution["finalized"] or resolution["states"].get("pending", 0):
        raise WeatherJoinError("Acquisition metadata is not finalized and verified.")
    acquisition = _verified_json(acquisition_dir / "manifest.json", "manifest_sha256")
    if acquisition["acquisition_id"] != acquisition_id or acquisition["split"] == "all":
        raise WeatherJoinError("Join requires one finalized development or backtest acquisition.")
    cohort, _all_jobs = _cohort(root, session["cohort_plan_id"])
    audit_id = cohort["source_audit_id"]
    _audit, label_rows, _audit_sha = _load_audit(
        root / "data/processed/flight-label-audits" / audit_id, audit_id
    )
    labels_by_key = {(item["local_date"], item["site_id"]): item for item in label_rows}
    cohort_directory = root / "data/processed/weather-cohorts" / session["cohort_plan_id"]
    selected = [
        json.loads(line)
        for line in (cohort_directory / "selected_site_days.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    by_job = {(item["target_local_date"], item["horizon_days"]): item for item in cohort_jobs}
    receipts = {item["job_key"]: item for item in acquisition["jobs"]}
    if len(receipts) != len(cohort_jobs):
        raise WeatherJoinError("Acquisition contains duplicate or missing job receipts.")
    connection = open_read_only_database(configured_database_url(database_url), root)
    connection.row_factory = sqlite3.Row
    examples = []
    excluded = []
    try:
        for site_day in selected:
            if site_day["split"] != acquisition["split"]:
                continue
            target = site_day["target_local_date"]
            site_id = site_day["site_id"]
            label = labels_by_key[(target, site_id)]
            if _sha(_encoded(label)) != site_day["label_row_sha256"]:
                raise WeatherJoinError("Selected label differs from its audited row.")
            label_evidence = {
                "labels": label["labels"],
                "flight_count": label["flight_count"],
                "max_distance_km": label["max_distance_km"],
                "coverage": label["coverage"],
                "label_row_sha256": site_day["label_row_sha256"],
            }
            for horizon in (1, 2, 3):
                job = by_job[(target, horizon)]
                receipt = receipts[f"{target}-D{horizon}"]
                identity = {
                    "site_id": site_id,
                    "site_slug": site_day["site_slug"],
                    "target_local_date": target,
                    "issue_local_date": job["issue_local_date"],
                    "horizon_days": horizon,
                    "split": site_day["split"],
                    "cycle_reference_utc": job["candidate_cycles"][0]["cycle_reference_utc"],
                    "lead_hours": job["candidate_cycles"][0]["lead_hours"],
                    "valid_times_utc": job["valid_times_utc"],
                    "sampling_weight": site_day["sampling_weight"],
                    "inclusion_probability": site_day["inclusion_probability"],
                }
                if receipt["state"] != "ready":
                    excluded.append(
                        {**identity, "reason": receipt["state"], "label_evidence": label_evidence}
                    )
                    continue
                if site_id not in receipt["site_ids"]:
                    raise WeatherJoinError("Resolved acquisition omitted a selected site.")
                weather = _weather_record(
                    connection, {**job, **receipt, "lead_hours": identity["lead_hours"]}, site_id
                )
                examples.append({**identity, "weather": weather, "label_evidence": label_evidence})
    finally:
        connection.close()
    expected = sum(1 for item in selected if item["split"] == acquisition["split"]) * 3
    if len(examples) + len(excluded) != expected:
        raise WeatherJoinError("Joined and excluded example counts do not cover the split.")
    if len(
        {(item["site_id"], item["target_local_date"], item["horizon_days"]) for item in examples}
    ) != len(examples):
        raise WeatherJoinError("Joined examples contain a duplicate site/date/horizon.")
    filename = (
        "training_examples.jsonl"
        if acquisition["split"] == "development"
        else "backtest_2025_examples.jsonl"
    )
    files = {
        filename: b"".join(_encoded(item) for item in examples),
        "excluded_examples.jsonl": b"".join(_encoded(item) for item in excluded),
    }
    manifest = {
        "schema_version": VERSION,
        "acquisition_id": acquisition_id,
        "acquisition_manifest_sha256": _sha((acquisition_dir / "manifest.json").read_bytes()),
        "cohort_plan_id": session["cohort_plan_id"],
        "source_audit_id": audit_id,
        "split": acquisition["split"],
        "examples": len(examples),
        "excluded": len(excluded),
        "excluded_reasons": dict(sorted(Counter(item["reason"] for item in excluded).items())),
        "outputs": {
            name: {"bytes": len(content), "sha256": _sha(content)}
            for name, content in sorted(files.items())
        },
    }
    dataset_id = _sha(_encoded(manifest))
    files["manifest.json"] = _encoded({**manifest, "dataset_id": dataset_id})
    destination = root / "data/processed/joined-weather" / dataset_id
    if destination.exists():
        if any((destination / name).read_bytes() != content for name, content in files.items()):
            raise WeatherJoinError("Existing joined dataset differs from its immutable identity.")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".joined-weather-", dir=destination.parent
        ) as temporary:
            staging = Path(temporary) / "dataset"
            staging.mkdir()
            for name, content in files.items():
                (staging / name).write_bytes(content)
            staging.rename(destination)
    return {
        "dataset_id": dataset_id,
        "output_directory": str(destination),
        "split": acquisition["split"],
        "examples": len(examples),
        "excluded": len(excluded),
    }
