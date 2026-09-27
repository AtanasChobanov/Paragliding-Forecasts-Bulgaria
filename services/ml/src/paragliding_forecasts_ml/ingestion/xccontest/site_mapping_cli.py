"""Command-line boundary for reviewed XCContest source-site mappings."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .site_mapping import (
    SiteMappingError,
    apply_mapping_decisions,
    auto_apply_coordinate_mappings,
    retire_site_exclusion,
    write_mapping_proposals,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xccontest-site-mappings",
        description="Propose or apply reviewed XCContest source-site mappings without source access.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    propose = subcommands.add_parser(
        "propose", help="Write grouped review proposals from parser staging."
    )
    propose.add_argument("--run-key", required=True, metavar="UUID")
    propose.add_argument("--database-url", metavar="DATABASE_URL")
    apply = subcommands.add_parser("apply", help="Apply a human-reviewed mapping JSONL file.")
    apply.add_argument("--review-file", required=True, type=Path, metavar="PATH")
    apply.add_argument("--database-url", metavar="DATABASE_URL")
    automatic = subcommands.add_parser(
        "auto-apply", help="Apply only deterministic unique-catchment coordinate mappings."
    )
    automatic.add_argument("--run-key", required=True, metavar="UUID")
    automatic.add_argument("--database-url", metavar="DATABASE_URL")
    retire = subcommands.add_parser(
        "retire-exclusion", help="Retire one active persistent exclusion."
    )
    retire.add_argument("--exclusion-id", required=True, type=int, metavar="ID")
    retire.add_argument("--reason", required=True, metavar="TEXT")
    retire.add_argument("--database-url", metavar="DATABASE_URL")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    namespace = build_parser().parse_args(arguments)
    try:
        if namespace.command == "propose":
            result = write_mapping_proposals(namespace.run_key, database_url=namespace.database_url)
        elif namespace.command == "auto-apply":
            result = auto_apply_coordinate_mappings(
                namespace.run_key, database_url=namespace.database_url
            )
        elif namespace.command == "retire-exclusion":
            result = retire_site_exclusion(
                namespace.exclusion_id, namespace.reason, database_url=namespace.database_url
            )
        else:
            result = apply_mapping_decisions(
                namespace.review_file, database_url=namespace.database_url
            )
    except (SiteMappingError, FileExistsError) as error:
        print(f"XCContest site mapping did not complete: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, default=str, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
