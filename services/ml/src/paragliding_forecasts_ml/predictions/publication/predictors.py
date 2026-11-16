"""Run or recover exact single-weather-run predictor bundles in worker processes."""

import json
from pathlib import Path

from ...ingestion.atmosphere.contracts import SHA256_PATTERN
from ..cloudbase.service import build_predictions
from ..cloudbase.service import load_prediction as load_cloudbase
from ..overdevelopment.artifacts import load_prediction as load_od
from ..overdevelopment.artifacts import publish_prediction
from ..overdevelopment.policy import load_policy
from ..overdevelopment.retained import read_inputs
from ..xc_probability.prediction import load_prediction as load_xc
from ..xc_probability.prediction import predict_runs
from .checkpoints import Checkpoints

PREDICTORS = ("xc", "cloudbase", "overdevelopment")


def _verify(kind: str, artifact_id: str, run_key: str, model_id: str, root: Path) -> None:
    if kind == "xc":
        batch = load_xc(prediction_id=artifact_id, project_root=root)
        matches = batch.metadata.run_keys == (run_key,) and batch.metadata.model_id == model_id
    elif kind == "cloudbase":
        batch = load_cloudbase(artifact_id, project_root=root)
        matches = [source["run_key"] for source in batch.sources] == [run_key]
    else:
        batch = load_od(artifact_id, project_root=root)
        matches = batch.run_keys == (run_key,)
    if not matches:
        raise ValueError(f"Saved {kind} package does not match the selected weather run and model.")


def _discover(kind: str, run_key: str, model_id: str, root: Path) -> str | None:
    # A process can stop after an immutable rename and before writing its checkpoint.
    subtree, filename = (
        ("xc-probability", "prediction.json") if kind == "xc" else (kind, "manifest.json")
    )
    directory = root / "data" / "processed" / subtree
    if kind == "xc":
        directory /= "prediction"
    if not directory.is_dir():
        return None
    candidates = []
    for path in directory.iterdir():
        if SHA256_PATTERN.fullmatch(path.name) is None or path.is_symlink() or not path.is_dir():
            continue
        metadata_path = path / filename
        if metadata_path.is_symlink() or not metadata_path.is_file():
            continue
        try:
            metadata = json.loads(metadata_path.read_bytes())
        except (OSError, ValueError):
            continue
        if (
            isinstance(metadata, dict)
            and metadata.get("run_keys") == [run_key]
            and (kind != "xc" or metadata.get("model_id") == model_id)
        ):
            candidates.append(path.name)
    if len(candidates) > 1:
        # Separate numerical environments can produce multiple immutable cloudbase
        # bundles. Adopt only an unambiguous completed package for the run.
        raise ValueError(f"Multiple existing {kind} packages match the selected weather run.")
    return candidates[0] if candidates else None


def run_predictor(
    kind: str, run_key: str, model_id: str, root: Path, database_url: str, checkpoints: Checkpoints
) -> tuple[str, bool]:
    artifact_id = checkpoints.load_prediction(run_key, model_id, kind)
    if artifact_id is None:
        artifact_id = _discover(kind, run_key, model_id, root)
    reused = artifact_id is not None
    if artifact_id is None:
        if kind == "xc":
            result = predict_runs(
                model_id=model_id, run_keys=(run_key,), project_root=root, database_url=database_url
            )
            artifact_id = result["prediction_id"]
        elif kind == "cloudbase":
            result = build_predictions([run_key], project_root=root, database_url=database_url)
            artifact_id = result["artifact_id"]
        else:
            policy, policy_bytes = load_policy()
            days, sources = read_inputs([run_key], project_root=root, database_url=database_url)
            manifest, _, _ = publish_prediction(root, days, sources, policy, policy_bytes)
            artifact_id = manifest.prediction_id
    _verify(kind, artifact_id, run_key, model_id, root)
    checkpoints.set_prediction(run_key, model_id, kind, artifact_id)
    return artifact_id, reused
