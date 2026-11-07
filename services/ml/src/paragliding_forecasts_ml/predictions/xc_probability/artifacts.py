"""Atomic, content-addressed XC bundles; execution metadata is outside identity."""

from __future__ import annotations

import json
import platform
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from importlib.metadata import version
from importlib.resources import files as resource_files
from pathlib import Path
from time import perf_counter

from ...ingestion.weather.serialization import canonical_json_bytes, pretty_json_bytes, sha256_bytes
from .models import ArtifactKind, ArtifactManifest, ArtifactParent
from .policy import POLICY_RESOURCE, load_policy


def numerical_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        **{name: version(name) for name in ("numpy", "scipy", "scikit-learn", "pydantic")},
    }


def identity(manifest: ArtifactManifest) -> dict:
    return manifest.model_dump(mode="json", exclude={"artifact_id", "created_at_utc", "execution"})


def artifact_directory(root: Path, kind: ArtifactKind, artifact_id: str) -> Path:
    if len(artifact_id) != 64 or any(char not in "0123456789abcdef" for char in artifact_id):
        raise ValueError("XC artifact ID must be a lowercase SHA-256.")
    base = (
        root / "data/models/xc-probability"
        if kind == "model"
        else root / "data/processed/xc-probability" / kind
    ).resolve()
    directory = (base / artifact_id).resolve()
    if directory.parent != base:
        raise ValueError("XC artifact path escapes its kind directory.")
    return directory


def read_bundle(
    directory: Path, *, kind: ArtifactKind, artifact_id: str
) -> tuple[ArtifactManifest, dict[str, bytes]]:
    """Validate compact bundle bytes without opening upstream history or a database."""
    if (directory / "manifest.json").is_symlink():
        raise ValueError("XC manifest must be a regular local file.")
    manifest = ArtifactManifest.model_validate_json((directory / "manifest.json").read_bytes())
    if manifest.kind != kind or manifest.artifact_id != artifact_id:
        raise ValueError("XC artifact kind or ID differs from its locator.")
    if sha256_bytes(canonical_json_bytes(identity(manifest))) != artifact_id:
        raise ValueError("XC manifest content identity differs.")
    if {path.name for path in directory.iterdir()} != {*manifest.files, "manifest.json"}:
        raise ValueError("XC bundle contains unexpected or missing files.")
    payloads = {}
    for name, digest in manifest.files.items():
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("XC bundle payload must be a regular local file.")
        content = path.read_bytes()
        if len(content) != digest.byte_count or sha256_bytes(content) != digest.sha256:
            raise ValueError(f"XC artifact payload changed: {name}.")
        payloads[name] = content
    _, policy_sha = load_policy()
    if (
        manifest.policy_sha256 != policy_sha
        or sha256_bytes(payloads.get("policy.json", b"")) != policy_sha
    ):
        raise ValueError("XC artifact policy differs from the supported packaged policy.")
    if manifest.numerical_versions != numerical_versions():
        raise ValueError("XC artifact numerical environment differs from this locked environment.")
    return manifest, payloads


def publish_bundle(
    *,
    root: Path,
    kind: ArtifactKind,
    payloads: dict[str, bytes],
    started_at: float,
    parents: tuple[ArtifactParent, ...] = (),
    validate_payload: Callable[[dict[str, bytes]], object],
) -> dict:
    """Validate before publishing; preserve the first execution metadata on reuse."""
    _, policy_sha = load_policy()
    payloads = {
        **payloads,
        "policy.json": resource_files(__package__)
        .joinpath("resources", POLICY_RESOURCE)
        .read_bytes(),
    }
    validate_payload(payloads)
    manifest = ArtifactManifest(
        kind=kind,
        artifact_id="0" * 64,
        policy_sha256=policy_sha,
        parents=parents,
        files={
            name: {"sha256": sha256_bytes(content), "byte_count": len(content)}
            for name, content in sorted(payloads.items())
        },
        numerical_versions=numerical_versions(),
        created_at_utc=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        execution={"elapsed_seconds_before_publication": perf_counter() - started_at},
    )
    artifact_id = sha256_bytes(canonical_json_bytes(identity(manifest)))
    manifest = manifest.model_copy(update={"artifact_id": artifact_id})
    directory = artifact_directory(root, kind, artifact_id)

    def verify_existing():
        existing, contents = read_bundle(directory, kind=kind, artifact_id=artifact_id)
        if identity(existing) != identity(manifest) or contents != payloads:
            raise ValueError("Existing immutable XC bundle differs from the requested content.")
        validate_payload(contents)

    reused = directory.exists()
    if reused:
        verify_existing()
    else:
        directory.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".xc-", dir=directory.parent) as temporary:
            staging = Path(temporary) / "bundle"
            staging.mkdir()
            for name, content in payloads.items():
                (staging / name).write_bytes(content)
            (staging / "manifest.json").write_bytes(pretty_json_bytes(manifest))
            _, staged_payloads = read_bundle(staging, kind=kind, artifact_id=artifact_id)
            validate_payload(staged_payloads)
            try:
                staging.rename(directory)
            except FileExistsError:
                verify_existing()
                reused = True
    return {
        f"{kind}_id": artifact_id,
        "output_directory": str(directory),
        "reused": reused,
        "elapsed_seconds": perf_counter() - started_at,
        "published_bytes": sum(path.stat().st_size for path in directory.iterdir()),
    }


def json_lines(payload: bytes) -> list[dict]:
    if not payload or not payload.endswith(b"\n"):
        raise ValueError("XC rows require nonempty JSONL with a final newline.")
    return [json.loads(line) for line in payload.splitlines()]
