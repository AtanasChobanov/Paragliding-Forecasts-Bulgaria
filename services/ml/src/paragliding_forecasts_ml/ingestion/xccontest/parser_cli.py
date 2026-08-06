"""Command-line boundary for offline XCContest parser staging."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from .parser import ParseError, parse_run


def build_parser() -> argparse.ArgumentParser:
    """Build the parser-only command interface."""

    parser = argparse.ArgumentParser(
        prog="xccontest-parse",
        description=(
            "Parse one immutable XCContest raw run offline into deduplicated normalized "
            "staging records. This command does not contact XCContest, match sites, or write SQLite."
        ),
    )
    parser.add_argument(
        "--run-key",
        required=True,
        metavar="UUID",
        help="Raw XCContest run key whose manifest and fragments will be parsed.",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Parse one raw run and report only local staging metadata."""

    namespace = build_parser().parse_args(arguments)
    try:
        parsed = parse_run(namespace.run_key)
    except (ParseError, FileExistsError) as error:
        print(f"XCContest parser did not complete: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "run_key": namespace.run_key,
                "output_dir": str(parsed.output_dir),
                "normalized_path": str(parsed.normalized_path),
                "rejections_path": str(parsed.rejections_path),
                "report_path": str(parsed.report_path),
                **parsed.report,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
