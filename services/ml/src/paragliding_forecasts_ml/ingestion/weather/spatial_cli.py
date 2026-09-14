"""Offline canonical-site sampling command for one normalized GFS run."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from ...storage.environment import file_environment
from ...storage.sqlite import configured_database_url
from .artifacts import ArtifactError
from .services import WeatherRunContext, sample_sites
from .sites import SiteSamplingConfigError
from .spatial import SpatialSamplingError
from .state import StateError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gfs-sample")
    parser.add_argument("--run-key", required=True, help="Existing normalized GFS run UUID.")
    parser.add_argument("--database-url", metavar="DATABASE_URL")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    namespace = build_parser().parse_args(arguments)
    project_root = namespace.project_root.resolve()
    file_values = file_environment(project_root / ".env", {"DATABASE_URL"})
    database_url = (
        namespace.database_url or os.environ.get("DATABASE_URL") or file_values.get("DATABASE_URL")
    )
    try:
        context = WeatherRunContext.open(
            namespace.run_key,
            project_root=project_root,
            database_url=configured_database_url(database_url),
        )
        result, context.snapshot = sample_sites(context)
    except (
        ArtifactError,
        OSError,
        SiteSamplingConfigError,
        SpatialSamplingError,
        StateError,
        ValueError,
    ) as error:
        print(f"GFS site sampling failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "run_key": namespace.run_key,
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
