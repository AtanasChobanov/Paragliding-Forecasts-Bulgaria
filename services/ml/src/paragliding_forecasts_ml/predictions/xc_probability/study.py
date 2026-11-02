"""Verified joined-v4 projection, grouped chronological folds and training weights."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Literal

from pydantic import Field, FiniteFloat, JsonValue, model_validator

from ...datasets.weather_join_verify import verify_joined_dataset
from ...ingestion.atmosphere.contracts import AtmosphericContract
from ...ingestion.weather.serialization import canonical_json_bytes, pretty_json_bytes, sha256_bytes
from .artifacts import artifact_directory, json_lines, publish_bundle, read_bundle
from .inputs import ForecastInput, joined_input, validate_features
from .models import Sha256
from .policy import Stage, XcPolicy, coordinate_groups, coordinate_ids, load_policy


class StudyRow(AtmosphericContract):
    row_id: Sha256
    inputs: ForecastInput
    source_season: Literal[2022, 2023, 2024]
    labels: tuple[Literal[0, 1], Literal[0, 1], Literal[0, 1]]
    sampling_weight: FiniteFloat = Field(gt=0)
    inclusion_numerator: int = Field(gt=0)
    inclusion_denominator: int = Field(gt=0)
    label_row_sha256: Sha256
    cohort_row_sha256: Sha256

    @model_validator(mode="after")
    def labels_and_weights_agree(self) -> StudyRow:
        if any(type(value) is not int for value in self.labels) or not (
            self.labels[2] <= self.labels[1] <= self.labels[0]
        ):
            raise ValueError("XC training labels must be known nested binary outcomes.")
        if self.inclusion_numerator > self.inclusion_denominator or self.sampling_weight != (
            self.inclusion_denominator / self.inclusion_numerator
        ):
            raise ValueError("XC sampling weight differs from its inverse inclusion probability.")
        if self.labels[1] and self.sampling_weight != 1:
            raise ValueError("The 200+ conversion cohort requires inclusion weight one.")
        return self


class Fold(AtmosphericContract):
    validation_season: Literal[2023, 2024]
    exclusive_training_cutoff: str
    training_row_ids: tuple[Sha256, ...] = Field(min_length=1)
    validation_row_ids: tuple[Sha256, ...] = Field(min_length=1)
    purged_row_ids: tuple[Sha256, ...]
    purged_target_dates: tuple[str, ...]


class FitWeights(AtmosphericContract):
    training_scope: Literal["2023", "2024", "final"]
    stage: Stage
    row_ids: tuple[Sha256, ...] = Field(min_length=1)
    row_weights: tuple[FiniteFloat, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def weights_match_rows(self) -> FitWeights:
        if len(self.row_ids) != len(self.row_weights) or len(set(self.row_ids)) != len(
            self.row_ids
        ):
            raise ValueError("XC fit weights require one value per distinct row ID.")
        if any(weight <= 0 for weight in self.row_weights):
            raise ValueError("XC fit weights must be finite and positive.")
        return self


class StudyMetadata(AtmosphericContract):
    schema_version: Literal["xc-probability-study/1"] = "xc-probability-study/1"
    dataset_id: Sha256
    parent_dataset_id: Sha256
    correction_id: Sha256
    cohort_plan_id: Sha256
    source_audit_id: Sha256
    dataset_manifest_sha256: Sha256
    cohort_manifest_sha256: Sha256
    site_categories: tuple[tuple[int, str], ...] = Field(min_length=7, max_length=7)
    feature_ids: tuple[str, ...] = Field(min_length=67, max_length=67)
    coordinate_ids: tuple[str, ...] = Field(min_length=82, max_length=82)
    coordinate_groups: tuple[str, ...] = Field(min_length=82, max_length=82)
    folds: tuple[Fold, Fold]
    summary: dict[str, JsonValue]


@dataclass(frozen=True)
class LoadedStudy:
    metadata: StudyMetadata
    rows: tuple[StudyRow, ...]
    weights: tuple[FitWeights, ...]


def adapt_joined_rows(
    lines: list[bytes], selected: list[dict], policy: XcPolicy
) -> tuple[StudyRow, ...]:
    cohort = {}
    for item in selected:
        if item["split"] != "development":
            continue
        key = item["site_id"], item["target_local_date"]
        if key in cohort:
            raise ValueError("Cohort repeats a development site-day.")
        cohort[key] = item
    result = []
    for line in lines:
        source = json.loads(line)
        key = source["site_id"], source["target_local_date"]
        if source["split"] != "development" or key not in cohort:
            raise ValueError("Joined row is outside the verified development cohort.")
        selected_row = cohort[key]
        if (
            any(
                source[key] != selected_row[key]
                for key in ("site_slug", "sampling_weight", "inclusion_probability")
            )
            or source["label_evidence"]["label_row_sha256"] != selected_row["label_row_sha256"]
        ):
            raise ValueError("Joined row differs from verified cohort labels or sampling metadata.")
        states = tuple(source["label_evidence"]["labels"][str(t)]["state"] for t in (100, 200, 300))
        if any(state not in {"positive", "negative"} for state in states) or states != tuple(
            selected_row["labels"][str(t)] for t in (100, 200, 300)
        ):
            raise ValueError("Joined labels are unknown or disagree with the verified cohort.")
        fraction = source["inclusion_probability"]
        result.append(
            StudyRow(
                row_id=sha256_bytes(line),
                inputs=joined_input(source, policy),
                source_season=selected_row["source_season"],
                labels=tuple(int(state == "positive") for state in states),
                sampling_weight=source["sampling_weight"],
                inclusion_numerator=fraction["numerator"],
                inclusion_denominator=fraction["denominator"],
                label_row_sha256=selected_row["label_row_sha256"],
                cohort_row_sha256=sha256_bytes(canonical_json_bytes(selected_row)),
            )
        )
    expected = {(site, target, horizon) for site, target in cohort for horizon in (1, 2, 3)}
    actual = {
        (row.inputs.site_id, row.inputs.target_local_date, row.inputs.horizon_days)
        for row in result
    }
    if actual != expected or len(actual) != len(result):
        raise ValueError("Study must cover every selected site-day exactly once at each horizon.")
    return tuple(
        sorted(
            result,
            key=lambda row: (
                row.inputs.target_local_date,
                row.inputs.site_id,
                row.inputs.horizon_days,
            ),
        )
    )


def validate_rows(rows: tuple[StudyRow, ...], policy: XcPolicy) -> None:
    if not rows or len({row.row_id for row in rows}) != len(rows):
        raise ValueError("Study row IDs must be distinct and nonempty.")
    groups = defaultdict(list)
    seasons_by_date = defaultdict(set)
    sites = defaultdict(set)
    for row in rows:
        validate_features(row.inputs, policy, require_available=True)
        groups[(row.inputs.site_id, row.inputs.target_local_date)].append(row)
        seasons_by_date[row.inputs.target_local_date].add(row.source_season)
        sites[row.inputs.site_id].add(row.inputs.site_slug)
    if len(sites) != 7 or any(len(slugs) != 1 for slugs in sites.values()):
        raise ValueError("Study requires seven stable canonical site categories.")
    if any(len(seasons) != 1 for seasons in seasons_by_date.values()):
        raise ValueError("All sites/horizons on one target date must have the same source season.")
    for group in groups.values():
        if sorted(row.inputs.horizon_days for row in group) != [1, 2, 3]:
            raise ValueError("Every training site-day must retain exactly three horizons.")
        signatures = {
            (
                row.source_season,
                row.labels,
                row.sampling_weight,
                row.inclusion_numerator,
                row.inclusion_denominator,
                row.label_row_sha256,
                row.cohort_row_sha256,
            )
            for row in group
        }
        if len(signatures) != 1:
            raise ValueError(
                "Site-day outcomes, cohort identity or weights differ across horizons."
            )


def make_folds(rows: tuple[StudyRow, ...]) -> tuple[Fold, Fold]:
    folds = []
    for validation_season in (2023, 2024):
        validation = [row for row in rows if row.source_season == validation_season]
        training = [row for row in rows if row.source_season < validation_season]
        if not validation or not training:
            raise ValueError("Both chronological trial training/validation parts must be nonempty.")
        cutoff = min(row.inputs.issue_local_date for row in validation)
        purged = [row for row in training if row.inputs.target_local_date >= cutoff]
        kept = [row for row in training if row.inputs.target_local_date < cutoff]
        folds.append(
            Fold(
                validation_season=validation_season,
                exclusive_training_cutoff=cutoff,
                training_row_ids=tuple(row.row_id for row in kept),
                validation_row_ids=tuple(row.row_id for row in validation),
                purged_row_ids=tuple(row.row_id for row in purged),
                purged_target_dates=tuple(sorted({row.inputs.target_local_date for row in purged})),
            )
        )
    return tuple(folds)


def training_weights(rows: tuple[StudyRow, ...], scope: str, stage: Stage) -> FitWeights:
    eligible = [row for row in rows if stage == "p100" or row.labels[0] == 1]
    unique = {(row.inputs.site_id, row.inputs.target_local_date): row for row in eligible}
    if not unique:
        raise ValueError("Conditional training has no eligible 100+ site-days.")
    mean_weight = math.fsum(row.sampling_weight for row in unique.values()) / len(unique)
    return FitWeights(
        training_scope=scope,
        stage=stage,
        row_ids=tuple(row.row_id for row in eligible),
        row_weights=tuple(row.sampling_weight / mean_weight / 3 for row in eligible),
    )


def summarize(rows: tuple[StudyRow, ...]) -> dict:
    unique = {(row.inputs.site_id, row.inputs.target_local_date): row for row in rows}
    return {
        "row_count": len(rows),
        "site_day_count": len(unique),
        "target_date_count": len({row.inputs.target_local_date for row in rows}),
        "positive_site_days": {
            str(t): sum(row.labels[index] for row in unique.values())
            for index, t in enumerate((100, 200, 300))
        },
        "sampling_weight_sum_unique_site_days": math.fsum(
            row.sampling_weight for row in unique.values()
        ),
        "rows_by_horizon": {
            str(h): sum(row.inputs.horizon_days == h for row in rows) for h in (1, 2, 3)
        },
    }


def compile_study(rows: tuple[StudyRow, ...], *, lineage: dict, policy: XcPolicy) -> LoadedStudy:
    validate_rows(rows, policy)
    folds = make_folds(rows)
    by_id = {row.row_id: row for row in rows}
    weights = []
    for fold in folds:
        for stage in ("p100", "q200"):
            weights.append(
                training_weights(
                    tuple(by_id[key] for key in fold.training_row_ids),
                    str(fold.validation_season),
                    stage,
                )
            )
    weights.extend(training_weights(rows, "final", stage) for stage in ("p100", "q200"))
    categories = tuple(sorted({(row.inputs.site_id, row.inputs.site_slug) for row in rows}))
    summary = {
        **summarize(rows),
        "source_seasons": {
            str(season): summarize(tuple(row for row in rows if row.source_season == season))
            for season in policy.development_seasons
        },
    }
    metadata = StudyMetadata(
        **lineage,
        site_categories=categories,
        feature_ids=tuple(item.feature_id for item in policy.required_features),
        coordinate_ids=coordinate_ids(policy, tuple(site for site, _ in categories)),
        coordinate_groups=coordinate_groups(policy),
        folds=folds,
        summary=summary,
    )
    return LoadedStudy(metadata=metadata, rows=rows, weights=tuple(weights))


def _assert_pinned_counts(study: LoadedStudy) -> None:
    summary = study.metadata.summary
    expected = {
        "row_count": 960,
        "site_day_count": 320,
        "target_date_count": 235,
        "positive_site_days": {"100": 160, "200": 42, "300": 3},
    }
    if any(summary[key] != value for key, value in expected.items()):
        raise ValueError(
            "Pinned corrected-v4 study counts differ from the accepted 960-row inventory."
        )
    for season, count, positives in (
        (2022, 94, (43, 10, 0)),
        (2023, 106, (53, 13, 2)),
        (2024, 120, (64, 19, 1)),
    ):
        part = summary["source_seasons"][str(season)]
        if part["site_day_count"] != count or part["positive_site_days"] != dict(
            zip(("100", "200", "300"), positives)
        ):
            raise ValueError("Pinned source-season support differs from the accepted inventory.")
    for fold, counts, cutoff in zip(
        study.metadata.folds, ((282, 318), (600, 360)), ("2022-09-28", "2023-10-02"), strict=True
    ):
        if (len(fold.training_row_ids), len(fold.validation_row_ids)) != counts or (
            fold.exclusive_training_cutoff != cutoff or fold.purged_row_ids
        ):
            raise ValueError(
                "Pinned chronological fold boundaries/counts differ from the accepted inventory."
            )


def _source_manifest(payload: bytes, id_field: str, expected_id: str) -> dict:
    manifest = json.loads(payload)
    if (
        manifest[id_field] != expected_id
        or sha256_bytes(
            canonical_json_bytes({key: value for key, value in manifest.items() if key != id_field})
        )
        != expected_id
    ):
        raise ValueError("Frozen upstream manifest identity differs.")
    return manifest


def validate_study_payload(payloads: dict[str, bytes]) -> LoadedStudy:
    if set(payloads) != {
        "policy.json",
        "study.json",
        "rows.jsonl",
        "weights.json",
        "dataset_manifest.json",
        "cohort_manifest.json",
    }:
        raise ValueError("Study bundle has unexpected or missing files.")
    policy, _ = load_policy()
    metadata = StudyMetadata.model_validate_json(payloads["study.json"])
    rows = tuple(StudyRow.model_validate_json(line) for line in payloads["rows.jsonl"].splitlines())
    json_lines(payloads["rows.jsonl"])
    lineage_keys = (
        "dataset_id",
        "parent_dataset_id",
        "correction_id",
        "cohort_plan_id",
        "source_audit_id",
        "dataset_manifest_sha256",
        "cohort_manifest_sha256",
    )
    rebuilt = compile_study(
        rows, lineage={key: getattr(metadata, key) for key in lineage_keys}, policy=policy
    )
    if rebuilt.metadata != metadata or json.loads(payloads["weights.json"]) != {
        "weights": [weight.model_dump(mode="json") for weight in rebuilt.weights]
    }:
        raise ValueError("Frozen study summary, temporal folds or weights differ from its rows.")
    for name, field, artifact_id, digest in (
        (
            "dataset_manifest.json",
            "dataset_id",
            metadata.dataset_id,
            metadata.dataset_manifest_sha256,
        ),
        (
            "cohort_manifest.json",
            "plan_id",
            metadata.cohort_plan_id,
            metadata.cohort_manifest_sha256,
        ),
    ):
        if sha256_bytes(payloads[name]) != digest:
            raise ValueError("Frozen source manifest bytes differ from study lineage.")
        _source_manifest(payloads[name], field, artifact_id)
    source = json.loads(payloads["dataset_manifest.json"])
    if (
        source.get("schema_version") != policy.dataset_schema_version
        or source.get("split") != "development"
        or (source.get("excluded") != 0 or source.get("examples") != len(rows))
        or any(
            source.get(key) != getattr(metadata, key)
            for key in ("parent_dataset_id", "correction_id", "cohort_plan_id", "source_audit_id")
        )
    ):
        raise ValueError("Study dataset lineage or development boundary differs.")
    if json.loads(payloads["cohort_manifest.json"])["source_audit_id"] != metadata.source_audit_id:
        raise ValueError("Frozen cohort points to a different source label audit.")
    return rebuilt


def load_study(*, study_id: str, project_root: Path) -> LoadedStudy:
    directory = artifact_directory(project_root, "study", study_id)
    manifest, payloads = read_bundle(directory, kind="study", artifact_id=study_id)
    if manifest.parents:
        raise ValueError("A study cannot have downstream XC artifact parents.")
    return validate_study_payload(payloads)


def prepare_study(*, dataset_id: str, project_root: Path) -> dict:
    started_at = perf_counter()
    root = project_root.resolve()
    policy, _ = load_policy()
    if dataset_id != policy.pinned_dataset_id:
        raise ValueError("This XC version requires the pinned corrected-v4 development dataset.")
    verification = verify_joined_dataset(dataset_id=dataset_id, project_root=root)
    if verification.get("verified") is not True or verification.get("excluded") != 0:
        raise ValueError("Study requires a successfully verified dataset with zero exclusions.")
    directory = root / "data/processed/joined-weather" / dataset_id
    dataset_bytes = (directory / "manifest.json").read_bytes()
    dataset = _source_manifest(dataset_bytes, "dataset_id", dataset_id)
    if (
        dataset["schema_version"] != policy.dataset_schema_version
        or dataset["split"] != "development"
    ):
        raise ValueError("XC preparation requires corrected-v4 development data.")
    cohort_dir = root / "data/processed/weather-cohorts" / dataset["cohort_plan_id"]
    cohort_bytes = (cohort_dir / "manifest.json").read_bytes()
    cohort = _source_manifest(cohort_bytes, "plan_id", dataset["cohort_plan_id"])

    def checked_bytes(path: Path, expected: dict) -> bytes:
        content = path.read_bytes()
        if expected != {"bytes": len(content), "sha256": sha256_bytes(content)}:
            raise ValueError(f"Verified study source changed before projection: {path.name}.")
        return content

    training = checked_bytes(
        directory / "training_examples.jsonl", dataset["outputs"]["training_examples.jsonl"]
    )
    selected = checked_bytes(
        cohort_dir / "selected_site_days.jsonl", cohort["outputs"]["selected_site_days.jsonl"]
    )
    excluded = checked_bytes(
        directory / "excluded_examples.jsonl", dataset["outputs"]["excluded_examples.jsonl"]
    )
    if excluded or dataset["excluded"] != 0:
        raise ValueError("XC preparation cannot silently drop excluded rows.")
    json_lines(training)
    rows = adapt_joined_rows(training.splitlines(keepends=True), json_lines(selected), policy)
    lineage = {
        **{
            key: dataset[key]
            for key in (
                "dataset_id",
                "parent_dataset_id",
                "correction_id",
                "cohort_plan_id",
                "source_audit_id",
            )
        },
        "dataset_manifest_sha256": sha256_bytes(dataset_bytes),
        "cohort_manifest_sha256": sha256_bytes(cohort_bytes),
    }
    study = compile_study(rows, lineage=lineage, policy=policy)
    _assert_pinned_counts(study)
    payloads = {
        "study.json": pretty_json_bytes(study.metadata),
        "rows.jsonl": b"".join(canonical_json_bytes(row) for row in rows),
        "weights.json": pretty_json_bytes(
            {"weights": [weight.model_dump(mode="json") for weight in study.weights]}
        ),
        "dataset_manifest.json": dataset_bytes,
        "cohort_manifest.json": cohort_bytes,
    }
    result = publish_bundle(
        root=root,
        kind="study",
        payloads=payloads,
        started_at=started_at,
        validate_payload=validate_study_payload,
    )
    return {
        **result,
        **study.metadata.summary,
        "physical_input_count": 67,
        "coordinate_count": 82,
        "dataset_verified": True,
        "network_access": False,
        "database_access": "none",
    }
