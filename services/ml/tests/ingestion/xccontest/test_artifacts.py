from __future__ import annotations

import hashlib
import json

import pytest

from paragliding_forecasts_ml.ingestion.xccontest.artifacts import RawArtifactStore
from paragliding_forecasts_ml.ingestion.xccontest.models import (
    PRIMARY_GLIDER_CATEGORY,
    FlightListScope,
    PageObservation,
    RowObservation,
    SeasonCollectionStatus,
)


def page() -> PageObservation:
    selected_scope = FlightListScope(PRIMARY_GLIDER_CATEGORY)
    return PageObservation(
        season=2025,
        scope=selected_scope,
        country_filter="BG",
        glider_category_filter="FAI3",
        date_filter="",
        rows=(RowObservation("123", 150.5, "BG"),),
        fragment_html='<section id="flights">synthetic test page</section>',
        has_next_page=False,
    )


def test_writes_immutable_fragment_and_manifest_with_hash(tmp_path) -> None:
    store = RawArtifactStore(project_root=tmp_path, run_key="test-run")
    selected_page = page()

    entry = store.write_page(selected_page)
    manifest_path = store.finalize_manifest(
        completed_seasons=(2025,),
        season_statuses=(SeasonCollectionStatus(2025, "complete_primary", ()),),
    )

    raw_path = tmp_path / entry.relative_path
    assert raw_path.read_text() == '<section id="flights">synthetic test page</section>'
    assert entry.sha256 == hashlib.sha256(raw_path.read_bytes()).hexdigest()
    assert raw_path.name == "season-2025-category-pg-date-all-sort-distance-descending.html"

    manifest = json.loads(manifest_path.read_text())
    assert manifest["manifest_schema_version"] == 1
    assert manifest["collector_version"] == "xccontest-collector/1"
    assert manifest["source_url"] == "https://www.xcontest.org/world/en/flights/"
    assert manifest["status"] == "complete"
    assert manifest["started_at_utc"].endswith("Z")
    assert manifest["completed_at_utc"].endswith("Z")
    assert manifest["scope"] == {
        "country": "BG",
        "primary_glider_category": "FAI3",
        "minimum_scored_distance_km": 100,
        "completed_seasons": [2025],
    }
    assert manifest["season_statuses"] == [
        {"season": 2025, "status": "complete_primary", "unresolved_scopes": []}
    ]
    assert "permission_reference" not in manifest
    assert manifest["observation_counts"] == {
        "views_written": 1,
        "row_observations_seen": 1,
        "distinct_source_flights_seen": 1,
        "repeated_source_flight_observations": 0,
    }
    assert manifest["artifacts"][0]["sha256"] == entry.sha256
    assert manifest["artifacts"][0]["category"] == "pg"
    assert manifest["artifacts"][0]["row_observation_count"] == 1
    assert manifest["artifacts"][0]["qualifying_row_observation_count"] == 1


def test_counts_repeated_observations_without_dropping_raw_rows(tmp_path) -> None:
    store = RawArtifactStore(project_root=tmp_path, run_key="test-run")
    selected_page = page()
    repeated_page = PageObservation(
        season=selected_page.season,
        scope=selected_page.scope,
        country_filter=selected_page.country_filter,
        glider_category_filter=selected_page.glider_category_filter,
        date_filter=selected_page.date_filter,
        rows=(
            RowObservation("same-flight", 150.0, "BG"),
            RowObservation("same-flight", 99.9, "BG"),
        ),
        fragment_html=selected_page.fragment_html,
        has_next_page=False,
    )

    entry = store.write_page(repeated_page)

    assert entry.row_observation_count == 2
    assert entry.qualifying_row_observation_count == 1
    assert store.row_observations_seen == 2
    assert store.distinct_source_flights_seen == 1
    assert store.repeated_source_flight_observations == 1


def test_refuses_to_overwrite_a_scope_artifact(tmp_path) -> None:
    store = RawArtifactStore(project_root=tmp_path, run_key="test-run")
    store.write_page(page())

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        store.write_page(page())
