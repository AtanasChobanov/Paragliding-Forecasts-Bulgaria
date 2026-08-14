"""Command-line boundary for approved-only XCContest site validation."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from .validator import ValidationError, validate_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xccontest-validate",
        description=(
            "Validate parser staging against approved XCContest source-site mappings. "
            "This command does not contact XCContest or persist flight records."
        ),
    )
    parser.add_argument("--run-key", required=True, metavar="UUID")
    parser.add_argument("--database-url", metavar="DATABASE_URL")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    namespace = build_parser().parse_args(arguments)
    try:
        validated = validate_run(namespace.run_key, database_url=namespace.database_url)
    except (ValidationError, FileExistsError) as error:
        print(f"XCContest validation did not complete: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "output_dir": str(validated.output_dir),
                "accepted_path": str(validated.accepted_path),
                "quarantine_path": str(validated.quarantine_path),
                "report_path": str(validated.report_path),
                **validated.report,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
