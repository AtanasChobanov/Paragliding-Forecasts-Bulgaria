"""Atomically record managed weather jobs and completed predictor packages."""

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ...ingestion.atmosphere.contracts import SHA256_PATTERN, UUID_V4_PATTERN, RequestPlan
from ...ingestion.weather.serialization import canonical_json_bytes, sha256_bytes
from .weather import ForecastHorizon


def sync_directory(path: Path) -> None:
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".forecast-", delete=False) as handle:
        staged = Path(handle.name)
        try:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            handle.close()
            staged.replace(path)
            sync_directory(path.parent)
        finally:
            staged.unlink(missing_ok=True)


def read_record(path: Path) -> bytes | None:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f"Invalid forecast checkpoint {path.name}.")
    return path.read_bytes() if path.is_file() else None


@dataclass(frozen=True)
class Checkpoints:
    directory: Path

    @classmethod
    def for_database(cls, root: Path, database: Path):
        identity = database.relative_to(root).as_posix()
        return cls(root / "data/local/forecast-publications" / sha256_bytes(identity.encode()))

    def _plan_path(self, horizon: ForecastHorizon) -> Path:
        return self.directory / "weather" / f"{horizon.issue_date}-d{horizon.days}.json"

    def load_plan(self, horizon: ForecastHorizon) -> RequestPlan | None:
        payload = read_record(self._plan_path(horizon))
        return RequestPlan.model_validate_json(payload, strict=True) if payload else None

    def set_plan(self, horizon: ForecastHorizon, plan: RequestPlan) -> None:
        write_atomic(self._plan_path(horizon), canonical_json_bytes(plan))

    def marker(self, run_key: str) -> Path:
        if UUID_V4_PATTERN.fullmatch(run_key) is None:
            raise ValueError("Invalid run key in forecast job checkpoint.")
        return self.directory / "managed" / f"{run_key}.json"

    def mark_managed(self, horizon: ForecastHorizon, run_key: str) -> None:
        record = canonical_json_bytes(
            {
                "version": 1,
                "run_key": run_key,
                "cycle_reference_utc": horizon.cycle,
                "target_local_date": horizon.target_date.isoformat(),
            }
        )
        path = self.marker(run_key)
        existing = read_record(path)
        if existing is None:
            write_atomic(path, record)
        elif existing != record:
            raise ValueError("Managed forecast checkpoint differs from the weather run.")

    def _predictor_path(self, run_key: str, model_id: str, kind: str) -> Path:
        if (
            UUID_V4_PATTERN.fullmatch(run_key) is None
            or SHA256_PATTERN.fullmatch(model_id) is None
            or kind not in {"xc", "cloudbase", "overdevelopment"}
        ):
            raise ValueError("Invalid predictor checkpoint identity.")
        return self.directory / "predictors" / run_key / model_id / f"{kind}.json"

    def load_prediction(self, run_key: str, model_id: str, kind: str) -> str | None:
        payload = read_record(self._predictor_path(run_key, model_id, kind))
        if payload is None:
            return None
        record = json.loads(payload)
        artifact_id = record.get("artifact_id") if isinstance(record, dict) else None
        if (
            not isinstance(artifact_id, str)
            or SHA256_PATTERN.fullmatch(artifact_id) is None
            or record != self._predictor_record(run_key, model_id, kind, artifact_id)
        ):
            raise ValueError("Invalid predictor checkpoint.")
        return artifact_id

    def set_prediction(self, run_key: str, model_id: str, kind: str, artifact_id: str) -> None:
        record = self._predictor_record(run_key, model_id, kind, artifact_id)
        write_atomic(self._predictor_path(run_key, model_id, kind), canonical_json_bytes(record))

    @staticmethod
    def _predictor_record(run_key: str, model_id: str, kind: str, artifact_id: str) -> dict:
        return {
            "version": 1,
            "run_key": run_key,
            "model_id": model_id,
            "predictor": kind,
            "artifact_id": artifact_id,
        }
