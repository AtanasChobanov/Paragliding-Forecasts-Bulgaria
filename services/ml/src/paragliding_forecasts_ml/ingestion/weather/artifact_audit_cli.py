"""CLI for deliberate effective-lineage or all-history weather artifact audits."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .artifact_audit import audit_weather_artifacts
from .artifacts import ArtifactError
from .retention import (
    _archive_receipt,
    _volume,
    archive_run,
    audit_compact,
    evict_local,
    restore_run,
)
from .state import StateError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="weather-artifacts",
        description="Verify immutable weather evidence without source-network access.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit = subparsers.add_parser("audit", help="Verify one run's artifact evidence.")
    audit.add_argument("--run-key", required=True, metavar="UUID")
    audit.add_argument("--scope", required=True, choices=("effective", "all", "compact"))
    audit.add_argument("--project-root", type=Path, default=Path.cwd())
    audit.add_argument("--database-url")
    for name in ("archive", "evict-local", "restore"):
        command = subparsers.add_parser(
            name, help="Manage a verified cold copy of one persisted run."
        )
        command.add_argument("--run-key", required=True, metavar="UUID")
        command.add_argument("--volume-root", required=True, type=Path)
        command.add_argument("--project-root", type=Path, default=Path.cwd())
        command.add_argument("--database-url")
    for name in ("archive-batch", "evict-batch"):
        command = subparsers.add_parser(
            name, help="Process completed batch runs on one cold volume."
        )
        command.add_argument("--batch-id", required=True)
        command.add_argument("--volume-root", required=True, type=Path)
        command.add_argument("--max-runs", type=int, default=25)
        command.add_argument("--project-root", type=Path, default=Path.cwd())
        command.add_argument("--database-url")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    if args.command in {"archive-batch", "evict-batch"} and args.max_runs < 1:
        print("--max-runs must be positive.", file=sys.stderr)
        return 2
    try:
        if args.command in {"archive-batch", "evict-batch"}:
            from paragliding_forecasts_ml.datasets.weather_full_backfill import _batch

            _directory, batch = _batch(args.project_root.resolve(), args.batch_id)
            _volume_root, volume_id = _volume(args.project_root.resolve(), args.volume_root)
            results = []
            for job in batch["jobs"]:
                if len(results) >= args.max_runs:
                    break
                run_key = job["run_key"]
                catalogue = args.project_root / "data/processed/weather-archives" / run_key
                if args.command == "archive-batch":
                    if (catalogue / "eviction-receipt.json").exists():
                        audit_compact(
                            run_key,
                            project_root=args.project_root,
                            database_url=args.database_url,
                        )
                        continue
                    if (catalogue / f"archive-{volume_id}.json").exists():
                        _archive_receipt(args.project_root.resolve(), run_key, args.volume_root)
                        continue
                    results.append(
                        archive_run(
                            run_key,
                            destination=args.volume_root,
                            project_root=args.project_root,
                            database_url=args.database_url,
                        )
                    )
                else:
                    if (catalogue / "eviction-receipt.json").exists():
                        audit_compact(
                            run_key,
                            project_root=args.project_root,
                            database_url=args.database_url,
                        )
                        continue
                    if not (catalogue / f"archive-{volume_id}.json").exists():
                        continue
                    results.append(
                        evict_local(
                            run_key,
                            destination=args.volume_root,
                            project_root=args.project_root,
                            database_url=args.database_url,
                        )
                    )
            report = {"batch_id": args.batch_id, "processed_runs": results}
        elif args.command == "audit":
            report = (
                audit_compact(
                    args.run_key, project_root=args.project_root, database_url=args.database_url
                )
                if args.scope == "compact"
                else audit_weather_artifacts(
                    args.run_key, scope=args.scope, project_root=args.project_root
                )
            )
        elif args.command == "archive":
            report = archive_run(
                args.run_key,
                destination=args.volume_root,
                project_root=args.project_root,
                database_url=args.database_url,
            )
        elif args.command == "evict-local":
            report = evict_local(
                args.run_key,
                destination=args.volume_root,
                project_root=args.project_root,
                database_url=args.database_url,
            )
        else:
            report = restore_run(
                args.run_key,
                destination=args.volume_root,
                project_root=args.project_root,
                database_url=args.database_url,
            )
    except (
        ArtifactError,
        FileNotFoundError,
        KeyError,
        OSError,
        RuntimeError,
        StateError,
        ValueError,
    ) as error:
        print(f"Weather artifact audit did not complete: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
