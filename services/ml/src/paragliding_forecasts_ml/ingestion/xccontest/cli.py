"""Command-line boundary for authorized XCContest collection."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence

from playwright.sync_api import Error as PlaywrightError

from .artifacts import RawArtifactStore, safe_failure_summary
from .browser import BrowserCollectionError, PlaywrightFlightListDriver
from .collector import CollectionError, FlightListCollector
from .models import CollectorConfig


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit, collector-only command interface."""

    parser = argparse.ArgumentParser(
        prog="xccontest-collect",
        description=(
            "Collect rendered XCContest Bulgarian PG flight-list views through the source UI. "
            "This command writes raw artifacts only; it does not parse or import flights."
        ),
    )
    parser.add_argument(
        "--season",
        type=int,
        action="append",
        required=True,
        metavar="YEAR",
        help="XCContest season to collect; repeat the option for multiple seasons.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show Chromium for local inspection instead of running headlessly.",
    )
    parser.add_argument(
        "--slow-mo-ms",
        type=int,
        default=0,
        metavar="MILLISECONDS",
        help="Optional Playwright action slowdown for local debugging (default: 0).",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        metavar="SECONDS",
        help="Per browser-operation timeout (default: 30).",
    )
    parser.add_argument(
        "--max-views",
        type=int,
        default=2_000,
        metavar="COUNT",
        help=("Fail-closed cap for rendered category/date/sort views per run (default: 2000)."),
    )
    return parser


def parse_config(arguments: Sequence[str] | None = None) -> CollectorConfig:
    """Parse arguments and make invalid collection scope fail before browser startup."""

    parser = build_parser()
    namespace = parser.parse_args(arguments)
    try:
        return CollectorConfig(
            seasons=tuple(namespace.season),
            headed=namespace.headed,
            slow_mo_ms=namespace.slow_mo_ms,
            timeout_seconds=namespace.timeout_seconds,
            max_views=namespace.max_views,
        )
    except ValueError as error:
        parser.error(str(error))


def main(arguments: Sequence[str] | None = None) -> int:
    """Run a collection and report artifact locations without exposing source data."""

    config = parse_config(arguments)
    artifacts = RawArtifactStore()
    try:
        with PlaywrightFlightListDriver(config, sleeper=time.sleep) as driver:
            report = FlightListCollector(
                config=config,
                driver=driver,
                artifacts=artifacts,
            ).collect()
    except (BrowserCollectionError, CollectionError, PlaywrightError) as error:
        artifacts.write_failure_report(error=safe_failure_summary(error))
        print(
            "XCContest collection did not complete. Review the local failure report; "
            "use --headed for a manual browser check.",
            file=sys.stderr,
        )
        return 1

    unresolved_scopes = sum(len(status.unresolved_scopes) for status in report.season_statuses)
    run_status = "incomplete" if unresolved_scopes else "complete"
    print(
        json.dumps(
            {
                "run_key": report.run_key,
                "status": run_status,
                "artifact_root": str(report.artifact_root),
                "manifest_path": str(report.manifest_path),
                "completed_seasons": list(report.completed_seasons),
                "unresolved_scope_count": unresolved_scopes,
                "artifact_count": len(report.artifacts),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
