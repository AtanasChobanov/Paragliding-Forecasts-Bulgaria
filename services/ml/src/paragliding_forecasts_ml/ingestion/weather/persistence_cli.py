"""Offline CLI for atomically persisting one verified weather run."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .persistence import WeatherPersistenceError, persist_weather_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="weather-persist",
        description="Persist one verified offline weather feature boundary into migrated SQLite.",
    )
    parser.add_argument("--run-key", required=True, metavar="UUID")
    parser.add_argument(
        "--policy-file",
        type=Path,
        metavar="PATH",
        help="Optional source-bound local JSON policy; defaults to data/local/<source>-usage-policy.json.",
    )
    parser.add_argument("--database-url", metavar="DATABASE_URL")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        report = persist_weather_run(
            args.run_key,
            args.policy_file,
            database_url=args.database_url,
            project_root=args.project_root,
        )
    except WeatherPersistenceError as error:
        print(f"Weather persistence did not complete: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
