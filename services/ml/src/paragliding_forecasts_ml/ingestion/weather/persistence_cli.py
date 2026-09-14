"""Offline CLI for atomically persisting one verified weather run."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from ...storage.environment import file_environment
from ...storage.sqlite import DatabaseConfigurationError, configured_database_url
from .artifacts import ArtifactError
from .persistence import WeatherPersistenceError
from .services import WeatherRunContext, persist_run
from .state import StateError


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
        root = args.project_root.resolve()
        file_values = file_environment(root / ".env", {"DATABASE_URL"})
        database_url = (
            args.database_url or os.environ.get("DATABASE_URL") or file_values.get("DATABASE_URL")
        )
        context = WeatherRunContext.open(
            args.run_key,
            project_root=root,
            database_url=configured_database_url(database_url),
        )
        result, context.snapshot = persist_run(context, args.policy_file)
    except (
        ArtifactError,
        DatabaseConfigurationError,
        OSError,
        StateError,
        ValueError,
        WeatherPersistenceError,
    ) as error:
        print(f"Weather persistence did not complete: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                **result.as_dict(),
                "verification_summary": context.verification_summary(),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
