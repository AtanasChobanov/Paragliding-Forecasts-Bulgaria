"""Offline S07 feature-artifact command for one validated weather run."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from ..atmosphere.contracts import ArtifactReference
from .artifacts import ArtifactError, WeatherArtifactStore
from .feature_stage import WeatherFeatureBuildError, build_weather_features
from .state import RunStateLedger, StateError
from .validation import validation_disposition


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validated_evidence(ledger: RunStateLedger) -> ArtifactReference:
    event = ledger.latest_stage_event(ledger.load_events(), "validated")
    if event is None or event.evidence is None:
        raise StateError("weather-build-features requires a validated weather run.")
    return event.evidence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="weather-build-features")
    parser.add_argument("--run-key", required=True, help="Existing validated weather run UUID.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    namespace = build_parser().parse_args(arguments)
    try:
        store = WeatherArtifactStore(
            namespace.run_key, project_root=namespace.project_root.resolve()
        )
        ledger = RunStateLedger(store)
        validation_manifest = _validated_evidence(ledger)
        disposition = validation_disposition(store, validation_manifest)
        if disposition == "quarantined":
            print(
                json.dumps(
                    {
                        "run_key": namespace.run_key,
                        "validation_manifest": validation_manifest.relative_path,
                        "disposition": disposition,
                        "feature_manifest": None,
                        "network_access": False,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 2
        if disposition != "complete":
            raise WeatherFeatureBuildError("Validation disposition is not complete.")
        occurred_at_utc = _utc_now()
        feature_manifest = build_weather_features(
            store, validation_manifest, occurred_at_utc=occurred_at_utc
        )
        previous = ledger.latest_stage_event(ledger.load_events(), "features_built")
        if previous is None or previous.evidence != feature_manifest:
            ledger.append(
                invocation_mode="resume",
                stage="features_built",
                disposition="complete",
                occurred_at_utc=occurred_at_utc,
                evidence=feature_manifest,
                supersedes_sequence=previous.sequence if previous is not None else None,
                detail="strict daily weather feature snapshots and quality evidence",
            )
    except (ArtifactError, OSError, StateError, ValueError, WeatherFeatureBuildError) as error:
        print(f"Weather feature build failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "run_key": namespace.run_key,
                "validation_manifest": validation_manifest.relative_path,
                "feature_manifest": feature_manifest.relative_path,
                "network_access": False,
                "disposition": "complete",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
