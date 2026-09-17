"""Bounded streaming collection and content-addressed reuse of IGRA snapshots."""

from __future__ import annotations

import json
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from ..atmosphere.contracts import ArtifactReference
from ..weather.serialization import canonical_json_bytes, sha256_bytes
from .artifacts import IgraArtifactError, IgraArtifactStore
from .inventory import _APPROVED_HOSTS, load_source_policy
from .models import IgraRemoteObject, IgraSourceSnapshotManifest
from .transport import IgraTransport
from .versions import COLLECTOR_VERSION


class IgraCollectionError(RuntimeError):
    """Provider bytes cannot meet the prior inventory, cap, or ZIP integrity contract."""


def collect_snapshot(
    store: IgraArtifactStore,
    transport: IgraTransport,
    *,
    station_id: str,
    archive_mode: str,
    objects: tuple[IgraRemoteObject, ...],
    maximum_total_mib: int,
    retrieved_started_at_utc: str | None = None,
) -> tuple[IgraSourceSnapshotManifest, bool]:
    """Verify/reuse a snapshot or stream all five inventory-authorized objects once."""

    if maximum_total_mib <= 0:
        raise IgraCollectionError("A positive explicit compressed-byte cap is required.")
    cap = maximum_total_mib * 1024 * 1024
    if sum(item.content_length for item in objects) > cap:
        raise IgraCollectionError("Inventory bytes exceed the reviewed IGRA compressed-byte cap.")
    cached = find_reusable_snapshot(store, station_id=station_id, archive_mode=archive_mode, objects=objects)
    if cached is not None:
        return cached, True
    policy, policy_sha256 = load_source_policy()
    started = retrieved_started_at_utc or _utc_now()
    work = store.create_work_directory()
    payload_directory = work / "payloads"
    payload_directory.mkdir(parents=True, exist_ok=False)
    try:
        for item in objects:
            _stream_verified_object(transport, item, payload_directory / item.safe_basename)
        _verify_zip_payloads(payload_directory, objects, policy)
        work_references = tuple(
            _reference_for_path(store, payload_directory / item.safe_basename, item.artifact_key)
            for item in objects
        )
        snapshot_id = source_snapshot_id(station_id, archive_mode, work_references)
        destination = store.snapshot_directory(station_id, snapshot_id)
        store.publish_directory(work, destination)
        references = tuple(
            _reference_for_path(store, destination / "payloads" / item.safe_basename, item.artifact_key)
            for item in objects
        )
        manifest = IgraSourceSnapshotManifest(
            source_snapshot_id=snapshot_id,
            station_id=station_id,
            archive_mode=archive_mode,
            source_policy_version=str(policy["policy_version"]),
            source_policy_sha256=policy_sha256,
            collector_version=COLLECTOR_VERSION,
            artifacts=references,
            remote_objects=objects,
            retrieved_started_at_utc=started,
            retrieved_completed_at_utc=_utc_now(),
            citation=str(policy["citation"]),
        )
        manifest_path = destination / "manifest.json"
        if manifest_path.exists():
            existing = IgraSourceSnapshotManifest.model_validate_json(manifest_path.read_bytes(), strict=True)
            if existing != manifest:
                raise IgraCollectionError("Existing snapshot manifest conflicts with identical content identity.")
        else:
            store.write_snapshot_manifest(station_id, snapshot_id, manifest)
        return manifest, False
    except Exception:
        # The protocol intentionally leaves only an unreferenced work directory for inspection/recovery.
        raise


def find_reusable_snapshot(
    store: IgraArtifactStore,
    *,
    station_id: str,
    archive_mode: str,
    objects: tuple[IgraRemoteObject, ...],
) -> IgraSourceSnapshotManifest | None:
    """Reuse only a recursively reverified local snapshot with matching source metadata."""

    station_root = store.raw_root / station_id
    if not station_root.is_dir():
        return None
    for path in sorted(station_root.glob("*/manifest.json")):
        try:
            manifest = IgraSourceSnapshotManifest.model_validate_json(path.read_bytes(), strict=True)
            if manifest.archive_mode != archive_mode or not _remote_metadata_matches(manifest.remote_objects, objects):
                continue
            snapshot_dir = path.parent
            for reference in manifest.artifacts:
                store.verify_reference(reference, expected_root=snapshot_dir)
            _verify_zip_payloads(snapshot_dir / "payloads", manifest.remote_objects, load_source_policy()[0])
            return manifest
        except (OSError, ValueError, IgraArtifactError, IgraCollectionError):
            continue
    return None


def source_snapshot_id(
    station_id: str, archive_mode: str, artifacts: tuple[ArtifactReference, ...]
) -> str:
    """The content identity excludes run, clock, parser and requested date selection."""

    return sha256_bytes(
        canonical_json_bytes(
            {
                "source_id": "noaa_igra_bum00015614",
                "station_id": station_id,
                "archive_mode": archive_mode,
                "artifacts": [
                    {"artifact_key": item.artifact_key, "byte_count": item.byte_count, "sha256": item.sha256}
                    for item in artifacts
                ],
            }
        )
    )


def _stream_verified_object(transport: IgraTransport, item: IgraRemoteObject, destination: Path) -> None:
    conditional = {"Accept-Encoding": "identity"}
    if item.etag:
        conditional["If-Match"] = item.etag
    elif item.last_modified:
        conditional["If-Unmodified-Since"] = item.last_modified
    response = transport.request(item.final_url, method="GET", headers=conditional)
    try:
        if response.status == 304:
            raise IgraCollectionError("A 304 response requires a separately verified local snapshot.")
        if response.status != 200:
            raise IgraCollectionError(f"IGRA GET failed for {item.artifact_key}: HTTP {response.status}.")
        _validate_get_headers(response, item)
        received = 0
        try:
            with destination.open("xb") as handle:
                for chunk in response.iter_chunks():
                    received += len(chunk)
                    if received > item.content_length:
                        raise IgraCollectionError("IGRA response exceeds its inventoried Content-Length.")
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        if received != item.content_length:
            destination.unlink(missing_ok=True)
            raise IgraCollectionError("IGRA response byte count differs from HEAD inventory.")
    finally:
        response.close()


def _validate_get_headers(response, item: IgraRemoteObject) -> None:
    final = urlparse(response.final_url)
    if final.scheme != "https" or final.hostname not in _APPROVED_HOSTS:
        raise IgraCollectionError("IGRA GET redirected outside the approved HTTPS hosts.")
    if response.header("Content-Encoding") not in {None, "", "identity"}:
        raise IgraCollectionError("IGRA GET uses an unexpected content encoding.")
    try:
        length = int(response.header("Content-Length") or "")
    except ValueError as error:
        raise IgraCollectionError("IGRA GET Content-Length is malformed.") from error
    if length != item.content_length:
        raise IgraCollectionError("IGRA object changed between HEAD and GET length checks.")
    if item.etag and response.header("ETag") != item.etag:
        raise IgraCollectionError("IGRA object changed between HEAD and GET ETag checks.")
    if not item.etag and item.last_modified and response.header("Last-Modified") != item.last_modified:
        raise IgraCollectionError("IGRA object changed between HEAD and GET modification checks.")


def _verify_zip_payloads(payload_directory: Path, objects: tuple[IgraRemoteObject, ...], policy: dict[str, object]) -> None:
    limits = policy["zip_limits"]
    assert isinstance(limits, dict)
    total_uncompressed = 0
    for item in objects:
        if item.media_class != "zip":
            continue
        path = payload_directory / item.safe_basename
        try:
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist()
                if len(infos) != 1:
                    raise IgraCollectionError("IGRA ZIP must contain exactly one member.")
                info = infos[0]
                if info.is_dir() or info.filename != item.expected_member_name or _unsafe_zip_member(info.filename):
                    raise IgraCollectionError("IGRA ZIP member is unsafe or not the expected provider member.")
                if info.flag_bits & 0x1 or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                    raise IgraCollectionError("IGRA ZIP encryption or compression method is not supported.")
                if info.file_size > int(limits["maximum_uncompressed_member_bytes"]):
                    raise IgraCollectionError("IGRA ZIP member exceeds the uncompressed byte limit.")
                if info.compress_size < 1 or info.file_size / info.compress_size > int(limits["maximum_compression_ratio"]):
                    raise IgraCollectionError("IGRA ZIP compression ratio exceeds the source policy.")
                total_uncompressed += info.file_size
                if archive.testzip() is not None:
                    raise IgraCollectionError("IGRA ZIP member CRC verification failed.")
        except (OSError, zipfile.BadZipFile) as error:
            raise IgraCollectionError("IGRA ZIP payload is invalid or truncated.") from error
    if total_uncompressed > int(limits["maximum_total_uncompressed_bytes"]):
        raise IgraCollectionError("IGRA ZIP members exceed the total uncompressed policy limit.")


def _reference_for_path(store: IgraArtifactStore, path: Path, key: str) -> ArtifactReference:
    media = "application/zip" if path.suffix == ".zip" else "text/plain"
    return store.reference_for(path, key, media_type=media)


def _remote_metadata_matches(
    cached: tuple[IgraRemoteObject, ...], current: tuple[IgraRemoteObject, ...]
) -> bool:
    if len(cached) != len(current):
        return False
    for old, new in zip(cached, current, strict=True):
        if (old.artifact_key, old.final_url, old.content_length) != (new.artifact_key, new.final_url, new.content_length):
            return False
        if old.etag is not None:
            if old.etag != new.etag:
                return False
        elif (old.last_modified, old.content_length) != (new.last_modified, new.content_length):
            return False
    return True


def _unsafe_zip_member(name: str) -> bool:
    normalized = name.replace("\\", "/")
    return normalized.startswith("/") or "../" in normalized or normalized.startswith("../")


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")