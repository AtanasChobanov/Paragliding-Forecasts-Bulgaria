"""Owner-run entry point for dated GFS prediction publication."""

import argparse
import json
import shutil
import sys
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, date, datetime
from multiprocessing import get_context
from pathlib import Path
from sqlite3 import Error as SqliteError

from ...ingestion.atmosphere.contracts import SHA256_PATTERN, UUID_V4_PATTERN
from ...ingestion.gfs.models import GFS_SOURCE_ID
from ...ingestion.gfs.transport import RetryingTransport, UrllibTransport
from ...ingestion.weather.persistence_models import load_weather_usage_policy
from ...ingestion.weather.pipeline import _preflight
from ...ingestion.weather.sites import load_site_sampling_configs
from ...storage.file_lock import file_lock
from ...storage.sqlite import open_read_only_database, repository_root, resolve_database_path
from ..xc_probability.model_io import load_model
from .checkpoints import Checkpoints
from .orchestration import ForecastSchedule
from .store import require_schema
from .weather import SITE_COUNT, utc_text
from .weather_jobs import WeatherJobs


def _clock() -> datetime:
    return datetime.now(UTC)


def _progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _positive(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Expected a positive integer.") from error
    if number <= 0:
        raise argparse.ArgumentTypeError("Expected a positive integer.")
    return number


def _issue_date(value: str) -> date:
    try:
        result = date.fromisoformat(value)
        if result.isoformat() == value:
            return result
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("Expected a date in YYYY-MM-DD form.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forecast-publish",
        description="Publish verified GFS 06Z XC, cloudbase and OD results.",
    )
    parser.add_argument("--model-id", required=True, help="Local frozen XC model bundle ID.")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--issue-date", type=_issue_date, help="Check this 06Z cycle once.")
    scope.add_argument(
        "--run-key", action="append", help="Use an exact retained GFS UUID; repeatable."
    )
    parser.add_argument("--database-url", help="Existing repository-relative SQLite file: URL.")
    parser.add_argument("--project-root", type=Path, default=repository_root())
    parser.add_argument("--policy-file", type=Path, help="Reviewed local GFS usage policy file.")
    parser.add_argument(
        "--maximum-total-mib",
        type=_positive,
        default=2048,
        help="Maximum selected NOAA GRIB range bytes per horizon in MiB (default: 2048).",
    )
    parser.add_argument(
        "--max-workers",
        type=_positive,
        default=5,
        help="Shared maximum number of active weather, predictor and write jobs (default: 5).",
    )
    parser.add_argument(
        "--allow-live-network", action="store_true", help="Allow requests to NOAA Open Data on AWS."
    )
    return parser


def _run(args, started: datetime) -> tuple[int, dict]:
    root = args.project_root.resolve()
    preflight = _preflight(args.policy_file, args.database_url, root)
    database = resolve_database_path(preflight.database_url, root)
    with file_lock(database.with_name(f"{database.name}.forecast-publish.lock")):
        with closing(open_read_only_database(preflight.database_url, root)) as connection:
            require_schema(connection)
            if (
                connection.execute(
                    "SELECT 1 FROM weather_sources WHERE code = ? AND source_kind = 'forecast' AND is_active = 1",
                    (GFS_SOURCE_ID,),
                ).fetchone()
                is None
            ):
                raise ValueError("Forecast publication requires the approved active GFS source.")
        policy, _ = load_weather_usage_policy(
            args.policy_file, source_family="gfs", project_root=root
        )
        if not policy.operational_use_allowed:
            raise ValueError("The GFS usage policy must permit operational use.")
        sites = load_site_sampling_configs(preflight.database_url, root, require_elevation=True)
        model = load_model(model_id=args.model_id, project_root=root)
        if len(sites) != SITE_COUNT or dict(model.site_categories) != {
            site.site_id: site.site_slug for site in sites
        }:
            raise ValueError("The frozen XC model must match the seven configured sites.")
        network = UrllibTransport() if args.allow_live_network and not args.run_key else None
        weather = WeatherJobs(
            root,
            preflight,
            args.policy_file,
            Checkpoints.for_database(root, database),
            args.model_id,
            args.maximum_total_mib * 2**20,
            network,
            RetryingTransport(network) if network else None,
            _clock,
            _progress,
        )
        schedule = ForecastSchedule(
            weather,
            started=started,
            clock=_clock,
            max_workers=args.max_workers,
            free_bytes=lambda: shutil.disk_usage(root / "data").free,
            progress=_progress,
        )
        with (
            ThreadPoolExecutor(max_workers=args.max_workers) as threads,
            ProcessPoolExecutor(
                max_workers=min(args.max_workers, 61), mp_context=get_context("spawn")
            ) as processes,
            ThreadPoolExecutor(max_workers=1) as writer,
        ):
            return schedule.run(
                threads,
                processes,
                writer,
                issue_date=args.issue_date,
                run_keys=tuple(args.run_key or ()),
            )


def main(arguments: Sequence[str] | None = None) -> int:
    started = _clock()
    parser = build_parser()
    args = parser.parse_args(arguments)
    if SHA256_PATTERN.fullmatch(args.model_id) is None:
        parser.error("--model-id requires a lowercase SHA-256 model ID")
    if args.run_key and (
        len(args.run_key) != len(set(args.run_key))
        or any(UUID_V4_PATTERN.fullmatch(key) is None for key in args.run_key)
    ):
        parser.error("--run-key requires distinct lowercase UUID v4 values")
    try:
        status, report = _run(args, started)
    except (RuntimeError, OSError, SqliteError, ValueError) as error:
        status = 1
        finished = _clock()
        report = {
            "status": "failed",
            "reason": type(error).__name__,
            "detail": str(error),
            "model_id": args.model_id,
            "started_at_utc": utc_text(started),
            "finished_at_utc": utc_text(finished),
            "elapsed_seconds": (finished - started).total_seconds(),
            "jobs": [],
        }
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
