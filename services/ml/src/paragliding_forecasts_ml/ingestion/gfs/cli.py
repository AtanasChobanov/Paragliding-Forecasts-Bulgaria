"""Explicit opt-in command for bounded GFS raw collection."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..atmosphere.contracts import RequestPlan
from ..weather.artifacts import WeatherArtifactStore
from ..weather.state import RunStateLedger, StateError
from .collector import GfsCollector
from .models import (
    SOFIA_FLYING_WINDOW_VERSION,
    GfsRequest,
    sofia_window_instants,
)
from .planner import GfsPlanner, GfsPlanningError
from .transport import RetryingTransport, UrllibTransport


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gfs-collect")
    time_scope = parser.add_mutually_exclusive_group(required=True)
    time_scope.add_argument(
        "--valid-at",
        action="append",
        metavar="UTC",
        help="One low-level UTC valid timestamp (repeatable; mutually exclusive with --local-date).",
    )
    time_scope.add_argument(
        "--local-date",
        metavar="YYYY-MM-DD",
        help="One Europe/Sofia date; derives the fixed 10:00--20:00 Sofia flying window.",
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--explicit-run-at", metavar="UTC", help="Exact GFS cycle timestamp (Z suffix)."
    )
    selection.add_argument(
        "--newest-complete-before", metavar="UTC", help="Newest complete cycle cutoff (Z suffix)."
    )
    parser.add_argument(
        "--purpose", choices=("historical_forecast", "operational_forecast"), required=True
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--maximum-total-mib", type=int, default=128)
    parser.add_argument(
        "--allow-live-network",
        action="store_true",
        help="Required acknowledgement before any NOAA request.",
    )
    return parser


def collect_gfs_run(
    request: GfsRequest,
    *,
    project_root: Path,
    duplicate_run_key: Callable[[RequestPlan], str | None] | None = None,
    occurred_at_utc: str | None = None,
) -> dict[str, Any]:
    """Plan and collect once; optional duplicate gate runs after inventory, before payload GETs."""

    transport = RetryingTransport(UrllibTransport())
    started_at_utc = occurred_at_utc or _utc_now()
    plan = GfsPlanner(transport).plan(request, created_at_utc=started_at_utc)
    existing_run_key = duplicate_run_key(plan) if duplicate_run_key is not None else None
    if existing_run_key is not None:
        return {
            "run_key": existing_run_key,
            "status": "already_succeeded",
            "manifest": None,
            "sha256": None,
        }
    store = WeatherArtifactStore.create_fresh(request.run_key, project_root=project_root)
    ledger = RunStateLedger(store)
    ledger.initialize(occurred_at_utc=started_at_utc)
    manifest_reference = GfsCollector(transport).fetch(plan, store)
    manifest = store.verify_raw_manifest(manifest_reference)
    ledger.append(
        invocation_mode="resume",
        stage="raw_complete",
        disposition="complete" if manifest.status == "complete" else manifest.status,
        occurred_at_utc=_utc_now(),
        evidence=manifest_reference,
        detail="bounded NOAA GFS collection",
    )
    return {
        "run_key": request.run_key,
        "status": manifest.status,
        "manifest": manifest_reference.relative_path,
        "sha256": manifest_reference.sha256,
    }


def main(arguments: Sequence[str] | None = None) -> int:
    namespace = build_parser().parse_args(arguments)
    if not namespace.allow_live_network:
        print(
            "Refusing network access: pass --allow-live-network after reviewing the requested scope.",
            file=sys.stderr,
        )
        return 2
    try:
        request = GfsRequest(
            run_key=str(uuid4()),
            request_purpose=namespace.purpose,
            valid_at_utc=(
                sofia_window_instants(namespace.local_date)
                if namespace.local_date is not None
                else tuple(namespace.valid_at)
            ),
            explicit_run_at_utc=namespace.explicit_run_at,
            newest_complete_before_utc=namespace.newest_complete_before,
            maximum_total_bytes=namespace.maximum_total_mib * 1024 * 1024,
            target_local_date=namespace.local_date,
            flying_window_version=(
                SOFIA_FLYING_WINDOW_VERSION if namespace.local_date is not None else None
            ),
        )
        result = collect_gfs_run(request, project_root=namespace.project_root)
    except (GfsPlanningError, StateError, ValueError, OSError) as error:
        print(f"GFS collection failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                **result,
            },
            indent=2,
        )
    )
    return 0 if result["status"] in {"complete", "already_succeeded"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
