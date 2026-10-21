"""Offline command for immutable thermal corrections to an existing joined dataset."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from paragliding_forecasts_ml.storage.sqlite import DatabaseConfigurationError, repository_root

from .weather_join import WeatherJoinError
from .weather_join_correction import build_corrected_joined_dataset
from .weather_join_correction_verify import verify_correction


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="weather-join-correct")
    subcommands = parser.add_subparsers(dest="command", required=True)
    build = subcommands.add_parser("build")
    build.add_argument("--parent-dataset-id", required=True)
    build.add_argument("--database-url")
    build.add_argument("--expected-candidates", type=int)
    build.add_argument("--project-root", type=Path, default=repository_root())
    verify = subcommands.add_parser("verify")
    verify.add_argument("--correction-id", required=True)
    verify.add_argument("--project-root", type=Path, default=repository_root())
    args = parser.parse_args(arguments)
    try:
        if args.command == "build":
            result = build_corrected_joined_dataset(
                parent_dataset_id=args.parent_dataset_id,
                database_url=args.database_url,
                expected_candidates=args.expected_candidates,
                project_root=args.project_root,
            )
        else:
            manifest, _records = verify_correction(
                correction_id=args.correction_id, project_root=args.project_root
            )
            result = {
                "correction_id": args.correction_id,
                "evaluated": manifest["evaluated"],
                "patched": manifest["patched"],
                "verified": True,
            }
    except (
        DatabaseConfigurationError,
        FileNotFoundError,
        KeyError,
        OSError,
        sqlite3.Error,
        TypeError,
        ValueError,
        WeatherJoinError,
    ) as error:
        print(f"Weather correction did not complete: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
