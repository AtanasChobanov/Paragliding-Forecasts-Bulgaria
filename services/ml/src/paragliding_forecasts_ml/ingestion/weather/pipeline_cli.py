"""CLI boundary for GFS weather fresh and strictly offline resume orchestration."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .pipeline import WeatherPipelineError, fresh_run, resume_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="weather-ingest",
        description="Collect one bounded GFS run or resume its weather stages entirely offline.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    fresh = commands.add_parser("fresh", help="Collect one explicit GFS scope, then persist it.")
    fresh.add_argument("--local-date", required=True, metavar="YYYY-MM-DD")
    fresh.add_argument(
        "--purpose", required=True, choices=("historical_forecast", "operational_forecast")
    )
    selection = fresh.add_mutually_exclusive_group(required=True)
    selection.add_argument("--explicit-run-at", metavar="UTC")
    selection.add_argument("--newest-complete-before", metavar="UTC")
    fresh.add_argument("--maximum-total-mib", required=True, type=int, metavar="MIB")
    fresh.add_argument("--allow-live-network", action="store_true")
    fresh.add_argument("--policy-file", type=Path, metavar="PATH")
    fresh.add_argument("--database-url", metavar="DATABASE_URL")
    fresh.add_argument("--project-root", type=Path, default=Path.cwd())

    resume = commands.add_parser(
        "resume", help="Resume from retained evidence without network access."
    )
    resume.add_argument("--run-key", required=True, metavar="UUID")
    resume.add_argument("--policy-file", type=Path, metavar="PATH")
    resume.add_argument("--database-url", metavar="DATABASE_URL")
    resume.add_argument("--project-root", type=Path, default=Path.cwd())
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        if args.command == "fresh":
            result = fresh_run(
                local_date=args.local_date,
                purpose=args.purpose,
                policy_path=args.policy_file,
                explicit_run_at=args.explicit_run_at,
                newest_complete_before=args.newest_complete_before,
                maximum_total_mib=args.maximum_total_mib,
                allow_live_network=args.allow_live_network,
                database_url=args.database_url,
                project_root=args.project_root,
            )
        else:
            result = resume_run(
                args.run_key,
                args.policy_file,
                database_url=args.database_url,
                project_root=args.project_root,
            )
    except WeatherPipelineError as error:
        print(f"Weather ingestion did not complete: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return (
        0
        if result["status"]
        in {
            "already_succeeded",
            "inserted",
            "revalidated_no_op",
            "recovered_committed_write",
        }
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
