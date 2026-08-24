"""Explicit opt-in command for bounded GFS raw collection."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ..weather.artifacts import WeatherArtifactStore
from ..weather.state import RunStateLedger, StateError
from .collector import GfsCollector
from .models import GfsRequest
from .planner import GfsPlanner, GfsPlanningError
from .transport import RetryingTransport, UrllibTransport


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gfs-collect")
    parser.add_argument(
        "--valid-at",
        action="append",
        required=True,
        metavar="UTC",
        help="Required valid timestamp (repeatable, Z suffix).",
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
            valid_at_utc=tuple(namespace.valid_at),
            explicit_run_at_utc=namespace.explicit_run_at,
            newest_complete_before_utc=namespace.newest_complete_before,
            maximum_total_bytes=namespace.maximum_total_mib * 1024 * 1024,
        )
        transport = RetryingTransport(UrllibTransport())
        occurred_at_utc = _utc_now()
        plan = GfsPlanner(transport).plan(request, created_at_utc=occurred_at_utc)
        store = WeatherArtifactStore.create_fresh(
            request.run_key, project_root=namespace.project_root
        )
        ledger = RunStateLedger(store)
        ledger.initialize(occurred_at_utc=occurred_at_utc)
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
    except (GfsPlanningError, StateError, ValueError, OSError) as error:
        print(f"GFS collection failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "run_key": request.run_key,
                "status": manifest.status,
                "manifest": manifest_reference.relative_path,
                "sha256": manifest_reference.sha256,
            },
            indent=2,
        )
    )
    return 0 if manifest.status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
