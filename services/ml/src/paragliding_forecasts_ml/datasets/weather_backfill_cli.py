"""Bounded, resumable technical GFS sample over a frozen flight cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from ..ingestion.atmosphere.contracts import RequestPlan
from ..ingestion.gfs.collector import GfsCollectionError, GfsCollector
from ..ingestion.gfs.models import SOFIA_FLYING_WINDOW_VERSION, GfsRequest
from ..ingestion.gfs.planner import GfsPlanner, GfsPlanningError
from ..ingestion.gfs.transport import GfsTransportError, RetryingTransport, UrllibTransport
from ..ingestion.weather.artifact_audit import audit_weather_artifacts
from ..ingestion.weather.artifacts import ArtifactError, WeatherArtifactStore, repository_root
from ..ingestion.weather.persistence_models import load_weather_usage_policy
from ..ingestion.weather.pipeline import WeatherPipelineError, _preflight, resume_run
from ..ingestion.weather.retention import audit_compact
from ..ingestion.weather.serialization import canonical_json_bytes, sha256_file
from ..ingestion.weather.state import RunStateLedger, StateError
from ..storage.sqlite import DatabaseConfigurationError, open_read_only_database


class BackfillError(RuntimeError):
    """A bounded sample cannot be probed or executed safely."""


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False).encode() + b"\n"


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cohort(root: Path, cohort_id: str) -> tuple[dict, list[dict]]:
    directory = (root / "data/processed/weather-cohorts" / cohort_id).resolve()
    if directory.parent != (root / "data/processed/weather-cohorts").resolve():
        raise BackfillError("Invalid cohort ID.")
    manifest = json.loads((directory / "manifest.json").read_bytes())
    if manifest.get("plan_id") != cohort_id:
        raise BackfillError("Cohort plan ID differs from its manifest.")
    identity = {key: value for key, value in manifest.items() if key != "plan_id"}
    if _sha(canonical_json_bytes(identity)) != cohort_id:
        raise BackfillError("Cohort manifest identity differs.")
    for name, expected in manifest["outputs"].items():
        content = (directory / name).read_bytes()
        if len(content) != expected["bytes"] or _sha(content) != expected["sha256"]:
            raise BackfillError(f"Cohort output changed: {name}.")
    jobs = [
        json.loads(line)
        for line in (directory / "acquisition_jobs.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    return manifest, jobs


def _sample(root: Path, sample_id: str) -> tuple[Path, dict]:
    directory = (root / "data/processed/weather-samples" / sample_id).resolve()
    if directory.parent != (root / "data/processed/weather-samples").resolve():
        raise BackfillError("Invalid sample ID.")
    manifest = json.loads((directory / "manifest.json").read_bytes())
    if manifest.get("sample_id") != sample_id:
        raise BackfillError("Sample ID differs from its manifest.")
    identity = {key: value for key, value in manifest.items() if key != "sample_id"}
    if _sha(canonical_json_bytes(identity)) != sample_id:
        raise BackfillError("Sample manifest identity differs.")
    for job in manifest["jobs"]:
        path = directory / job["plan_file"]
        if sha256_file(path) != job["plan_sha256"]:
            raise BackfillError(f"Sample request plan changed: {path.name}.")
        plan = RequestPlan.model_validate_json(path.read_bytes(), strict=True)
        if plan.run_key != job["run_key"]:
            raise BackfillError("Sample run key differs from request plan.")
    return directory, manifest


def _workload(root: Path, args: argparse.Namespace) -> tuple[Path, dict]:
    if getattr(args, "batch_id", None) is not None:
        from .weather_full_backfill import _batch

        return _batch(root, args.batch_id)
    return _sample(root, args.sample_id)


def probe(args: argparse.Namespace) -> dict:
    if not args.allow_metadata_network:
        raise BackfillError("Pass --allow-metadata-network for NOAA HEAD/index requests.")
    root = args.project_root.resolve()
    cohort, cohort_jobs = _cohort(root, args.cohort_plan_id)
    sample_dates = set(cohort["policy"]["technical_sample_target_dates"])
    selected_dates = set(args.target_date or sample_dates)
    if not selected_dates or not selected_dates <= sample_dates:
        raise BackfillError("Target dates must be from the cohort's pinned technical sample.")
    selected = [job for job in cohort_jobs if job["target_local_date"] in selected_dates]
    if len(selected) != 3 * len(selected_dates) or len(selected) > args.max_jobs:
        raise BackfillError("Expected all three horizons per date within --max-jobs.")
    preflight = _preflight(args.policy_file, args.database_url, root)
    _usage_policy, usage_policy_sha256 = load_weather_usage_policy(
        args.policy_file, source_family="gfs", project_root=root
    )
    transport = RetryingTransport(UrllibTransport())
    planner = GfsPlanner(transport)
    outputs: list[tuple[str, bytes]] = []
    planned: list[dict] = []
    total_bytes = 0
    for job in selected:
        run_at = f"{job['issue_local_date']}T{args.cycle:02d}:00:00Z"
        request = GfsRequest(
            run_key=str(uuid4()),
            request_purpose="historical_forecast",
            valid_at_utc=tuple(job["valid_times_utc"]),
            explicit_run_at_utc=run_at,
            maximum_total_bytes=args.maximum_total_mib * 2**20,
            target_local_date=job["target_local_date"],
            flying_window_version=SOFIA_FLYING_WINDOW_VERSION,
            site_config_sha256=preflight.site_config_sha256,
            sampling_policy_sha256=preflight.sampling_policy_sha256,
            compact_selection_version=preflight.compact_selection_version,
        )
        plan = planner.plan(request, created_at_utc=_now())
        resolved = plan.adapter_request
        if resolved["available_at_utc"] > job["issue_cutoff_utc"]:
            raise BackfillError(
                "Technical cycle metadata is later than the cohort 20:00 source cutoff."
            )
        count = sum(item["byte_end"] - item["byte_start"] + 1 for item in resolved["ranges"])
        total_bytes += count
        filename = f"{job['target_local_date']}-D{job['horizon_days']}-request-plan.json"
        content = _json_bytes(plan.model_dump(mode="json"))
        outputs.append((filename, content))
        planned.append(
            {
                "target_local_date": job["target_local_date"],
                "issue_local_date": job["issue_local_date"],
                "horizon_days": job["horizon_days"],
                "site_ids": job["site_ids"],
                "issue_cutoff_utc": job["issue_cutoff_utc"],
                "selected_cycle_utc": run_at,
                "available_at_utc": resolved["available_at_utc"],
                "selected_bytes": count,
                "run_key": request.run_key,
                "plan_file": filename,
                "plan_sha256": _sha(content),
            }
        )
        print(
            f"Probed {job['target_local_date']} D+{job['horizon_days']} "
            f"{run_at}: {count} selected bytes, metadata {resolved['available_at_utc']}",
            file=sys.stderr,
            flush=True,
        )
    if total_bytes > args.maximum_sample_gib * 2**30:
        raise BackfillError("Selected ranges exceed --maximum-sample-gib; nothing was published.")
    body = {
        "schema_version": "weather-technical-sample/1",
        "cohort_plan_id": args.cohort_plan_id,
        "cycle_hour_utc": args.cycle,
        "target_dates": sorted(selected_dates),
        "total_selected_bytes": total_bytes,
        "site_config_sha256": preflight.site_config_sha256,
        "sampling_policy_sha256": preflight.sampling_policy_sha256,
        "compact_selection_version": preflight.compact_selection_version,
        "usage_policy_sha256": usage_policy_sha256,
        "jobs": planned,
        "purpose": "technical_timing_only_not_training_as_of_policy",
    }
    sample_id = _sha(canonical_json_bytes(body))
    parent = root / "data/processed/weather-samples"
    destination = parent / sample_id
    if destination.exists():
        _sample(root, sample_id)
    else:
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".weather-sample-", dir=parent) as temporary:
            staging = Path(temporary) / "sample"
            staging.mkdir()
            for filename, content in outputs:
                (staging / filename).write_bytes(content)
            (staging / "manifest.json").write_bytes(_json_bytes({**body, "sample_id": sample_id}))
            staging.rename(destination)
    return {
        "sample_id": sample_id,
        "output_directory": str(destination),
        "job_count": len(planned),
        "total_selected_bytes": total_bytes,
        "jobs": planned,
    }


def _job_status(root: Path, job: dict) -> dict:
    raw = root / "data/raw/weather" / job["run_key"]
    interim = root / "data/interim/weather" / job["run_key"]
    if not raw.exists() and not interim.exists():
        return {"state": "pending", "checkpoint_files": 0}
    store = WeatherArtifactStore(job["run_key"], project_root=root)
    snapshot = RunStateLedger(store).load_state()
    checkpoints = len(list((raw / "checkpoints").glob("*.json")))
    persisted = snapshot.effective_event("persisted")
    if persisted and persisted.disposition == "persisted":
        state = "persisted"
    elif snapshot.effective_event("raw_complete"):
        state = "raw_complete_or_offline_pending"
    else:
        state = "raw_partial_or_not_started"
    return {
        "state": state,
        "checkpoint_files": checkpoints,
        "last_stage": snapshot.events[-1].stage if snapshot.events else None,
    }


def _require_persisted_row(database_url: str, root: Path, run_key: str) -> None:
    connection = open_read_only_database(database_url, root)
    try:
        row = connection.execute(
            "SELECT status FROM weather_ingestion_runs WHERE run_key = ?", (run_key,)
        ).fetchone()
    finally:
        connection.close()
    if row is None or row[0] != "succeeded":
        raise BackfillError("Persisted sample ledger lacks a successful SQLite run row.")


def status(args: argparse.Namespace) -> dict:
    root = args.project_root.resolve()
    directory, sample = _workload(root, args)
    lock = directory / "run.lock"
    return {
        "batch_id" if getattr(args, "batch_id", None) is not None else "sample_id": (
            args.batch_id if getattr(args, "batch_id", None) is not None else args.sample_id
        ),
        "writer_lock": json.loads(lock.read_bytes()) if lock.exists() else None,
        "jobs": [
            {
                **{key: job[key] for key in ("target_local_date", "horizon_days", "run_key")},
                **_job_status(root, job),
            }
            for job in sample["jobs"]
        ],
    }


def recover_lock(args: argparse.Namespace) -> dict:
    if not args.confirm_writer_stopped:
        raise BackfillError("Pass --confirm-writer-stopped only after checking the writer exited.")
    root = args.project_root.resolve()
    directory, _ = _workload(root, args)
    lock = directory / "run.lock"
    if not lock.exists():
        raise BackfillError("No writer lock exists.")
    metadata = json.loads(lock.read_bytes())
    started = datetime.strptime(metadata["started_at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=UTC
    )
    if datetime.now(UTC) - started < timedelta(minutes=5):
        raise BackfillError("Writer lock is younger than five minutes; refusing recovery.")
    # Validate all run ledgers before permitting a new writer. Preserve the old
    # lock as a receipt rather than deleting the evidence of an interrupted run.
    status(args)
    receipt = directory / f"run-lock-recovered-{uuid4().hex}.json"
    lock.rename(receipt)
    return {"recovered_lock": str(receipt)}


def run(args: argparse.Namespace) -> dict:
    if not args.allow_live_network:
        raise BackfillError("Pass --allow-live-network for source checks and missing ranges.")
    root = args.project_root.resolve()
    directory, sample = _workload(root, args)
    preflight = _preflight(args.policy_file, args.database_url, root)
    _usage_policy, usage_policy_sha256 = load_weather_usage_policy(
        args.policy_file, source_family="gfs", project_root=root
    )
    if usage_policy_sha256 != sample["usage_policy_sha256"]:
        raise BackfillError("Current GFS usage policy differs from the frozen sample.")
    for field in ("site_config_sha256", "sampling_policy_sha256", "compact_selection_version"):
        if getattr(preflight, field) != sample[field]:
            raise BackfillError(f"Current {field} differs from the frozen sample.")
    lock = directory / "run.lock"
    try:
        with lock.open("xb") as handle:
            handle.write(_json_bytes({"pid": os.getpid(), "started_at_utc": _now()}))
    except FileExistsError as error:
        raise BackfillError("Sample writer lock exists; inspect it before recovery.") from error
    results = []
    try:
        for job in sample["jobs"]:
            if len(results) >= args.max_jobs:
                break
            state = _job_status(root, job)
            if state["state"] == "persisted":
                eviction = (
                    root
                    / "data/processed/weather-archives"
                    / job["run_key"]
                    / "eviction-receipt.json"
                )
                if eviction.exists():
                    audit_compact(
                        job["run_key"], project_root=root, database_url=preflight.database_url
                    )
                else:
                    audit_weather_artifacts(job["run_key"], scope="effective", project_root=root)
                _require_persisted_row(preflight.database_url, root, job["run_key"])
                continue
            if state["state"] != "raw_complete_or_offline_pending":
                free = shutil.disk_usage(root).free
                reserve = sample.get("minimum_free_gib", args.minimum_free_gib)
                scratch = 2 if getattr(args, "batch_id", None) is not None else 0
                if free < job["selected_bytes"] + (reserve + scratch) * 2**30:
                    raise BackfillError("Free space is below planned job bytes plus reserve.")
            plan = RequestPlan.model_validate_json(
                (directory / job["plan_file"]).read_bytes(), strict=True
            )
            started_at = _now()
            print(
                f"Starting {job['target_local_date']} D+{job['horizon_days']} "
                f"{job['selected_cycle_utc']} run_key={job['run_key']}",
                file=sys.stderr,
                flush=True,
            )
            raw = root / "data/raw/weather" / job["run_key"]
            if raw.exists():
                store = WeatherArtifactStore(job["run_key"], project_root=root)
            else:
                store = WeatherArtifactStore.create_fresh(job["run_key"], project_root=root)
                RunStateLedger(store).initialize(occurred_at_utc=_now())
            ledger = RunStateLedger(store)
            snapshot = ledger.load_state()
            if not snapshot.events:
                if (store.raw_dir / "request-plan.json").exists() or any(
                    (store.raw_dir / "payloads").glob("*")
                ):
                    raise BackfillError("Weather run has payloads but no state ledger.")
                ledger.initialize(occurred_at_utc=_now())
                snapshot = ledger.load_state()
            if snapshot.effective_event("raw_complete") is None:
                manifest_path = store.raw_dir / "manifest.json"
                if manifest_path.exists():
                    raw_reference = GfsCollector._existing_reference(
                        store, manifest_path, "raw_manifest", "application/json"
                    )
                    store.verify_raw_manifest(raw_reference)
                else:
                    transport = RetryingTransport(UrllibTransport())
                    raw_reference = GfsCollector(transport).fetch_resumable(
                        plan,
                        store,
                        progress=lambda done, total, run_key=job["run_key"]: print(
                            f"{run_key}: ranges {done}/{total}",
                            file=sys.stderr,
                            flush=True,
                        ),
                    )
                ledger.append(
                    invocation_mode="resume",
                    stage="raw_complete",
                    disposition="complete",
                    occurred_at_utc=_now(),
                    evidence=raw_reference,
                    detail="bounded resumable technical GFS sample",
                )
            raw_completed_at = _now()
            print(
                f"Raw complete {job['run_key']}; finishing offline stages",
                file=sys.stderr,
                flush=True,
            )
            result = resume_run(
                job["run_key"],
                args.policy_file,
                database_url=args.database_url,
                project_root=root,
            )
            results.append(
                {
                    "target_local_date": job["target_local_date"],
                    "horizon_days": job["horizon_days"],
                    "run_key": job["run_key"],
                    "status": result["status"],
                    "started_at_utc": started_at,
                    "raw_complete_at_utc": raw_completed_at,
                    "finished_at_utc": _now(),
                    "result": result,
                }
            )
            if result["status"] not in {
                "inserted",
                "revalidated_no_op",
                "recovered_committed_write",
            }:
                break
    finally:
        lock.unlink(missing_ok=True)
    return {
        "batch_id" if getattr(args, "batch_id", None) is not None else "sample_id": (
            args.batch_id if getattr(args, "batch_id", None) is not None else args.sample_id
        ),
        "executed_jobs": results,
        "remaining": status(args)["jobs"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="weather-backfill", description="Bounded T-020 technical GFS sample only."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    probe_cmd = sub.add_parser("probe", help="Resolve source metadata without GRIB payloads.")
    probe_cmd.add_argument("--cohort-plan-id", required=True)
    probe_cmd.add_argument("--target-date", action="append", metavar="YYYY-MM-DD")
    probe_cmd.add_argument("--cycle", type=int, choices=(6, 12), required=True)
    probe_cmd.add_argument("--max-jobs", type=int, default=15)
    probe_cmd.add_argument("--maximum-total-mib", type=int, default=2048)
    probe_cmd.add_argument("--maximum-sample-gib", type=int, default=25)
    probe_cmd.add_argument("--allow-metadata-network", action="store_true")
    for name in ("run", "resume-live"):
        command = sub.add_parser(name, help="Fetch missing ranges and finish jobs through SQLite.")
        command.add_argument("--sample-id", required=True)
        command.add_argument("--max-jobs", type=int, default=1)
        command.add_argument("--minimum-free-gib", type=int, default=20)
        command.add_argument("--allow-live-network", action="store_true")
    status_cmd = sub.add_parser("status", help="Inspect sample and job checkpoints offline.")
    status_cmd.add_argument("--sample-id", required=True)
    recover_cmd = sub.add_parser("recover-lock", help="Release a stale writer lock offline.")
    recover_cmd.add_argument("--sample-id", required=True)
    recover_cmd.add_argument("--confirm-writer-stopped", action="store_true")
    resolve_cmd = sub.add_parser(
        "resolve", help="Checkpoint exact 06Z metadata for a cohort split."
    )
    resolve_cmd.add_argument("--cohort-plan-id", required=True)
    resolve_cmd.add_argument("--split", choices=("development", "backtest", "all"), required=True)
    resolve_cmd.add_argument("--max-new-jobs", type=int, default=75)
    resolve_cmd.add_argument("--maximum-total-mib", type=int, default=2048)
    resolve_cmd.add_argument("--allow-metadata-network", action="store_true")
    resolution_status_cmd = sub.add_parser(
        "resolution-status", help="Inspect 06Z metadata checkpoints offline."
    )
    resolution_status_cmd.add_argument("--acquisition-id", required=True)
    batch_create_cmd = sub.add_parser(
        "batch-create", help="Freeze the next capacity-bounded 06Z batch offline."
    )
    batch_create_cmd.add_argument("--acquisition-id", required=True)
    batch_create_cmd.add_argument("--max-target-dates", type=int, default=25)
    batch_create_cmd.add_argument("--max-new-gib", type=int, default=100)
    batch_create_cmd.add_argument("--minimum-free-gib", type=int, default=80)
    batch_create_cmd.add_argument("--database-url")
    for name in ("batch-run", "batch-resume-live"):
        command = sub.add_parser(name, help="Finish a 06Z batch through SQLite.")
        command.add_argument("--batch-id", required=True)
        command.add_argument("--max-jobs", type=int, default=1)
        command.add_argument("--minimum-free-gib", type=int, default=80)
        command.add_argument("--allow-live-network", action="store_true")
    batch_status_cmd = sub.add_parser(
        "batch-status", help="Inspect a batch's job checkpoints offline."
    )
    batch_status_cmd.add_argument("--batch-id", required=True)
    batch_recover_cmd = sub.add_parser(
        "batch-recover-lock", help="Release a stale batch writer lock offline."
    )
    batch_recover_cmd.add_argument("--batch-id", required=True)
    batch_recover_cmd.add_argument("--confirm-writer-stopped", action="store_true")
    for command in (
        probe_cmd,
        status_cmd,
        recover_cmd,
        sub.choices["run"],
        sub.choices["resume-live"],
        resolve_cmd,
        resolution_status_cmd,
        batch_create_cmd,
        sub.choices["batch-run"],
        sub.choices["batch-resume-live"],
        batch_status_cmd,
        batch_recover_cmd,
    ):
        command.add_argument("--project-root", type=Path, default=repository_root())
        if command not in (
            status_cmd,
            recover_cmd,
            resolution_status_cmd,
            batch_create_cmd,
            batch_status_cmd,
            batch_recover_cmd,
        ):
            command.add_argument("--policy-file", type=Path)
            command.add_argument("--database-url")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    if (
        args.command in {"probe", "run", "resume-live", "batch-run", "batch-resume-live"}
        and args.max_jobs < 1
    ):
        print("--max-jobs must be positive.", file=sys.stderr)
        return 2
    if args.command == "probe" and (args.maximum_total_mib < 1 or args.maximum_sample_gib < 1):
        print("Byte caps must be positive.", file=sys.stderr)
        return 2
    if (
        args.command in {"run", "resume-live", "batch-run", "batch-resume-live", "batch-create"}
        and args.minimum_free_gib < 0
    ):
        print("--minimum-free-gib cannot be negative.", file=sys.stderr)
        return 2
    if args.command == "resolve" and (args.max_new_jobs < 1 or args.maximum_total_mib < 1):
        print("Metadata job and byte caps must be positive.", file=sys.stderr)
        return 2
    if args.command == "batch-create" and (args.max_target_dates < 1 or args.max_new_gib < 3):
        print("Batch date cap must be positive and byte cap at least 3 GiB.", file=sys.stderr)
        return 2
    try:
        from . import weather_full_backfill as full

        result = (
            probe(args)
            if args.command == "probe"
            else status(args)
            if args.command == "status"
            else recover_lock(args)
            if args.command == "recover-lock"
            else full.resolve(args)
            if args.command == "resolve"
            else full.resolution_status(args)
            if args.command == "resolution-status"
            else full.batch_create(args)
            if args.command == "batch-create"
            else status(args)
            if args.command == "batch-status"
            else recover_lock(args)
            if args.command == "batch-recover-lock"
            else run(args)
        )
    except (
        ArtifactError,
        BackfillError,
        DatabaseConfigurationError,
        FileNotFoundError,
        GfsCollectionError,
        GfsPlanningError,
        GfsTransportError,
        KeyError,
        OSError,
        sqlite3.Error,
        StateError,
        TypeError,
        ValueError,
        WeatherPipelineError,
    ) as error:
        print(f"Weather backfill did not complete: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.command in {"run", "resume-live", "batch-run", "batch-resume-live"} and any(
        job["status"] not in {"inserted", "revalidated_no_op", "recovered_committed_write"}
        for job in result["executed_jobs"]
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
