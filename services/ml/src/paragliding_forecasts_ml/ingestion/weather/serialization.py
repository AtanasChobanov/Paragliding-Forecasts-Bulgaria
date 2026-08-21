"""Deterministic JSON serialization and SHA-256 helpers for weather artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ..atmosphere.contracts import ensure_json_compatible


def canonical_json_bytes(value: BaseModel | dict[str, Any]) -> bytes:
    """Serialize a contract deterministically for fingerprints and immutable files."""

    payload: Any = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    ensure_json_compatible(payload)
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(content: bytes) -> str:
    """Return a lowercase SHA-256 of the exact bytes written to disk."""

    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash a durable artifact without loading its entire content at once."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
