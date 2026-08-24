"""Explicit live-network command for canonical-site Copernicus elevations."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from ...storage.environment import file_environment
from ...storage.sqlite import configured_database_url
from ..weather.sites import SiteSamplingConfigError, load_site_sampling_configs
from .elevation import (
    CopernicusElevationClient,
    CopernicusElevationError,
    UrllibTransport,
)

DEFAULT_OUTPUT = Path("data/interim/weather/site-elevations/copernicus-dem-glo30-v1.json")


def _setting(name: str, file_values: Mapping[str, str]) -> str | None:
    return os.environ.get(name) or file_values.get(name)


def _output_path(project_root: Path, requested: Path) -> Path:
    root = project_root.resolve()
    output = requested if requested.is_absolute() else root / requested
    output = output.resolve()
    interim_root = (root / "data" / "interim").resolve()
    try:
        output.relative_to(interim_root)
    except ValueError as error:
        raise CopernicusElevationError("Elevation output must stay below data/interim/.") from error
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="copernicus-elevations")
    parser.add_argument("--database-url", metavar="DATABASE_URL")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--allow-live-network",
        action="store_true",
        help="Required acknowledgement before OAuth or Copernicus DEM requests.",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    namespace = build_parser().parse_args(arguments)
    if not namespace.allow_live_network:
        print(
            "Refusing network access: pass --allow-live-network after reviewing the request.",
            file=sys.stderr,
        )
        return 2

    project_root = namespace.project_root.resolve()
    file_values = file_environment(
        project_root / ".env", {"CDSE_CLIENT_ID", "CDSE_CLIENT_SECRET", "DATABASE_URL"}
    )
    database_url = namespace.database_url or _setting("DATABASE_URL", file_values)
    try:
        sites = load_site_sampling_configs(
            configured_database_url(database_url), project_root, require_elevation=False
        )
        client = CopernicusElevationClient(
            UrllibTransport(),
            client_id=_setting("CDSE_CLIENT_ID", file_values) or "",
            client_secret=_setting("CDSE_CLIENT_SECRET", file_values) or "",
        )
        proposal = client.fetch(sites)
        output = _output_path(project_root, namespace.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(proposal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (CopernicusElevationError, SiteSamplingConfigError, OSError) as error:
        print(f"Copernicus elevation fetch failed: {error}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "output": output.relative_to(project_root).as_posix(),
                "site_count": len(sites),
                "schema_version": proposal["schema_version"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
