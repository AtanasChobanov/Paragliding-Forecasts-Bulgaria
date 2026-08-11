from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .persistence import PersistenceError, persist_import


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xccontest-persist",
        description="Persist one integrity-verified XCContest validation snapshot into migrated SQLite.",
    )
    parser.add_argument("--run-key", required=True, metavar="UUID")
    parser.add_argument("--validation-snapshot", required=True, metavar="SHA256")
    parser.add_argument("--policy-file", required=True, type=Path, metavar="PATH")
    parser.add_argument("--database-url", metavar="DATABASE_URL")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        report = persist_import(
            args.run_key, args.validation_snapshot, args.policy_file, database_url=args.database_url
        )
    except PersistenceError as error:
        print(f"XCContest persistence did not complete: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
