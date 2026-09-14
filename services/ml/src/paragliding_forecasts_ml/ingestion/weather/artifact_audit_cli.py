"""CLI for deliberate effective-lineage or all-history weather artifact audits."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .artifact_audit import audit_weather_artifacts
from .artifacts import ArtifactError
from .state import StateError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="weather-artifacts",
        description="Verify immutable weather evidence without source-network access.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit = subparsers.add_parser("audit", help="Verify one run's artifact evidence.")
    audit.add_argument("--run-key", required=True, metavar="UUID")
    audit.add_argument("--scope", required=True, choices=("effective", "all"))
    audit.add_argument("--project-root", type=Path, default=Path.cwd())
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        report = audit_weather_artifacts(
            args.run_key,
            scope=args.scope,
            project_root=args.project_root,
        )
    except (ArtifactError, OSError, StateError, ValueError) as error:
        print(f"Weather artifact audit did not complete: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
