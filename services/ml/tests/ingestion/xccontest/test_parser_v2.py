from __future__ import annotations

import hashlib
import json

import pytest

from paragliding_forecasts_ml.ingestion.xccontest.parser import ParseError, parse_run
from paragliding_forecasts_ml.ingestion.xccontest.versions import (
    PARSER_OUTPUT_DIRECTORY,
    PARSER_REVISION,
    PARSER_VERSION,
)


def row(flight_id: str, season: int, distance: float) -> str:
    short_year = str(season)[-2:]
    detail_prefix = "" if season == 2026 else f"{season}/"
    return f"""<tr id="flight-{flight_id}">
      <td>1</td>
      <td><div class="full">05.08.{short_year} <em>11:17</em><span class="XCutcOffset">=UTC+03:00</span></div></td>
      <td class="plt"><b>Private pilot name</b></td>
      <td><span class="cic">BG</span><a class="lau" title="Zmeevo" href="https://www.xcontest.org/world/en/flights-search/?filter[point]=28.02228%2043.61223">Zmeevo</a></td>
      <td><div class="disc-vp" title="free flight"></div></td>
      <td class="km"><strong>{distance:.2f}</strong> km</td>
      <td class="dur"><strong>8 : 50</strong> h</td>
      <td><a class="detail" href="https://www.xcontest.org/{detail_prefix}world/en/flights/detail:pilot/5.08.{season}/08:17">details</a></td>
    </tr>"""


def write_v2_run(tmp_path, *, status: str = "complete"):
    run_key = "v2-run"
    raw_dir = tmp_path / "data" / "raw" / "xccontest" / run_key
    raw_dir.mkdir(parents=True)
    artifact_inputs = [
        (2025, row("100", 2025, 150), row("101", 2025, 99)),
        (2026, row("200", 2026, 160), row("201", 2026, 98)),
    ]
    artifacts = []
    all_ids: list[str] = []
    for season, *rows in artifact_inputs:
        html = (
            f'<div id="flights"><table class="XClist"><tbody>{"".join(rows)}</tbody></table></div>'
        )
        path = raw_dir / f"season-{season}-country-BG.html"
        path.write_text(html, encoding="utf-8")
        ids = [value.split('id="flight-', 1)[1].split('"', 1)[0] for value in rows]
        all_ids.extend(ids)
        artifacts.append(
            {
                "path": path.relative_to(tmp_path).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "season": season,
                "country_code": "BG",
                "category": "pg",
                "date_filter": None,
                "sort_key": "distance",
                "sort_direction": "descending",
                "retrieved_at_utc": "2026-08-07T07:00:00Z",
                "first_flight_id": ids[0],
                "last_flight_id": ids[-1],
                "first_distance_km": 150 if season == 2025 else 160,
                "last_distance_km": 99 if season == 2025 else 98,
                "row_observation_count": 2,
                "qualifying_row_observation_count": 1,
            }
        )
    manifest = {
        "manifest_schema_version": 2,
        "collector_version": "xccontest-collector/2",
        "source": "xccontest",
        "source_url": "https://www.xcontest.org/world/en/flights/",
        "run_key": run_key,
        "status": status,
        "started_at_utc": "2026-08-07T06:00:00Z",
        "completed_at_utc": "2026-08-07T07:00:00Z",
        "scope": {
            "country_codes": ["BG"],
            "country_scope_source": "all_sites",
            "requested_seasons": [2025, 2026],
            "primary_glider_category": "FAI3",
            "minimum_scored_distance_km": 100,
            "completed_seasons": [2025, 2026],
        },
        "target_statuses": [
            {
                "season": season,
                "country_code": "BG",
                "status": "complete_primary",
                "unresolved_scopes": [],
            }
            for season in (2025, 2026)
        ],
        "observation_counts": {
            "views_written": 2,
            "row_observations_seen": 4,
            "distinct_source_flights_seen": len(set(all_ids)),
            "repeated_source_flight_observations": len(all_ids) - len(set(all_ids)),
        },
        "artifacts": artifacts,
    }
    (raw_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return run_key, raw_dir


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_parses_complete_multi_season_manifest_v2_and_both_detail_url_shapes(tmp_path) -> None:
    run_key, _ = write_v2_run(tmp_path)

    parsed = parse_run(run_key, project_root=tmp_path)

    records = read_jsonl(parsed.normalized_path)
    assert [record["source_flight_id"] for record in records] == ["100", "200"]
    assert records[1]["source_flight_url"] == (
        "https://www.xcontest.org/world/en/flights/detail:pilot/5.08.2026/08:17"
    )
    assert parsed.output_dir.name == PARSER_OUTPUT_DIRECTORY
    assert parsed.report["parser_version"] == PARSER_VERSION
    assert PARSER_OUTPUT_DIRECTORY == f"parser-v{PARSER_REVISION}"
    assert parsed.report["raw_manifest_schema_version"] == 2
    assert parsed.report["raw_manifest_observation_counts_verified"] is True
    assert parsed.report["raw_country_codes"] == ["BG"]
    assert parsed.report["raw_seasons"] == [2025, 2026]
    assert parsed.report["threshold_exclusions"] == 2
    assert parsed.report["records_rejected"] == 2


def test_manifest_v2_fails_closed_for_incomplete_status_or_counter_drift(tmp_path) -> None:
    run_key, raw_dir = write_v2_run(tmp_path, status="incomplete")
    with pytest.raises(ParseError, match="complete collection status"):
        parse_run(run_key, project_root=tmp_path)

    manifest_path = raw_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "complete"
    manifest["observation_counts"]["row_observations_seen"] = 5
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ParseError, match="do not match its artifacts"):
        parse_run(run_key, project_root=tmp_path)
