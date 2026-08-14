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
    TargetCollectionStatus,
)
from paragliding_forecasts_ml.ingestion.xccontest.versions import (
    COLLECTOR_VERSION,
    RAW_MANIFEST_SCHEMA_VERSION,
)


def page(country_code: str = "BG") -> PageObservation:
    selected_scope = FlightListScope(PRIMARY_GLIDER_CATEGORY)
    return PageObservation(
        season=2025,
        scope=selected_scope,
        country_filter=country_code,
        glider_category_filter="FAI3",
        date_filter="",
        rows=(RowObservation("123", 150.5, country_code),),
        fragment_html='<section id="flights">synthetic test page</section>',
        has_next_page=False,
    )


def target_status(country_code: str = "BG") -> TargetCollectionStatus:
    return TargetCollectionStatus(2025, country_code, "complete_primary", ())


def finalize(store: RawArtifactStore, country_codes: tuple[str, ...] = ("BG",)):
    return store.finalize_manifest(
        requested_seasons=(2025,),
        country_codes=country_codes,
        completed_seasons=(2025,),
        target_statuses=tuple(target_status(country_code) for country_code in country_codes),
        delay_seconds=30,
        acknowledge_rate_limit_risk=False,
    )


def test_writes_country_aware_immutable_fragment_and_manifest_v3(tmp_path) -> None:
    store = RawArtifactStore(project_root=tmp_path, run_key="test-run")
    entry = store.write_page(page())
    manifest_path = finalize(store)

    raw_path = tmp_path / entry.relative_path
    assert raw_path.read_text() == '<section id="flights">synthetic test page</section>'
    assert entry.sha256 == hashlib.sha256(raw_path.read_bytes()).hexdigest()
    assert (
        raw_path.name == "season-2025-country-BG-category-pg-date-all-sort-distance-descending.html"
    )

    manifest = json.loads(manifest_path.read_text())
    assert manifest["manifest_schema_version"] == RAW_MANIFEST_SCHEMA_VERSION
    assert manifest["collector_version"] == COLLECTOR_VERSION
    assert manifest["source_url"] == "https://www.xcontest.org/world/en/flights/"
    assert manifest["status"] == "complete"
    assert manifest["source_pacing"] == {
        "delay_seconds": 30,
        "recommended_delay_seconds": 30,
        "below_recommended_delay_acknowledged": False,
    }
    assert manifest["scope"] == {
        "country_codes": ["BG"],
        "country_scope_source": "all_sites",
        "requested_seasons": [2025],
        "primary_glider_category": "FAI3",
        "minimum_scored_distance_km": 100,
        "completed_seasons": [2025],
    }
    assert manifest["target_statuses"] == [
        {
            "season": 2025,
            "country_code": "BG",
            "status": "complete_primary",
            "unresolved_scopes": [],
        }
    ]
    assert "permission_reference" not in manifest
    assert manifest["artifacts"][0]["country_code"] == "BG"
    assert manifest["artifacts"][0]["row_observation_count"] == 1
    assert manifest["artifacts"][0]["qualifying_row_observation_count"] == 1


def test_country_aware_paths_prevent_scope_collisions(tmp_path) -> None:
    store = RawArtifactStore(project_root=tmp_path, run_key="test-run")

    bulgaria = store.write_page(page("BG"))
    serbia = store.write_page(page("RS"))

    assert bulgaria.relative_path != serbia.relative_path
    assert "country-BG" in bulgaria.relative_path
    assert "country-RS" in serbia.relative_path
    assert finalize(store, ("BG", "RS")).is_file()


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


def test_refuses_to_overwrite_a_country_scope_artifact(tmp_path) -> None:
    store = RawArtifactStore(project_root=tmp_path, run_key="test-run")
    store.write_page(page())

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        store.write_page(page())
