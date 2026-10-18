"""Verified cold archive and reversible hot raw eviction for persisted weather runs."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from paragliding_forecasts_ml.storage.sqlite import (
    configured_database_url,
    open_read_only_database,
)

from .artifact_audit import audit_weather_artifacts
from .persistence import _canonical_run_graph, _graph_sha256, _load_persisted_run_rows
from .serialization import canonical_json_bytes, sha256_file

ARCHIVE_SCHEMA = "weather-cold-archive/1"


class RetentionError(RuntimeError):
    """A weather run cannot be archived, evicted, or restored safely."""


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False).encode() + b"\n"


def _sha(value: dict) -> str:
    import hashlib

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _write_once(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = _json_bytes(value)
    if path.exists():
        if path.read_bytes() != content:
            raise RetentionError(f"Immutable retention record differs: {path}.")
        return
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{path.name}-", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != content:
                raise RetentionError(f"Immutable retention record differs: {path}.") from None
        except OSError:
            if path.exists():
                if path.read_bytes() != content:
                    raise RetentionError(f"Immutable retention record differs: {path}.") from None
            else:
                temporary.rename(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _read_record(path: Path, identity_field: str) -> dict:
    value = json.loads(path.read_bytes())
    digest = value.pop(identity_field, None)
    if digest != _sha(value):
        raise RetentionError(f"Retention record identity differs: {path}.")
    return {**value, identity_field: digest}


def _run_paths(root: Path, run_key: str) -> tuple[Path, Path, Path]:
    try:
        if str(UUID(run_key)) != run_key:
            raise ValueError(run_key)
    except ValueError as error:
        raise RetentionError("run-key must be a canonical UUID.") from error
    raw = root / "data/raw/weather" / run_key
    interim = root / "data/interim/weather" / run_key
    catalogue = root / "data/processed/weather-archives" / run_key
    if not raw.is_dir() or not interim.is_dir():
        raise RetentionError("Both canonical weather run directories are required.")
    return raw, interim, catalogue


def _database_graph(root: Path, run_key: str, database_url: str | None) -> dict:
    connection = open_read_only_database(configured_database_url(database_url), root)
    try:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """SELECT id, status, raw_manifest_sha256, feature_manifest_sha256,
                      model_training_allowed, target_local_date
               FROM weather_ingestion_runs WHERE run_key = ?""",
            (run_key,),
        ).fetchone()
        if row is None or row["status"] != "succeeded":
            raise RetentionError("Run lacks succeeded SQLite evidence.")
        graph = _canonical_run_graph(_load_persisted_run_rows(connection, int(row["id"])))
        return {
            "graph_sha256": _graph_sha256(graph),
            "raw_manifest_sha256": row["raw_manifest_sha256"],
            "feature_manifest_sha256": row["feature_manifest_sha256"],
            "target_local_date": row["target_local_date"],
        }
    finally:
        connection.close()


def _volume(root: Path, destination: Path) -> tuple[Path, str]:
    destination = destination.resolve()
    if destination == root or root in destination.parents or destination in root.parents:
        raise RetentionError("Cold destination must be a separate storage root.")
    if root.drive and destination.drive.lower() == root.drive.lower():
        raise RetentionError("Cold destination must be on another drive.")
    if not destination.is_dir():
        raise RetentionError("Cold destination directory does not exist.")
    marker = destination / ".weather-volume-id.json"
    if marker.exists():
        value = _read_record(marker, "marker_sha256")
    else:
        body = {"schema_version": "weather-volume/1", "volume_id": str(uuid4())}
        _write_once(marker, {**body, "marker_sha256": _sha(body)})
        value = _read_record(marker, "marker_sha256")
    if value["schema_version"] != "weather-volume/1":
        raise RetentionError("Cold volume marker schema differs.")
    return destination, value["volume_id"]


def _files(raw: Path, interim: Path) -> list[dict]:
    result = []
    for zone, directory in (("raw", raw), ("interim", interim)):
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise RetentionError("Weather run contains a symlink; refusing archive.")
            if path.is_file():
                result.append(
                    {
                        "path": f"{zone}/{path.relative_to(directory).as_posix()}",
                        "bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                )
    return result


def _safe_archive_path(directory: Path, relative: str) -> Path:
    value = PurePosixPath(relative)
    if (
        not relative
        or "\\" in relative
        or ":" in relative
        or value.is_absolute()
        or ".." in value.parts
        or value.parts[0] not in {"raw", "interim"}
    ):
        raise RetentionError("Archive file path is unsafe.")
    path = (directory / Path(*value.parts)).resolve()
    if directory.resolve() not in path.parents:
        raise RetentionError("Archive file path escapes its run root.")
    return path


def _check_files(directory: Path, files: list[dict], *, allow_evicted: bool = False) -> None:
    expected = {item["path"] for item in files}
    actual = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file() and path.relative_to(directory).as_posix() != "archive-manifest.json"
    }
    allowed_missing = {
        item["path"]
        for item in files
        if allow_evicted
        and item["path"].startswith("raw/payloads/")
        and item["path"].endswith(".grib2")
    }
    if actual - expected or expected - actual - allowed_missing:
        raise RetentionError("Archive file inventory differs from the verified receipt.")
    for item in files:
        path = _safe_archive_path(directory, item["path"])
        if path.exists() and (
            path.stat().st_size != item["bytes"] or sha256_file(path) != item["sha256"]
        ):
            raise RetentionError(f"Archived file hash differs: {item['path']}.")


def _archive_receipt(root: Path, run_key: str, destination: Path) -> tuple[dict, Path]:
    _raw, _interim, catalogue = _run_paths(root, run_key)
    destination, volume_id = _volume(root, destination)
    receipt = _read_record(catalogue / f"archive-{volume_id}.json", "receipt_sha256")
    if receipt["run_key"] != run_key or receipt["volume_id"] != volume_id:
        raise RetentionError("Archive receipt run or volume differs.")
    archive_dir = destination / "weather-archives" / run_key
    manifest = _read_record(archive_dir / "archive-manifest.json", "manifest_sha256")
    if manifest != receipt["archive_manifest"]:
        raise RetentionError("Cold archive manifest differs from local catalogue.")
    _check_files(archive_dir, manifest["files"])
    return receipt, archive_dir


def archive_run(
    run_key: str, *, destination: Path, project_root: Path, database_url: str | None = None
) -> dict:
    root = project_root.resolve()
    raw, interim, catalogue = _run_paths(root, run_key)
    if (catalogue / "eviction-receipt.json").exists():
        raise RetentionError("Restore evicted raw payloads before creating another archive.")
    audit_weather_artifacts(run_key, scope="effective", project_root=root)
    graph = _database_graph(root, run_key, database_url)
    destination, volume_id = _volume(root, destination)
    files = _files(raw, interim)
    bytes_total = sum(item["bytes"] for item in files)
    target = destination / "weather-archives" / run_key
    manifest_body = {
        "schema_version": ARCHIVE_SCHEMA,
        "run_key": run_key,
        "volume_id": volume_id,
        "database_graph": graph,
        "files": files,
    }
    manifest = {**manifest_body, "manifest_sha256": _sha(manifest_body)}
    receipt_body = {
        "run_key": run_key,
        "volume_id": volume_id,
        "archive_relative_path": f"weather-archives/{run_key}",
        "archive_manifest": manifest,
    }
    receipt = {**receipt_body, "receipt_sha256": _sha(receipt_body)}
    if target.exists():
        existing = _read_record(target / "archive-manifest.json", "manifest_sha256")
        if existing != manifest:
            raise RetentionError("Existing archive differs from the local run.")
        _check_files(target, files)
        _write_once(catalogue / f"archive-{volume_id}.json", receipt)
        return {"run_key": run_key, "state": "archived_verified", "bytes": bytes_total}
    if shutil.disk_usage(destination).free < bytes_total + 5 * 2**30:
        raise RetentionError("Cold volume lacks archive bytes plus 5 GiB reserve.")
    staging = destination / "weather-archives" / f".{run_key}-{uuid4().hex}"
    staging.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(raw, staging / "raw")
        shutil.copytree(interim, staging / "interim")
        _check_files(staging, files)
        _write_once(staging / "archive-manifest.json", manifest)
        staging.rename(target)
        _write_once(catalogue / f"archive-{volume_id}.json", receipt)
    except Exception:
        if staging.exists():
            if staging.resolve().parent != (destination / "weather-archives").resolve():
                raise RetentionError(
                    "Refusing to clean staging outside cold archive root."
                ) from None
            shutil.rmtree(staging)
        raise
    return {"run_key": run_key, "state": "archived_verified", "bytes": bytes_total}


def evict_local(
    run_key: str, *, destination: Path, project_root: Path, database_url: str | None = None
) -> dict:
    root = project_root.resolve()
    raw, _interim, catalogue = _run_paths(root, run_key)
    receipt, _archive_dir = _archive_receipt(root, run_key, destination)
    graph = _database_graph(root, run_key, database_url)
    if graph != receipt["archive_manifest"]["database_graph"]:
        raise RetentionError("SQLite graph changed since archive verification.")
    files = receipt["archive_manifest"]["files"]
    payloads = [
        item
        for item in files
        if item["path"].startswith("raw/payloads/") and item["path"].endswith(".grib2")
    ]
    intent = catalogue / "eviction-intent.json"
    if not intent.exists():
        audit_weather_artifacts(run_key, scope="effective", project_root=root)
        body = {
            "run_key": run_key,
            "archive_receipt_sha256": receipt["receipt_sha256"],
            "payloads": payloads,
        }
        _write_once(intent, {**body, "intent_sha256": _sha(body)})
    recorded = _read_record(intent, "intent_sha256")
    if (
        recorded["archive_receipt_sha256"] != receipt["receipt_sha256"]
        or recorded["payloads"] != payloads
    ):
        raise RetentionError("Eviction intent differs from the verified archive.")
    for item in payloads:
        parts = PurePosixPath(item["path"]).parts
        if len(parts) != 3 or parts[:2] != ("raw", "payloads"):
            raise RetentionError("Eviction target is outside this run's raw payloads.")
        path = (raw / "payloads" / parts[2]).resolve()
        if path.parent != (raw / "payloads").resolve():
            raise RetentionError("Eviction target is outside this run's raw payloads.")
        if path.exists():
            if path.stat().st_size != item["bytes"] or sha256_file(path) != item["sha256"]:
                raise RetentionError("Local raw payload differs before eviction.")
            path.unlink()
    body = {
        "run_key": run_key,
        "archive_receipt_sha256": receipt["receipt_sha256"],
        "evicted_bytes": sum(item["bytes"] for item in payloads),
    }
    _write_once(catalogue / "eviction-receipt.json", {**body, "receipt_sha256": _sha(body)})
    audit_compact(run_key, project_root=root, database_url=database_url)
    return {
        "run_key": run_key,
        "state": "archived_verified",
        "evicted_bytes": body["evicted_bytes"],
    }


def audit_compact(run_key: str, *, project_root: Path, database_url: str | None = None) -> dict:
    root = project_root.resolve()
    raw, interim, catalogue = _run_paths(root, run_key)
    eviction = _read_record(catalogue / "eviction-receipt.json", "receipt_sha256")
    matching = list(catalogue.glob("archive-*.json"))
    receipt = next(
        (
            _read_record(path, "receipt_sha256")
            for path in matching
            if _read_record(path, "receipt_sha256")["receipt_sha256"]
            == eviction["archive_receipt_sha256"]
        ),
        None,
    )
    if receipt is None:
        raise RetentionError("Evicted run lacks its immutable archive receipt.")
    graph = _database_graph(root, run_key, database_url)
    if graph != receipt["archive_manifest"]["database_graph"]:
        raise RetentionError("Persisted graph differs from archived evidence.")
    files = receipt["archive_manifest"]["files"]
    local = {
        "raw/" + path.relative_to(raw).as_posix(): path for path in raw.rglob("*") if path.is_file()
    }
    local.update(
        {
            "interim/" + path.relative_to(interim).as_posix(): path
            for path in interim.rglob("*")
            if path.is_file()
        }
    )
    expected = {item["path"] for item in files}
    evicted = {
        item["path"]
        for item in files
        if item["path"].startswith("raw/payloads/") and item["path"].endswith(".grib2")
    }
    state = (
        "archived_verified"
        if set(local) == expected - evicted
        else "restored_full"
        if set(local) == expected
        else None
    )
    if state is None:
        raise RetentionError("Compact evidence inventory differs after raw eviction.")
    for item in files:
        if item["path"] in local:
            path = local[item["path"]]
            if path.stat().st_size != item["bytes"] or sha256_file(path) != item["sha256"]:
                raise RetentionError("Compact evidence hash differs.")
    return {
        "run_key": run_key,
        "scope": "compact",
        "state": state,
        "graph_sha256": graph["graph_sha256"],
    }


def restore_run(
    run_key: str, *, destination: Path, project_root: Path, database_url: str | None = None
) -> dict:
    root = project_root.resolve()
    raw, interim, _catalogue = _run_paths(root, run_key)
    receipt, archive_dir = _archive_receipt(root, run_key, destination)
    if (
        _database_graph(root, run_key, database_url)
        != receipt["archive_manifest"]["database_graph"]
    ):
        raise RetentionError("SQLite graph changed since archive verification.")
    for item in receipt["archive_manifest"]["files"]:
        local_root = raw if item["path"].startswith("raw/") else interim
        _safe_archive_path(archive_dir, item["path"])
        relative = Path(*PurePosixPath(item["path"]).parts[1:])
        target = local_root / relative
        if target.exists():
            if target.stat().st_size != item["bytes"] or sha256_file(target) != item["sha256"]:
                raise RetentionError("Local artifact differs from its archived copy.")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(archive_dir / item["path"], target)
            if sha256_file(target) != item["sha256"]:
                raise RetentionError("Restored artifact hash differs.")
    audit_weather_artifacts(run_key, scope="effective", project_root=root)
    return {
        "run_key": run_key,
        "state": "restored_full",
        "archive_receipt_sha256": receipt["receipt_sha256"],
    }
