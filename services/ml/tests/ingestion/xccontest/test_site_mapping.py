from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from paragliding_forecasts_ml.ingestion.xccontest.site_mapping import (
    SiteMappingError,
    apply_mapping_decisions,
    catchment_suggestions,
    load_mapping_catalog,
    source_site_token,
    write_mapping_proposals,
)


def database_url() -> str:
    return "file:./data/local/site-mapping.db"


def create_database(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "local" / "site-mapping.db"
    database_path.parent.mkdir(parents=True)
    connection = sqlite3.connect(database_path)
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
        INSERT INTO flight_sources (id, code) VALUES (1, 'xccontest');
        INSERT INTO sites VALUES
          (1, 'sopot', 'Sopot', 'BG', 'launch_area', 42.68733, 24.749962, 5),
          (2, 'dobrich-region', 'Dobrich region', 'BG', 'region', 43.56667, 27.83333, 30),
          (3, 'outside', 'Outside', 'BG', 'launch_area', 41, 22, NULL);
        """
    )
    connection.commit()
    connection.close()


def record(*, flight_id: str = "100", latitude: float = 42.68733, longitude: float = 24.749962):
    return {
        "source": "xccontest",
        "source_flight_id": flight_id,
        "parser_status": "normalized",
        "launch_name_raw": "Sopot",
        "launch_country_code_iso2": "BG",
        "launch_latitude_deg": latitude,
        "launch_longitude_deg": longitude,
        "launch_search_url": "https://www.xcontest.org/world/en/hotspots?detail#filter[site]=MjQ4.token",
        "artifact_references": [{"season": 2026}],
    }


def write_parser_staging(tmp_path: Path, records: list[dict]) -> None:
    output = tmp_path / "data" / "interim" / "xccontest" / "test-run" / "parser-v2"
    output.mkdir(parents=True)
    (output / "normalized-flights.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in records), encoding="utf-8"
    )
    (output / "parse-report.json").write_text(
        json.dumps(
            {
                "source": "xccontest",
                "run_key": "test-run",
                "normalized_candidates": len(records),
            }
        ),
        encoding="utf-8",
    )


def write_decisions(tmp_path: Path, decisions: list[dict]) -> Path:
    path = tmp_path / "decisions.jsonl"
    path.write_text("".join(json.dumps(item) + "\n" for item in decisions), encoding="utf-8")
    return path


def test_extracts_current_fragment_token_and_uses_any_site_radius(tmp_path: Path) -> None:
    create_database(tmp_path)
    assert source_site_token(record()["launch_search_url"]) == "MjQ4.token"

    catalog = load_mapping_catalog(database_url(), project_root=tmp_path)
    suggestions = catchment_suggestions(record(), catalog.sites)

    assert suggestions == [
        {
            "site_id": 1,
            "site_slug": "sopot",
            "distance_km": 0.0,
            "catchment_radius_km": 5.0,
            "reason": "inside_configured_catchment",
        }
    ]


def test_writes_grouped_coordinate_proposals_without_database_writes(tmp_path: Path) -> None:
    create_database(tmp_path)
    write_parser_staging(tmp_path, [record(flight_id="100"), record(flight_id="101")])

    result = write_mapping_proposals("test-run", database_url=database_url(), project_root=tmp_path)

    proposals = [json.loads(line) for line in result["proposals_path"].read_text().splitlines()]
    assert len(proposals) == 1
    assert proposals[0]["candidate_count"] == 2
    assert proposals[0]["recommendation"] == "inside_unique_catchment"
    assert proposals[0]["catchment_suggestions"][0]["site_slug"] == "sopot"
    assert load_mapping_catalog(database_url(), project_root=tmp_path).mappings == ()


def test_apply_requires_review_evidence_and_promotes_provisional(tmp_path: Path) -> None:
    create_database(tmp_path)
    provisional = {
        "decision": "provisional",
        "key_type": "source_site_token",
        "key_value": "MjQ4.token",
        "source_display_name": "Sopot",
        "site_slug": "sopot",
    }
    result = apply_mapping_decisions(
        write_decisions(tmp_path, [provisional]), database_url=database_url(), project_root=tmp_path
    )
    assert result["inserted"] == 1

    approved = {
        **provisional,
        "decision": "approved",
        "verification_reference": "manual review test-run flight 100",
        "verified_at_utc": "2026-08-08T12:00:00Z",
    }
    result = apply_mapping_decisions(
        write_decisions(tmp_path, [approved]), database_url=database_url(), project_root=tmp_path
    )
    assert result["promoted"] == 1
    mapping = load_mapping_catalog(database_url(), project_root=tmp_path).mappings[0]
    assert mapping.status == "approved"
    assert mapping.verification_reference == "manual review test-run flight 100"


def test_apply_rolls_back_conflicting_active_mapping(tmp_path: Path) -> None:
    create_database(tmp_path)
    decisions = [
        {
            "decision": "approved",
            "key_type": "source_site_token",
            "key_value": "shared",
            "site_slug": "sopot",
            "verification_reference": "review one",
        },
        {
            "decision": "approved",
            "key_type": "source_site_token",
            "key_value": "shared",
            "site_slug": "dobrich-region",
            "verification_reference": "review two",
        },
    ]

    with pytest.raises(SiteMappingError, match="different site"):
        apply_mapping_decisions(
            write_decisions(tmp_path, decisions), database_url=database_url(), project_root=tmp_path
        )

    assert load_mapping_catalog(database_url(), project_root=tmp_path).mappings == ()


def test_groups_generic_names_by_distinct_source_points(tmp_path: Path) -> None:
    create_database(tmp_path)
    first = record(flight_id="100")
    first.update(
        {
            "launch_name_raw": "?",
            "launch_latitude_deg": 42.68733,
            "launch_longitude_deg": 24.749962,
            "launch_search_url": "https://www.xcontest.org/world/en/flights-search/?filter[point]=24.749962%2042.68733",
        }
    )
    second = record(flight_id="101")
    second.update(
        {
            "launch_name_raw": "?",
            "launch_latitude_deg": 42.7302,
            "launch_longitude_deg": 24.0923,
            "launch_search_url": "https://www.xcontest.org/world/en/flights-search/?filter[point]=24.0923%2042.7302",
        }
    )
    write_parser_staging(tmp_path, [first, second])

    result = write_mapping_proposals("test-run", database_url=database_url(), project_root=tmp_path)

    proposals = [json.loads(line) for line in result["proposals_path"].read_text().splitlines()]
    assert [proposal["key_type"] for proposal in proposals] == ["source_point", "source_point"]
    assert {
        (proposal["point_latitude_deg"], proposal["point_longitude_deg"]) for proposal in proposals
    } == {(42.68733, 24.749962), (42.7302, 24.0923)}
