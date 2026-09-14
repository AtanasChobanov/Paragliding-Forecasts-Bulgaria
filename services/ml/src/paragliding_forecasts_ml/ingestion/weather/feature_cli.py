"""Offline S07 feature-artifact command for one validated weather run."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .artifacts import ArtifactError
from .feature_stage import WeatherFeatureBuildError
from .services import WeatherRunContext, build_features
from .state import StateError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="weather-build-features")
    parser.add_argument("--run-key", required=True, help="Existing validated weather run UUID.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    namespace = build_parser().parse_args(arguments)
    try:
        context = WeatherRunContext.open(
            namespace.run_key,
            project_root=namespace.project_root.resolve(),
        )
        result, context.snapshot = build_features(context)
    except (ArtifactError, OSError, StateError, ValueError, WeatherFeatureBuildError) as error:
        print(f"Weather feature build failed: {error}", file=sys.stderr)
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
    return 2 if result.disposition == "quarantined" else 0


if __name__ == "__main__":
    raise SystemExit(main())
