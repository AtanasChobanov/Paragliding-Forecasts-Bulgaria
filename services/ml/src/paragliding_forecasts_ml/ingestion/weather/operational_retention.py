"""Durable proof of intentional operational GRIB removal."""

import stat
from pathlib import Path

from ..atmosphere.contracts import ArtifactReference
from .artifacts import ArtifactError, WeatherArtifactStore
from .serialization import canonical_json_bytes, sha256_bytes, sha256_file

INTENT = "operational-prune-intent.json"
RECEIPT = "operational-prune-receipt.json"


def manifest_reference(store: WeatherArtifactStore) -> ArtifactReference:
    path = store.raw_dir / "manifest.json"
    require_regular_path(path, store.raw_dir)
    return ArtifactReference(
        artifact_key="raw_manifest",
        relative_path=path.relative_to(store.project_root).as_posix(),
        sha256=sha256_file(path),
        byte_count=path.stat().st_size,
        media_type="application/json",
    )


def require_regular_path(path: Path, root: Path, *, missing_ok: bool = False) -> bool:
    if root.resolve() != root or path.resolve() != path or not path.is_relative_to(root):
        raise ArtifactError(
            "Operational retention path escapes its canonical run or uses a symlink."
        )
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        if missing_ok:
            return False
        raise
    if not stat.S_ISREG(mode):
        raise ArtifactError(f"Expected regular file for operational retention: {path.name}.")
    return True


def grib_references(
    store: WeatherArtifactStore, ref: ArtifactReference
) -> tuple[ArtifactReference, ...]:
    manifest = store.read_raw_manifest(ref)
    payloads = tuple(item for item in manifest.artifacts if item.relative_path.endswith(".grib2"))
    if manifest.status != "complete" or not payloads:
        raise ArtifactError("Operational retention requires a complete raw GRIB inventory.")
    seen = set()
    for item in payloads:
        path = store.project_root / item.relative_path
        if (
            path.parent != store.raw_dir / "payloads"
            or item.media_type != "application/x-grib2"
            or path in seen
        ):
            raise ArtifactError("Operational GRIB inventory has an invalid or duplicate target.")
        seen.add(path)
    return payloads


def record_bytes(body: dict) -> bytes:
    return canonical_json_bytes({**body, "sha256": sha256_bytes(canonical_json_bytes(body))})


def read_record(path: Path, root: Path) -> bytes | None:
    return path.read_bytes() if require_regular_path(path, root, missing_ok=True) else None


def intent_body(
    ref: ArtifactReference, payloads: tuple[ArtifactReference, ...], run_key: str
) -> dict:
    return {
        "version": 1,
        "run_key": run_key,
        "raw_manifest_sha256": ref.sha256,
        "payloads": [item.model_dump(mode="json") for item in payloads],
    }


def receipt_body(intent: bytes, payloads: tuple[ArtifactReference, ...], run_key: str) -> dict:
    return {
        "version": 1,
        "run_key": run_key,
        "intent_sha256": sha256_bytes(intent),
        "pruned_bytes": sum(item.byte_count for item in payloads),
    }


def check_record(payload: bytes, expected: dict) -> None:
    if payload != record_bytes(expected):
        raise ArtifactError("Operational retention record differs from the manifest or intent.")


def pruned_gribs(
    store: WeatherArtifactStore, expected_manifest_sha256: str
) -> tuple[ArtifactReference, ...]:
    ref = manifest_reference(store)
    if ref.sha256 != expected_manifest_sha256:
        raise ArtifactError("Operational raw manifest differs from SQLite.")
    payloads = grib_references(store, ref)
    intent = read_record(store.raw_dir / INTENT, store.raw_dir)
    receipt = read_record(store.raw_dir / RECEIPT, store.raw_dir)
    if intent is None or receipt is None:
        raise ArtifactError("Operational pruning is incomplete. Resume forecast-prune.")
    check_record(intent, intent_body(ref, payloads, store.run_key))
    check_record(receipt, receipt_body(intent, payloads, store.run_key))
    for item in payloads:
        if require_regular_path(
            store.project_root / item.relative_path, store.raw_dir, missing_ok=True
        ):
            raise ArtifactError("A GRIB marked pruned by the receipt is present on disk.")
    return payloads
