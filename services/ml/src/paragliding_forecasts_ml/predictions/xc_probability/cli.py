"""Offline XC probability workflow; stdout is one JSON result."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from ...datasets.weather_backfill_cli import BackfillError
from ...datasets.weather_cohort import CohortPlanError
from ...datasets.weather_join import WeatherJoinError
from ...storage.sqlite import repository_root
from .study import prepare_study
from .trials import train_trials


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="xc-probability", description="Offline baseline XC probability workflow."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser(
        "prepare", help="Freeze the verified corrected-v4 development study."
    )
    prepare.add_argument("--dataset-id", required=True)
    prepare.add_argument("--project-root", type=Path, default=repository_root())
    trial = commands.add_parser(
        "train-trials", help="Fit six stage variants and evaluate nine chronological candidates."
    )
    trial.add_argument("--study-id", required=True)
    trial.add_argument("--fold", type=int, choices=(2023, 2024), required=True)
    trial.add_argument("--project-root", type=Path, default=repository_root())
    args = parser.parse_args(arguments)
    try:
        if args.command == "prepare":
            result = prepare_study(dataset_id=args.dataset_id, project_root=args.project_root)
        else:
            result = train_trials(
                study_id=args.study_id, fold=args.fold, project_root=args.project_root
            )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        BackfillError,
        CohortPlanError,
        WeatherJoinError,
    ) as error:
        print(f"XC probability command did not complete: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
