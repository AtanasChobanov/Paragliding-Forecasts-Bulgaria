"""One offline command for cloudbase prediction from retained GFS runs."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from ...ingestion.weather.artifacts import ArtifactError
from ...ingestion.weather.state import StateError
from ...storage.sqlite import DatabaseConfigurationError, repository_root
from .service import build_predictions


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cloudbase-predict",
        description="Offline conditional cumulus-base baseline. No fetch, training or SQLite writes.",
    )
    parser.add_argument(
        "--run-key",
        action="append",
        required=True,
        help="Succeeded retained GFS 06Z run UUID; repeat to process several runs.",
    )
    parser.add_argument("--database-url", help="Existing repository-relative SQLite file: URL.")
    parser.add_argument("--project-root", type=Path, default=repository_root())
    args = parser.parse_args(arguments)
    try:
        result = build_predictions(
            args.run_key, project_root=args.project_root.resolve(), database_url=args.database_url
        )
    except (
        ArtifactError,
        StateError,
        DatabaseConfigurationError,
        FileNotFoundError,
        OSError,
        ValueError,
        KeyError,
        sqlite3.Error,
    ) as error:
        print(f"Cloudbase prediction did not complete: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
