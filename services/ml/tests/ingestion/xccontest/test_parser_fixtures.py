"""Fixture-based integration/regression coverage for the offline XCContest parser."""

from __future__ import annotations

import json
from pathlib import Path
from shutil import copytree

from paragliding_forecasts_ml.ingestion.xccontest.parser import parse_run

RUN_KEY = "t015-synthetic-mini-run-v1"
FIXTURE_ROOT = (
    Path(__file__).resolve().parents[5]
    / "data"
    / "samples"
    / "xccontest"
    / "parser-v2"
    / "synthetic-mini-run-v1"
)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_replays_the_frozen_synthetic_manifest_v3_mini_run(tmp_path: Path) -> None:
    """Run the real parser against committed inputs and compare all golden artifacts."""

    raw_run_dir = tmp_path / "data" / "raw" / "xccontest" / RUN_KEY
    copytree(FIXTURE_ROOT / "input", raw_run_dir)

    parsed = parse_run(RUN_KEY, project_root=tmp_path)

    expected_dir = FIXTURE_ROOT / "expected"
    assert read_jsonl(parsed.normalized_path) == read_jsonl(
        expected_dir / "normalized-flights.jsonl"
    )
    assert read_jsonl(parsed.rejections_path) == read_jsonl(expected_dir / "parse-rejections.jsonl")
    assert json.loads(parsed.report_path.read_text(encoding="utf-8")) == json.loads(
        (expected_dir / "parse-report.json").read_text(encoding="utf-8")
    )

    records = {record["source_flight_id"]: record for record in read_jsonl(parsed.normalized_path)}
    assert records["150001"]["scored_distance_km"] == 100.0
    assert records["150001"]["scored_distance_km"] != 999.99
    assert records["150003"]["scored_distance_km"] == 200.0
    assert records["150005"]["scored_distance_km"] == 300.0
    assert records["150009"]["scored_distance_km"] == 150.5
    assert records["150009"]["route_type"] == "unknown"
    assert records["150010"]["route_type"] == "other"
    assert records["150002"]["parser_status"] == "conflicted"
    assert len(records["150001"]["artifact_references"]) == 2

    output_text = "\n".join(
        (
            parsed.normalized_path.read_text(encoding="utf-8"),
            parsed.rejections_path.read_text(encoding="utf-8"),
            parsed.report_path.read_text(encoding="utf-8"),
        )
    )
    assert "SYNTHETIC PILOT" not in output_text
