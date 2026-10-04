"""Offline command for the T-020 phase 3 site-day and GFS-request cohort."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .weather_cohort import CohortPlanError, plan_weather_cohort


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="weather-cohort",
        description="Freeze known flight site-days and three-horizon GFS requests offline.",
    )
    parser.add_argument("--audit-id", help="Must match the source audit ID in the cohort policy.")
    parser.add_argument(
        "--policy-file", type=Path, help="Versioned JSON policy; default: packaged T-020 policy."
    )
    parser.add_argument(
        "--output-directory", type=Path, help="New or identical directory below data/processed/."
    )
    args = parser.parse_args(arguments)
    try:
        result = plan_weather_cohort(
            audit_id=args.audit_id,
            policy_file=args.policy_file,
            output_directory=args.output_directory,
        )
    except (
        CohortPlanError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ) as error:
        print(f"Weather cohort did not complete: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
