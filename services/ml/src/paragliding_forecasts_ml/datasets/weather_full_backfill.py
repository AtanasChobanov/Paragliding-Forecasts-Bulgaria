"""Checkpointed metadata resolution and bounded batches for the fixed 06Z cohort."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from paragliding_forecasts_ml.ingestion.atmosphere.contracts import RequestPlan
from paragliding_forecasts_ml.ingestion.gfs.models import SOFIA_FLYING_WINDOW_VERSION, GfsRequest
from paragliding_forecasts_ml.ingestion.gfs.planner import GfsPlanner, GfsPlanningError
from paragliding_forecasts_ml.ingestion.gfs.transport import RetryingTransport, UrllibTransport
from paragliding_forecasts_ml.ingestion.weather.persistence_models import load_weather_usage_policy
from paragliding_forecasts_ml.ingestion.weather.pipeline import _preflight
from paragliding_forecasts_ml.ingestion.weather.serialization import (
    canonical_json_bytes,
    sha256_file,
)
from paragliding_forecasts_ml.storage.sqlite import configured_database_url, open_read_only_database

from .weather_backfill_cli import BackfillError, _cohort, _job_status, _json_bytes, _now, _sha

ACQUISITION_SCHEMA = "weather-06z-acquisition/1"
BATCH_SCHEMA = "weather-06z-batch/1"
SPLITS = ("development", "backtest", "all")


def _directory(root: Path, kind: str, identity: str) -> Path:
    if len(identity) != 64 or any(char not in "0123456789abcdef" for char in identity):
        raise BackfillError(f"Invalid {kind} identity.")
    parent = (root / "data/processed" / kind).resolve()
    directory = (parent / identity).resolve()
    if directory.parent != parent:
        raise BackfillError(f"Invalid {kind} path.")
    return directory


def _verified_json(path: Path, identity_field: str | None = None) -> dict:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise BackfillError(f"Invalid JSON object: {path}.")
    if identity_field is not None:
        identity = value.get(identity_field)
        body = {key: item for key, item in value.items() if key != identity_field}
        if not isinstance(identity, str) or _sha(canonical_json_bytes(body)) != identity:
            raise BackfillError(f"Identity mismatch: {path}.")
    return value


def _exclusive_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = _json_bytes(value)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{path.name}-", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    except FileExistsError:
        if path.read_bytes() != content:
            raise BackfillError(f"Immutable checkpoint differs: {path}.") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _job_key(job: dict) -> str:
    return f"{job['target_local_date']}-D{job['horizon_days']}"


def _resolution(root: Path, acquisition_id: str) -> tuple[Path, dict, list[dict]]:
    directory = _directory(root, "weather-acquisitions", acquisition_id)
    session = _verified_json(directory / "session.json", "acquisition_id")
    if (
        session["acquisition_id"] != acquisition_id
        or session["schema_version"] != ACQUISITION_SCHEMA
    ):
        raise BackfillError("Acquisition session identity/schema differs.")
    cohort, jobs = _cohort(root, session["cohort_plan_id"])
    if cohort.get("schema_version") != "weather-cohort-plan/2":
        raise BackfillError("Acquisition requires the fixed 06Z cohort plan.")
    selected = [job for job in jobs if session["split"] in ("all", job["split"])]
    if len(selected) != session["job_count"]:
        raise BackfillError("Cohort job count differs from acquisition session.")
    return directory, session, selected


def _receipt(directory: Path, job: dict) -> dict | None:
    path = directory / "jobs" / f"{_job_key(job)}.json"
    if not path.exists():
        return None
    receipt = _verified_json(path, "receipt_sha256")
    if receipt["job_key"] != _job_key(job):
        raise BackfillError("Acquisition checkpoint belongs to another job.")
    if receipt["state"] == "ready":
        plan_path = directory / "plans" / receipt["plan_file"]
        if sha256_file(plan_path) != receipt["plan_sha256"]:
            raise BackfillError("Frozen acquisition request plan changed.")
        plan = RequestPlan.model_validate_json(plan_path.read_bytes(), strict=True)
        if plan.run_key != receipt["run_key"]:
            raise BackfillError("Acquisition plan run key differs.")
    return receipt


def resolve(args) -> dict:
    """Perform at most max_new_jobs metadata checks; never request GRIB payloads."""
    if not args.allow_metadata_network:
        raise BackfillError("Pass --allow-metadata-network for NOAA HEAD/index requests.")
    root = args.project_root.resolve()
    cohort, cohort_jobs = _cohort(root, args.cohort_plan_id)
    if (
        cohort.get("schema_version") != "weather-cohort-plan/2"
        or cohort["policy"].get("cycle_hour_utc") != 6
        or cohort["policy"].get("source_ready_time_local") != "16:00"
    ):
        raise BackfillError("Full resolution requires the fixed 06Z/16:00 cohort plan.")
    selected = [job for job in cohort_jobs if args.split in ("all", job["split"])]
    preflight = _preflight(args.policy_file, args.database_url, root)
    _usage, usage_hash = load_weather_usage_policy(
        args.policy_file, source_family="gfs", project_root=root
    )
    body = {
        "schema_version": ACQUISITION_SCHEMA,
        "cohort_plan_id": args.cohort_plan_id,
        "split": args.split,
        "job_count": len(selected),
        "maximum_total_mib": args.maximum_total_mib,
        "site_config_sha256": preflight.site_config_sha256,
        "sampling_policy_sha256": preflight.sampling_policy_sha256,
        "compact_selection_version": preflight.compact_selection_version,
        "usage_policy_sha256": usage_hash,
    }
    acquisition_id = _sha(canonical_json_bytes(body))
    directory = _directory(root, "weather-acquisitions", acquisition_id)
    _exclusive_json(directory / "session.json", {**body, "acquisition_id": acquisition_id})
    directory, _session, selected = _resolution(root, acquisition_id)
    planner = GfsPlanner(RetryingTransport(UrllibTransport()))
    new_count = 0
    for job in selected:
        if _receipt(directory, job) is not None:
            continue
        if new_count >= args.max_new_jobs:
            break
        candidates = job["candidate_cycles"]
        expected_cycle = f"{job['issue_local_date']}T06:00:00Z"
        if len(candidates) != 1 or candidates[0]["cycle_reference_utc"] != expected_cycle:
            raise BackfillError("Cohort job does not pin its issue day's 06Z cycle.")
        plan_path = directory / "plans" / f"{_job_key(job)}.json"
        if plan_path.exists():
            plan = RequestPlan.model_validate_json(plan_path.read_bytes(), strict=True)
        else:
            request = GfsRequest(
                run_key=str(uuid4()),
                request_purpose="historical_forecast",
                valid_at_utc=tuple(job["valid_times_utc"]),
                explicit_run_at_utc=expected_cycle,
                maximum_total_bytes=args.maximum_total_mib * 2**20,
                target_local_date=job["target_local_date"],
                flying_window_version=SOFIA_FLYING_WINDOW_VERSION,
                site_config_sha256=preflight.site_config_sha256,
                sampling_policy_sha256=preflight.sampling_policy_sha256,
                compact_selection_version=preflight.compact_selection_version,
            )
            try:
                plan = planner.plan(request, created_at_utc=_now())
            except GfsPlanningError as error:
                if "exceeds the configured total byte cap" in str(error):
                    raise BackfillError(
                        "GFS job exceeds --maximum-total-mib; raise the reviewed cap before continuing."
                    ) from error
                if error.kind not in {"absent_file", "incomplete_run"}:
                    raise
                missing = {
                    "job_key": _job_key(job),
                    "state": "missing_weather",
                    "reason": error.kind,
                    "target_local_date": job["target_local_date"],
                    "issue_local_date": job["issue_local_date"],
                    "horizon_days": job["horizon_days"],
                    "split": job["split"],
                    "site_ids": job["site_ids"],
                    "cycle_reference_utc": expected_cycle,
                    "issue_cutoff_utc": job["issue_cutoff_utc"],
                }
                _exclusive_json(
                    directory / "jobs" / f"{_job_key(job)}.json",
                    {**missing, "receipt_sha256": _sha(canonical_json_bytes(missing))},
                )
                new_count += 1
                continue
            _exclusive_json(plan_path, plan.model_dump(mode="json"))
        resolved = plan.adapter_request
        ranges = resolved["ranges"]
        source_latest = max(
            max(item["object_last_modified_utc"], item["index_last_modified_utc"])
            for item in ranges
        )
        if (
            plan.run_key is None
            or resolved["resolved_run_at_utc"] != expected_cycle
            or source_latest != resolved["available_at_utc"]
        ):
            raise BackfillError("06Z acquisition source identity is inconsistent.")
        state = "ready" if source_latest <= job["issue_cutoff_utc"] else "late_source"
        count = sum(item["byte_end"] - item["byte_start"] + 1 for item in ranges)
        receipt = {
            "job_key": _job_key(job),
            "state": state,
            "target_local_date": job["target_local_date"],
            "issue_local_date": job["issue_local_date"],
            "horizon_days": job["horizon_days"],
            "split": job["split"],
            "site_ids": job["site_ids"],
            "issue_cutoff_utc": job["issue_cutoff_utc"],
            "delivery_deadline_utc": job["delivery_deadline_utc"],
            "cycle_reference_utc": expected_cycle,
            "available_at_utc": source_latest,
            "selected_bytes": count,
            "run_key": plan.run_key,
            "plan_file": plan_path.name,
            "plan_sha256": sha256_file(plan_path),
        }
        _exclusive_json(
            directory / "jobs" / f"{_job_key(job)}.json",
            {**receipt, "receipt_sha256": _sha(canonical_json_bytes(receipt))},
        )
        new_count += 1
    receipts = [_receipt(directory, job) for job in selected]
    if all(item is not None for item in receipts):
        completed = [item for item in receipts if item is not None]
        result = {
            "schema_version": ACQUISITION_SCHEMA,
            "acquisition_id": acquisition_id,
            "cohort_plan_id": args.cohort_plan_id,
            "split": args.split,
            "session_sha256": sha256_file(directory / "session.json"),
            "jobs": completed,
            "total_selected_bytes": sum(
                item["selected_bytes"] for item in completed if item["state"] == "ready"
            ),
        }
        _exclusive_json(
            directory / "manifest.json",
            {**result, "manifest_sha256": _sha(canonical_json_bytes(result))},
        )
    return resolution_status(SimpleNamespace(project_root=root, acquisition_id=acquisition_id))


def resolution_status(args) -> dict:
    root = args.project_root.resolve()
    directory, session, jobs = _resolution(root, args.acquisition_id)
    receipts = [_receipt(directory, job) for job in jobs]
    states = defaultdict(int)
    for item in receipts:
        states[item["state"] if item is not None else "pending"] += 1
    manifest_path = directory / "manifest.json"
    if manifest_path.exists():
        manifest = _verified_json(manifest_path, "manifest_sha256")
        if manifest["acquisition_id"] != args.acquisition_id or len(manifest["jobs"]) != len(jobs):
            raise BackfillError("Acquisition final manifest differs from checkpoints.")
        if manifest["jobs"] != receipts:
            raise BackfillError("Acquisition final manifest jobs differ from checkpoints.")
    return {
        "acquisition_id": args.acquisition_id,
        "split": session["split"],
        "job_count": len(jobs),
        "states": dict(states),
        "finalized": manifest_path.exists(),
        "total_selected_bytes": sum(
            item["selected_bytes"]
            for item in receipts
            if item is not None and item["state"] == "ready"
        ),
        "output_directory": str(directory),
    }


def _batch(root: Path, batch_id: str) -> tuple[Path, dict]:
    directory = _directory(root, "weather-batches", batch_id)
    manifest = _verified_json(directory / "manifest.json", "batch_id")
    if manifest["schema_version"] != BATCH_SCHEMA or manifest["batch_id"] != batch_id:
        raise BackfillError("Weather batch schema or identity differs.")
    for job in manifest["jobs"]:
        path = directory / job["plan_file"]
        if sha256_file(path) != job["plan_sha256"]:
            raise BackfillError("Weather batch request plan changed.")
        plan = RequestPlan.model_validate_json(path.read_bytes(), strict=True)
        if plan.run_key != job["run_key"]:
            raise BackfillError("Weather batch run key differs.")
    return directory, manifest


def batch_create(args) -> dict:
    root = args.project_root.resolve()
    acquisition_dir, _session, _jobs = _resolution(root, args.acquisition_id)
    acquisition = _verified_json(acquisition_dir / "manifest.json", "manifest_sha256")
    if acquisition["acquisition_id"] != args.acquisition_id:
        raise BackfillError("Acquisition manifest ID differs.")
    parent = root / "data/processed/weather-batches"
    used: set[str] = set()
    if parent.exists():
        connection = open_read_only_database(
            configured_database_url(getattr(args, "database_url", None)), root
        )
        for path in sorted(parent.iterdir()):
            if not path.is_dir():
                continue
            _directory_check, existing = _batch(root, path.name)
            if existing["acquisition_id"] != args.acquisition_id:
                continue
            if any(_job_status(root, job)["state"] != "persisted" for job in existing["jobs"]):
                connection.close()
                return {
                    "batch_id": path.name,
                    "acquisition_id": args.acquisition_id,
                    "target_dates": existing["target_dates"],
                    "job_count": len(existing["jobs"]),
                    "planned_selected_bytes": existing["planned_selected_bytes"],
                    "output_directory": str(path),
                    "resume_existing": True,
                }
            for job in existing["jobs"]:
                row = connection.execute(
                    "SELECT status FROM weather_ingestion_runs WHERE run_key = ?",
                    (job["run_key"],),
                ).fetchone()
                if row is None or row[0] != "succeeded":
                    connection.close()
                    raise BackfillError("A completed batch lacks its succeeded SQLite row.")
                used.add(job["run_key"])
        connection.close()
    by_date: dict[str, list[dict]] = defaultdict(list)
    for job in acquisition["jobs"]:
        by_date[job["target_local_date"]].append(job)
    selected: list[dict] = []
    selected_dates: list[str] = []
    planned_bytes = 0
    cap = args.max_new_gib * 2**30
    for target, group in sorted(by_date.items()):
        ready = [job for job in group if job["state"] == "ready" and job["run_key"] not in used]
        if not ready:
            continue
        if len(selected_dates) >= args.max_target_dates:
            break
        next_bytes = sum(job["selected_bytes"] + 64 * 2**20 for job in ready)
        if planned_bytes + next_bytes + 2 * 2**30 > cap:
            if not selected:
                raise BackfillError("The next complete target date exceeds the batch byte cap.")
            break
        selected.extend(ready)
        selected_dates.append(target)
        planned_bytes += next_bytes
    if not selected:
        return {"acquisition_id": args.acquisition_id, "complete": True, "next_batch": None}
    if shutil.disk_usage(root).free < planned_bytes + (args.minimum_free_gib + 2) * 2**30:
        raise BackfillError("D: free space cannot hold the proposed batch and reserve.")
    jobs = [
        {
            **{
                key: job[key]
                for key in (
                    "target_local_date",
                    "issue_local_date",
                    "horizon_days",
                    "split",
                    "site_ids",
                    "issue_cutoff_utc",
                    "delivery_deadline_utc",
                    "cycle_reference_utc",
                    "available_at_utc",
                    "selected_bytes",
                    "run_key",
                    "plan_file",
                    "plan_sha256",
                )
            },
            "selected_cycle_utc": job["cycle_reference_utc"],
        }
        for job in selected
    ]
    body = {
        "schema_version": BATCH_SCHEMA,
        "acquisition_id": args.acquisition_id,
        "acquisition_manifest_sha256": sha256_file(acquisition_dir / "manifest.json"),
        "target_dates": selected_dates,
        "jobs": jobs,
        "planned_selected_bytes": sum(job["selected_bytes"] for job in jobs),
        "planned_new_bytes_with_allowance": planned_bytes + 2 * 2**30,
        "max_new_gib": args.max_new_gib,
        "minimum_free_gib": args.minimum_free_gib,
        "site_config_sha256": _session["site_config_sha256"],
        "sampling_policy_sha256": _session["sampling_policy_sha256"],
        "compact_selection_version": _session["compact_selection_version"],
        "usage_policy_sha256": _session["usage_policy_sha256"],
    }
    batch_id = _sha(canonical_json_bytes(body))
    directory = _directory(root, "weather-batches", batch_id)
    if directory.exists():
        _batch(root, batch_id)
    else:
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".weather-batch-", dir=parent) as temporary:
            staging = Path(temporary) / "batch"
            staging.mkdir()
            for job in jobs:
                source = acquisition_dir / "plans" / job["plan_file"]
                shutil.copyfile(source, staging / job["plan_file"])
            _exclusive_json(staging / "manifest.json", {**body, "batch_id": batch_id})
            staging.rename(directory)
    return {
        "batch_id": batch_id,
        "acquisition_id": args.acquisition_id,
        "target_dates": selected_dates,
        "job_count": len(jobs),
        "planned_selected_bytes": body["planned_selected_bytes"],
        "output_directory": str(directory),
    }
