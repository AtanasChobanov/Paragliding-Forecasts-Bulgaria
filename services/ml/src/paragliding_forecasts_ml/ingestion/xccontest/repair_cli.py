"""Explicit offline audit and bounded live repair CLI for XCContest raw runs."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from .models import CollectorConfig
from .repair import RepairError, audit_run, collect_repair


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="xccontest-repair")
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser("audit", help="Read-only audit of a completed raw run.")
    audit.add_argument("--run-key", required=True)
    collect = commands.add_parser("collect", help="Recollect only audited inconsistent views.")
    collect.add_argument("--run-key", required=True)
    collect.add_argument("--headed", action="store_true")
    collect.add_argument("--timeout-seconds", type=int, default=90)
    collect.add_argument("--source-delay-seconds", type=float, default=30)
    collect.add_argument("--max-views", type=int, default=100)
    collect.add_argument("--allow-live-network", action="store_true", required=True)
    resume = commands.add_parser(
        "resume", help="Resume an interrupted repair from verified artifacts."
    )
    resume.add_argument("--repair-run-key", required=True)
    resume.add_argument("--allow-live-network", action="store_true", required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        if args.command == "audit":
            result = audit_run(args.run_key)
        elif args.command == "collect":
            audit = audit_run(args.run_key)
            config = CollectorConfig(
                seasons=tuple(dict.fromkeys(issue["season"] for issue in audit["issues"])),
                country_codes=tuple(
                    dict.fromkeys(issue["country_code"] for issue in audit["issues"])
                ),
                headed=args.headed,
                timeout_seconds=args.timeout_seconds,
                delay_seconds=args.source_delay_seconds,
                max_views=args.max_views,
            )
            result = collect_repair(
                args.run_key,
                config=config,
                on_run_ready=lambda key: print(
                    f"Repair run key: {key}", file=sys.stderr, flush=True
                ),
                on_view_completed=lambda done, total, path: print(
                    f"Verified repair view {done}/{total}: {path.rsplit('/', 1)[-1]}",
                    file=sys.stderr,
                    flush=True,
                ),
            )
        else:
            result = collect_repair(
                repair_run_key=args.repair_run_key,
                on_run_ready=lambda key: print(
                    f"Repair run key: {key}", file=sys.stderr, flush=True
                ),
                on_view_completed=lambda done, total, path: print(
                    f"Verified repair view {done}/{total}: {path.rsplit('/', 1)[-1]}",
                    file=sys.stderr,
                    flush=True,
                ),
            )
    except (RepairError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
