"""Read-only SQLite/raw/stage verification and immutable label-audit publication."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from selectolax.parser import HTMLParser

from paragliding_forecasts_ml.ingestion.xccontest.manifest import load_manifest
from paragliding_forecasts_ml.ingestion.xccontest.models import is_supported_activity_date
from paragliding_forecasts_ml.ingestion.xccontest.persistence import digest, local_path
from paragliding_forecasts_ml.ingestion.xccontest.pipeline import _actionable_quarantines
from paragliding_forecasts_ml.ingestion.xccontest.selectors import DISTANCE_SELECTOR, ROW_SELECTOR
from paragliding_forecasts_ml.storage.sqlite import (
    configured_database_url,
    open_read_only_database,
    repository_root,
    resolve_database_path,
)

from .flight_labels import (
    MATURE_RUNS,
    MATURITY_POLICY,
    POLICY,
    THRESHOLDS,
    VERSION,
    LabelAuditError,
    build_rows,
    flying_date,
    season_dates,
    source_season,
    summarize,
)

QUERY_VERSION = "canonical-approved-flights-with-effective-persistence/1"


def encoded(value: Any) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class EvidenceReader:
    def __init__(self, root: Path, runs: dict[str, dict[str, Any]]) -> None:
        self.root = root
        self.runs = runs
        self.files: dict[str, str] = {}
        self.verified: dict[str, dict[str, Any]] = {}

    def file(self, path: str, expected: str | None = None) -> Path:
        target = local_path(path, self.root, "Audit input")
        actual = digest(target)
        if expected is not None and actual != expected:
            raise LabelAuditError(f"Evidence hash mismatch: {path}")
        if path in self.files and self.files[path] != actual:
            raise LabelAuditError("Evidence changed during verification.")
        self.files[path] = actual
        return target

    def run(self, key: str) -> dict[str, Any]:
        if key in self.verified:
            return self.verified[key]
        run = self.runs.get(key)
        if run is None or run["status"] != "succeeded" or run["model_training_allowed"] != 1:
            raise LabelAuditError(
                "Evidence run must be persisted, succeeded, and training-permitted."
            )
        manifest_path = self.file(run["raw_manifest_path"], run["raw_manifest_sha256"])
        _, manifest, artifacts, contract = load_manifest(key, self.root)
        if manifest_path != self.root / "data/raw/xccontest" / key / "manifest.json":
            raise LabelAuditError("Database manifest path does not identify this run.")
        all_ids = []
        raw_distances = defaultdict(list)
        for artifact in artifacts:
            path = self.file(artifact["path"], artifact["sha256"])
            document = HTMLParser(path.read_text(encoding="utf-8"))
            rows = document.css(ROW_SELECTOR)
            contract.verify_dated_artifact(artifact, document, rows)
            all_ids.extend(contract.verify_artifact_rows(artifact, rows))
            for row in rows:
                value = float(row.css_first(DISTANCE_SELECTOR).text().strip().replace(",", "."))
                raw_distances[row.attributes["id"].removeprefix("flight-")].append(value)
        contract.verify_run_rows(all_ids)
        event = json.loads(run["notes"])["persistence_events"][-1]
        # Persistence hashes cover its effective event, independently of mutable DB counters.
        event_body = {
            "schema_version": 1,
            "run_key": key,
            **{
                k: event[k]
                for k in (
                    "validation_snapshot_sha256",
                    "validation_report_sha256",
                    "accepted_flights_sha256",
                    "mapping_review_complete",
                )
            },
        }
        event_sha = hashlib.sha256(
            json.dumps(event_body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if event_sha != event["event_sha256"]:
            raise LabelAuditError("Persistence event hash mismatch.")
        report_path = self.file(event["validation_report_path"], event["validation_report_sha256"])
        report = read_json(report_path)
        if report["source"] != "xccontest" or report["run_key"] != key:
            raise LabelAuditError("Validation report belongs to a different run.")
        if report["parser_version"] not in {"xccontest-parser/2", "xccontest-parser/3"} or report[
            "validator_version"
        ] not in {"xccontest-validation/2", "xccontest-validation/4"}:
            raise LabelAuditError("Unsupported historical validation contract.")
        for name in (
            "accepted_flights",
            "site_quarantine",
            "parser_normalized",
            "parser_report",
            "raw_manifest",
        ):
            self.file(report[name + "_path"], report[name + "_sha256"])
        if (
            report["raw_manifest_sha256"] != run["raw_manifest_sha256"]
            or report["mapping_snapshot_sha256"] != event["validation_snapshot_sha256"]
        ):
            raise LabelAuditError("Validation provenance disagrees with persistence.")
        if (report["accepted_flights_path"], report["accepted_flights_sha256"]) != (
            event["accepted_flights_path"],
            event["accepted_flights_sha256"],
        ):
            raise LabelAuditError("Effective accepted snapshot disagrees with validation.")
        accepted = read_jsonl(self.root / event["accepted_flights_path"])
        accepted_by_id = {r["source_flight_id"]: r for r in accepted}
        if len(accepted_by_id) != len(accepted) or len(accepted) != report["records_accepted"]:
            raise LabelAuditError("Accepted records have duplicates or inconsistent counters.")
        if report["records_seen"] != sum(
            report[k]
            for k in (
                "records_accepted",
                "records_rejected",
                "records_quarantined",
                "records_deduplicated",
            )
        ):
            raise LabelAuditError("Validation counters do not reconcile.")
        parser_report = read_json(self.root / report["parser_report_path"])
        if any(
            parser_report.get(k) != report[k]
            for k in ("source", "run_key", "parser_version", "raw_manifest_path")
        ):
            raise LabelAuditError("Parser provenance disagrees with validation.")
        normalized = read_jsonl(self.root / report["parser_normalized_path"])
        normalized_ids = {r["source_flight_id"] for r in normalized}
        if (
            len(normalized_ids) != len(normalized)
            or len(normalized) != parser_report["normalized_candidates"]
        ):
            raise LabelAuditError("Normalized candidate identities/counters do not reconcile.")
        for record in accepted:
            if record.get("validation_status") != "accepted" or record.get("source") != "xccontest":
                raise LabelAuditError("Non-accepted flight in accepted evidence.")
            if record["source_flight_id"] not in normalized_ids:
                raise LabelAuditError("Accepted flight absent from normalized parser evidence.")
            distances = raw_distances.get(record["source_flight_id"], [])
            if not distances or any(d != record["scored_distance_km"] for d in distances):
                raise LabelAuditError("Accepted distance disagrees with raw evidence.")
        result = {
            "run": run,
            "manifest": manifest,
            "artifacts": artifacts,
            "event": event,
            "report": report,
            "accepted": accepted_by_id,
            "raw_distances": raw_distances,
        }
        self.verified[key] = result
        return result

    def coverage(
        self, key: str, seasons: tuple[int, ...]
    ) -> dict[tuple[int, str, str], dict[str, Any]]:
        evidence = self.run(key)
        manifest, report, event = evidence["manifest"], evidence["report"], evidence["event"]
        if manifest.get("manifest_schema_version") != 5:
            raise LabelAuditError("Negative coverage requires manifest v5.")
        # Review files are not hashed in historical reports; freeze their exact bytes here.
        mapping_dir = Path("data/interim/xccontest") / key / "site-mapping-v4"
        for name in (
            "mapping-proposals.jsonl",
            "mapping-decisions.jsonl",
            "automatic-mapping-decisions.jsonl",
            "automatic-mapping-report.json",
        ):
            path = mapping_dir / name
            if (self.root / path).is_file():
                self.file(path.as_posix())
        unresolved, reviewed_rejected = _actionable_quarantines(report, key, self.root)
        parser_dir = Path(report["parser_report_path"]).parent
        rejections = read_jsonl(self.file((parser_dir / "parse-rejections.jsonl").as_posix()))
        parser_report = read_json(self.root / report["parser_report_path"])
        if len(rejections) != parser_report["records_rejected"]:
            raise LabelAuditError("Parser rejections do not reconcile.")
        # A lost/ambiguous threshold candidate conservatively blocks absence for the whole run.
        lost = {
            str(t): bool(
                parser_report.get("conflict_candidates")
                or parser_report.get("threshold_exclusions")
            )
            for t in THRESHOLDS
        }
        for rejected in rejections:
            ref = rejected["artifact_reference"]
            self.file(ref["artifact_path"], ref["artifact_sha256"])
            distances = evidence["raw_distances"].get(rejected["source_flight_id"], [])
            for t in THRESHOLDS:
                if not distances or any(not 0 <= d < t for d in distances):
                    lost[str(t)] = True
        quarantines = read_jsonl(self.root / report["site_quarantine_path"])
        if len(quarantines) != report["records_quarantined"]:
            raise LabelAuditError("Quarantine counters do not reconcile.")
        terminal = {"auto_rejected", "persisted_rejection", "review_required"}
        for item in quarantines:
            if item.get("mapping_disposition") not in terminal:
                for t in THRESHOLDS:
                    lost[str(t)] = True
        scopes = defaultdict(list)
        for scope in manifest["activity_scope_statuses"]:
            scopes[(scope["season"], scope["date_filter"], scope["country_code"])].append(scope)
        targets = {(x["season"], x["country_code"]): x for x in manifest["target_statuses"]}
        result = {}
        for season in seasons:
            for country in manifest["scope"]["country_codes"]:
                target = targets.get((season, country))
                if target is None:
                    raise LabelAuditError("Selected season is not covered by this repaired run.")
                for day in season_dates(season):
                    identity = (season, day.isoformat(), country)
                    statuses = scopes.get(identity, [])
                    daily = [
                        a
                        for a in evidence["artifacts"]
                        if (a["season"], a["date_filter"], a["country_code"]) == identity
                        and a["acquisition_purpose"] == "all_distance_activity"
                    ]
                    parent = [
                        a
                        for a in daily
                        if a["category"] == "pg" and a["sort_mode"] == "source_default"
                    ]
                    # Exact-category fallback must not masquerade as exhaustive parent coverage.
                    complete = (
                        len(parent) == 1
                        and not parent[0]["has_next_page"]
                        and any(
                            s["category"] == "pg"
                            and s["status"] in {"complete", "empty"}
                            and s["source_default_captured"]
                            for s in statuses
                        )
                    )
                    if complete:
                        state = "empty" if parent[0]["row_observation_count"] == 0 else "complete"
                        reason = "verified_complete_parent_daily_view"
                    elif not is_supported_activity_date(day.isoformat()):
                        state, reason = "out_of_window", "outside_activity_window"
                    elif statuses or daily:
                        state, reason = "partial", "incomplete_daily_activity_scope"
                    else:
                        state, reason = "missing", "no_all_distance_scope"
                    result[identity] = {
                        "run_key": key,
                        "raw_manifest_sha256": evidence["run"]["raw_manifest_sha256"],
                        "mapping_snapshot_sha256": event["validation_snapshot_sha256"],
                        "maturity_policy_version": MATURITY_POLICY,
                        "mature": season in MATURE_RUNS.get(key, ()),
                        "activity_state": state,
                        "activity_reason": reason,
                        "activity_scope_statuses": statuses,
                        "mapping_complete": unresolved == 0
                        and event["mapping_review_complete"] is True,
                        "unresolved_mapping_count": unresolved,
                        "reviewed_rejected_count": reviewed_rejected,
                        "threshold_complete": {
                            str(t): complete and not lost[str(t)] for t in THRESHOLDS
                        },
                        "threshold_reason": "verified_daily_parent_and_no_lost_threshold_candidate"
                        if complete and not any(lost.values())
                        else "incomplete_threshold_evidence",
                        "raw_artifacts": [
                            {"path": a["path"], "sha256": a["sha256"]} for a in daily
                        ],
                    }
        return result

    def recheck(self) -> None:
        for path, expected in self.files.items():
            if digest(self.root / path) != expected:
                raise LabelAuditError("Evidence changed during audit; no output published.")


def audit_labels(
    *,
    seasons: tuple[int, ...] = (2022, 2023, 2024, 2025),
    database_url: str | None = None,
    output_directory: Path | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    root = (project_root or repository_root()).resolve()
    if (
        not seasons
        or len(set(seasons)) != len(seasons)
        or not set(seasons) <= {2022, 2023, 2024, 2025}
    ):
        raise LabelAuditError("Choose unique source seasons from 2022 through 2025.")
    url = configured_database_url(database_url)
    db_path = resolve_database_path(url, root)
    db_hash = digest(db_path)
    connection = open_read_only_database(url, root)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        if [r[0] for r in connection.execute("PRAGMA quick_check")] != ["ok"] or connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall():
            raise LabelAuditError("SQLite integrity checks failed.")
        sites = [
            dict(r)
            for r in connection.execute("SELECT id, slug, country_code_iso2 FROM sites ORDER BY id")
        ]
        runs = {
            r["run_key"]: dict(r) for r in connection.execute("SELECT * FROM flight_ingestion_runs")
        }
        reader = EvidenceReader(root, runs)
        candidates = [
            dict(r)
            for r in connection.execute(
                "SELECT f.*, m.site_id, m.status AS mapping_status, r.run_key AS evidence_run_key "
                "FROM flight_records f JOIN source_site_mappings m ON m.id=f.source_site_mapping_id "
                "JOIN flight_ingestion_runs r ON r.id=f.last_validated_by_ingestion_run_id ORDER BY f.id"
            )
            if source_season(flying_date(r["takeoff_at_utc"])) in seasons
        ]
        coverage = {}
        for key, allowed_seasons in MATURE_RUNS.items():
            selected = tuple(s for s in sorted(seasons) if s in allowed_seasons)
            if selected:
                coverage.update(reader.coverage(key, selected))
        canonical = {(r["source_id"], r["source_flight_id"]): r for r in candidates}
        if len(canonical) != len(candidates):
            raise LabelAuditError("Duplicate canonical source identities.")
        # Repaired snapshots must reconcile in both directions; include the earlier verified
        # out-of-window canonical positive, with its own run and no repaired negative coverage.
        for key in list(reader.verified):
            evidence = reader.verified[key]
            for source_id, accepted in (
                (evidence["run"]["source_id"], r) for r in evidence["accepted"].values()
            ):
                if source_season(flying_date(accepted["takeoff_at_utc"])) not in seasons:
                    continue
                stored = canonical.get((source_id, accepted["source_flight_id"]))
                if stored is None:
                    raise LabelAuditError("Accepted repaired flight is absent from SQLite.")
                match_flight(stored, accepted)
        for flight in candidates:
            if flight["mapping_status"] != "approved":
                raise LabelAuditError("Canonical flight does not have approved site mapping.")
            evidence = reader.run(flight["evidence_run_key"])
            accepted = evidence["accepted"].get(flight["source_flight_id"])
            if accepted is None or flight["source_id"] != evidence["run"]["source_id"]:
                raise LabelAuditError("Canonical flight is not in its effective accepted snapshot.")
            match_flight(flight, accepted)
        rows = build_rows(sites, candidates, coverage, tuple(sorted(seasons)))
        snapshots = {
            "sites": sites,
            "canonical_flights": candidates,
            "mappings": [
                dict(r)
                for r in connection.execute("SELECT * FROM source_site_mappings ORDER BY id")
            ],
        }
        snapshot_hash = hashlib.sha256(encoded(snapshots)).hexdigest()
    finally:
        connection.close()
    reader.recheck()
    if digest(db_path) != db_hash:
        raise LabelAuditError("Database changed during audit; repeat on a stable snapshot.")
    summary = {
        "overall": summarize(rows),
        "fully_known": summarize([r for r in rows if r["all_labels_known"]]),
        "by_season": {
            str(s): summarize([r for r in rows if r["source_season"] == s]) for s in sorted(seasons)
        },
        "by_site": {
            s["slug"]: summarize([r for r in rows if r["site_id"] == s["id"]]) for s in sites
        },
        "by_site_season": {
            s["slug"]: {
                str(year): summarize(
                    [r for r in rows if r["site_id"] == s["id"] and r["source_season"] == year]
                )
                for year in sorted(seasons)
            }
            for s in sites
        },
    }
    files = {
        "site_day_label_audit.jsonl": b"".join(encoded(r) for r in rows),
        "known_site_day_labels.jsonl": b"".join(encoded(r) for r in rows if r["all_labels_known"]),
        "unknown_site_day_labels.jsonl": b"".join(
            encoded(r) for r in rows if not r["all_labels_known"]
        ),
        "summary.json": encoded(summary),
    }
    manifest = {
        "schema_version": VERSION,
        "negative_policy_version": POLICY,
        "maturity_policy_version": MATURITY_POLICY,
        "query_version": QUERY_VERSION,
        "source_seasons": sorted(seasons),
        "timezone": "Europe/Sofia",
        "calendar_scope": "October 1 of preceding year through September 30; every site/date",
        "minimum_activity_flights": 1,
        "thresholds_km": list(THRESHOLDS),
        "database_path": db_path.relative_to(root).as_posix(),
        "database_sha256": db_hash,
        "database_snapshot_sha256": snapshot_hash,
        "evidence_files": dict(sorted(reader.files.items())),
        "runs": {
            key: {
                "raw_manifest_path": e["run"]["raw_manifest_path"],
                "raw_manifest_sha256": e["run"]["raw_manifest_sha256"],
                "collector_version": e["manifest"]["collector_version"],
                "parser_version": e["report"]["parser_version"],
                "validator_version": e["report"]["validator_version"],
                "persistence_pipeline_version": e["run"]["pipeline_version"],
                "persistence_event": e["event"],
                "role": "reviewed_mature_repaired_coverage"
                if key in MATURE_RUNS
                else "supplemental_accepted_positive_evidence",
            }
            for key, e in sorted(reader.verified.items())
        },
        "outputs": {
            name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
            for name, data in files.items()
        },
        "limitations": [
            "Recorded XC achievement, not weather-only potential or safety.",
            "Unknown vectors are excluded from supervised fitting.",
            "No weather join, split selection, model, or GFS acquisition.",
            "Conservative negatives require complete parent daily coverage; exact-category fallback is not exhaustive.",
        ],
    }
    audit_id = hashlib.sha256(encoded(manifest)).hexdigest()
    files["manifest.json"] = encoded({**manifest, "audit_id": audit_id})
    destination = (
        output_directory or root / "data/processed/flight-label-audits" / audit_id
    ).resolve()
    try:
        destination.relative_to((root / "data/processed").resolve())
    except ValueError as error:
        raise LabelAuditError("Audit outputs must stay below ignored data/processed/.") from error
    if destination.exists():
        if (
            not destination.is_dir()
            or {p.name for p in destination.iterdir()} != set(files)
            or any((destination / name).read_bytes() != data for name, data in files.items())
        ):
            raise LabelAuditError("Existing audit differs; refusing to overwrite it.")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".flight-label-build-", dir=destination.parent
        ) as temporary:
            staging = Path(temporary) / "audit"
            staging.mkdir()
            for name, data in files.items():
                (staging / name).write_bytes(data)
            staging.rename(destination)
    return {
        "audit_id": audit_id,
        "output_directory": str(destination),
        "summary": summary["overall"],
    }


def match_flight(stored: dict[str, Any], accepted: dict[str, Any]) -> None:
    for field in ("site_id", "source_site_mapping_id", "takeoff_at_utc", "scored_distance_km"):
        if stored[field] != accepted[field]:
            raise LabelAuditError(f"Canonical flight disagrees with accepted evidence: {field}")
