"""Offline parser and normalizer command for an existing hash-verified GFS run."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from ..weather.artifacts import WeatherArtifactStore
from .normalizer import normalize
from .parser import GfsParserError, parse


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gfs-parse")
    parser.add_argument("--run-key", required=True, help="Existing S03 GFS run UUID.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    namespace = build_parser().parse_args(arguments)
    try:
        store = WeatherArtifactStore(namespace.run_key, project_root=namespace.project_root)
        parser_manifest = parse(store, occurred_at_utc=_utc_now())
        normalizer_manifest = normalize(store, parser_manifest, occurred_at_utc=_utc_now())
    except (GfsParserError, OSError, ValueError) as error:
        print(f"GFS parser failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "run_key": namespace.run_key,
                "parser_manifest": parser_manifest.relative_path,
                "normalizer_manifest": normalizer_manifest.relative_path,
                "network_access": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
