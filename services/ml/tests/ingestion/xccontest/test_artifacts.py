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
    assert manifest["artifacts"][0]["sha256"] == entry.sha256
    assert manifest["artifacts"][0]["category"] == "pg"


def test_refuses_to_overwrite_a_scope_artifact(tmp_path) -> None:
    store = RawArtifactStore(project_root=tmp_path, run_key="test-run")
    store.write_page(page())

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        store.write_page(page())
