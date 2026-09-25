from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from paragliding_forecasts_ml.ingestion.xccontest import site_mapping_cli
from paragliding_forecasts_ml.ingestion.xccontest.site_mapping import (
    SiteMappingError,
    apply_mapping_decisions,
    auto_apply_coordinate_mappings,
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
            "launch_latitude_deg": 42.6902,
            "launch_longitude_deg": 24.749962,
            "launch_search_url": "https://www.xcontest.org/world/en/flights-search/?filter[point]=24.749962%2042.6902",
        }
    )
    write_parser_staging(tmp_path, [first, second])

    result = write_mapping_proposals("test-run", database_url=database_url(), project_root=tmp_path)

    proposals = [json.loads(line) for line in result["proposals_path"].read_text().splitlines()]
    assert [proposal["key_type"] for proposal in proposals] == ["source_point", "source_point"]
    assert {
        (proposal["point_latitude_deg"], proposal["point_longitude_deg"]) for proposal in proposals
    } == {(42.68733, 24.749962), (42.6902, 24.749962)}


def test_auto_applies_unique_coordinate_evidence_and_is_reusable(tmp_path: Path) -> None:
    create_database(tmp_path)
    candidate = record()
    candidate["launch_takeoff_id"] = "sopot-takeoff-id"
    candidate["launch_search_url"] = (
        "https://www.xcontest.org/world/en/hotspots?detail#filter[site]=sopot-auto-token"
    )
    write_parser_staging(tmp_path, [candidate])

    result = auto_apply_coordinate_mappings(
        "test-run", database_url=database_url(), project_root=tmp_path
    )

    assert result["automatic_decision_count"] == 3
    assert result["applied"]["inserted"] == 3
    mappings = load_mapping_catalog(database_url(), project_root=tmp_path).mappings
    assert {(mapping.key_type, mapping.status, mapping.site_id) for mapping in mappings} == {
        ("source_point", "approved", 1),
        ("source_site_token", "approved", 1),
        ("source_takeoff_id", "approved", 1),
    }
    reused = auto_apply_coordinate_mappings(
        "test-run", database_url=database_url(), project_root=tmp_path
    )
    assert reused == result


def test_outside_coordinate_is_not_proposed_or_persisted_as_a_mapping(tmp_path: Path) -> None:
    create_database(tmp_path)
    write_parser_staging(tmp_path, [record(latitude=40.0, longitude=22.0)])

    automatic = auto_apply_coordinate_mappings(
        "test-run", database_url=database_url(), project_root=tmp_path
    )
    proposals = write_mapping_proposals(
        "test-run", database_url=database_url(), project_root=tmp_path
    )

    assert automatic["automatic_decision_count"] == 0
    assert automatic["applied"]["records_seen"] == 0
    assert proposals["proposal_count"] == 0
    assert proposals["automatically_rejected_candidate_count"] == 1
    assert load_mapping_catalog(database_url(), project_root=tmp_path).mappings == ()


def test_coordinate_conflict_with_approved_token_remains_a_review_proposal(tmp_path: Path) -> None:
    create_database(tmp_path)
    apply_mapping_decisions(
        write_decisions(
            tmp_path,
            [
                {
                    "decision": "approved",
                    "key_type": "source_site_token",
                    "key_value": "known-sopot-token",
                    "site_slug": "sopot",
                    "verification_reference": "manual confirmation",
                }
            ],
        ),
        database_url=database_url(),
        project_root=tmp_path,
    )
    conflicting = record(latitude=43.56667, longitude=27.83333)
    conflicting["launch_search_url"] = (
        "https://www.xcontest.org/world/en/hotspots?detail#filter[site]=known-sopot-token"
    )
    conflicting["launch_takeoff_id"] = "conflicting-takeoff-id"
    write_parser_staging(tmp_path, [conflicting])

    result = write_mapping_proposals("test-run", database_url=database_url(), project_root=tmp_path)
    proposal = next(json.loads(line) for line in result["proposals_path"].read_text().splitlines())

    assert proposal["key_type"] == "source_takeoff_id"
    assert proposal["key_value"] == "conflicting-takeoff-id"
    assert proposal["recommendation"] == "mapping_coordinate_conflict"
    assert proposal["review_reasons"] == ["mapping_coordinate_conflict"]
    assert proposal["matching_mapping_ids"]


def test_auto_apply_cli_dispatches_without_source_access(monkeypatch, capsys) -> None:
    calls: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        site_mapping_cli,
        "auto_apply_coordinate_mappings",
        lambda run_key, *, database_url=None: (
            calls.append((run_key, database_url))
            or {"automatic_decision_count": 2, "run_key": run_key}
        ),
    )

    exit_code = site_mapping_cli.main(
        ["auto-apply", "--run-key", "test-run", "--database-url", "file:./test.db"]
    )

    assert exit_code == 0
    assert calls == [("test-run", "file:./test.db")]
    assert '"automatic_decision_count": 2' in capsys.readouterr().out
