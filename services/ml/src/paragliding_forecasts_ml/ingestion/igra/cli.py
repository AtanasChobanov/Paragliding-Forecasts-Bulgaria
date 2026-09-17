"""Machine-readable command boundary for bounded IGRA inventory/fresh/offline resume."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .inventory import IgraInventoryError, inventory, parse_selection
from .pipeline import IgraPipelineError, fresh, resume
from .transport import RetryingIgraTransport, UrllibIgraTransport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="igra-ingest")
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("inventory", "fresh"):
        command = subcommands.add_parser(name)
        _selectors(command)
        command.add_argument("--allow-live-network", action="store_true")
        if name == "fresh":
            command.add_argument("--maximum-total-mib", type=int)
    resume_parser = subcommands.add_parser("resume")
    resume_parser.add_argument("--run-key", required=True)
    resume_parser.add_argument("--project-root", type=Path, default=Path.cwd())
    return parser


def _selectors(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--station-id", required=True)
    parser.add_argument("--date", dest="dates", action="append", default=[])
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument(
        "--nominal-hour", dest="nominal_hours", action="append", type=int, default=[]
    )
    parser.add_argument("--archive", choices=("auto", "recent", "period-of-record"), default="auto")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "resume":
            result = resume(run_key=args.run_key, project_root=args.project_root)
        else:
            if not args.allow_live_network:
                raise IgraInventoryError("inventory and fresh require --allow-live-network.")
            dates, hours = parse_selection(
                dates=tuple(args.dates),
                start_date=args.start_date,
                end_date=args.end_date,
                nominal_hours=tuple(args.nominal_hours),
            )
            transport = RetryingIgraTransport(UrllibIgraTransport())
            if args.command == "inventory":
                result, _policy_sha = inventory(
                    transport,
                    station_id=args.station_id,
                    dates_utc=dates,
                    nominal_hours=hours,
                    requested_archive_mode=args.archive,
                )
                _write(result.model_dump(mode="json"))
                return 0
            if args.maximum_total_mib is None or args.maximum_total_mib <= 0:
                raise IgraInventoryError("fresh requires a positive --maximum-total-mib.")
            result = fresh(
                station_id=args.station_id,
                dates_utc=dates,
                nominal_hours=hours,
                archive=args.archive,
                maximum_total_mib=args.maximum_total_mib,
                project_root=args.project_root,
                transport=transport,
            )
        _write(result)
        return int(result["exit_code"])
    except (IgraInventoryError, IgraPipelineError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


def _write(result: object) -> None:
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
