"""Offline canonical-site sampling command for one normalized GFS run."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from ...storage.environment import file_environment
from ...storage.sqlite import configured_database_url
from ..atmosphere.contracts import ArtifactReference
from .artifacts import ArtifactError, WeatherArtifactStore
from .sites import SiteSamplingConfigError
from .spatial import SpatialSamplingError, sample_canonical_sites
from .state import RunStateLedger, StateError


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalizer_evidence(ledger: RunStateLedger) -> ArtifactReference:
    events = ledger.load_events()
    matches = [
        event.evidence
        for event in events
        if event.stage == "normalized"
        and event.disposition == "complete"
        and event.evidence is not None
    ]
    if not matches:
        raise StateError("gfs-sample requires a complete normalized state event.")
    return matches[-1]


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
        store = WeatherArtifactStore(namespace.run_key, project_root=project_root)
        ledger = RunStateLedger(store)
        normalizer_manifest = _normalizer_evidence(ledger)
        occurred_at_utc = _utc_now()
        spatial_manifest = sample_canonical_sites(
            store,
            normalizer_manifest,
            database_url=configured_database_url(database_url),
            occurred_at_utc=occurred_at_utc,
            project_root=project_root,
        )
        ledger.append(
            invocation_mode="resume",
            stage="spatially_aligned",
            disposition="complete",
            occurred_at_utc=occurred_at_utc,
            evidence=spatial_manifest,
            detail="bilinear point samples and 50 km physical-radius node evidence",
        )
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
                "spatial_manifest": spatial_manifest.relative_path,
                "network_access": False,
                "database_access": "read_only",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
