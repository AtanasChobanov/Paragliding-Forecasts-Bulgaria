"""Offline source-aware validation command for one spatial weather run."""

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
from .state import RunStateLedger, StateError
from .validation import (
    WEATHER_VALIDATOR_VERSION,
    WeatherValidationError,
    validate_weather_run,
    validation_disposition,
    validation_upstream_boundary,
    validation_version,
)


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validated_evidence(ledger: RunStateLedger) -> ArtifactReference | None:
    matches = [
        event.evidence
        for event in ledger.load_events()
        if event.stage == "validated" and event.evidence is not None
    ]
    return matches[-1] if matches else None


def _spatial_evidence(ledger: RunStateLedger) -> ArtifactReference:
    events = ledger.load_events()
    matches = [
        event.evidence
        for event in events
        if event.stage == "spatially_aligned"
        and event.disposition == "complete"
        and event.evidence is not None
    ]
    if not matches:
        raise StateError("weather-validate requires a complete spatially aligned state event.")
    return matches[-1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="weather-validate")
    parser.add_argument(
        "--run-key", required=True, help="Existing spatially aligned weather run UUID."
    )
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
        existing_manifest = _validated_evidence(ledger)
        spatial_manifest = _spatial_evidence(ledger)
        if (
            existing_manifest is None
            or validation_version(store, existing_manifest) != WEATHER_VALIDATOR_VERSION
            or validation_upstream_boundary(store, existing_manifest) != spatial_manifest
        ):
            occurred_at_utc = _utc_now()
            validation_manifest = validate_weather_run(
                store,
                spatial_manifest,
                database_url=configured_database_url(database_url),
                occurred_at_utc=occurred_at_utc,
                project_root=project_root,
            )
            disposition = validation_disposition(store, validation_manifest)
            ledger.append(
                invocation_mode="resume",
                stage="validated",
                disposition=disposition,
                occurred_at_utc=occurred_at_utc,
                evidence=validation_manifest,
                supersedes_sequence=(
                    previous.sequence
                    if (previous := ledger.latest_stage_event(ledger.load_events(), "validated"))
                    is not None
                    else None
                ),
                detail="source-aware offline validation and quarantine evidence",
            )
        else:
            validation_manifest = existing_manifest
            disposition = validation_disposition(store, validation_manifest)
    except (ArtifactError, OSError, StateError, ValueError, WeatherValidationError) as error:
        print(f"Weather validation failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "run_key": namespace.run_key,
                "validation_manifest": validation_manifest.relative_path,
                "network_access": False,
                "database_access": "read_only",
                "disposition": disposition,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 2 if disposition == "quarantined" else 0


if __name__ == "__main__":
    raise SystemExit(main())
