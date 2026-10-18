"""Artifact-only validation of a published T-020 joined dataset."""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from paragliding_forecasts_ml.ingestion.atmosphere.catalogue import load_catalogue
from paragliding_forecasts_ml.ingestion.gfs.models import sofia_window_instants
from paragliding_forecasts_ml.ingestion.weather.features.policy import load_feature_policy
from paragliding_forecasts_ml.storage.sqlite import repository_root

from .weather_backfill_cli import _cohort
from .weather_cohort import _encoded
from .weather_full_backfill import _resolution, _verified_json, resolution_status
from .weather_join import VERSION, WeatherJoinError, _sha

SOFIA = ZoneInfo("Europe/Sofia")
KNOWN_STATES = {"positive", "negative"}
ABSENT_STATES = {"missing", "sentinel_missing", "invalid_payload", "unsupported"}
QUALITY_STATES = ABSENT_STATES | {"real", "derived"}
HEX = frozenset("0123456789abcdef")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WeatherJoinError(message)


def _sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX


def _utc(value: Any) -> datetime:
    _require(isinstance(value, str) and value.endswith("Z"), "Joined UTC timestamp is invalid.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise WeatherJoinError("Joined UTC timestamp is invalid.") from error
    _require(
        parsed.strftime("%Y-%m-%dT%H:%M:%SZ") == value, "Joined UTC timestamp is not canonical."
    )
    return parsed


def _labels(evidence: Any) -> None:
    _require(isinstance(evidence, dict), "Joined label evidence is missing.")
    labels = evidence.get("labels")
    _require(
        isinstance(labels, dict) and set(labels) == {"100", "200", "300"},
        "Joined label vector is incomplete.",
    )
    _require(_sha256(evidence.get("label_row_sha256")), "Joined label hash is invalid.")
    count = evidence.get("flight_count")
    maximum = evidence.get("max_distance_km")
    _require(type(count) is int and count > 0, "Joined label activity count is invalid.")
    _require(
        type(maximum) in (int, float) and math.isfinite(maximum) and maximum > 0,
        "Joined maximum flight distance is invalid.",
    )
    coverage = evidence.get("coverage")
    _require(
        isinstance(coverage, dict) and coverage.get("mature") is True,
        "Joined label coverage is not mature.",
    )
    for threshold in (100, 200, 300):
        item = labels[str(threshold)]
        _require(
            isinstance(item, dict) and item.get("state") in KNOWN_STATES,
            "Unknown label entered a supervised cohort.",
        )
        _require(
            isinstance(item.get("reason"), str) and bool(item["reason"]),
            "Joined label reason is missing.",
        )
        ids = item.get("positive_source_flight_ids")
        _require(
            isinstance(ids, list) and all(isinstance(value, str) for value in ids),
            "Joined flight IDs are invalid.",
        )
        if item["state"] == "positive":
            _require(
                bool(ids) and maximum >= threshold, "Positive label disagrees with flight evidence."
            )
        else:
            _require(
                not ids and maximum < threshold, "Negative label disagrees with flight evidence."
            )
    for low, high in ((100, 200), (200, 300)):
        _require(
            labels[str(high)]["state"] != "positive" or labels[str(low)]["state"] == "positive",
            "Joined positive labels are not nested.",
        )
        _require(
            labels[str(low)]["state"] != "negative" or labels[str(high)]["state"] == "negative",
            "Joined negative labels are not nested.",
        )


def _identity(row: dict[str, Any], split: str) -> tuple[int, str, int]:
    site = row.get("site_id")
    horizon = row.get("horizon_days")
    _require(
        type(site) is int and site > 0 and type(horizon) is int and horizon in (1, 2, 3),
        "Joined site or horizon is invalid.",
    )
    _require(
        row.get("split") == split
        and isinstance(row.get("site_slug"), str)
        and bool(row["site_slug"]),
        "Joined split or site is invalid.",
    )
    try:
        target = date.fromisoformat(row["target_local_date"])
        issue = date.fromisoformat(row["issue_local_date"])
    except (KeyError, TypeError, ValueError) as error:
        raise WeatherJoinError("Joined target or issue date is invalid.") from error
    _require(issue == target - timedelta(days=horizon), "Joined issue date does not match horizon.")
    cycle = _utc(row.get("cycle_reference_utc"))
    cutoff = _utc(row.get("issue_cutoff_utc"))
    delivery = _utc(row.get("delivery_deadline_utc"))
    _require(
        cycle == datetime.combine(issue, time(6), tzinfo=ZoneInfo("UTC")),
        "Joined cycle is not the issue-date 06Z run.",
    )
    _require(
        cutoff == datetime.combine(issue, time(16), tzinfo=SOFIA)
        and delivery == datetime.combine(issue, time(20), tzinfo=SOFIA),
        "Joined cutoff or delivery deadline differs from the pinned policy.",
    )
    valid = row.get("valid_times_utc")
    leads = row.get("lead_hours")
    _require(
        isinstance(valid, list)
        and valid == list(sofia_window_instants(target.isoformat()))
        and isinstance(leads, list)
        and len(leads) == len(valid) == 11,
        "Joined flying window or forecast leads are incomplete.",
    )
    _require(
        all(
            type(lead) is int and (_utc(hour) - cycle).total_seconds() == lead * 3600
            for hour, lead in zip(valid, leads, strict=True)
        ),
        "Joined forecast lead differs from cycle and valid hour.",
    )
    fraction = row.get("inclusion_probability")
    weight = row.get("sampling_weight")
    _require(
        isinstance(fraction, dict)
        and type(fraction.get("numerator")) is int
        and type(fraction.get("denominator")) is int
        and 0 < fraction["numerator"] <= fraction["denominator"]
        and type(weight) in (int, float)
        and math.isfinite(weight)
        and weight > 0,
        "Joined sampling metadata is invalid.",
    )
    _labels(row.get("label_evidence"))
    return site, target.isoformat(), horizon


def _feature_scope(
    values: Any, quality: Any, entries: Any, *, layer_index: int | None = None
) -> None:
    catalogue = load_catalogue()
    expected = {item.feature_key: item for item in entries}
    _require(
        isinstance(values, dict) and set(values) == set(expected),
        "Joined feature key set differs from the pinned policy.",
    )
    _require(
        isinstance(quality, list) and len(quality) == len(expected),
        "Joined feature provenance count differs from features.",
    )
    expected_identity = {
        (entry.field_code, entry.variant or "canonical", entry.statistic): entry
        for entry in entries
    }
    _require(
        len(expected_identity) == len(expected),
        "Pinned feature provenance identities are ambiguous.",
    )
    seen: set[tuple[str, str, str]] = set()
    for item in quality:
        _require(isinstance(item, dict), "Joined feature provenance is invalid.")
        if layer_index is not None:
            _require(
                item.get("layer_index") == layer_index,
                "Joined profile provenance points to another layer.",
            )
        identity = (item.get("field_code"), item.get("field_variant"), item.get("statistic_type"))
        _require(
            identity in expected_identity and identity not in seen,
            "Joined feature provenance identity is missing or duplicated.",
        )
        seen.add(identity)
        entry = expected_identity[identity]
        _require(
            item.get("native_unit") == catalogue.field_unit(entry.field_code),
            "Joined feature unit differs from the catalogue.",
        )
        state = item.get("quality_state")
        value = values[entry.feature_key]
        _require(state in QUALITY_STATES, "Joined feature quality state is invalid.")
        if state in ABSENT_STATES:
            _require(
                value is None and bool(item.get("missing_reason_code")),
                "Missing feature lacks null value or reason.",
            )
        else:
            _require(
                type(value) in (int, float)
                and math.isfinite(value)
                and item.get("missing_reason_code") is None,
                "Available feature lacks a finite value or has a missing reason.",
            )
        _require(
            bool(item.get("derivation_version")), "Joined feature derivation version is missing."
        )


def _weather(row: dict[str, Any], policy: Any) -> None:
    weather = row.get("weather")
    _require(isinstance(weather, dict), "Ready joined example lacks weather.")
    _require(
        weather.get("feature_contract_version") == policy.feature_contract_version,
        "Joined feature contract differs from policy.",
    )
    _require(
        weather.get("product_reference_at_utc") == row["cycle_reference_utc"],
        "Joined product cycle differs from row identity.",
    )
    _require(
        _utc(weather.get("required_inputs_last_modified_at_utc")) <= _utc(row["issue_cutoff_utc"]),
        "Joined source became ready after the issue cutoff.",
    )
    for key in ("raw_manifest_sha256", "feature_manifest_sha256", "persistence_input_sha256"):
        _require(_sha256(weather.get(key)), f"Joined weather {key} is invalid.")
    _require(
        isinstance(weather.get("run_key"), str) and bool(weather["run_key"]),
        "Joined weather run key is missing.",
    )
    features = weather.get("features")
    _require(
        isinstance(features, dict)
        and features.get("feature_contract_version") == policy.feature_contract_version,
        "Joined feature values have wrong contract version.",
    )
    _feature_scope(
        {key: value for key, value in features.items() if key != "feature_contract_version"},
        weather.get("feature_quality"),
        policy.daily_fields,
    )
    layers = weather.get("profile_layers")
    quality = weather.get("profile_layer_quality")
    _require(
        isinstance(layers, list)
        and len(layers) == len(policy.profile_layers)
        and isinstance(quality, list),
        "Joined profile layers differ from policy.",
    )
    _require(
        all(isinstance(item, dict) for item in quality), "Joined profile provenance is invalid."
    )
    for index, (layer, spec) in enumerate(zip(layers, policy.profile_layers, strict=True)):
        _require(
            isinstance(layer, dict)
            and layer.get("layer_base_agl_m") == spec.layer_base_agl_m
            and layer.get("layer_top_agl_m") == spec.layer_top_agl_m,
            "Joined profile layer bounds differ from policy.",
        )
        layer_values = {
            key: value
            for key, value in layer.items()
            if key not in {"layer_base_agl_m", "layer_top_agl_m"}
        }
        expected_keys = {entry.feature_key for entry in policy.entries_for_layer(spec)}
        _require(
            set(layer_values)
            == {entry.feature_key for entry in policy.profile_layer_fields}
            | {entry.feature_key for group in policy.profile_layers for entry in group.fields}
            and all(
                value is None for key, value in layer_values.items() if key not in expected_keys
            ),
            "Joined profile layer has an unexpected or populated non-applicable field.",
        )
        _feature_scope(
            {key: layer_values[key] for key in expected_keys},
            [item for item in quality if item.get("layer_index") == index],
            policy.entries_for_layer(spec),
            layer_index=index,
        )
    _require(
        len(quality) == sum(len(policy.entries_for_layer(spec)) for spec in policy.profile_layers),
        "Joined profile provenance contains an extra layer or field.",
    )


def verify_joined_dataset(*, dataset_id: str, project_root: Path | None = None) -> dict[str, Any]:
    """Verify published bytes, policy, cohort coverage, labels, and feature provenance."""
    root = (project_root or repository_root()).resolve()
    _require(_sha256(dataset_id), "Invalid joined dataset ID.")
    parent = (root / "data/processed/joined-weather").resolve()
    directory = (parent / dataset_id).resolve()
    _require(directory.parent == parent, "Invalid joined dataset path.")
    manifest = json.loads((directory / "manifest.json").read_bytes())
    _require(isinstance(manifest, dict), "Joined manifest is invalid.")
    identity = {key: value for key, value in manifest.items() if key != "dataset_id"}
    _require(
        manifest.get("dataset_id") == dataset_id
        and _sha(_encoded(identity)) == dataset_id
        and manifest.get("schema_version") == VERSION,
        "Joined manifest identity or schema differs.",
    )
    split = manifest.get("split")
    _require(split in {"development", "backtest"}, "Joined split is invalid.")
    example_file = (
        "training_examples.jsonl" if split == "development" else "backtest_2025_examples.jsonl"
    )
    _require(
        set(manifest.get("outputs", {})) == {example_file, "excluded_examples.jsonl"},
        "Joined output filenames differ from the split contract.",
    )
    for name, evidence in manifest["outputs"].items():
        content = (directory / name).read_bytes()
        _require(
            len(content) == evidence.get("bytes") and _sha(content) == evidence.get("sha256"),
            f"Joined output changed: {name}.",
        )
    acquisition_id = manifest.get("acquisition_id")
    acquisition_dir, session, jobs = _resolution(root, acquisition_id)
    status = resolution_status(SimpleNamespace(project_root=root, acquisition_id=acquisition_id))
    _require(
        status["finalized"] and not status["states"].get("pending", 0),
        "Joined acquisition is not finalized.",
    )
    _require(
        session["cohort_plan_id"] == manifest.get("cohort_plan_id")
        and session["split"] == split
        and _sha((acquisition_dir / "manifest.json").read_bytes())
        == manifest.get("acquisition_manifest_sha256"),
        "Joined acquisition identity differs from manifest.",
    )
    acquisition = _verified_json(acquisition_dir / "manifest.json", "manifest_sha256")
    receipts = {item["job_key"]: item for item in acquisition["jobs"]}
    _require(len(receipts) == len(jobs), "Joined acquisition receipts are duplicated.")
    cohort, _ = _cohort(root, session["cohort_plan_id"])
    _require(
        cohort["source_audit_id"] == manifest.get("source_audit_id"),
        "Joined label audit identity differs.",
    )
    selected_path = (
        root
        / "data/processed/weather-cohorts"
        / session["cohort_plan_id"]
        / "selected_site_days.jsonl"
    )
    selected = {
        (item["site_id"], item["target_local_date"]): item
        for line in selected_path.read_text(encoding="utf-8").splitlines()
        if (item := json.loads(line))["split"] == split
    }
    _require(bool(selected), "Joined split has no selected site-days.")
    expected = {(site, target, horizon) for site, target in selected for horizon in (1, 2, 3)}
    policy, _ = load_feature_policy()
    seen: set[tuple[int, str, int]] = set()
    counts: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    for filename in (example_file, "excluded_examples.jsonl"):
        with (directory / filename).open(encoding="utf-8") as handle:
            for line in handle:
                _require(bool(line.strip()), "Joined JSONL contains an empty line.")
                row = json.loads(line)
                _require(isinstance(row, dict), "Joined JSONL row is invalid.")
                key = _identity(row, split)
                _require(
                    key in expected and key not in seen,
                    "Joined site/date/horizon is unexpected or duplicated.",
                )
                seen.add(key)
                selected_row = selected[(key[0], key[1])]
                _require(
                    row["label_evidence"]["label_row_sha256"] == selected_row["label_row_sha256"]
                    and row["sampling_weight"] == selected_row["sampling_weight"]
                    and row["inclusion_probability"] == selected_row["inclusion_probability"],
                    "Joined label or sampling evidence differs from cohort.",
                )
                receipt = receipts[f"{key[1]}-D{key[2]}"]
                _require(
                    row["cycle_reference_utc"] == receipt["cycle_reference_utc"]
                    and row["issue_cutoff_utc"] == receipt["issue_cutoff_utc"],
                    "Joined row differs from acquisition issue evidence.",
                )
                if filename == example_file:
                    _require(
                        receipt["state"] == "ready", "Joined example uses unavailable weather."
                    )
                    _weather(row, policy)
                    _require(
                        row["weather"]["run_key"] == receipt["run_key"]
                        and row["weather"]["required_inputs_last_modified_at_utc"]
                        == receipt["available_at_utc"],
                        "Joined weather differs from acquisition receipt.",
                    )
                    counts[f"D+{key[2]}"] += 1
                else:
                    _require(
                        receipt["state"] in {"missing_weather", "late_source"}
                        and row.get("reason") == receipt["state"]
                        and "weather" not in row,
                        "Joined exclusion does not match unavailable weather.",
                    )
                    if receipt["state"] == "late_source":
                        _require(
                            _utc(receipt.get("available_at_utc")) > _utc(row["issue_cutoff_utc"]),
                            "Joined late-source exclusion has no late source evidence.",
                        )
                    reasons[row["reason"]] += 1
    _require(seen == expected, "Joined dataset does not cover every selected horizon.")
    _require(
        sum(counts.values()) == manifest.get("examples")
        and sum(reasons.values()) == manifest.get("excluded")
        and dict(sorted(reasons.items())) == manifest.get("excluded_reasons"),
        "Joined manifest counts differ from validated rows.",
    )
    return {
        "dataset_id": dataset_id,
        "split": split,
        "selected_site_days": len(selected),
        "examples": sum(counts.values()),
        "examples_by_horizon": dict(sorted(counts.items())),
        "excluded": sum(reasons.values()),
        "excluded_reasons": dict(sorted(reasons.items())),
        "verified": True,
    }
