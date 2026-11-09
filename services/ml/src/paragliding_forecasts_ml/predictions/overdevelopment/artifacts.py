"""Publish immutable OD batches and verify them without upstream access."""

import re
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from ...ingestion.atmosphere.contracts import (
    SHA256_PATTERN,
    ArtifactReference,
    AtmosphericContract,
    validate_utc_timestamp,
)
from ...ingestion.weather.serialization import canonical_json_bytes, pretty_json_bytes, sha256_bytes
from .models import ForecastDay
from .policy import Policy
from .scoring import evaluate_day

PAYLOAD_NAMES = {"policy.json", "inputs.jsonl", "predictions.jsonl"}


class FileDigest(AtmosphericContract):
    sha256: str = Field(pattern=SHA256_PATTERN)
    byte_count: int = Field(gt=0)


class SourceEvidence(AtmosphericContract):
    run_key: str
    database_identity: str = Field(pattern=r"^data/[a-z0-9_./-]+$")
    usage_policy_sha256: str = Field(pattern=SHA256_PATTERN)
    persistence_input_sha256: str = Field(pattern=SHA256_PATTERN)
    references: tuple[ArtifactReference, ...] = Field(min_length=1)


class Manifest(AtmosphericContract):
    schema_version: Literal["overdevelopment-batch/1"] = "overdevelopment-batch/1"
    method_version: Literal["daily-rule-score/1"] = "daily-rule-score/1"
    policy_version: str
    policy_sha256: str = Field(pattern=SHA256_PATTERN)
    run_keys: tuple[str, ...] = Field(min_length=1)
    sources: tuple[SourceEvidence, ...] = Field(min_length=1)
    daily_count: int = Field(gt=0)
    risk_counts: dict[Literal["low", "medium", "high"], int]
    partial_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    files: dict[str, FileDigest]
    prediction_id: str = Field(pattern=SHA256_PATTERN)
    created_at_utc: str


def _identity(manifest: Manifest) -> dict:
    return manifest.model_dump(mode="json", exclude={"prediction_id", "created_at_utc"})


def _summary(predictions: list[dict]) -> dict:
    levels = Counter(row["risk_level"] for row in predictions)
    return {
        "daily_count": len(predictions),
        "risk_counts": {level: levels[level] for level in ("low", "medium", "high")},
        "partial_count": sum(not row["coverage"]["complete"] for row in predictions),
        "missing_count": levels[None],
    }


def _jsonl(records: list) -> bytes:
    return b"".join(canonical_json_bytes(record) for record in records)


def _validate_payloads(manifest: Manifest, payloads: dict[str, bytes]) -> None:
    policy_bytes = payloads["policy.json"]
    policy = Policy.model_validate_json(policy_bytes)
    if (
        policy.policy_version != manifest.policy_version
        or sha256_bytes(policy_bytes) != manifest.policy_sha256
    ):
        raise ValueError("OD policy snapshot differs from the manifest.")
    days = [ForecastDay.model_validate_json(line) for line in payloads["inputs.jsonl"].splitlines()]
    keys = [day.key for day in days]
    run_keys = tuple(sorted({day.run_key for day in days}))
    if (
        not keys
        or keys != sorted(set(keys))
        or run_keys != manifest.run_keys
        or tuple(source.run_key for source in manifest.sources) != run_keys
        or _jsonl(days) != payloads["inputs.jsonl"]
    ):
        raise ValueError("OD saved inputs have inconsistent identities or encoding.")
    predictions = [evaluate_day(day, policy, manifest.policy_sha256) for day in days]
    if _jsonl(predictions) != payloads["predictions.jsonl"]:
        raise ValueError("OD saved predictions do not match their replay.")
    if any(getattr(manifest, key) != value for key, value in _summary(predictions).items()):
        raise ValueError("OD prediction counts differ from the manifest.")


def _read_bundle(directory: Path, prediction_id: str) -> tuple[Manifest, dict[str, bytes]]:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("OD bundle must be a regular local directory.")
    if {path.name for path in directory.iterdir()} != {*PAYLOAD_NAMES, "manifest.json"}:
        raise ValueError("OD bundle contains unexpected or missing files.")
    for path in directory.iterdir():
        if path.is_symlink() or not path.is_file():
            raise ValueError("OD bundle payloads must be regular local files.")
    manifest = Manifest.model_validate_json((directory / "manifest.json").read_bytes())
    validate_utc_timestamp(manifest.created_at_utc)
    if (
        manifest.prediction_id != prediction_id
        or sha256_bytes(canonical_json_bytes(_identity(manifest))) != prediction_id
        or set(manifest.files) != PAYLOAD_NAMES
    ):
        raise ValueError("OD bundle content identity differs.")
    payloads = {}
    for name, digest in manifest.files.items():
        payload = (directory / name).read_bytes()
        if len(payload) != digest.byte_count or sha256_bytes(payload) != digest.sha256:
            raise ValueError(f"OD artifact payload changed: {name}.")
        payloads[name] = payload
    _validate_payloads(manifest, payloads)
    return manifest, payloads


def load_prediction(prediction_id: str, *, project_root: Path) -> Manifest:
    """Replay the saved bundle with no SQLite or weather input reads."""
    if re.fullmatch(SHA256_PATTERN, prediction_id) is None:
        raise ValueError("Expected a lowercase SHA-256 OD prediction ID.")
    directory = project_root / "data" / "processed" / "overdevelopment" / prediction_id
    manifest, _ = _read_bundle(directory, prediction_id)
    return manifest


def publish_prediction(
    project_root: Path,
    days: list[ForecastDay],
    sources: list[dict],
    policy: Policy,
    policy_bytes: bytes,
) -> tuple[Manifest, Path, bool]:
    days = sorted(days, key=lambda day: day.key)
    policy_sha256 = sha256_bytes(policy_bytes)
    predictions = [evaluate_day(day, policy, policy_sha256) for day in days]
    payloads = {
        "policy.json": policy_bytes,
        "inputs.jsonl": _jsonl(days),
        "predictions.jsonl": _jsonl(predictions),
    }
    manifest = Manifest(
        policy_version=policy.policy_version,
        policy_sha256=policy_sha256,
        run_keys=tuple(sorted({day.run_key for day in days})),
        sources=tuple(
            SourceEvidence.model_validate_json(canonical_json_bytes(source)) for source in sources
        ),
        files={
            name: FileDigest(sha256=sha256_bytes(payload), byte_count=len(payload))
            for name, payload in payloads.items()
        },
        prediction_id="0" * 64,
        created_at_utc=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **_summary(predictions),
    )
    prediction_id = sha256_bytes(canonical_json_bytes(_identity(manifest)))
    manifest = manifest.model_copy(update={"prediction_id": prediction_id})
    _validate_payloads(manifest, payloads)
    directory = project_root / "data" / "processed" / "overdevelopment" / prediction_id

    def verify_existing() -> Manifest:
        existing, existing_payloads = _read_bundle(directory, prediction_id)
        if _identity(existing) != _identity(manifest) or existing_payloads != payloads:
            raise ValueError("Existing immutable OD bundle differs from requested content.")
        return existing

    if directory.exists() or directory.is_symlink():
        return verify_existing(), directory, True

    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".od-", dir=directory.parent) as temporary:
        staging = Path(temporary) / "bundle"
        staging.mkdir()
        for name, payload in payloads.items():
            (staging / name).write_bytes(payload)
        (staging / "manifest.json").write_bytes(pretty_json_bytes(manifest))
        _read_bundle(staging, prediction_id)
        try:
            staging.rename(directory)
        except OSError:
            if not directory.exists() and not directory.is_symlink():
                raise
            return verify_existing(), directory, True
    return manifest, directory, False
