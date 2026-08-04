from __future__ import annotations

import hashlib
import json

import pytest

from paragliding_forecasts_ml.ingestion.xccontest.artifacts import RawArtifactStore
from paragliding_forecasts_ml.ingestion.xccontest.models import PageObservation, RowObservation


def page() -> PageObservation:
    return PageObservation(
        season=2025,
        page_number=1,
        country_filter="BG",
        glider_category_filter="FAI3",
        rows=(RowObservation("123", 150.5, "BG"),),
        fragment_html='<section id="flights">synthetic test page</section>',
        has_next_page=False,
    )


def test_writes_immutable_fragment_and_manifest_with_hash(tmp_path) -> None:
    store = RawArtifactStore(project_root=tmp_path, run_key="test-run")

    entry = store.write_page(page())
    manifest_path = store.finalize_manifest(completed_seasons=(2025,))

    raw_path = tmp_path / entry.relative_path
    assert raw_path.read_text() == '<section id="flights">synthetic test page</section>'
    assert entry.sha256 == hashlib.sha256(raw_path.read_bytes()).hexdigest()

    manifest = json.loads(manifest_path.read_text())
    assert manifest["scope"] == {
        "country": "BG",
        "glider_category": "FAI3",
        "minimum_scored_distance_km": 100,
        "completed_seasons": [2025],
    }
    assert "permission_reference" not in manifest
    assert manifest["artifacts"][0]["sha256"] == entry.sha256


def test_refuses_to_overwrite_a_page_artifact(tmp_path) -> None:
    store = RawArtifactStore(project_root=tmp_path, run_key="test-run")
    store.write_page(page())

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        store.write_page(page())
