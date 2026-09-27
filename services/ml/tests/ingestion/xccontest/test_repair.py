from __future__ import annotations

import hashlib
import json
from typing import ClassVar

import pytest

from paragliding_forecasts_ml.ingestion.xccontest.artifacts import RawArtifactStore
from paragliding_forecasts_ml.ingestion.xccontest.manifest import load_manifest
from paragliding_forecasts_ml.ingestion.xccontest.models import (
    PRIMARY_GLIDER_CATEGORY,
    CollectorConfig,
    PageObservation,
    RowObservation,
    TargetCollectionStatus,
    source_default_scope,
)
from paragliding_forecasts_ml.ingestion.xccontest.repair import (
    RepairError,
    _verified_repair_page,
    audit_run,
    collect_repair,
)


def fragment(date: str, *, row_date: str) -> str:
    return (
        '<div id="flights"><select name="filter[date]">'
        f'<option value="{date}" selected>{date}</option></select>'
        '<table class="XClist"><tbody><tr id="flight-123">'
        f'<td></td><td><span class="full">{row_date}</span></td>'
        '<td class="km"><strong>55.0</strong></td>'
        "</tr></tbody></table></div>"
    )


def observation(date: str, *, html_date: str, row_date: str) -> PageObservation:
    return PageObservation(
        season=2025,
        scope=source_default_scope(PRIMARY_GLIDER_CATEGORY, date_filter=date),
        country_filter="BG",
        glider_category_filter="FAI3",
        date_filter=date,
        rows=(RowObservation("123", 55.0, "BG"),),
        fragment_html=fragment(html_date, row_date=row_date),
        has_next_page=False,
    )


def source_run(tmp_path, *, second_bad: bool = False):
    store = RawArtifactStore(project_root=tmp_path, run_key="source")
    good = observation("2025-05-13", html_date="2025-05-13", row_date="13.05.25")
    bad = observation("2025-05-14", html_date="2025-05-13", row_date="13.05.25")
    good_entry = store.write_page(good, acquisition_purpose="all_distance_activity")
    bad_entry = store.write_page(bad, acquisition_purpose="all_distance_activity")
    if second_bad:
        another_bad = observation("2025-05-15", html_date="2025-05-14", row_date="14.05.25")
        store.write_page(another_bad, acquisition_purpose="all_distance_activity")
    store.finalize_manifest(
        requested_seasons=(2025,),
        country_codes=("BG",),
        completed_seasons=(2025,),
        target_statuses=(TargetCollectionStatus(2025, "BG", "complete_primary", ()),),
        delay_seconds=30,
        acknowledge_rate_limit_risk=False,
    )
    return good_entry, bad_entry


class Driver:
    calls: ClassVar[list[str]] = []

    def __init__(self, config, *, sleeper):
        self.config = config

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def prepare_season(self, season):
        self.calls.append(f"season:{season}")

    def select_country(self, country):
        self.calls.append(f"country:{country}")

    def select_scope(self, scope):
        self.calls.append(f"date:{scope.date_filter}")

    def read_page(self, season, scope):
        date = scope.date_filter
        return observation(date, html_date=date, row_date=f"{date[8:10]}.{date[5:7]}.{date[2:4]}")


def test_audit_and_repair_preserve_source_and_copy_good_artifact(tmp_path):
    good, bad = source_run(tmp_path)
    original_good = (tmp_path / good.relative_path).read_bytes()
    original_bad = (tmp_path / bad.relative_path).read_bytes()
    audit = audit_run("source", project_root=tmp_path)
    assert audit["repair_view_count"] == 1
    assert audit["issues"][0]["date_filter"] == "2025-05-14"
    assert set(audit["issues"][0]["reasons"]) == {
        "serialized_date_mismatch",
        "flight_date_mismatch",
    }
    Driver.calls = []
    result = collect_repair(
        "source",
        config=CollectorConfig(seasons=(2025,), country_codes=("BG",)),
        project_root=tmp_path,
        driver_factory=Driver,
    )
    assert result["recollected_view_count"] == 1
    assert result["copied_view_count"] == 1
    assert Driver.calls == ["season:2025", "country:BG", "date:2025-05-14"]
    assert (tmp_path / good.relative_path).read_bytes() == original_good
    assert (tmp_path / bad.relative_path).read_bytes() == original_bad
    _, manifest, artifacts, contract = load_manifest(result["repair_run_key"], tmp_path)
    assert manifest["observation_counts"]["views_written"] == 2
    assert len(artifacts) == 2
    assert (tmp_path / artifacts[0]["path"]).read_bytes() == original_good
    assert contract.verify_run_rows(["123", "123"]) is None
    provenance = json.loads(
        (
            tmp_path / "data/raw/xccontest" / result["repair_run_key"] / "repair-provenance.json"
        ).read_text()
    )
    assert provenance["source_run_key"] == "source"
    assert (
        provenance["repair_manifest_sha256"]
        == hashlib.sha256((tmp_path / result["manifest_path"]).read_bytes()).hexdigest()
    )


def test_repair_rejects_stale_browser_page(tmp_path):
    source_run(tmp_path)

    class StaleDriver(Driver):
        def read_page(self, season, scope):
            return observation(scope.date_filter, html_date="2025-05-13", row_date="13.05.25")

    with pytest.raises(RepairError, match="Repair run .* stopped after 0 views") as failure:
        collect_repair(
            "source",
            config=CollectorConfig(seasons=(2025,), country_codes=("BG",)),
            project_root=tmp_path,
            driver_factory=StaleDriver,
        )
    repair_key = str(failure.value).split()[2]
    checkpoint = tmp_path / "data/interim/xccontest" / repair_key / "checkpoint.json"
    assert checkpoint.exists()
    Driver.calls = []
    result = collect_repair(
        repair_run_key=repair_key,
        project_root=tmp_path,
        driver_factory=Driver,
    )
    assert result["status"] == "complete"
    assert Driver.calls == ["season:2025", "country:BG", "date:2025-05-14"]


def test_repair_page_rejects_unexpected_pagination():
    page = observation("2025-05-14", html_date="2025-05-14", row_date="14.05.25")
    from dataclasses import replace

    with pytest.raises(RepairError, match="paginated"):
        _verified_repair_page(replace(page, has_next_page=True), "2025-05-14", "BG")


def test_resume_skips_already_checkpointed_repair_views(tmp_path):
    source_run(tmp_path, second_bad=True)

    class InterruptOnSecondView(Driver):
        def read_page(self, season, scope):
            if scope.date_filter == "2025-05-15":
                raise RepairError("synthetic interruption")
            return super().read_page(season, scope)

    with pytest.raises(RepairError, match="stopped after 1 views") as failure:
        collect_repair(
            "source",
            config=CollectorConfig(seasons=(2025,), country_codes=("BG",)),
            project_root=tmp_path,
            driver_factory=InterruptOnSecondView,
        )
    repair_key = str(failure.value).split()[2]
    Driver.calls = []
    result = collect_repair(repair_run_key=repair_key, project_root=tmp_path, driver_factory=Driver)
    assert result["recollected_view_count"] == 2
    assert Driver.calls == ["season:2025", "country:BG", "date:2025-05-15"]
