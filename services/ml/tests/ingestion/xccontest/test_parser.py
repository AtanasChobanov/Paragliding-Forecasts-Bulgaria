from __future__ import annotations

import hashlib
import json

import pytest

from paragliding_forecasts_ml.ingestion.xccontest.parser import ParseError, parse_run
from paragliding_forecasts_ml.ingestion.xccontest.parser_cli import build_parser


def flight_row(
    flight_id: str,
    *,
    date: str = "02.08.25",
    time: str = "10:55",
    offset: str = "=UTC+03:00",
    launch_name: str = "Kominite",
    distance: str = "400.86",
    duration: str = "9 : 05",
) -> str:
    return f'''<tr id="flight-{flight_id}">
      <td>1</td><td><div class="full">{date} <em>{time}</em><span class="XCutcOffset">{offset}</span></div></td>
      <td class="plt"><b>Private pilot name</b></td>
      <td><span class="cic">BG</span><a class="lau" title="{launch_name}" href="https://www.xcontest.org/2025/world/en/flights-search/?filter[point]=28.074375%2043.74609">{launch_name}</a></td>
      <td><div class="disc-vp" title="free flight"></div></td>
      <td class="km"><strong>{distance}</strong> km</td><td class="dur"><strong>{duration}</strong> h</td>
      <td><a class="detail" href="https://www.xcontest.org/2025/world/en/flights/detail:adit0/2.08.2025/07:55">details</a></td>
    </tr>'''


def fragment(*rows: str) -> str:
    return f'<div id="flights"><table class="XClist"><tbody>{"".join(rows)}</tbody></table></div>'


def write_run(
    tmp_path, *, run_key: str = "test-run", fragments: list[str], version: int | None = None
):
    raw_dir = tmp_path / "data" / "raw" / "xccontest" / run_key
    raw_dir.mkdir(parents=True)
    artifacts = []
    for index, html in enumerate(fragments, start=1):
        path = raw_dir / f"view-{index}.html"
        path.write_text(html, encoding="utf-8")
        artifacts.append(
            {
                "path": path.relative_to(tmp_path).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "season": 2025,
                "country_code": "BG" if version == 2 else None,
                "category": "pg",
                "date_filter": None,
                "sort_key": "distance",
                "sort_direction": "descending",
            }
        )
    manifest = {
        "source": "xccontest",
        "run_key": run_key,
        "scope": {"country_codes": ["BG"]} if version == 2 else {"country": "BG"},
        "artifacts": artifacts,
    }
    if version is not None:
        manifest["manifest_schema_version"] = version
    (raw_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return raw_dir


def jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_normalizes_and_removes_identical_same_run_duplicates(tmp_path) -> None:
    write_run(tmp_path, fragments=[fragment(flight_row("123")), fragment(flight_row("123"))])

    parsed = parse_run("test-run", project_root=tmp_path)

    records = jsonl(parsed.normalized_path)
    assert len(records) == 1
    record = records[0]
    assert record["parser_status"] == "normalized"
    assert record["source_flight_id"] == "123"
    assert record["takeoff_at_utc"] == "2025-08-02T07:55:00Z"
    assert record["scored_distance_km"] == 400.86
    assert record["duration_seconds"] == 32_700
    assert record["route_type"] == "free_flight"
    assert record["launch_point_token"] == "28.074375 43.74609"
    assert record["launch_longitude_deg"] == 28.074375
    assert record["launch_latitude_deg"] == 43.74609
    assert record["source_flight_url"].startswith("https://www.xcontest.org/")
    assert len(record["artifact_references"]) == 2
    assert "Private pilot name" not in json.dumps(record)
    assert parsed.report["duplicate_observations_removed"] == 1


def test_emits_one_conflicted_candidate_without_choosing_a_value(tmp_path) -> None:
    write_run(
        tmp_path,
        fragments=[
            fragment(flight_row("123", distance="400.86")),
            fragment(flight_row("123", distance="401.00")),
        ],
    )

    records = jsonl(parse_run("test-run", project_root=tmp_path).normalized_path)

    assert len(records) == 1
    assert records[0]["parser_status"] == "conflicted"
    assert records[0]["conflicting_fields"] == ["scored_distance_km"]
    assert {variant["scored_distance_km"] for variant in records[0]["variants"]} == {400.86, 401.0}


def test_rejects_threshold_and_malformed_legacy_rows(tmp_path) -> None:
    write_run(
        tmp_path,
        fragments=[
            fragment(
                flight_row("1"), flight_row("2", distance="99.99"), flight_row("3", duration="9:99")
            )
        ],
    )

    parsed = parse_run("test-run", project_root=tmp_path)

    assert [record["source_flight_id"] for record in jsonl(parsed.normalized_path)] == ["1"]
    assert len(jsonl(parsed.rejections_path)) == 2
    assert parsed.report["threshold_exclusions"] == 1
    assert parsed.report["records_rejected"] == 2
    assert parsed.report["raw_manifest_schema_version"] == 1
    assert parsed.output_dir.name == "parser-v2"


def test_fails_closed_for_artifact_hash_escape_and_existing_output(tmp_path) -> None:
    raw_dir = write_run(tmp_path, fragments=[fragment(flight_row("1"))])
    manifest_path = raw_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["artifacts"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ParseError, match="SHA-256"):
        parse_run("test-run", project_root=tmp_path)

    raw_dir = write_run(tmp_path, run_key="fresh-run", fragments=[fragment(flight_row("1"))])
    parse_run("fresh-run", project_root=tmp_path)
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        parse_run("fresh-run", project_root=tmp_path)


def test_cross_year_season_time_and_cli_contract(tmp_path) -> None:
    write_run(
        tmp_path, fragments=[fragment(flight_row("123", date="01.10.24", offset="=UTC+02:00"))]
    )

    record = jsonl(parse_run("test-run", project_root=tmp_path).normalized_path)[0]

    assert record["takeoff_at_utc"] == "2024-10-01T08:55:00Z"
    namespace = build_parser().parse_args(["--run-key", "test-run"])
    assert namespace.run_key == "test-run"
