from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from paragliding_forecasts_ml.ingestion.xccontest.persistence import (
    PersistenceError,
    validate_record,
)
from paragliding_forecasts_ml.ingestion.xccontest.site_mapping import auto_apply_coordinate_mappings
from paragliding_forecasts_ml.ingestion.xccontest.validator import validate_run
from paragliding_forecasts_ml.ingestion.xccontest.versions import (
    PARSER_OUTPUT_DIRECTORY,
    PARSER_VERSION,
    VALIDATION_VERSION,
)


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
          catchment_radius_km REAL,
          is_active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE source_site_mappings (
          id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL, site_id INTEGER NOT NULL,
          key_type TEXT NOT NULL, key_value TEXT, source_display_name TEXT,
          point_latitude_deg REAL, point_longitude_deg REAL, status TEXT NOT NULL,
          verification_reference TEXT, verified_at_utc TEXT, notes TEXT
        );
        CREATE TABLE source_site_exclusions (
          id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL, key_type TEXT NOT NULL,
          key_value TEXT NOT NULL, origin_run_key TEXT NOT NULL, origin_proposal_id TEXT NOT NULL,
          notes TEXT, status TEXT NOT NULL, created_at_utc TEXT NOT NULL,
          retired_at_utc TEXT, retirement_reason TEXT
        );
        INSERT INTO flight_sources VALUES (1, 'xccontest');
        INSERT INTO sites (id, slug, name, country_code_iso2, site_type, latitude_deg, longitude_deg, catchment_radius_km) VALUES
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
        "scored_distance_km": 78.5,
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
    staging = tmp_path / "data" / "interim" / "xccontest" / "test-run" / PARSER_OUTPUT_DIRECTORY
    staging.mkdir(parents=True)
    (staging / "normalized-flights.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )
    (staging / "parse-report.json").write_text(
        json.dumps(
            {
                "source": "xccontest",
                "run_key": "test-run",
                "parser_version": PARSER_VERSION,
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


@pytest.mark.parametrize("distance", [0, 78.5, 100, 2_000])
def test_persistence_accepts_the_full_storage_distance_domain(distance: float) -> None:
    record = {
        "source": "xccontest",
        "validation_status": "accepted",
        "validator_version": VALIDATION_VERSION,
        "source_flight_id": "100",
        "source_flight_url": "https://www.xcontest.org/world/en/flights/detail:pilot/1",
        "source_site_mapping_id": 1,
        "site_id": 1,
        "mapping_key_type": "source_site_token",
        "scored_distance_km": distance,
        "duration_seconds": 3600,
        "route_type": "free_flight",
        "takeoff_at_utc": "2026-08-01T12:00:00Z",
        "validated_at_utc": "2026-08-08T12:00:00Z",
    }

    validate_record(record)


@pytest.mark.parametrize("distance", [-0.01, 2_000.01, float("nan")])
def test_persistence_rejects_distances_outside_the_storage_domain(distance: float) -> None:
    record = {
        "source": "xccontest",
        "validation_status": "accepted",
        "validator_version": VALIDATION_VERSION,
        "source_flight_id": "100",
        "source_flight_url": "https://www.xcontest.org/world/en/flights/detail:pilot/1",
        "source_site_mapping_id": 1,
        "site_id": 1,
        "mapping_key_type": "source_site_token",
        "scored_distance_km": distance,
        "duration_seconds": 3600,
        "route_type": "free_flight",
        "takeoff_at_utc": "2026-08-01T12:00:00Z",
        "validated_at_utc": "2026-08-08T12:00:00Z",
    }

    with pytest.raises(PersistenceError, match="invalid distance"):
        validate_record(record)


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
    assert validated.report["accepted_flights_path"].endswith("accepted-flights.jsonl")
    assert len(validated.report["accepted_flights_sha256"]) == 64
    assert validated.report["site_quarantine_path"].endswith("site-quarantine.jsonl")
    assert len(validated.report["site_quarantine_sha256"]) == 64


def test_quarantines_invalid_distance_before_mapping_resolution(tmp_path: Path) -> None:
    create_database(tmp_path)
    invalid = candidate("100", token="sopot-token")
    invalid["scored_distance_km"] = -0.1
    write_parser_output(tmp_path, [invalid])

    validated = validate_run("test-run", database_url=database_url(), project_root=tmp_path)

    quarantined = read_jsonl(validated.quarantine_path)
    assert quarantined[0]["reason"] == "invalid_scored_distance"


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


def test_auto_mapped_unique_coordinate_is_accepted_without_manual_review(tmp_path: Path) -> None:
    create_database(tmp_path)
    record = candidate("100", token="auto-sopot-token")
    record["launch_takeoff_id"] = "auto-sopot-takeoff"
    write_parser_output(tmp_path, [record])

    automatic = auto_apply_coordinate_mappings(
        "test-run", database_url=database_url(), project_root=tmp_path
    )
    validated = validate_run("test-run", database_url=database_url(), project_root=tmp_path)

    accepted = read_jsonl(validated.accepted_path)
    assert automatic["automatic_decision_count"] == 3
    assert accepted[0]["site_slug"] == "sopot"
    assert accepted[0]["mapping_key_type"] == "source_takeoff_id"


def test_auto_rejects_outside_coordinate_without_mapping_review(tmp_path: Path) -> None:
    create_database(tmp_path)
    outside = candidate("100", token="unknown-token")
    outside["launch_latitude_deg"] = 40.0
    outside["launch_longitude_deg"] = 22.0
    write_parser_output(tmp_path, [outside])

    validated = validate_run("test-run", database_url=database_url(), project_root=tmp_path)

    quarantined = read_jsonl(validated.quarantine_path)
    assert quarantined[0]["reason"] == "outside_configured_catchments"
    assert quarantined[0]["mapping_disposition"] == "auto_rejected"
    assert validated.report["records_auto_rejected"] == 1


def test_quarantines_known_mapping_with_conflicting_coordinate(tmp_path: Path) -> None:
    create_database(tmp_path)
    conflicting = candidate("100", token="sopot-token")
    conflicting["launch_latitude_deg"] = 42.7302
    conflicting["launch_longitude_deg"] = 24.0923
    write_parser_output(tmp_path, [conflicting])

    validated = validate_run("test-run", database_url=database_url(), project_root=tmp_path)

    quarantined = read_jsonl(validated.quarantine_path)
    assert quarantined[0]["reason"] == "mapping_coordinate_conflict"
    assert quarantined[0]["mapping_disposition"] == "review_required"


def test_persisted_exclusion_is_nonblocking_but_fresh_coordinate_conflicts(tmp_path: Path) -> None:
    create_database(tmp_path)
    connection = sqlite3.connect(tmp_path / "data" / "local" / "validator.db")
    connection.execute(
        "INSERT INTO source_site_exclusions VALUES (1, 1, 'source_site_token', 'excluded-token', 'review-run', 'proposal', NULL, 'active', '2026-09-26T12:00:00Z', NULL, NULL)"
    )
    connection.commit()
    connection.close()
    excluded = candidate("100", token="excluded-token")
    excluded.pop("launch_latitude_deg")
    excluded.pop("launch_longitude_deg")
    write_parser_output(tmp_path, [excluded])

    validated = validate_run("test-run", database_url=database_url(), project_root=tmp_path)
    quarantined = read_jsonl(validated.quarantine_path)
    assert quarantined[0]["reason"] == "known_source_site_exclusion"
    assert quarantined[0]["mapping_disposition"] == "persisted_rejection"
    assert quarantined[0]["source_site_exclusion_id"] == 1
    assert validated.report["records_persisted_exclusions"] == 1
