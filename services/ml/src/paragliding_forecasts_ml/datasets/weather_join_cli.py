"""Offline T-020 joined dataset command."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from paragliding_forecasts_ml.storage.sqlite import DatabaseConfigurationError, repository_root

from .weather_backfill_cli import BackfillError
from .weather_cohort import CohortPlanError
from .weather_join import WeatherJoinError, build_joined_dataset


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="weather-join", description="Build horizon-matched audited weather examples offline."
    )
    parser.add_argument("--acquisition-id", required=True)
    parser.add_argument("--database-url")
    parser.add_argument("--project-root", type=Path, default=repository_root())
    args = parser.parse_args(arguments)
    try:
        result = build_joined_dataset(
            acquisition_id=args.acquisition_id,
            database_url=args.database_url,
            project_root=args.project_root,
        )
    except (
        BackfillError,
        CohortPlanError,
        DatabaseConfigurationError,
        FileNotFoundError,
        KeyError,
        OSError,
        sqlite3.Error,
        ValueError,
        WeatherJoinError,
    ) as error:
        print(f"Weather join did not complete: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
