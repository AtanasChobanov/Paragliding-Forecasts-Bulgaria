"""Offline OD prediction entry point."""

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path
from time import perf_counter

from ...ingestion.atmosphere.contracts import UUID_V4_PATTERN
from ...ingestion.weather.artifacts import ArtifactError
from ...ingestion.weather.features.policy import FeaturePolicyError
from ...ingestion.weather.state import StateError
from ...storage.sqlite import DatabaseConfigurationError, repository_root
from .artifacts import publish_prediction
from .policy import load_policy
from .retained import read_inputs


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="overdevelopment-predict",
        description="Daily OD baseline from explicitly selected, retained GFS forecasts.",
    )
    parser.add_argument(
        "--run-key", action="append", required=True, help="GFS run UUID, repeatable."
    )
    parser.add_argument("--project-root", type=Path, default=repository_root())
    parser.add_argument("--database-url", help="Existing repository-relative SQLite file: URL.")
    args = parser.parse_args(arguments)
    if len(set(args.run_key)) != len(args.run_key) or any(
        UUID_V4_PATTERN.fullmatch(key) is None for key in args.run_key
    ):
        parser.error("--run-key requires distinct lowercase UUID v4 values")
    started = perf_counter()
    try:
        root = args.project_root.resolve()
        policy, policy_bytes = load_policy()
        days, sources = read_inputs(args.run_key, project_root=root, database_url=args.database_url)
        manifest, directory, reused = publish_prediction(root, days, sources, policy, policy_bytes)
        published_bytes = sum(path.stat().st_size for path in directory.iterdir())
    except (
        ArtifactError,
        StateError,
        FeaturePolicyError,
        DatabaseConfigurationError,
        OSError,
        ValueError,
        sqlite3.Error,
    ) as error:
        print(f"Overdevelopment prediction did not complete: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "prediction_id": manifest.prediction_id,
                "output_directory": str(directory),
                "run_keys": manifest.run_keys,
                "daily_count": manifest.daily_count,
                "risk_counts": manifest.risk_counts,
                "partial_count": manifest.partial_count,
                "missing_count": manifest.missing_count,
                "reused": reused,
                "elapsed_seconds": perf_counter() - started,
                "published_bytes": published_bytes,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
