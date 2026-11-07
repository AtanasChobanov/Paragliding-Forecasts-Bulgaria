"""Offline XC probability workflow; stdout is one JSON result."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from ...datasets.weather_backfill_cli import BackfillError
from ...datasets.weather_cohort import CohortPlanError
from ...datasets.weather_join import WeatherJoinError
from ...ingestion.weather.artifacts import ArtifactError
from ...ingestion.weather.state import StateError
from ...storage.sqlite import DatabaseConfigurationError, repository_root
from .experiment import CURRENT_EXPERIMENT_VERSION, SUPPORTED_EXPERIMENT_VERSIONS
from .model_io import train_final
from .prediction import predict_runs
from .scoring_layout import VALIDATION_SEASONS
from .selection import select_recipe
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
        "train-trials", help="Fit the versioned C grid and evaluate chronological candidates."
    )
    trial.add_argument("--study-id", required=True)
    trial.add_argument("--fold", type=int, choices=VALIDATION_SEASONS, required=True)
    trial.add_argument(
        "--experiment-version",
        type=int,
        choices=SUPPORTED_EXPERIMENT_VERSIONS,
        default=CURRENT_EXPERIMENT_VERSION,
        help="C search: 2 (default) uses nine values/81 pairs; 1 reproduces three values/nine pairs.",
    )
    trial.add_argument("--project-root", type=Path, default=repository_root())
    selection = commands.add_parser(
        "select", help="Select a recipe from both verified chronological trials."
    )
    selection.add_argument("--study-id", required=True)
    selection.add_argument("--trial-id", action="append", required=True)
    selection.add_argument("--project-root", type=Path, default=repository_root())
    final = commands.add_parser(
        "train-final", help="Refit the selected recipe on all frozen development rows."
    )
    final.add_argument("--study-id", required=True)
    final.add_argument("--selection-id", required=True)
    final.add_argument("--project-root", type=Path, default=repository_root())
    predict = commands.add_parser(
        "predict", help="Predict from explicitly selected persisted GFS runs."
    )
    predict.add_argument("--model-id", required=True)
    predict.add_argument("--run-key", action="append", required=True)
    predict.add_argument("--database-url")
    predict.add_argument("--project-root", type=Path, default=repository_root())
    args = parser.parse_args(arguments)
    try:
        if args.command == "prepare":
            result = prepare_study(dataset_id=args.dataset_id, project_root=args.project_root)
        elif args.command == "train-trials":
            result = train_trials(
                study_id=args.study_id,
                fold=args.fold,
                project_root=args.project_root,
                experiment_version=args.experiment_version,
            )
        elif args.command == "select":
            result = select_recipe(
                study_id=args.study_id, trial_ids=args.trial_id, project_root=args.project_root
            )
        elif args.command == "train-final":
            result = train_final(
                study_id=args.study_id,
                selection_id=args.selection_id,
                project_root=args.project_root,
            )
        else:
            result = predict_runs(
                model_id=args.model_id,
                run_keys=tuple(args.run_key),
                project_root=args.project_root,
                database_url=args.database_url,
            )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        BackfillError,
        CohortPlanError,
        WeatherJoinError,
        ArtifactError,
        StateError,
        DatabaseConfigurationError,
        sqlite3.Error,
    ) as error:
        print(f"XC probability command did not complete: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
