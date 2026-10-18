"""Dataset inputs are reviewed configuration, not source-code run identities."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from paragliding_forecasts_ml.ingestion.xccontest.persistence import UUID4

from .flight_labels import LabelAuditError


@dataclass(frozen=True)
class AuditPolicy:
    document: dict[str, Any]
    sha256: str

    @property
    def version(self) -> str:
        return self.document["policy_version"]

    @property
    def runs(self) -> dict[str, dict[str, Any]]:
        return {entry["run_key"]: entry for entry in self.document["coverage_runs"]}

    @property
    def seasons(self) -> tuple[int, ...]:
        return tuple(sorted(s for entry in self.runs.values() for s in entry["seasons"]))


def load_policy(path: Path | None = None) -> AuditPolicy:
    content = (
        path.read_bytes()
        if path is not None
        else resources.files("paragliding_forecasts_ml.datasets")
        .joinpath("resources", "flight-label-audit-policy.json")
        .read_bytes()
    )
    document = json.loads(content)
    if (
        not isinstance(document, dict)
        or set(document) != {"schema_version", "policy_version", "coverage_runs"}
        or document["schema_version"] != 1
    ):
        raise LabelAuditError("Unsupported audit-policy schema.")
    if not isinstance(document["policy_version"], str) or not document["policy_version"].strip():
        raise LabelAuditError("Audit policy must identify its version.")
    entries = document["coverage_runs"]
    if not isinstance(entries, list) or not entries:
        raise LabelAuditError("Audit policy must declare at least one coverage run.")
    keys, seasons = set(), set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"run_key", "seasons", "mature"}:
            raise LabelAuditError("Audit policy run requires exactly run_key, seasons, and mature.")
        key, declared, mature = entry["run_key"], entry["seasons"], entry["mature"]
        if not isinstance(key, str) or UUID4.fullmatch(key) is None or key in keys:
            raise LabelAuditError("Audit policy requires unique UUID-v4 run identities.")
        if (
            not isinstance(declared, list)
            or not declared
            or any(type(s) is not int or not 2000 <= s <= 2100 for s in declared)
        ):
            raise LabelAuditError("Audit policy seasons must be integers from 2000 through 2100.")
        if len(set(declared)) != len(declared) or seasons.intersection(declared):
            raise LabelAuditError(
                "Audit policy has ambiguous/duplicate season coverage; choose one snapshot per season."
            )
        if type(mature) is not bool:
            raise LabelAuditError("Audit policy mature must be a JSON boolean.")
        keys.add(key)
        seasons.update(declared)
    return AuditPolicy(document, hashlib.sha256(content).hexdigest())
