"""Supported offline entry point for the T-020 phase 2 audit."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from .flight_label_audit import audit_labels


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="flight-label-audit",
        description="Audit site-day 100/200/300 km labels offline from persisted repaired seasons.",
    )
    parser.add_argument(
        "--season",
        type=int,
        choices=(2022, 2023, 2024, 2025),
        action="append",
        help="Repeat to select source seasons; default: all four.",
    )
    parser.add_argument("--database-url")
    parser.add_argument(
        "--output-directory",
        type=Path,
        help="New or identical audit directory below data/processed/.",
    )
    args = parser.parse_args(arguments)
    try:
        result = audit_labels(
            seasons=tuple(args.season or (2022, 2023, 2024, 2025)),
            database_url=args.database_url,
            output_directory=args.output_directory,
        )
    except (RuntimeError, ValueError, KeyError, TypeError, OSError, sqlite3.Error) as error:
        print(f"Flight-label audit did not complete: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
