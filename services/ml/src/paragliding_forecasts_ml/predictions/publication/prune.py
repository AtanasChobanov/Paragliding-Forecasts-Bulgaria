"""Remove verified operational GRIBs after their publication retention period."""

import argparse
import json
from collections.abc import Sequence
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from sqlite3 import Error as SqliteError
from sqlite3 import Row

from ...ingestion.weather.artifacts import ArtifactError, WeatherArtifactStore
from ...ingestion.weather.operational_retention import (
    INTENT,
    RECEIPT,
    check_record,
    grib_references,
    intent_body,
    manifest_reference,
    pruned_gribs,
    read_record,
    receipt_body,
    record_bytes,
    require_regular_path,
)
from ...ingestion.weather.state import RunStateLedger
from ...storage.file_lock import LockBusyError, file_lock, weather_run_lock
from ...storage.sqlite import (
    configured_database_url,
    open_read_only_database,
    repository_root,
    resolve_database_path,
)
from .checkpoints import Checkpoints, sync_directory, write_atomic
from .store import existing_publication, require_schema
from .weather import read_weather, utc_text

RETENTION = timedelta(hours=48)
PRUNE_ERRORS = (OSError, RuntimeError, SqliteError, ValueError)


def _prune_payloads(store: WeatherArtifactStore, expected: tuple[str, str]) -> tuple[str, int]:
    ref = manifest_reference(store)
    if (ref.relative_path, ref.sha256) != expected:
        raise ArtifactError("Raw manifest reference differs from SQLite.")
    event = RunStateLedger(store).load_state().effective_event("raw_complete")
    if event is None or event.disposition != "complete" or event.evidence != ref:
        raise ArtifactError("Raw manifest reference differs from the effective ledger.")
    payloads = grib_references(store, ref)
    intent_path, receipt_path = store.raw_dir / INTENT, store.raw_dir / RECEIPT
    intent = read_record(intent_path, store.raw_dir)
    if read_record(receipt_path, store.raw_dir) is not None:
        pruned_gribs(store, ref.sha256)
        return "already_pruned", 0
    body = intent_body(ref, payloads, store.run_key)
    if intent is not None:
        check_record(intent, body)
    pending = []
    for item in payloads:
        path = store.project_root / item.relative_path
        if require_regular_path(path, store.raw_dir, missing_ok=intent is not None):
            if intent is not None:
                store.verify_reference(item, expected_root=store.raw_dir, require_disk_hash=True)
            pending.append((path, item.byte_count))
    if intent is None:
        # Validate the whole raw boundary before recording the first removal.
        store.verify_raw_manifest(ref)
        intent = record_bytes(body)
        write_atomic(intent_path, intent)
    freed = 0
    for path, size in pending:
        path.unlink()
        freed += size
    sync_directory(store.raw_dir / "payloads")
    write_atomic(receipt_path, record_bytes(receipt_body(intent, payloads, store.run_key)))
    return "pruned", freed


def prune(root: Path, database_url: str, now: datetime) -> dict:
    database = resolve_database_path(database_url, root)
    checkpoints = Checkpoints.for_database(root, database)
    managed = checkpoints.directory / "managed"
    output = {"pruned_runs": [], "skipped_runs": [], "errors": [], "freed_bytes": 0}
    with closing(open_read_only_database(database_url, root)) as db:
        db.row_factory = Row
        require_schema(db)
        for marker in sorted(managed.glob("*.json")):
            key = marker.stem
            try:
                with file_lock(weather_run_lock(root, key)):
                    result, freed = _run(db, root, checkpoints, key, now)
                field = "pruned_runs" if result == "pruned" else "skipped_runs"
                output[field].append({"run_key": key, "reason": result, "freed_bytes": freed})
                output["freed_bytes"] += freed
            except LockBusyError:
                output["skipped_runs"].append({"run_key": key, "reason": "active_run"})
            except PRUNE_ERRORS as error:
                output["errors"].append({"run_key": key, "detail": str(error)})
    return output


def _run(db, root, checkpoints, key, now) -> tuple[str, int]:
    row = db.execute(
        "SELECT status, request_purpose FROM weather_ingestion_runs WHERE run_key=?", (key,)
    ).fetchone()
    if row is None or row["status"] != "succeeded":
        return "unpublished", 0
    if row["request_purpose"] != "operational_forecast":
        return "non_operational", 0
    weather = read_weather(db, key)
    checkpoints.mark_managed(weather.horizon, key)
    publications = db.execute(
        """SELECT xc_model_id FROM prediction_runs WHERE weather_ingestion_run_id = ?
           AND created_at_utc <= ? ORDER BY created_at_utc, id""",
        (weather.id, utc_text(now - RETENTION)),
    ).fetchall()
    if not publications:
        return "no_publication_at_least_48_hours_old", 0
    if existing_publication(db, weather, publications[0][0]) is None:
        raise ArtifactError("Expected forecast publication disappeared during prune verification.")
    archive = root / "data/processed/weather-archives" / key
    if (archive / "eviction-intent.json").exists() or any(archive.glob("archive-*.json")):
        return "cold_archive_workflow", 0
    return _prune_payloads(WeatherArtifactStore(key, project_root=root), weather.raw_manifest)


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forecast-prune", description=__doc__)
    parser.add_argument("--database-url", help="Existing repository-relative SQLite file: URL.")
    parser.add_argument("--project-root", type=Path, default=repository_root())
    args = parser.parse_args(arguments)
    try:
        report = prune(
            args.project_root.resolve(),
            configured_database_url(args.database_url),
            datetime.now(UTC),
        )
    except PRUNE_ERRORS as error:
        report = {
            "pruned_runs": [],
            "skipped_runs": [],
            "errors": [{"detail": str(error)}],
            "freed_bytes": 0,
        }
    print(json.dumps(report, sort_keys=True))
    return int(bool(report["errors"]))
