from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from paragliding_forecasts_ml.ingestion.xccontest.validator import validate_run


def database_url() -> str:
    return "file:./data/local/validator.db"


def create_database(tmp_path: Path) -> None:
    path = tmp_path / "data" / "local" / "validator.db"
    path.parent.mkdir(parents=True)
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE flight_sources (id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE);
        CREATE TABLE sites (
          id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
          country_code_iso2 TEXT NOT NULL, site_type TEXT NOT NULL,
          latitude_deg REAL NOT NULL, longitude_deg REAL NOT NULL,
          catchment_radius_km REAL
        );
        CREATE TABLE source_site_mappings (
          id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL, site_id INTEGER NOT NULL,
          key_type TEXT NOT NULL, key_value TEXT, source_display_name TEXT,
          point_latitude_deg REAL, point_longitude_deg REAL, status TEXT NOT NULL,
          verification_reference TEXT, verified_at_utc TEXT, notes TEXT
        );
        INSERT INTO flight_sources VALUES (1, 'xccontest');
        INSERT INTO sites VALUES
          (1, 'sopot', 'Sopot', 'BG', 'launch_area', 42.68733, 24.749962, 5),
          (2, 'zlatitsa', 'Zlatitsa', 'BG', 'launch_area', 42.7302, 24.0923, 5);
        INSERT INTO source_site_mappings VALUES
          (1, 1, 1, 'source_site_token', 'sopot-token', 'Sopot', NULL, NULL,
           'approved', 'manual review', '2026-08-08T12:00:00Z', NULL);
        """
    )
    connection.commit()
    connection.close()


def candidate(flight_id: str, *, token: str, name: str = "Sopot") -> dict:
    return {
        "source": "xccontest",
        "source_flight_id": flight_id,
        "source_flight_url": "https://www.xcontest.org/world/en/flights/detail:pilot/1.01.2026/10:00",
        "parser_status": "normalized",
        "launch_name_raw": name,
        "launch_country_code_iso2": "BG",
        "launch_latitude_deg": 42.68733,
        "launch_longitude_deg": 24.749962,
        "launch_search_url": f"https://www.xcontest.org/world/en/hotspots?detail#filter[site]={token}",
        "artifact_references": [{"season": 2026}],
    }


def write_parser_output(tmp_path: Path, records: list[dict]) -> None:
    raw = tmp_path / "data" / "raw" / "xccontest" / "test-run"
    raw.mkdir(parents=True)
    (raw / "manifest.json").write_text('{"source":"xccontest"}\n', encoding="utf-8")
    staging = tmp_path / "data" / "interim" / "xccontest" / "test-run" / "parser-v2"
    staging.mkdir(parents=True)
    (staging / "normalized-flights.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )
    (staging / "parse-report.json").write_text(
        json.dumps(
            {
                "source": "xccontest",
                "run_key": "test-run",
                "parser_version": "xccontest-parser/2",
                "normalized_candidates": len(records),
                "row_observations_seen": len(records),
                "records_rejected": 0,
                "duplicate_observations_removed": 0,
                "raw_manifest_path": "data/raw/xccontest/test-run/manifest.json",
            }
        ),
        encoding="utf-8",
    )


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_accepts_only_approved_mapping_and_quarantines_unknown(tmp_path: Path) -> None:
    create_database(tmp_path)
    write_parser_output(
        tmp_path,
        [candidate("100", token="sopot-token"), candidate("101", token="unknown-token")],
    )

    validated = validate_run("test-run", database_url=database_url(), project_root=tmp_path)

    accepted = read_jsonl(validated.accepted_path)
    quarantined = read_jsonl(validated.quarantine_path)
    assert accepted[0]["source_site_mapping_id"] == 1
    assert accepted[0]["site_slug"] == "sopot"
    assert quarantined[0]["reason"] == "unknown_mapping"
    assert validated.report["records_accepted"] == 1
    assert validated.report["records_quarantined"] == 1


def test_quarantines_conflicting_approved_evidence(tmp_path: Path) -> None:
    create_database(tmp_path)
    connection = sqlite3.connect(tmp_path / "data" / "local" / "validator.db")
    connection.execute(
        """INSERT INTO source_site_mappings VALUES
           (2, 1, 2, 'normalized_name', 'sopot', 'Sopot', NULL, NULL,
            'approved', 'review', '2026-08-08T12:00:00Z', NULL)"""
    )
    connection.commit()
    connection.close()
    write_parser_output(tmp_path, [candidate("100", token="sopot-token")])

    validated = validate_run("test-run", database_url=database_url(), project_root=tmp_path)

    quarantined = read_jsonl(validated.quarantine_path)
    assert quarantined[0]["reason"] == "ambiguous_mapping"
    assert quarantined[0]["matching_mapping_ids"] == [1, 2]
