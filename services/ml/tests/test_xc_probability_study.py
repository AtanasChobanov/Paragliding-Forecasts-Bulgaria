"""Synthetic preparation/immutable bundle checks, independent of the owner's data."""

import copy
import json
import math
import socket
import sqlite3
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from time import perf_counter
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from paragliding_forecasts_ml.ingestion.gfs.models import sofia_window_instants
from paragliding_forecasts_ml.ingestion.weather.serialization import (
    canonical_json_bytes,
    pretty_json_bytes,
    sha256_bytes,
)
from paragliding_forecasts_ml.predictions.xc_probability import artifacts, cli, study
from paragliding_forecasts_ml.predictions.xc_probability.policy import LAYER_BOUNDS, load_policy


def synthetic_sources(*, full=False):
    policy, _ = load_policy()
    selected, rows = [], []
    for season, first, day_count, site_days, positives in (
        (2022, "2021-10-01", 64, 94, (43, 10, 0)),
        (2023, "2022-10-01", 82, 106, (53, 13, 2)),
        (2024, "2023-10-05", 89, 120, (64, 19, 1)),
    ):
        keys = (
            [
                (date.fromisoformat(first) + timedelta(days=index), index % 7 + 1)
                for index in range(day_count)
            ]
            if full
            else [
                (date.fromisoformat(first) + timedelta(days=index), site)
                for index in range(2)
                for site in range(1, 8)
            ]
        )
        if full:
            keys.extend(
                (date.fromisoformat(first) + timedelta(days=index), (index + 1) % 7 + 1)
                for index in range(site_days - day_count)
            )
        for index, (target, site_id) in enumerate(keys):
            counts = positives if full else (7, 3, 0 if season == 2022 else 1)
            labels = {
                str(threshold): "positive" if index < counts[position] else "negative"
                for position, threshold in enumerate((100, 200, 300))
            }
            fraction = {"numerator": 1, "denominator": 1 if labels["200"] == "positive" else 2}
            item = {
                "site_id": site_id,
                "site_slug": f"site-{site_id}",
                "target_local_date": target.isoformat(),
                "source_season": season,
                "split": "development",
                "labels": labels,
                "label_row_sha256": "a" * 64,
                "inclusion_probability": fraction,
                "sampling_weight": float(fraction["denominator"]),
            }
            selected.append(item)
            for horizon in (1, 2, 3):
                issue = target - timedelta(days=horizon)
                weather = {
                    "run_key": str(UUID(int=target.toordinal() * 3 + horizon, version=4)),
                    "feature_contract_version": policy.feature_contract_version,
                    "required_inputs_last_modified_at_utc": f"{issue}T10:00:00Z",
                    "raw_manifest_sha256": "b" * 64,
                    "feature_manifest_sha256": "c" * 64,
                    "persistence_input_sha256": "d" * 64,
                    "features": {"feature_contract_version": policy.feature_contract_version},
                    "profile_layers": [
                        {"layer_base_agl_m": base, "layer_top_agl_m": top}
                        for base, top in LAYER_BOUNDS.values()
                    ],
                    "feature_quality": [],
                    "profile_layer_quality": [],
                }
                for feature_index, spec in enumerate(policy.required_features):
                    provenance = {
                        "field_code": spec.field_code,
                        "field_variant": spec.variant or "canonical",
                        "statistic_type": spec.statistic,
                        "native_unit": spec.canonical_unit,
                        "quality_state": "derived",
                        "missing_reason_code": None,
                        "derivation_method": spec.derivation_method,
                        "derivation_version": "synthetic/1",
                        "raw_artifact_key": "synthetic-grid",
                        "native_message_reference": "synthetic",
                    }
                    value = float(feature_index + horizon + index + 1)
                    if spec.scope == "daily":
                        weather["features"][spec.feature_key] = value
                        weather["feature_quality"].append(provenance)
                    else:
                        layer_index = 0 if spec.scope == "layer_0_1500" else 1
                        weather["profile_layers"][layer_index][spec.feature_key] = value
                        weather["profile_layer_quality"].append(
                            {**provenance, "layer_index": layer_index}
                        )
                rows.append(
                    {
                        **{
                            key: item[key]
                            for key in (
                                "site_id",
                                "site_slug",
                                "target_local_date",
                                "split",
                                "sampling_weight",
                                "inclusion_probability",
                            )
                        },
                        "horizon_days": horizon,
                        "issue_local_date": issue.isoformat(),
                        "cycle_reference_utc": f"{issue}T06:00:00Z",
                        "issue_cutoff_utc": datetime.combine(
                            issue, time(16), tzinfo=ZoneInfo("Europe/Sofia")
                        )
                        .astimezone(UTC)
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "valid_times_utc": list(sofia_window_instants(target.isoformat())),
                        "weather": weather,
                        "label_evidence": {
                            "label_row_sha256": item["label_row_sha256"],
                            "labels": {key: {"state": state} for key, state in labels.items()},
                            "positive_source_flight_ids": ["never-a-predictor"],
                        },
                    }
                )
    selected.append(
        {
            **selected[-1],
            "split": "backtest",
            "source_season": 2025,
            "target_local_date": "2025-06-01",
        }
    )
    return selected, rows


def projection(selected, rows):
    policy, _ = load_policy()
    return study.adapt_joined_rows([canonical_json_bytes(row) for row in rows], selected, policy)


def lineage():
    return {
        key: letter * 64
        for key, letter in zip(
            (
                "dataset_id",
                "parent_dataset_id",
                "correction_id",
                "cohort_plan_id",
                "source_audit_id",
                "dataset_manifest_sha256",
                "cohort_manifest_sha256",
            ),
            "abcdefa",
            strict=True,
        )
    }


def test_projection_folds_and_weights_use_source_seasons_and_unique_site_days():
    selected, source = synthetic_sources()
    rows = projection(selected, source)
    policy, _ = load_policy()
    result = study.compile_study(rows, lineage=lineage(), policy=policy)
    assert len(rows) == 126
    assert result.metadata.summary["site_day_count"] == 42
    assert result.metadata.folds[0].exclusive_training_cutoff == "2022-09-28"
    assert result.metadata.folds[1].exclusive_training_cutoff == "2023-10-02"
    assert len(result.metadata.folds[0].training_row_ids) == 42
    assert len(result.metadata.folds[1].training_row_ids) == 84
    assert len(result.metadata.coordinate_ids) == 82
    assert len(result.weights) == 6
    assert all(row.source_season in (2022, 2023, 2024) for row in rows)
    assert rows[0].source_season == 2022 and rows[0].inputs.target_local_date.startswith("2021")
    assert "never-a-predictor" not in rows[0].model_dump_json()
    assert "labels" not in rows[0].inputs.model_dump()
    by_id = {row.row_id: row for row in rows}
    for weights in result.weights:
        subset = [by_id[key] for key in weights.row_ids]
        unique = {(row.inputs.site_id, row.inputs.target_local_date) for row in subset}
        assert math.fsum(weights.row_weights) == pytest.approx(len(unique), abs=1e-12)
        if weights.stage == "q200":
            assert all(row.labels[0] == 1 for row in subset)
        per_day = {}
        for row, weight in zip(subset, weights.row_weights, strict=True):
            per_day.setdefault((row.inputs.site_id, row.inputs.target_local_date), []).append(
                weight
            )
        assert all(len(values) == 3 and len(set(values)) == 1 for values in per_day.values())
    with pytest.raises(ValueError, match="960-row"):
        study._assert_pinned_counts(result)


def test_purge_keeps_target_date_sites_and_horizons_together_and_final_refit_restores_rows():
    selected, source = synthetic_sources()
    # Put a complete 2022 site-day on the first 2023 validation issue date.
    moved = copy.deepcopy([row for row in source if row["site_id"] == 1][:3])
    moved_selected = copy.deepcopy(selected[0])
    moved_selected["target_local_date"] = "2022-09-28"
    for row in moved:
        row["target_local_date"] = "2022-09-28"
        issue = date(2022, 9, 28) - timedelta(days=row["horizon_days"])
        row.update(
            issue_local_date=str(issue),
            cycle_reference_utc=f"{issue}T06:00:00Z",
            issue_cutoff_utc=f"{issue}T13:00:00Z",
            valid_times_utc=list(sofia_window_instants("2022-09-28")),
        )
        row["weather"]["required_inputs_last_modified_at_utc"] = f"{issue}T10:00:00Z"
    result = study.compile_study(
        projection([*selected, moved_selected], [*source, *moved]),
        lineage=lineage(),
        policy=load_policy()[0],
    )
    fold = result.metadata.folds[0]
    assert len(fold.purged_row_ids) == 3 and fold.purged_target_dates == ("2022-09-28",)
    assert not set(fold.purged_row_ids) & set(fold.training_row_ids)
    final = next(
        weights
        for weights in result.weights
        if weights.training_scope == "final" and weights.stage == "p100"
    )
    assert set(fold.purged_row_ids) <= set(final.row_ids)


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "nan",
        "unit",
        "unknown_label",
        "non_nested",
        "season_2025",
        "duplicate",
        "horizon_missing",
        "source_late",
        "inverse_weight",
        "repeated_provenance",
    ],
)
def test_projection_rejects_unusable_or_inconsistent_training_evidence(change):
    selected, source = synthetic_sources()
    row = source[0]
    if change == "missing":
        row["weather"]["features"]["air_temperature_2m_mean_k"] = None
        row["weather"]["feature_quality"][0].update(
            quality_state="missing", missing_reason_code="missing"
        )
    elif change == "nan":
        # Nonfinite source is rejected even before artifact publication.
        row["weather"]["features"]["air_temperature_2m_mean_k"] = float("nan")
    elif change == "unit":
        row["weather"]["feature_quality"][0]["native_unit"] = "Celsius"
    elif change in {"unknown_label", "non_nested"}:
        state = "unknown" if change == "unknown_label" else "negative"
        row["label_evidence"]["labels"]["100"]["state"] = state
        selected[0]["labels"]["100"] = state
    elif change == "season_2025":
        selected[0]["source_season"] = 2025
    elif change == "duplicate":
        source.append(copy.deepcopy(row))
    elif change == "horizon_missing":
        del source[0]
    elif change == "source_late":
        row["weather"]["required_inputs_last_modified_at_utc"] = (
            datetime.fromisoformat(row["issue_cutoff_utc"]) + timedelta(hours=1)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    elif change == "inverse_weight":
        source[0]["sampling_weight"] = 2.0
        selected[0]["sampling_weight"] = 2.0
    else:
        row["weather"]["feature_quality"].append(
            copy.deepcopy(row["weather"]["feature_quality"][0])
        )
    with pytest.raises(ValueError):
        projection(selected, source)


def write_sources(root, selected, rows):
    selected_bytes = b"".join(canonical_json_bytes(item) for item in selected)
    cohort = {
        "source_audit_id": "a" * 64,
        "outputs": {
            "selected_site_days.jsonl": {
                "bytes": len(selected_bytes),
                "sha256": sha256_bytes(selected_bytes),
            }
        },
    }
    cohort_id = sha256_bytes(canonical_json_bytes(cohort))
    cohort_directory = root / "data/processed/weather-cohorts" / cohort_id
    cohort_directory.mkdir(parents=True)
    (cohort_directory / "manifest.json").write_bytes(
        canonical_json_bytes({**cohort, "plan_id": cohort_id})
    )
    (cohort_directory / "selected_site_days.jsonl").write_bytes(selected_bytes)
    training = b"".join(canonical_json_bytes(row) for row in rows)
    dataset = {
        "schema_version": "weather-flight-joined-dataset/4",
        "split": "development",
        "parent_dataset_id": "b" * 64,
        "correction_id": "c" * 64,
        "cohort_plan_id": cohort_id,
        "source_audit_id": "a" * 64,
        "examples": len(rows),
        "excluded": 0,
        "outputs": {
            "training_examples.jsonl": {"bytes": len(training), "sha256": sha256_bytes(training)},
            "excluded_examples.jsonl": {"bytes": 0, "sha256": sha256_bytes(b"")},
        },
    }
    dataset_id = sha256_bytes(canonical_json_bytes(dataset))
    dataset_directory = root / "data/processed/joined-weather" / dataset_id
    dataset_directory.mkdir(parents=True)
    (dataset_directory / "manifest.json").write_bytes(
        canonical_json_bytes({**dataset, "dataset_id": dataset_id})
    )
    (dataset_directory / "training_examples.jsonl").write_bytes(training)
    (dataset_directory / "excluded_examples.jsonl").write_bytes(b"")
    return dataset_id


def no_external_access(*args, **kwargs):
    raise AssertionError("Synthetic XC preparation must not open SQLite or use the network.")


def test_prepare_full_synthetic_inventory_reuses_verifier_once_and_freezes_reloadable_bundle(
    tmp_path, monkeypatch
):
    selected, rows = synthetic_sources(full=True)
    dataset_id = write_sources(tmp_path, selected, rows)
    policy, fingerprint = load_policy()
    # Only the source locator changes: the complete accepted 960-row regression
    # inventory and original packaged model policy are exercised unchanged.
    monkeypatch.setattr(
        study,
        "load_policy",
        lambda: (policy.model_copy(update={"pinned_dataset_id": dataset_id}), fingerprint),
    )
    calls = []

    def verify(**kwargs):
        calls.append(kwargs)
        return {"verified": True, "examples": 960, "excluded": 0}

    monkeypatch.setattr(study, "verify_joined_dataset", verify)
    monkeypatch.setattr(sqlite3, "connect", no_external_access)
    monkeypatch.setattr(socket, "create_connection", no_external_access)
    first = study.prepare_study(dataset_id=dataset_id, project_root=tmp_path)
    assert calls == [{"dataset_id": dataset_id, "project_root": tmp_path}]
    assert first["row_count"] == 960 and first["physical_input_count"] == 67
    assert first["coordinate_count"] == 82 and first["target_date_count"] == 235
    assert first["positive_site_days"] == {"100": 160, "200": 42, "300": 3}
    directory = Path(first["output_directory"])
    assert not (directory / "report.md").exists()
    original_manifest = (directory / "manifest.json").read_bytes()
    assert first["published_bytes"] == sum(path.stat().st_size for path in directory.iterdir())
    assert first["elapsed_seconds"] >= 0
    second = study.prepare_study(dataset_id=dataset_id, project_root=tmp_path)
    assert len(calls) == 2 and second["study_id"] == first["study_id"] and second["reused"]
    assert (directory / "manifest.json").read_bytes() == original_manifest
    monkeypatch.setattr(study, "verify_joined_dataset", no_external_access)
    loaded = study.load_study(study_id=first["study_id"], project_root=tmp_path)
    assert len(loaded.rows) == 960 and len(loaded.weights) == 6
    assert [
        (len(fold.training_row_ids), len(fold.validation_row_ids)) for fold in loaded.metadata.folds
    ] == [(282, 318), (600, 360)]
    assert [
        sum(
            row.labels[2]
            for row in loaded.rows
            if row.row_id in set(fold.training_row_ids) and row.inputs.horizon_days == 1
        )
        for fold in loaded.metadata.folds
    ] == [0, 2]
    _, payloads = artifacts.read_bundle(directory, kind="study", artifact_id=first["study_id"])
    for filename in ("study.json", "weights.json"):
        changed = json.loads(payloads[filename])
        if filename == "study.json":
            changed["summary"]["row_count"] += 1
        else:
            changed["weights"][0]["row_weights"][0] *= 3
        with pytest.raises(ValueError, match="summary, temporal folds or weights"):
            study.validate_study_payload({**payloads, filename: pretty_json_bytes(changed)})
    (directory / "rows.jsonl").write_bytes(b"changed\n")
    with pytest.raises(ValueError, match="payload changed"):
        study.load_study(study_id=first["study_id"], project_root=tmp_path)


@pytest.mark.parametrize(
    "change", ["bytes", "missing_file", "extra_file", "identity", "wrong_kind", "versions"]
)
def test_bundle_consumers_reject_changed_or_incompatible_artifacts(tmp_path, change):
    result = artifacts.publish_bundle(
        root=tmp_path,
        kind="model",
        payloads={"model.json": b"{}\n"},
        started_at=perf_counter(),
        validate_payload=lambda payloads: None,
    )
    directory = Path(result["output_directory"])
    if change == "bytes":
        (directory / "model.json").write_bytes(b"[]\n")
    elif change == "missing_file":
        (directory / "model.json").unlink()
    elif change == "extra_file":
        (directory / "unexpected.json").write_bytes(b"{}\n")
    else:
        manifest = json.loads((directory / "manifest.json").read_bytes())
        if change == "identity":
            manifest["artifact_id"] = "a" * 64
        elif change == "wrong_kind":
            manifest["kind"] = "trial"
        else:
            manifest["numerical_versions"]["numpy"] = "unexpected"
            # Rehash the changed manifest so compatibility is independently checked.
            identity = {
                key: value
                for key, value in manifest.items()
                if key not in {"artifact_id", "created_at_utc", "execution"}
            }
            new_id = sha256_bytes(canonical_json_bytes(identity))
            manifest["artifact_id"] = new_id
            target = directory.parent / new_id
            directory.rename(target)
            directory = target
            result["model_id"] = new_id
        (directory / "manifest.json").write_bytes(pretty_json_bytes(manifest))
    with pytest.raises(ValueError):
        artifacts.read_bundle(directory, kind="model", artifact_id=result["model_id"])


def test_producer_validates_before_publication_and_rejects_changed_existing_bytes(tmp_path):
    def reject(payloads):
        raise ValueError("invalid payload")

    with pytest.raises(ValueError, match="invalid payload"):
        artifacts.publish_bundle(
            root=tmp_path,
            kind="study",
            payloads={},
            started_at=perf_counter(),
            validate_payload=reject,
        )
    assert not (tmp_path / "data").exists()
    first = artifacts.publish_bundle(
        root=tmp_path,
        kind="study",
        payloads={"data.json": b"{}\n"},
        started_at=perf_counter(),
        validate_payload=lambda payloads: None,
    )
    (Path(first["output_directory"]) / "data.json").write_bytes(b"changed")
    with pytest.raises(ValueError, match="payload changed"):
        artifacts.publish_bundle(
            root=tmp_path,
            kind="study",
            payloads={"data.json": b"{}\n"},
            started_at=perf_counter(),
            validate_payload=lambda payloads: None,
        )


def test_cli_emits_one_json_object_and_errors_only_to_stderr(tmp_path, monkeypatch, capsys):
    received = []

    def prepare(**kwargs):
        received.append(kwargs)
        return {"study_id": "a" * 64, "output_directory": str(tmp_path), "elapsed_seconds": 0.1}

    monkeypatch.setattr(cli, "prepare_study", prepare)
    assert cli.main(["prepare", "--dataset-id", "b" * 64, "--project-root", str(tmp_path)]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["study_id"] == "a" * 64 and not output.err
    assert received == [{"dataset_id": "b" * 64, "project_root": tmp_path}]
    monkeypatch.setattr(
        cli, "prepare_study", lambda **kwargs: (_ for _ in ()).throw(ValueError("bad source"))
    )
    assert cli.main(["prepare", "--dataset-id", "b" * 64]) == 1
    output = capsys.readouterr()
    assert not output.out and "bad source" in output.err
    with pytest.raises(SystemExit):
        cli.main(["verify"])
