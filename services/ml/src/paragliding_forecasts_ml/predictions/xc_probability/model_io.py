"""Final refit and self-contained, hash-verified JSON model loading."""

from __future__ import annotations

from importlib.metadata import version
from importlib.resources import files
from pathlib import Path
from time import perf_counter
from typing import Literal

import numpy as np
from pydantic import Field, JsonValue

from ...ingestion.atmosphere.contracts import AtmosphericContract
from ...ingestion.weather.serialization import canonical_json_bytes, pretty_json_bytes, sha256_bytes
from .artifacts import artifact_directory, identity, numerical_versions, publish_bundle, read_bundle
from .experiment import experiment_payloads, validate_experiment_payload
from .learning import (
    LOGISTIC_ARGUMENTS,
    FittedStage,
    conversion_support,
    fit_stage,
    grouped_contributions,
)
from .models import ArtifactManifest, ArtifactParent, ConversionSupport, Sha256
from .policy import POLICY_RESOURCE, DriverGroup, coordinate_groups, coordinate_ids, load_policy
from .selection import SelectionMetadata, load_selection, selection_parents, selection_report
from .study import load_study


class FinalModel(AtmosphericContract):
    schema_version: Literal["xc-probability-model/1"] = "xc-probability-model/1"
    study_id: Sha256
    selection_id: Sha256
    dataset_id: Sha256
    policy_sha256: Sha256
    selection_snapshot: SelectionMetadata
    selection_identity: dict[str, JsonValue]
    site_categories: tuple[tuple[int, str], ...] = Field(min_length=7, max_length=7)
    feature_ids: tuple[str, ...] = Field(min_length=67, max_length=67)
    coordinate_ids: tuple[str, ...] = Field(min_length=82, max_length=82)
    coordinate_group_ids: tuple[str, ...] = Field(min_length=82, max_length=82)
    driver_groups: tuple[DriverGroup, ...] = Field(min_length=15, max_length=15)
    models: tuple[FittedStage, FittedStage]
    conversion: ConversionSupport
    training_summary: dict[str, JsonValue]
    training_row_ids_sha256: dict[Literal["p100", "q200"], Sha256]
    algorithm: dict[str, JsonValue]
    logistic_arguments: dict[str, JsonValue]
    threadpoolctl_version: str
    confidence_policy_version: Literal["xc-confidence/1"] = "xc-confidence/1"
    confidence_reasons: dict[str, tuple[str, ...]]
    confidence_notes: dict[str, str]
    explanation_policy_version: Literal["xc-grouped-logit/1"] = "xc-grouped-logit/1"
    templates: dict[str, str]
    data_status: Literal["baseline"] = "baseline"
    calibration_status: Literal["not_calibrated"] = "not_calibrated"
    independent_reliability_status: Literal["unverified"] = "unverified"
    available_confidence_level: Literal["low"] = "low"


def validate_model_payload(payloads: dict[str, bytes]) -> FinalModel:
    model = FinalModel.model_validate_json(payloads["model.json"])
    experiment_version = model.selection_snapshot.experiment_version
    validate_experiment_payload(payloads, experiment_version)
    if set(payloads) != {"policy.json", "model.json"} | set(
        experiment_payloads(experiment_version)
    ):
        raise ValueError("Final model bundle has unexpected or missing files.")
    policy, policy_sha = load_policy()
    if (
        model.policy_sha256 != policy_sha
        or model.algorithm != policy.algorithm
        or (
            model.logistic_arguments != LOGISTIC_ARGUMENTS
            or model.threadpoolctl_version != version("threadpoolctl")
        )
    ):
        raise ValueError("Final model method, numerical compatibility or policy differs.")
    if model.feature_ids != tuple(spec.feature_id for spec in policy.required_features) or (
        model.coordinate_ids
        != coordinate_ids(policy, tuple(site for site, _ in model.site_categories))
        or model.coordinate_group_ids != coordinate_groups(policy)
        or model.driver_groups != policy.groups
    ):
        raise ValueError("Final model coordinate/category/group inventory differs from policy.")
    if (
        model.confidence_reasons != policy.confidence_reasons
        or model.confidence_notes != policy.confidence_notes
        or model.templates != policy.templates
    ):
        raise ValueError("Final model explanation/confidence catalog differs from policy.")
    snapshot = model.selection_snapshot
    if snapshot.study_id != model.study_id or snapshot.dataset_id != model.dataset_id:
        raise ValueError("Final model and frozen selection source lineage differ.")
    # Reconstruct only nonidentity metadata. Verify the exact selection identity
    # and payloads from the embedded snapshot, without reading study/trial files.
    selection_manifest = ArtifactManifest.model_validate_json(
        canonical_json_bytes(
            {
                **model.selection_identity,
                "artifact_id": model.selection_id,
                "created_at_utc": "1970-01-01T00:00:00Z",
                "execution": {"elapsed_seconds_before_publication": 0.0},
            }
        )
    )
    if (
        selection_manifest.kind != "selection"
        or identity(selection_manifest) != model.selection_identity
        or (
            sha256_bytes(canonical_json_bytes(model.selection_identity)) != model.selection_id
            or selection_manifest.parents != selection_parents(snapshot)
            or selection_manifest.numerical_versions != numerical_versions()
        )
    ):
        raise ValueError("Final model frozen selection identity or parents differ.")
    selection_payloads = {
        **experiment_payloads(experiment_version),
        "selection.json": pretty_json_bytes(snapshot),
        "report.md": selection_report(snapshot),
        "policy.json": files(__package__).joinpath("resources", POLICY_RESOURCE).read_bytes(),
    }
    if (
        set(selection_manifest.files) != set(selection_payloads)
        or selection_manifest.policy_sha256 != policy_sha
    ):
        raise ValueError("Frozen selection payload contract differs.")
    for name, content in selection_payloads.items():
        digest = selection_manifest.files[name]
        if digest.sha256 != sha256_bytes(content) or digest.byte_count != len(content):
            raise ValueError(
                "Final model selection snapshot differs from its original artifact identity."
            )
    if tuple(stage.parameters.stage for stage in model.models) != ("p100", "q200"):
        raise ValueError("Final model must contain the p100 and q200 stages exactly once.")
    first, conditional = (stage.parameters for stage in model.models)
    if (first.regularization_c, conditional.regularization_c) != (
        snapshot.winner.c100,
        snapshot.winner.c200,
    ):
        raise ValueError("Final fitted regularization differs from the verified selection.")
    summary = model.training_summary
    seasons = summary["source_seasons"]
    if (
        set(seasons) != {str(season) for season in policy.development_seasons}
        or any(
            sum(part[key] for part in seasons.values()) != summary[key]
            for key in ("row_count", "site_day_count", "target_date_count")
        )
        or any(
            sum(part["positive_site_days"][threshold] for part in seasons.values())
            != summary["positive_site_days"][threshold]
            for threshold in ("100", "200", "300")
        )
    ):
        raise ValueError(
            "Final training summary must retain consistent development-season support."
        )
    if (
        any(not slug.strip() for _, slug in model.site_categories)
        or len({slug for _, slug in model.site_categories}) != 7
    ):
        raise ValueError("Final model site categories require seven distinct nonblank slugs.")
    if (
        first.support.row_count != summary["row_count"]
        or first.support.site_day_count != summary["site_day_count"]
        or (
            first.support.target_date_count != summary["target_date_count"]
            or first.support.positive_site_day_count != summary["positive_site_days"]["100"]
            or conditional.support.site_day_count != first.support.positive_site_day_count
            or conditional.support.positive_site_day_count != summary["positive_site_days"]["200"]
            or model.conversion.k != summary["positive_site_days"]["300"]
            or model.conversion.n != conditional.support.positive_site_day_count
        )
    ):
        raise ValueError("Final training support or unique-site-day conversion counts disagree.")
    if (
        model.conversion.study_id != model.study_id
        or any(
            seasons != policy.development_seasons
            for seasons in (
                first.support.source_seasons,
                conditional.support.source_seasons,
                model.conversion.training_source_seasons,
            )
        )
        or set(model.training_row_ids_sha256) != {"p100", "q200"}
    ):
        raise ValueError("Final fit requires all development seasons with explicit row lineage.")
    for stage in model.models:
        encoded = np.asarray([check.encoded for check in stage.self_checks], dtype=np.float64)
        grouped_contributions(stage.parameters, encoded, model.coordinate_group_ids)
    return model


def load_model(*, model_id: str, project_root: Path) -> FinalModel:
    manifest, payloads = read_bundle(
        artifact_directory(project_root, "model", model_id), kind="model", artifact_id=model_id
    )
    model = validate_model_payload(payloads)
    if manifest.parents != (
        ArtifactParent(kind="study", artifact_id=model.study_id),
        ArtifactParent(kind="selection", artifact_id=model.selection_id),
    ):
        raise ValueError("Final model manifest parents differ from its frozen lineage.")
    return model


def train_final(*, study_id: str, selection_id: str, project_root: Path) -> dict:
    started_at = perf_counter()
    study = load_study(study_id=study_id, project_root=project_root)
    selection = load_selection(
        selection_id=selection_id, study_id=study_id, study=study, project_root=project_root
    )
    policy, policy_sha = load_policy()
    by_id = {row.row_id: row for row in study.rows}
    site_ids = tuple(site for site, _ in study.metadata.site_categories)
    models, row_hashes = [], {}
    for stage, c in (
        ("p100", selection.metadata.winner.c100),
        ("q200", selection.metadata.winner.c200),
    ):
        weights = next(
            part for part in study.weights if part.training_scope == "final" and part.stage == stage
        )
        rows = tuple(by_id[key] for key in weights.row_ids)
        models.append(
            fit_stage(
                rows,
                weights,
                regularization_c=c,
                site_ids=site_ids,
                policy=policy,
                experiment_version=selection.metadata.experiment_version,
            )
        )
        row_hashes[stage] = sha256_bytes(canonical_json_bytes({"row_ids": list(weights.row_ids)}))
    model = FinalModel(
        study_id=study_id,
        selection_id=selection_id,
        dataset_id=study.metadata.dataset_id,
        policy_sha256=policy_sha,
        selection_snapshot=selection.metadata,
        selection_identity=selection.content_identity,
        site_categories=study.metadata.site_categories,
        feature_ids=study.metadata.feature_ids,
        coordinate_ids=study.metadata.coordinate_ids,
        coordinate_group_ids=study.metadata.coordinate_groups,
        driver_groups=policy.groups,
        models=tuple(models),
        conversion=conversion_support(study.rows, study_id=study_id),
        training_summary=study.metadata.summary,
        training_row_ids_sha256=row_hashes,
        algorithm=policy.algorithm,
        logistic_arguments=LOGISTIC_ARGUMENTS,
        threadpoolctl_version=version("threadpoolctl"),
        confidence_reasons=policy.confidence_reasons,
        confidence_notes=policy.confidence_notes,
        templates=policy.templates,
    )
    result = publish_bundle(
        root=project_root.resolve(),
        kind="model",
        started_at=started_at,
        parents=(
            ArtifactParent(kind="study", artifact_id=study_id),
            ArtifactParent(kind="selection", artifact_id=selection_id),
        ),
        payloads={
            **experiment_payloads(selection.metadata.experiment_version),
            "model.json": pretty_json_bytes(model),
        },
        validate_payload=validate_model_payload,
    )
    return {
        **result,
        "study_id": study_id,
        "selection_id": selection_id,
        "experiment_version": selection.metadata.experiment_version,
        **selection.metadata.winner.model_dump(),
        "training_row_count": len(study.rows),
        "conditional_training_row_count": model.models[1].parameters.support.row_count,
        "source_seasons": list(policy.development_seasons),
        "conversion": model.conversion.model_dump(mode="json"),
        "data_status": "baseline",
        "calibration_status": "not_calibrated",
        "independent_reliability_status": "unverified",
    }
