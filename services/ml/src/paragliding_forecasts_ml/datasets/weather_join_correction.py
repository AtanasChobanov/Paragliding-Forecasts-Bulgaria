"""Read-only thermal correction of an immutable joined weather dataset."""

from __future__ import annotations

import json
import math
import sqlite3
import tempfile
from datetime import date
from itertools import pairwise
from pathlib import Path
from typing import Any

from paragliding_forecasts_ml.ingestion.weather.features.aggregation import (
    IntervalValue,
    interval_maximum,
    interval_weighted_mean,
    sofia_flying_window,
)
from paragliding_forecasts_ml.ingestion.weather.features.policy import load_feature_policy
from paragliding_forecasts_ml.ingestion.weather.features.thermodynamics import (
    HeightProfilePoint,
    ThermodynamicError,
    thermal_strength_from_surface_fluxes,
)
from paragliding_forecasts_ml.storage.sqlite import (
    configured_database_url,
    open_read_only_database,
    repository_root,
)

from .weather_cohort import _encoded
from .weather_join import WeatherJoinError, _sha
from .weather_join_verify import verify_joined_dataset

CORRECTION_VERSION = "weather-joined-correction/1"
JOIN_VERSION = "weather-flight-joined-dataset/4"
CALCULATION_VERSION = "thermal-profile-two-metre-anchor/2"
DERIVATION_VERSION = "exact-interval-thermal-reduction/2"
THERMAL_KEYS = (
    "surface_buoyancy_flux_kinematic_mean_m2_s3",
    "surface_buoyancy_flux_kinematic_max_m2_s3",
    "convective_velocity_scale_mean_m_s",
    "convective_velocity_scale_max_m_s",
)
FLUX_CODES = (
    "surface_sensible_heat_flux_upward_w_m2",
    "surface_latent_heat_flux_upward_w_m2",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WeatherJoinError(message)


def _rows(connection: sqlite3.Connection, query: str, parameters: tuple = ()) -> list[dict]:
    return [dict(item) for item in connection.execute(query, parameters)]


def _key(row: dict) -> tuple[int, str, int]:
    return row["site_id"], row["target_local_date"], row["horizon_days"]


def _read_jsonl(path: Path) -> list[dict]:
    content = path.read_bytes()
    _require(not content or content.endswith(b"\n"), f"JSONL lacks final newline: {path.name}.")
    return [json.loads(line) for line in content.splitlines()]


def _publish(directory: Path, files: dict[str, bytes]) -> None:
    if directory.exists():
        _require(
            {path.name for path in directory.iterdir()} == set(files)
            and all((directory / name).read_bytes() == content for name, content in files.items()),
            f"Existing artifact differs from immutable identity: {directory.name}.",
        )
        return
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".correction-", dir=directory.parent) as temporary:
        staging = Path(temporary) / "artifact"
        staging.mkdir()
        for name, content in files.items():
            (staging / name).write_bytes(content)
        staging.rename(directory)


def _parent(root: Path, dataset_id: str) -> tuple[dict, Path, list[dict], list[dict]]:
    _require(
        isinstance(dataset_id, str)
        and len(dataset_id) == 64
        and all(character in "0123456789abcdef" for character in dataset_id),
        "Parent joined dataset ID is invalid.",
    )
    directory = root / "data/processed/joined-weather" / dataset_id
    manifest = json.loads((directory / "manifest.json").read_bytes())
    _require(
        manifest["schema_version"] == "weather-flight-joined-dataset/3"
        and manifest["split"] == "development",
        "Correction requires the verified v3 development dataset.",
    )
    verify_joined_dataset(dataset_id=dataset_id, project_root=root)
    return (
        manifest,
        directory,
        _read_jsonl(directory / "training_examples.jsonl"),
        _read_jsonl(directory / "excluded_examples.jsonl"),
    )


def _quality_index(row: dict) -> dict[str, dict]:
    policy, _ = load_feature_policy("weather-feature-policy-v4.json")
    by_identity = {
        (item.field_code, item.variant or "canonical", item.statistic): item.feature_key
        for item in policy.daily_fields
    }
    return {
        by_identity[(item["field_code"], item["field_variant"], item["statistic_type"])]: item
        for item in row["weather"]["feature_quality"]
    }


def _candidate(row: dict) -> bool:
    features = row["weather"]["features"]
    quality = _quality_index(row)
    absent = [features[key] is None for key in THERMAL_KEYS]
    if any(absent) and not all(absent):
        raise WeatherJoinError(f"Mixed thermal values require review: {_key(row)}.")
    if not all(absent):
        return False
    reasons = {quality[key]["missing_reason_code"] for key in THERMAL_KEYS}
    _require(reasons == {"interval_value_missing"}, f"Unexpected thermal absence: {_key(row)}.")
    return True


def _projection(connection: sqlite3.Connection, row: dict) -> dict:
    key = _key(row)
    weather = row["weather"]
    runs = _rows(
        connection,
        """SELECT id, product_run_id, run_key, status, target_local_date, raw_manifest_sha256,
                  feature_manifest_sha256, persistence_input_sha256
           FROM weather_ingestion_runs WHERE run_key = ?""",
        (weather["run_key"],),
    )
    _require(len(runs) == 1, f"Correction run is missing/duplicated: {key}.")
    run = runs[0]
    _require(
        run["status"] == "succeeded"
        and run["target_local_date"] == key[1]
        and all(
            run[field] == weather[field]
            for field in (
                "raw_manifest_sha256",
                "feature_manifest_sha256",
                "persistence_input_sha256",
            )
        ),
        f"Correction source graph disagrees with parent: {key}.",
    )
    snapshots = _rows(
        connection,
        """SELECT daily.id, daily.feature_contract_version, daily.point_footprint_id
           FROM weather_daily_feature_snapshots AS daily
           JOIN weather_sampling_footprints AS footprint
             ON footprint.id = daily.point_footprint_id
           WHERE daily.ingestion_run_id = ? AND footprint.site_id = ?""",
        (run["id"], key[0]),
    )
    _require(len(snapshots) == 1, f"Correction snapshot is ambiguous: {key}.")
    snapshot = snapshots[0]
    _require(
        snapshot["feature_contract_version"] == weather["feature_contract_version"],
        f"Correction source feature contract disagrees: {key}.",
    )
    samples = _rows(
        connection,
        """SELECT point.id, point.ingestion_run_id, point.point_footprint_id,
                  point.surface_pressure_pa,
                  point.air_temperature_2m_k, point.specific_humidity_2m_kg_per_kg,
                  point.provider_boundary_layer_height_agl_m,
                  valid.valid_at_utc, valid.lead_hours, valid.product_run_id,
                  valid.required_inputs_last_modified_at_utc
           FROM weather_daily_feature_snapshot_inputs AS link
           JOIN weather_point_samples AS point ON point.id = link.weather_point_sample_id
           JOIN weather_product_valid_times AS valid ON valid.id = point.product_valid_time_id
           WHERE link.daily_feature_snapshot_id = ? ORDER BY valid.valid_at_utc""",
        (snapshot["id"],),
    )
    window = sofia_flying_window(date.fromisoformat(key[1]))
    _require(
        len(samples) == 11
        and [item["valid_at_utc"] for item in samples] == list(window.expected_instants_utc)
        and [item["lead_hours"] for item in samples] == row["lead_hours"]
        and all(
            item["ingestion_run_id"] == run["id"]
            and item["point_footprint_id"] == snapshot["point_footprint_id"]
            and item["product_run_id"] == run["product_run_id"]
            for item in samples
        )
        and all(item["required_inputs_last_modified_at_utc"] for item in samples)
        and max(item["required_inputs_last_modified_at_utc"] for item in samples)
        == weather["required_inputs_last_modified_at_utc"],
        f"Correction source hours differ from parent: {key}.",
    )
    hours: list[dict] = []
    for previous, sample in pairwise(samples):
        profiles = _rows(
            connection,
            """SELECT pressure_pa, level_height_site_agl_m AS height_agl_m,
                      air_temperature_k AS temperature_k,
                      specific_humidity_kg_per_kg
               FROM weather_point_profile_levels
               WHERE weather_point_sample_id = ?
               ORDER BY level_height_site_agl_m, pressure_pa""",
            (sample["id"],),
        )
        flux_rows = _rows(
            connection,
            """SELECT measurement.field_code, measurement.interval_start_utc,
                      measurement.interval_end_utc, measurement.canonical_value,
                      provenance.quality_state, provenance.missing_reason_code
               FROM weather_point_interval_measurements AS measurement
               LEFT JOIN weather_field_provenance AS provenance
                 ON provenance.point_interval_measurement_id = measurement.id
               WHERE measurement.weather_point_sample_id = ?
                 AND measurement.field_code IN (?, ?)
               ORDER BY measurement.field_code""",
            (sample["id"], *FLUX_CODES),
        )
        _require(
            len(flux_rows) == len({item["field_code"] for item in flux_rows})
            and all(item["field_code"] in FLUX_CODES for item in flux_rows),
            f"Duplicate/unexpected thermal flux: {key}, {sample['valid_at_utc']}.",
        )
        for item in flux_rows:
            _require(
                item["interval_start_utc"] == previous["valid_at_utc"]
                and item["interval_end_utc"] == sample["valid_at_utc"],
                f"Thermal flux interval differs from flying window: {key}.",
            )
        hours.append(
            {
                "valid_at_utc": sample["valid_at_utc"],
                "interval_start_utc": previous["valid_at_utc"],
                "surface_pressure_pa": sample["surface_pressure_pa"],
                "surface_temperature_k": sample["air_temperature_2m_k"],
                "surface_specific_humidity_kg_per_kg": sample["specific_humidity_2m_kg_per_kg"],
                "provider_boundary_layer_height_agl_m": sample[
                    "provider_boundary_layer_height_agl_m"
                ],
                "profile": profiles,
                "fluxes": flux_rows,
            }
        )
    return {
        "run_key": weather["run_key"],
        "site_id": key[0],
        "target_local_date": key[1],
        "horizon_days": key[2],
        "persistence_input_sha256": weather["persistence_input_sha256"],
        "hours": hours,
    }


def _evaluate(projection: dict) -> tuple[dict[str, float] | None, list[dict]]:
    window = sofia_flying_window(date.fromisoformat(projection["target_local_date"]))
    _require(len(projection["hours"]) == 10, "Thermal correction needs ten intervals.")
    buoyancy_intervals: list[IntervalValue] = []
    velocity_intervals: list[IntervalValue] = []
    hourly: list[dict] = []
    for (expected_start, expected_end), hour in zip(
        pairwise(window.expected_instants_utc), projection["hours"], strict=True
    ):
        _require(
            hour["interval_start_utc"] == expected_start and hour["valid_at_utc"] == expected_end,
            "Thermal correction hour differs from Sofia window.",
        )
        fluxes = {item["field_code"]: item for item in hour["fluxes"]}
        _require(
            len(fluxes) == len(hour["fluxes"]) and set(fluxes) <= set(FLUX_CODES),
            "Thermal correction flux identities are invalid.",
        )
        required = (
            hour["surface_pressure_pa"],
            hour["surface_temperature_k"],
            hour["surface_specific_humidity_kg_per_kg"],
            hour["provider_boundary_layer_height_agl_m"],
        )
        missing = any(value is None for value in required) or set(fluxes) != set(FLUX_CODES)
        for flux in fluxes.values():
            _require(
                flux["interval_start_utc"] == expected_start
                and flux["interval_end_utc"] == expected_end,
                "Thermal correction flux interval is invalid.",
            )
            if flux["canonical_value"] is None or flux["quality_state"] not in {"real", "derived"}:
                missing = True
        if missing:
            buoyancy = velocity = None
            reason = "thermal_strength_input_missing"
        else:
            try:
                result = thermal_strength_from_surface_fluxes(
                    surface_pressure_pa=required[0],
                    surface_temperature_k=required[1],
                    surface_specific_humidity_kg_per_kg=required[2],
                    sensible_heat_flux_upward_w_m2=fluxes[FLUX_CODES[0]]["canonical_value"],
                    latent_heat_flux_upward_w_m2=fluxes[FLUX_CODES[1]]["canonical_value"],
                    provider_boundary_layer_height_agl_m=required[3],
                    profile=tuple(HeightProfilePoint(**item) for item in hour["profile"]),
                )
            except (ThermodynamicError, TypeError, ValueError) as error:
                raise WeatherJoinError(
                    f"Thermal correction cannot derive {projection['run_key']} "
                    f"{expected_end}: {error}"
                ) from error
            buoyancy = result.surface_buoyancy_flux_kinematic_m2_s3
            velocity = result.convective_velocity_scale_m_s
            reason = None
        hourly.append(
            {
                "valid_at_utc": expected_end,
                "buoyancy": buoyancy,
                "convective_velocity": velocity,
                "missing_reason": reason,
            }
        )
        buoyancy_intervals.append(IntervalValue(expected_start, expected_end, buoyancy))
        velocity_intervals.append(IntervalValue(expected_start, expected_end, velocity))
    mean_b = interval_weighted_mean(buoyancy_intervals, window)
    max_b = interval_maximum(buoyancy_intervals, window)
    mean_w = interval_weighted_mean(velocity_intervals, window)
    max_w = interval_maximum(velocity_intervals, window)
    if any(result.value is None for result in (mean_b, max_b, mean_w, max_w)):
        _require(
            all(
                result.missing_reason == "interval_value_missing"
                for result in (mean_b, max_b, mean_w, max_w)
            ),
            "Thermal correction has incomplete or malformed interval coverage.",
        )
        return None, hourly
    values = dict(
        zip(THERMAL_KEYS, (mean_b.value, max_b.value, mean_w.value, max_w.value), strict=True)
    )
    _require(
        all(math.isfinite(value) for value in values.values()),
        "Thermal correction produced a nonfinite daily value.",
    )
    return values, hourly


def _patched_quality(row: dict, values: dict[str, float]) -> dict[str, dict]:
    old = _quality_index(row)
    return {
        key: {
            **old[key],
            "quality_state": "derived",
            "missing_reason_code": None,
            "derivation_method": DERIVATION_VERSION,
            "derivation_version": DERIVATION_VERSION,
        }
        for key in values
    }


def _apply(row: dict, record: dict, correction_id: str) -> dict:
    if record["outcome"] != "patched":
        return row
    changed = json.loads(json.dumps(row))
    changed["weather"]["features"].update(record["new_values"])
    by_old_id = {
        (item["field_code"], item["field_variant"], item["statistic_type"]): index
        for index, item in enumerate(changed["weather"]["feature_quality"])
    }
    policy, _ = load_feature_policy("weather-feature-policy-v4.json")
    entries = {item.feature_key: item for item in policy.daily_fields}
    for key, quality in record["new_quality"].items():
        entry = entries[key]
        identity = (entry.field_code, entry.variant or "canonical", entry.statistic)
        changed["weather"]["feature_quality"][by_old_id[identity]] = quality
    changed["weather"]["feature_correction"] = {
        "correction_id": correction_id,
        "input_projection_sha256": record["input_projection_sha256"],
        "calculation_version": CALCULATION_VERSION,
    }
    return changed


def build_corrected_joined_dataset(
    *,
    parent_dataset_id: str,
    project_root: Path | None = None,
    database_url: str | None = None,
    expected_candidates: int | None = None,
) -> dict[str, Any]:
    root = (project_root or repository_root()).resolve()
    parent_manifest, parent_dir, examples, excluded = _parent(root, parent_dataset_id)
    candidates = [row for row in examples if _candidate(row)]
    if expected_candidates is not None:
        _require(
            len(candidates) == expected_candidates,
            f"Expected {expected_candidates} correction candidates, found {len(candidates)}.",
        )
    _require(bool(candidates), "Parent dataset has no thermal correction candidates.")
    connection = open_read_only_database(configured_database_url(database_url), root)
    connection.row_factory = sqlite3.Row
    records: list[dict] = []
    try:
        connection.execute("BEGIN")
        _require(
            connection.execute("PRAGMA quick_check").fetchone()[0] == "ok",
            "Source SQLite quick_check failed.",
        )
        _require(
            not connection.execute("PRAGMA foreign_key_check").fetchone(),
            "Source SQLite has a foreign-key violation.",
        )
        for row in sorted(candidates, key=_key):
            projection = _projection(connection, row)
            values, hourly = _evaluate(projection)
            old_quality = _quality_index(row)
            records.append(
                {
                    "key": list(_key(row)),
                    "run_key": row["weather"]["run_key"],
                    "parent_row_sha256": _sha(_encoded(row)),
                    "input_projection_sha256": _sha(_encoded(projection)),
                    "input_projection": projection,
                    "hourly_results": hourly,
                    "outcome": "patched" if values is not None else "unchanged_missing_input",
                    "old_values": {key: row["weather"]["features"][key] for key in THERMAL_KEYS},
                    "old_quality": {key: old_quality[key] for key in THERMAL_KEYS},
                    "new_values": values,
                    "new_quality": _patched_quality(row, values) if values is not None else None,
                }
            )
        connection.rollback()
    finally:
        connection.close()
    record_bytes = b"".join(_encoded(record) for record in records)
    correction_manifest = {
        "schema_version": CORRECTION_VERSION,
        "parent_dataset_id": parent_dataset_id,
        "parent_manifest_sha256": _sha((parent_dir / "manifest.json").read_bytes()),
        "parent_training_sha256": parent_manifest["outputs"]["training_examples.jsonl"]["sha256"],
        "acquisition_id": parent_manifest["acquisition_id"],
        "calculation_version": CALCULATION_VERSION,
        "allowed_feature_keys": list(THERMAL_KEYS),
        "evaluated": len(records),
        "patched": sum(record["outcome"] == "patched" for record in records),
        "unchanged_missing_input": sum(
            record["outcome"] == "unchanged_missing_input" for record in records
        ),
        "outputs": {
            "corrections.jsonl": {"bytes": len(record_bytes), "sha256": _sha(record_bytes)}
        },
    }
    correction_id = _sha(_encoded(correction_manifest))
    correction_files = {
        "corrections.jsonl": record_bytes,
        "manifest.json": _encoded({**correction_manifest, "correction_id": correction_id}),
    }
    correction_dir = root / "data/processed/joined-weather-corrections" / correction_id
    _publish(correction_dir, correction_files)
    by_key = {tuple(record["key"]): record for record in records}
    parent_lines = (parent_dir / "training_examples.jsonl").read_bytes().splitlines(keepends=True)
    _require(len(parent_lines) == len(examples), "Parent JSONL row count changed.")
    training_bytes = b"".join(
        _encoded(_apply(row, by_key[_key(row)], correction_id))
        if _key(row) in by_key and by_key[_key(row)]["outcome"] == "patched"
        else line
        for row, line in zip(examples, parent_lines, strict=True)
    )
    excluded_bytes = (parent_dir / "excluded_examples.jsonl").read_bytes()
    _require(len(excluded) == parent_manifest["excluded"], "Parent excluded rows changed.")
    outputs = {
        "training_examples.jsonl": training_bytes,
        "excluded_examples.jsonl": excluded_bytes,
    }
    joined_manifest = {
        **{
            key: value
            for key, value in parent_manifest.items()
            if key not in {"dataset_id", "schema_version", "outputs"}
        },
        "schema_version": JOIN_VERSION,
        "parent_dataset_id": parent_dataset_id,
        "correction_id": correction_id,
        "correction_manifest_sha256": _sha(correction_files["manifest.json"]),
        "outputs": {
            name: {"bytes": len(content), "sha256": _sha(content)}
            for name, content in sorted(outputs.items())
        },
    }
    dataset_id = _sha(_encoded(joined_manifest))
    joined_dir = root / "data/processed/joined-weather" / dataset_id
    _publish(
        joined_dir,
        {**outputs, "manifest.json": _encoded({**joined_manifest, "dataset_id": dataset_id})},
    )
    return {
        "correction_id": correction_id,
        "dataset_id": dataset_id,
        "evaluated": len(records),
        "patched": correction_manifest["patched"],
        "unchanged_missing_input": correction_manifest["unchanged_missing_input"],
        "examples": len(examples),
        "excluded": len(excluded),
    }
