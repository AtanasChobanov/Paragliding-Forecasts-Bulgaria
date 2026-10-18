"""Targeted, provenance-preserving repair of finalized XCContest raw runs."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from selectolax.parser import HTMLParser

from .artifacts import RawArtifactStore
from .browser import BrowserCollectionError, PlaywrightFlightListDriver
from .collector import CollectionError, FlightListCollector
from .manifest import ManifestValidationError, load_manifest
from .models import (
    EXACT_GLIDER_CATEGORIES,
    PRIMARY_GLIDER_CATEGORY,
    CollectorConfig,
    source_default_scope,
)
from .selectors import DATE_SELECTOR, DISTANCE_SELECTOR, ROW_SELECTOR, TAKEOFF_CELL_SELECTOR
from .site_mapping import repository_root
from .versions import COLLECTOR_VERSION

REPAIR_SCHEMA_VERSION = 1
CATEGORY_BY_KEY = {
    category.key: category for category in (PRIMARY_GLIDER_CATEGORY, *EXACT_GLIDER_CATEGORIES)
}
DATE_PATTERN = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{2})\b")


class RepairError(RuntimeError):
    """A raw repair cannot be proven or safely continued."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _selected_date(document: HTMLParser) -> str:
    option = document.css_first(f"{DATE_SELECTOR} option[selected]")
    return option.attributes.get("value", "") if option is not None else ""


def _row_date(row: Any) -> str | None:
    cell = row.css_first(f"{TAKEOFF_CELL_SELECTOR} .full")
    match = DATE_PATTERN.search(cell.text()) if cell is not None else None
    if match is None:
        return None
    day, month, year = match.groups()
    return f"20{year}-{month}-{day}"


def _fragment_evidence(path: Path) -> tuple[str, list[str], list[str | None], int, int]:
    document = HTMLParser(path.read_text(encoding="utf-8"))
    rows = document.css(ROW_SELECTOR)
    ids: list[str] = []
    dates: list[str | None] = []
    above = 0
    for row in rows:
        ids.append(row.attributes.get("id", "").removeprefix("flight-"))
        dates.append(_row_date(row))
        distance = row.css_first(DISTANCE_SELECTOR)
        try:
            above += float(distance.text().strip().replace(",", ".")) >= 100 if distance else 0
        except ValueError:
            pass
    return _selected_date(document), ids, dates, len(rows), above


def audit_run(run_key: str, *, project_root: Path | None = None) -> dict[str, Any]:
    """Verify hashes and classify every wrong-date/count/ID artifact without writes."""

    root = (project_root or repository_root()).resolve()
    try:
        manifest_path, manifest, artifacts, _ = load_manifest(run_key, root)
    except ManifestValidationError as error:
        raise RepairError(str(error)) from error
    if manifest.get("manifest_schema_version") != 5 or manifest.get("status") != "complete":
        raise RepairError("Targeted repair requires a finalized, complete manifest-v5 run.")
    issues: list[dict[str, Any]] = []
    for artifact in artifacts:
        selected, ids, dates, count, above = _fragment_evidence(root / artifact["path"])
        expected = artifact.get("date_filter") or ""
        reasons: list[str] = []
        if expected and selected != expected:
            reasons.append("serialized_date_mismatch")
        if ids != artifact["source_flight_ids"]:
            reasons.append("source_flight_ids_mismatch")
        if count != artifact["row_observation_count"]:
            reasons.append("row_count_mismatch")
        if above != artifact["at_or_above_100km_row_observation_count"]:
            reasons.append("threshold_count_mismatch")
        if expected and any(date != expected for date in dates):
            reasons.append("flight_date_mismatch")
        if reasons:
            issues.append(
                {
                    "path": artifact["path"],
                    "season": artifact["season"],
                    "country_code": artifact["country_code"],
                    "acquisition_purpose": artifact["acquisition_purpose"],
                    "category": artifact["category"],
                    "date_filter": artifact["date_filter"],
                    "sort_mode": artifact["sort_mode"],
                    "serialized_date": selected,
                    "row_count": count,
                    "manifest_row_count": artifact["row_observation_count"],
                    "reasons": reasons,
                }
            )
    return {
        "repair_schema_version": REPAIR_SCHEMA_VERSION,
        "source_run_key": run_key,
        "source_manifest_sha256": _sha256(manifest_path),
        "artifact_count": len(artifacts),
        "repair_view_count": len(issues),
        "issues": issues,
    }


def _repair_reference_path(root: Path, run_key: str) -> Path:
    return root / "data" / "interim" / "xccontest" / run_key / "repair-source.json"


def _write_json_new(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, ensure_ascii=False, indent=2, sort_keys=True)
        output.write("\n")


def _verified_repair_page(page: Any, expected_date: str, expected_country: str) -> None:
    document = HTMLParser(page.fragment_html)
    selected = _selected_date(document)
    rows = document.css(ROW_SELECTOR)
    ids = [row.attributes.get("id", "").removeprefix("flight-") for row in rows]
    if selected != expected_date:
        raise RepairError(f"Rendered HTML still selects {selected!r}, expected {expected_date}.")
    if ids != [row.source_flight_id for row in page.rows]:
        raise RepairError("Rendered HTML and browser row observations disagree.")
    if any(_row_date(row) != expected_date for row in rows):
        raise RepairError("Rendered flight date does not match the requested repair date.")
    if any(row.launch_country_code != expected_country for row in page.rows):
        raise RepairError("Rendered flight country does not match the requested country.")
    if page.has_next_page:
        raise RepairError("Repaired first page is paginated; coverage needs category/sort review.")


def _entry_metadata(entry: Any) -> dict[str, Any]:
    return {
        "path": entry.relative_path,
        "sha256": entry.sha256,
        "season": entry.season,
        "country_code": entry.country_code,
        "acquisition_purpose": entry.acquisition_purpose,
        "category": entry.category,
        "date_filter": entry.date_filter,
        "sort_mode": entry.sort_mode,
        "sort_key": entry.sort_key,
        "sort_direction": entry.sort_direction,
        "retrieved_at_utc": entry.retrieved_at_utc.isoformat().replace("+00:00", "Z"),
        "first_flight_id": entry.first_flight_id,
        "last_flight_id": entry.last_flight_id,
        "first_distance_km": entry.first_distance_km,
        "last_distance_km": entry.last_distance_km,
        "has_next_page": entry.has_next_page,
        "source_flight_ids": list(entry.source_flight_ids),
        "row_observation_count": entry.row_observation_count,
        "below_100km_row_observation_count": entry.below_threshold_row_observation_count,
        "at_or_above_100km_row_observation_count": entry.qualifying_row_observation_count,
    }


def _copy_verified(source: Path, destination: Path, expected_sha: str) -> None:
    if destination.exists():
        if _sha256(destination) != expected_sha:
            raise RepairError(
                f"Existing copied artifact is not the verified original: {destination}"
            )
        return
    with source.open("rb") as input_file, destination.open("xb") as output_file:
        shutil.copyfileobj(input_file, output_file)
    if _sha256(destination) != expected_sha:
        raise RepairError(f"Copied artifact SHA-256 differs from its source: {destination}")


def _refresh_activity_statuses(
    manifest: dict[str, Any], repaired_scopes: set[tuple[Any, ...]]
) -> None:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for artifact in manifest["artifacts"]:
        if artifact["acquisition_purpose"] == "all_distance_activity":
            key = (
                artifact["season"],
                artifact["country_code"],
                artifact["category"],
                artifact["date_filter"],
            )
            grouped[key].append(artifact)
    for status in manifest["activity_scope_statuses"]:
        key = (status["season"], status["country_code"], status["category"], status["date_filter"])
        if key not in repaired_scopes:
            continue
        entries = grouped[key]
        ids = [source_id for entry in entries for source_id in entry["source_flight_ids"]]
        descending = next(
            (
                entry
                for entry in entries
                if entry["sort_mode"] == "explicit"
                and entry["sort_key"] == "distance"
                and entry["sort_direction"] == "descending"
            ),
            None,
        )
        if not ids:
            state, reason = "empty", None
        elif descending is not None and descending["has_next_page"]:
            state, reason = "partial_saturated", "distance_descending_has_next_page"
        elif descending is None and any(
            entry["sort_mode"] == "source_default" and entry["has_next_page"] for entry in entries
        ):
            state, reason = "partial_saturated", "source_default_has_next_page"
        else:
            state, reason = "complete", None
        status.update(
            row_observations_seen=sum(entry["row_observation_count"] for entry in entries),
            distinct_source_flights_seen=len(set(ids)),
            duplicate_observations=len(ids) - len(set(ids)),
            distance_descending_has_next_page=descending["has_next_page"] if descending else None,
            status=state,
            reason=reason,
        )


def _finalize(
    root: Path, source_key: str, store: RawArtifactStore, audit: dict[str, Any]
) -> dict[str, Any]:
    source_path, source_manifest, _, source_contract = load_manifest(source_key, root)
    if _sha256(source_path) != audit["source_manifest_sha256"]:
        raise RepairError("Source manifest changed after repair planning.")
    if len(store.entries) != audit["repair_view_count"]:
        raise RepairError("Not all planned repair views have been collected.")
    replacement = {entry.relative_path.rsplit("/", 1)[-1]: entry for entry in store.entries}
    problem_names = {issue["path"].rsplit("/", 1)[-1] for issue in audit["issues"]}
    if set(replacement) != problem_names:
        raise RepairError("Collected repair views do not cover the audit plan exactly.")
    manifest = json.loads(json.dumps(source_manifest))
    manifest["run_key"] = store.run_key
    manifest["collector_version"] = COLLECTOR_VERSION
    manifest["started_at_utc"] = store.started_at_utc.isoformat().replace("+00:00", "Z")
    manifest["completed_at_utc"] = (
        datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    lineage: list[dict[str, str]] = []
    repaired_artifacts: list[dict[str, Any]] = []
    for original in source_manifest["artifacts"]:
        name = original["path"].rsplit("/", 1)[-1]
        if name in replacement:
            updated = _entry_metadata(replacement[name])
            lineage.append(
                {
                    "source_path": original["path"],
                    "source_sha256": original["sha256"],
                    "repair_path": updated["path"],
                    "repair_sha256": updated["sha256"],
                }
            )
        else:
            destination = store.raw_dir / name
            _copy_verified(root / original["path"], destination, original["sha256"])
            updated = {**original, "path": destination.relative_to(root).as_posix()}
        repaired_artifacts.append(updated)
    manifest["artifacts"] = repaired_artifacts
    ids = [
        source_id for artifact in repaired_artifacts for source_id in artifact["source_flight_ids"]
    ]
    counts = manifest["observation_counts"]
    counts.update(
        views_written=len(repaired_artifacts),
        row_observations_seen=len(ids),
        distinct_source_flights_seen=len(set(ids)),
        repeated_source_flight_observations=len(ids) - len(set(ids)),
        below_100km_row_observations=sum(
            a["below_100km_row_observation_count"] for a in repaired_artifacts
        ),
        at_or_above_100km_row_observations=sum(
            a["at_or_above_100km_row_observation_count"] for a in repaired_artifacts
        ),
    )
    repaired_scopes = {
        (issue["season"], issue["country_code"], issue["category"], issue["date_filter"])
        for issue in audit["issues"]
        if issue["acquisition_purpose"] == "all_distance_activity"
    }
    _refresh_activity_statuses(manifest, repaired_scopes)
    # Validate all copied and newly collected rows before publishing the immutable manifest.
    preflight_contract = replace(source_contract, expected_observation_counts=counts)
    try:
        for artifact in repaired_artifacts:
            rows = HTMLParser((root / artifact["path"]).read_text(encoding="utf-8")).css(
                ROW_SELECTOR
            )
            preflight_contract.verify_artifact_rows(artifact, rows)
        preflight_contract.verify_run_rows(ids)
    except ManifestValidationError as error:
        raise RepairError(f"Repair artifact preflight failed: {error}") from error
    manifest_path = store.raw_dir / "manifest.json"
    _write_json_new(manifest_path, manifest)
    try:
        _, _, artifacts, contract = load_manifest(store.run_key, root)
        for artifact in artifacts:
            rows = HTMLParser((root / artifact["path"]).read_text(encoding="utf-8")).css(
                ROW_SELECTOR
            )
            contract.verify_artifact_rows(artifact, rows)
        contract.verify_run_rows(ids)
    except (ManifestValidationError, ValueError) as error:
        raise RepairError(f"Final repair manifest did not verify: {error}") from error
    provenance = {
        "repair_schema_version": REPAIR_SCHEMA_VERSION,
        "source_run_key": source_key,
        "source_manifest_sha256": audit["source_manifest_sha256"],
        "repair_run_key": store.run_key,
        "repair_manifest_sha256": _sha256(manifest_path),
        "copied_view_count": len(repaired_artifacts) - len(lineage),
        "recollected_view_count": len(lineage),
        "replacements": lineage,
    }
    _write_json_new(store.raw_dir / "repair-provenance.json", provenance)
    return {
        "status": "complete",
        "repair_run_key": store.run_key,
        "manifest_path": manifest_path.relative_to(root).as_posix(),
        "manifest_sha256": provenance["repair_manifest_sha256"],
        "recollected_view_count": len(lineage),
        "copied_view_count": provenance["copied_view_count"],
    }


def collect_repair(
    source_run_key: str | None = None,
    *,
    repair_run_key: str | None = None,
    config: CollectorConfig | None = None,
    project_root: Path | None = None,
    driver_factory: Callable[..., Any] = PlaywrightFlightListDriver,
    on_run_ready: Callable[[str], None] | None = None,
    on_view_completed: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Collect only audited views; resume from hash-verified local progress."""

    root = (project_root or repository_root()).resolve()
    if repair_run_key is None:
        if source_run_key is None or config is None:
            raise RepairError("New repair requires source run key and collector configuration.")
        audit = audit_run(source_run_key, project_root=root)
        if not audit["issues"]:
            raise RepairError("Source run has no repairable inconsistent views.")
        if audit["repair_view_count"] > config.max_views:
            raise RepairError("Repair view count exceeds --max-views.")
        if set(config.seasons) != {issue["season"] for issue in audit["issues"]} or set(
            config.country_codes
        ) != {issue["country_code"] for issue in audit["issues"]}:
            raise RepairError("Repair configuration must match the audited seasons and countries.")
        if any(
            issue["date_filter"] is None
            or issue["category"] not in CATEGORY_BY_KEY
            or issue["sort_mode"] != "source_default"
            for issue in audit["issues"]
        ):
            raise RepairError("This repair command accepts only dated source-default views.")
        store = RawArtifactStore(project_root=root)
        store.set_collection_context(config)
        _write_json_new(_repair_reference_path(root, store.run_key), audit)
        first = audit["issues"][0]
        first_scope = source_default_scope(
            CATEGORY_BY_KEY[first["category"]], date_filter=first["date_filter"]
        )
        store.write_checkpoint(
            season=first["season"],
            country_code=first["country_code"],
            status="in_progress",
            scope=first_scope,
            acquisition_purpose=first["acquisition_purpose"],
        )
    else:
        try:
            store = RawArtifactStore.resume(repair_run_key, project_root=root)
            audit = json.loads(
                _repair_reference_path(root, repair_run_key).read_text(encoding="utf-8")
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise RepairError(f"Repair checkpoint is not reusable: {error}") from error
        source_run_key = audit["source_run_key"]
        context = store.collection_context
        config = CollectorConfig(
            seasons=tuple(context["seasons"]),
            country_codes=tuple(context["country_codes"]),
            headed=bool(context["headed"]),
            slow_mo_ms=int(context["slow_mo_ms"]),
            timeout_seconds=int(context["timeout_seconds"]),
            max_views=int(context["max_views"]),
            delay_seconds=float(context["delay_seconds"]),
            acknowledge_rate_limit_risk=bool(context["acknowledge_rate_limit_risk"]),
        )
        if audit_run(source_run_key, project_root=root) != audit:
            raise RepairError(
                "Source evidence or the repair plan changed since checkpoint creation."
            )
    assert source_run_key is not None and config is not None
    if on_run_ready is not None:
        on_run_ready(store.run_key)
    try:
        last_season: int | None = None
        last_country: str | None = None
        with driver_factory(config, sleeper=time.sleep) as driver:
            for issue in audit["issues"]:
                season, country = issue["season"], issue["country_code"]
                category = CATEGORY_BY_KEY[issue["category"]]
                scope = source_default_scope(category, date_filter=issue["date_filter"])
                if (
                    store.recovered_page(
                        season=season,
                        country_code=country,
                        scope=scope,
                        acquisition_purpose=issue["acquisition_purpose"],
                    )
                    is not None
                ):
                    continue
                if store.view_count >= config.max_views:
                    raise RepairError("Repair reached its configured view cap.")
                if season != last_season:
                    driver.prepare_season(season)
                    last_season, last_country = season, None
                if country != last_country:
                    driver.select_country(country)
                    last_country = country
                driver.select_scope(scope)
                page = driver.read_page(season, scope)
                FlightListCollector._validate_page(
                    page,
                    expected_season=season,
                    expected_country_code=country,
                    expected_scope=scope,
                    require_rows=False,
                )
                _verified_repair_page(page, issue["date_filter"], country)
                store.write_page(page, acquisition_purpose=issue["acquisition_purpose"])
                store.write_checkpoint(
                    season=season,
                    country_code=country,
                    status="in_progress",
                    scope=scope,
                    acquisition_purpose=issue["acquisition_purpose"],
                )
                if on_view_completed is not None:
                    on_view_completed(store.view_count, audit["repair_view_count"], issue["path"])
    except (
        BrowserCollectionError,
        CollectionError,
        RepairError,
        PlaywrightError,
        ValueError,
        OSError,
        KeyboardInterrupt,
    ) as error:
        raise RepairError(
            f"Repair run {store.run_key} stopped after {store.view_count} views: {error}"
        ) from error
    return _finalize(root, source_run_key, store, audit)
