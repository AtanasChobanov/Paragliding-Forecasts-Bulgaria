"""Command-line boundary for authorized XCContest collection."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence

from playwright.sync_api import Error as PlaywrightError

from ...storage.sqlite import (
    DatabaseConfigurationError,
    configured_database_url,
    load_site_country_codes,
)
from .artifacts import RawArtifactStore, safe_failure_summary
from .browser import BrowserCollectionError, PlaywrightFlightListDriver
from .collector import CollectionError, FlightListCollector
from .models import CollectorConfig


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit, collector-only command interface."""

    parser = argparse.ArgumentParser(
        prog="xccontest-collect",
        description=(
            "Collect rendered XCContest country-scoped PG flight-list views through the source UI. "
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
        "--database-url",
        metavar="FILE_URL",
        help=(
            "Optional local SQLite file URL. Defaults to DATABASE_URL or "
            "file:./data/local/paragliding.db."
        ),
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
        help="Optional Playwright action slowdown for local debugging; not source rate limiting (default: 0).",
    )
    parser.add_argument(
        "--source-delay-seconds",
        type=float,
        default=30,
        metavar="SECONDS",
        help="Minimum delay before each source-changing browser operation (default: 30).",
    )
    parser.add_argument(
        "--acknowledge-rate-limit-risk",
        action="store_true",
        help="Required only when --source-delay-seconds is below the recommended 30 seconds.",
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


def _collector_config(
    namespace: argparse.Namespace, country_codes: tuple[str, ...]
) -> CollectorConfig:
    """Build a validated collector scope after database discovery succeeds."""

    return CollectorConfig(
        seasons=tuple(namespace.season),
        country_codes=country_codes,
        headed=namespace.headed,
        slow_mo_ms=namespace.slow_mo_ms,
        timeout_seconds=namespace.timeout_seconds,
        max_views=namespace.max_views,
        delay_seconds=namespace.source_delay_seconds,
        acknowledge_rate_limit_risk=namespace.acknowledge_rate_limit_risk,
    )


def main(arguments: Sequence[str] | None = None) -> int:
    """Run a collection and report artifact locations without exposing source data."""

    parser = build_parser()
    namespace = parser.parse_args(arguments)
    database_url = configured_database_url(namespace.database_url)
    try:
        country_codes = load_site_country_codes(database_url)
        config = _collector_config(namespace, country_codes)
    except (DatabaseConfigurationError, ValueError) as error:
        print(
            f"XCContest collection could not resolve its database country scope: {error}",
            file=sys.stderr,
        )
        return 1

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

    print(
        json.dumps(
            {
                "run_key": report.run_key,
                "status": report.status,
                "manifest_relative_path": report.manifest_relative_path,
                "manifest_sha256": report.manifest_sha256,
                "started_at_utc": report.started_at_utc.isoformat().replace("+00:00", "Z"),
                "completed_at_utc": report.completed_at_utc.isoformat().replace("+00:00", "Z"),
                "country_codes": list(report.country_codes),
                "completed_seasons": list(report.completed_seasons),
                "completed_target_count": report.completed_target_count,
                "unresolved_scope_count": report.unresolved_scope_count,
                "artifact_count": report.artifact_count,
                "row_observations_seen": report.row_observations_seen,
                "distinct_source_flights_seen": report.distinct_source_flights_seen,
                "repeated_source_flight_observations": (report.repeated_source_flight_observations),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
