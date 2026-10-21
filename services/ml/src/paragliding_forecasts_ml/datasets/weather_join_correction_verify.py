"""Artifact-only verification of thermal corrections and their v4 joined dataset."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paragliding_forecasts_ml.ingestion.weather.features.policy import load_feature_policy
from paragliding_forecasts_ml.storage.sqlite import repository_root

from .weather_cohort import _encoded
from .weather_join import _sha
from .weather_join_correction import (
    CALCULATION_VERSION,
    CORRECTION_VERSION,
    JOIN_VERSION,
    THERMAL_KEYS,
    _apply,
    _candidate,
    _evaluate,
    _key,
    _parent,
    _patched_quality,
    _quality_index,
    _read_jsonl,
    _require,
)
from .weather_join_verify import _weather


def verify_correction(
    *, correction_id: str, project_root: Path | None = None
) -> tuple[dict, list[dict]]:
    root = (project_root or repository_root()).resolve()
    _require(
        len(correction_id) == 64 and all(c in "0123456789abcdef" for c in correction_id),
        "Invalid correction ID.",
    )
    base = (root / "data/processed/joined-weather-corrections").resolve()
    directory = (base / correction_id).resolve()
    _require(directory.parent == base, "Correction path escapes artifact root.")
    manifest_bytes = (directory / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    identity = {key: value for key, value in manifest.items() if key != "correction_id"}
    _require(
        manifest.get("correction_id") == correction_id
        and _sha(_encoded(identity)) == correction_id
        and manifest.get("schema_version") == CORRECTION_VERSION
        and manifest.get("calculation_version") == CALCULATION_VERSION
        and manifest.get("allowed_feature_keys") == list(THERMAL_KEYS),
        "Correction manifest identity or contract differs.",
    )
    _require(
        set(manifest.get("outputs", {})) == {"corrections.jsonl"}, "Correction output list differs."
    )
    content = (directory / "corrections.jsonl").read_bytes()
    _require(
        manifest["outputs"]["corrections.jsonl"]
        == {"bytes": len(content), "sha256": _sha(content)},
        "Correction JSONL hash or byte count differs.",
    )
    parent_manifest, parent_dir, parent_rows, _excluded = _parent(
        root, manifest["parent_dataset_id"]
    )
    _require(
        manifest["parent_manifest_sha256"] == _sha((parent_dir / "manifest.json").read_bytes())
        and manifest["parent_training_sha256"]
        == parent_manifest["outputs"]["training_examples.jsonl"]["sha256"]
        and manifest["acquisition_id"] == parent_manifest["acquisition_id"],
        "Correction parent or acquisition hash differs.",
    )
    expected = {_key(row): row for row in parent_rows if _candidate(row)}
    records = _read_jsonl(directory / "corrections.jsonl")
    _require(
        content == b"".join(_encoded(record) for record in records),
        "Correction JSONL is not canonically encoded.",
    )
    _require(
        len(records) == len(expected) == manifest["evaluated"],
        "Correction evaluation coverage differs from parent candidates.",
    )
    seen: set[tuple[int, str, int]] = set()
    patched = 0
    unchanged = 0
    for record in records:
        key = tuple(record["key"])
        _require(
            key in expected and key not in seen, "Correction candidate is unexpected or duplicated."
        )
        seen.add(key)
        parent = expected[key]
        projection = record["input_projection"]
        _require(
            record["parent_row_sha256"] == _sha(_encoded(parent))
            and record["input_projection_sha256"] == _sha(_encoded(projection))
            and record["run_key"] == projection["run_key"] == parent["weather"]["run_key"]
            and key
            == (projection["site_id"], projection["target_local_date"], projection["horizon_days"])
            and projection["persistence_input_sha256"]
            == parent["weather"]["persistence_input_sha256"],
            "Correction source projection is not bound to the parent row.",
        )
        values, hourly = _evaluate(projection)
        _require(
            record["hourly_results"] == hourly,
            "Correction hourly results differ from source inputs.",
        )
        old_quality = _quality_index(parent)
        _require(
            record["old_values"]
            == {feature: parent["weather"]["features"][feature] for feature in THERMAL_KEYS}
            and record["old_quality"]
            == {feature: old_quality[feature] for feature in THERMAL_KEYS},
            "Correction old value/provenance differs from parent.",
        )
        if values is None:
            _require(
                record["outcome"] == "unchanged_missing_input"
                and record["new_values"] is None
                and record["new_quality"] is None
                and any(
                    item["missing_reason"] == "thermal_strength_input_missing" for item in hourly
                ),
                "Correction no-op does not have missing input evidence.",
            )
            unchanged += 1
        else:
            _require(
                record["outcome"] == "patched"
                and record["new_values"] == values
                and record["new_quality"] == _patched_quality(parent, values),
                "Correction values or quality differ from recomputation.",
            )
            patched += 1
    _require(seen == set(expected), "Correction omitted a parent candidate.")
    _require(
        patched == manifest["patched"] and unchanged == manifest["unchanged_missing_input"],
        "Correction outcome counts differ from manifest.",
    )
    return manifest, records


def verify_corrected_joined_dataset(
    *, dataset_id: str, project_root: Path | None = None
) -> dict[str, Any]:
    root = (project_root or repository_root()).resolve()
    base = (root / "data/processed/joined-weather").resolve()
    directory = (base / dataset_id).resolve()
    _require(directory.parent == base, "Joined path escapes artifact root.")
    manifest = json.loads((directory / "manifest.json").read_bytes())
    identity = {key: value for key, value in manifest.items() if key != "dataset_id"}
    _require(
        manifest.get("dataset_id") == dataset_id
        and _sha(_encoded(identity)) == dataset_id
        and manifest.get("schema_version") == JOIN_VERSION,
        "Corrected joined manifest identity or schema differs.",
    )
    correction_manifest, records = verify_correction(
        correction_id=manifest["correction_id"], project_root=root
    )
    parent_manifest, parent_dir, parent_rows, parent_excluded = _parent(
        root, manifest["parent_dataset_id"]
    )
    _require(
        manifest["parent_dataset_id"] == correction_manifest["parent_dataset_id"]
        and manifest["correction_manifest_sha256"]
        == _sha(
            (
                root
                / "data/processed/joined-weather-corrections"
                / manifest["correction_id"]
                / "manifest.json"
            ).read_bytes()
        ),
        "Corrected joined lineage differs from correction artifact.",
    )
    for key in (
        "acquisition_id",
        "acquisition_manifest_sha256",
        "cohort_plan_id",
        "source_audit_id",
        "split",
        "examples",
        "excluded",
        "excluded_reasons",
    ):
        _require(
            manifest.get(key) == parent_manifest.get(key),
            f"Corrected joined {key} differs from parent.",
        )
    _require(
        set(manifest.get("outputs", {})) == {"training_examples.jsonl", "excluded_examples.jsonl"},
        "Corrected joined output names differ.",
    )
    for name, evidence in manifest["outputs"].items():
        content = (directory / name).read_bytes()
        _require(
            evidence == {"bytes": len(content), "sha256": _sha(content)},
            f"Corrected joined output differs: {name}.",
        )
    corrected = _read_jsonl(directory / "training_examples.jsonl")
    corrected_lines = (directory / "training_examples.jsonl").read_bytes().splitlines(keepends=True)
    parent_lines = (parent_dir / "training_examples.jsonl").read_bytes().splitlines(keepends=True)
    excluded = _read_jsonl(directory / "excluded_examples.jsonl")
    _require(
        len(corrected) == len(parent_rows) and excluded == parent_excluded,
        "Corrected joined coverage/exclusions differ from parent.",
    )
    by_key = {tuple(item["key"]): item for item in records}
    policy, _ = load_feature_policy("weather-feature-policy-v4.json")
    patched = 0
    for original, new, old_line, new_line in zip(
        parent_rows, corrected, parent_lines, corrected_lines, strict=True
    ):
        key = _key(original)
        record = by_key.get(key)
        expected = (
            original if record is None else _apply(original, record, manifest["correction_id"])
        )
        _require(new == expected, f"Corrected joined row contains an unauthorized edit: {key}.")
        _require(
            new_line == (old_line if new == original else _encoded(expected)),
            f"Corrected joined row bytes differ from the permitted patch: {key}.",
        )
        _weather(new, policy)
        if record is not None and record["outcome"] == "patched":
            patched += 1
    _require(
        patched == correction_manifest["patched"],
        "Corrected joined patch count differs from correction artifact.",
    )
    return {
        "dataset_id": dataset_id,
        "parent_dataset_id": manifest["parent_dataset_id"],
        "correction_id": manifest["correction_id"],
        "examples": len(corrected),
        "excluded": len(excluded),
        "patched": patched,
        "verified": True,
    }
