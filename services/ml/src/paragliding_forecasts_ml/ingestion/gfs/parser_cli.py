"""Offline parser and normalizer command for an existing hash-verified GFS run."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from ..atmosphere.contracts import ArtifactReference
from ..weather.artifacts import WeatherArtifactStore
from ..weather.state import RunStateLedger, StateError
from .normalizer import normalize
from .parser import GfsParserError, parse, raw_manifest_reference


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gfs-parse")
    parser.add_argument("--run-key", required=True, help="Existing S03 GFS run UUID.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    return parser


def _complete_evidence(ledger: RunStateLedger, stage: str) -> ArtifactReference | None:
    matches = [
        event.evidence
        for event in ledger.load_events()
        if event.stage == stage and event.disposition == "complete" and event.evidence is not None
    ]
    return matches[-1] if matches else None


def main(arguments: Sequence[str] | None = None) -> int:
    namespace = build_parser().parse_args(arguments)
    try:
        store = WeatherArtifactStore(namespace.run_key, project_root=namespace.project_root)
        ledger = RunStateLedger(store)
        raw_evidence = _complete_evidence(ledger, "raw_complete")
        if raw_evidence is None or raw_evidence != raw_manifest_reference(store):
            raise StateError("gfs-parse requires the current complete raw manifest state event.")
        parser_manifest = _complete_evidence(ledger, "parsed")
        if parser_manifest is None:
            occurred_at_utc = _utc_now()
            parser_manifest = parse(store, occurred_at_utc=occurred_at_utc)
            ledger.append(
                invocation_mode="resume",
                stage="parsed",
                disposition="complete",
                occurred_at_utc=occurred_at_utc,
                evidence=parser_manifest,
                detail="offline ecCodes native-grid parse",
            )
        if _complete_evidence(ledger, "normalized") is not None:
            raise StateError("This GFS run is already normalized; continue with gfs-sample.")
        occurred_at_utc = _utc_now()
        normalizer_manifest = normalize(store, parser_manifest, occurred_at_utc=occurred_at_utc)
        ledger.append(
            invocation_mode="resume",
            stage="normalized",
            disposition="complete",
            occurred_at_utc=occurred_at_utc,
            evidence=normalizer_manifest,
            detail="canonical GFS grid normalization",
        )
    except (GfsParserError, StateError, OSError, ValueError) as error:
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
