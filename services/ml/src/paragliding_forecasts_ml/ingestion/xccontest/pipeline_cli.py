"""Command-line boundary for durable XCContest ingestion orchestration."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from ...storage.sqlite import (
    DatabaseConfigurationError,
    configured_database_url,
    load_site_country_codes,
)
from .models import CollectorConfig
from .pipeline import PipelineError, fresh_run, resume_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xccontest-ingest",
        description="Collect or resume XCContest ingestion through durable stage artifacts.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    fresh = commands.add_parser(
        "fresh", help="Collect a new raw run and continue through review/persistence."
    )
    fresh.add_argument("--season", type=int, action="append", required=True, metavar="YEAR")
    fresh.add_argument("--policy-file", required=True, type=Path, metavar="PATH")
    fresh.add_argument("--database-url", metavar="FILE_URL")
    fresh.add_argument("--headed", action="store_true")
    fresh.add_argument("--slow-mo-ms", type=int, default=0, metavar="MILLISECONDS")
    fresh.add_argument("--source-delay-seconds", type=float, default=30, metavar="SECONDS")
    fresh.add_argument("--acknowledge-rate-limit-risk", action="store_true")
    fresh.add_argument("--timeout-seconds", type=int, default=30, metavar="SECONDS")
    fresh.add_argument("--max-views", type=int, default=2_000, metavar="COUNT")
    fresh.add_argument(
        "--persist-approved-only",
        action="store_true",
        help="Bypass the mapping-review pause and persist approved records despite actionable quarantines.",
    )
    resume = commands.add_parser(
        "resume", help="Continue offline from a raw or parser artifact run without source access."
    )
    resume.add_argument("--run-key", required=True, metavar="UUID")
    resume.add_argument("--policy-file", required=True, type=Path, metavar="PATH")
    resume.add_argument("--database-url", metavar="FILE_URL")
    resume.add_argument("--persist-approved-only", action="store_true")
    return parser


def _fresh_config(args: argparse.Namespace) -> tuple[CollectorConfig, str]:
    database_url = configured_database_url(args.database_url)
    try:
        countries = load_site_country_codes(database_url)
        config = CollectorConfig(
            seasons=tuple(args.season),
            country_codes=countries,
            headed=args.headed,
            slow_mo_ms=args.slow_mo_ms,
            timeout_seconds=args.timeout_seconds,
            max_views=args.max_views,
            delay_seconds=args.source_delay_seconds,
            acknowledge_rate_limit_risk=args.acknowledge_rate_limit_risk,
        )
    except (DatabaseConfigurationError, ValueError) as error:
        raise PipelineError(
            f"XCContest fresh pipeline could not resolve collection scope: {error}"
        ) from error
    return config, database_url


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        if args.command == "fresh":
            config, database_url = _fresh_config(args)
            result = fresh_run(
                config,
                args.policy_file,
                database_url=database_url,
                persist_approved_only=args.persist_approved_only,
            )
        else:
            result = resume_run(
                args.run_key,
                args.policy_file,
                database_url=args.database_url,
                persist_approved_only=args.persist_approved_only,
            )
    except PipelineError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["status"] == "succeeded" else 2


if __name__ == "__main__":
    raise SystemExit(main())
