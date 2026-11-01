"""Synthetic contract boundaries; no owner data, product runs or model fitting."""

import json
from collections import Counter
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from paragliding_forecasts_ml.ingestion.weather.features.policy import load_feature_policy
from paragliding_forecasts_ml.predictions.xc_probability import policy as policy_module
from paragliding_forecasts_ml.predictions.xc_probability.models import (
    ArtifactManifest,
    AvailableMetric,
    Confidence,
    ConversionSupport,
    MissingMetric,
    StageExplanation,
    StageParameters,
    ThresholdProbabilities,
    TrainingSupport,
)
from paragliding_forecasts_ml.predictions.xc_probability.policy import (
    coordinate_groups,
    coordinate_ids,
    load_policy,
)


def test_fixed_inventory_matches_weather_paths_units_and_exclusions():
    policy, fingerprint = load_policy()
    assert len(fingerprint) == 64
    weather, _ = load_feature_policy("weather-feature-policy-v5.json")
    daily = {item.feature_key for item in policy.required_features if item.scope == "daily"}
    assert daily == {
        item.feature_key
        for item in weather.daily_fields
        if not item.feature_key.startswith("provider_cloud_base_agl_")
    }
    assert Counter(item.scope for item in policy.required_features) == {
        "daily": 43,
        "layer_0_1500": 11,
        "layer_1500_3000": 13,
    }
    assert not any(
        "vertical_velocity" in item.feature_key
        for item in policy.required_features
        if item.scope == "layer_0_1500"
    )
    coordinates = coordinate_ids(policy, (7, 3, 9, 1, 2, 5, 4))
    assert len(coordinates) == len(set(coordinates)) == 82
    assert coordinates[70:72] == ("season.sin", "season.cos")
    assert coordinates[72:79] == (
        "site.7",
        "site.3",
        "site.9",
        "site.1",
        "site.2",
        "site.5",
        "site.4",
    )
    assert coordinates[-3:] == ("horizon.1", "horizon.2", "horizon.3")
    assert Counter(coordinate_groups(policy))["wind"] == 18
    assert set(coordinate_groups(policy)) == {group.group_id for group in policy.groups}
    for feature in policy.required_features:
        if feature.encoding == "sin_cos":
            assert f"{feature.feature_id}.sin" in coordinates
            assert f"{feature.feature_id}.cos" in coordinates
            assert feature.feature_id not in coordinates


@pytest.mark.parametrize(
    "site_ids", [(1, 2, 3), (1, 2, 3, 4, 5, 6, 6), (0, 1, 2, 3, 4, 5, 6), (True, 2, 3, 4, 5, 6, 7)]
)
def test_categories_cannot_be_invented_or_implicitly_encoded(site_ids):
    policy, _ = load_policy()
    with pytest.raises(ValueError, match="seven distinct"):
        coordinate_ids(policy, site_ids)


def test_policy_keeps_threshold_confidence_reasons_and_complete_template_catalog():
    policy, _ = load_policy()
    common = (
        "baseline_model",
        "limited_development_support",
        "independent_reliability_unverified",
        "not_calibrated",
    )
    assert policy.confidence_reasons["100"] == common
    assert policy.confidence_reasons["200"] == (
        *common,
        "sparse_200_support",
        "conditional_model_chain",
    )
    assert policy.confidence_reasons["300"] == (
        *policy.confidence_reasons["200"],
        "pooled_empirical_300_conversion",
        "no_separate_300_model",
    )
    assert set(policy.templates) == {
        "group_supports",
        "group_reduces",
        "no_distinct_driver",
        "required_inputs_missing",
        "empirical_300_method",
        "insufficient_300_support",
        "baseline_limitation",
    }
    params = {
        "group_label": "Wind",
        "stage_label": "100+ probability",
        "feature_ids": "daily.x",
        "k": 1,
        "n": 7,
    }
    assert all(template.format(**params).strip() for template in policy.templates.values())


@pytest.mark.parametrize("change", ["unit", "source_key", "group", "duplicate"])
def test_frozen_policy_rejects_drift(monkeypatch, change):
    policy, _ = load_policy()
    payload = policy.model_dump(mode="json")
    entry = payload["required_features"][0]
    if change == "unit":
        entry["canonical_unit"] = "Celsius"
    elif change == "source_key":
        entry["feature_key"] = "unknown_temperature"
        entry["feature_id"] = "daily.unknown_temperature"
    elif change == "group":
        entry["group_id"] = "wind"
    else:
        payload["required_features"][1] = entry
    resource = Mock()
    resource.joinpath.return_value.read_bytes.return_value = json.dumps(payload).encode("utf-8")
    monkeypatch.setattr(policy_module, "files", lambda package: resource)
    with pytest.raises(ValueError):
        load_policy()


@pytest.mark.parametrize(
    "k,n,state",
    [(1, 7, "supported"), (0, 10, "insufficient_300_support"), (0, 0, "insufficient_300_support")],
)
def test_conversion_retains_observed_counts_and_explicit_support(k, n, state):
    conversion = ConversionSupport(
        k=k,
        n=n,
        ratio=k / n if n else None,
        support_state=state,
        study_id="a" * 64,
        training_source_seasons=(2022,),
    )
    assert ConversionSupport.model_validate_json(conversion.model_dump_json()) == conversion
    if n:
        with pytest.raises(ValidationError, match="without smoothing"):
            ConversionSupport.model_validate(
                {**conversion.model_dump(), "ratio": (k + 0.5) / (n + 1)}
            )
    with pytest.raises(ValidationError, match="support"):
        ConversionSupport.model_validate(
            {
                **conversion.model_dump(),
                "support_state": (
                    "insufficient_300_support" if state == "supported" else "supported"
                ),
            }
        )


def stage_parameters():
    return StageParameters(
        stage="p100",
        regularization_c=0.03,
        means=(0.0,) * 72,
        scales=(1.0,) * 72,
        coefficients=(0.0,) * 82,
        intercept=0.0,
        reference=(0.0,) * 72 + (1 / 7,) * 7 + (1 / 3,) * 3,
        baseline_logit=0.0,
        support=TrainingSupport(
            row_count=12,
            site_day_count=4,
            target_date_count=3,
            positive_site_day_count=2,
            source_seasons=(2022,),
            normalized_weight_sum=4.0,
        ),
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("means", (0.0,) * 71),
        ("scales", (0.0,) * 72),
        ("coefficients", (float("nan"),) * 82),
        ("intercept", float("inf")),
        ("reference", (1.0,) * 82),
        ("baseline_logit", 1.0),
    ],
)
def test_serialized_stage_rejects_invalid_numeric_state(field, value):
    payload = stage_parameters().model_dump()
    with pytest.raises(ValidationError):
        StageParameters.model_validate({**payload, field: value})


@pytest.mark.parametrize(
    "changes",
    [
        {"row_count": 36},
        {"normalized_weight_sum": 12.0},
        {"source_seasons": (2025,)},
        {"positive_site_day_count": 4},
    ],
)
def test_support_rejects_horizon_tripling_reserved_season_and_single_class(changes):
    payload = stage_parameters().support.model_dump()
    with pytest.raises(ValidationError):
        TrainingSupport.model_validate({**payload, **changes})


def available(value):
    policy, _ = load_policy()
    return AvailableMetric(
        value=value,
        confidence=Confidence(
            note=policy.confidence_notes["100"],
            reason_codes=policy.confidence_reasons["100"],
        ),
    )


def test_metrics_reject_false_availability_confidence_and_non_nested_probabilities():
    missing = MissingMetric(missing_reason="insufficient_300_support")
    valid = ThresholdProbabilities(p100=available(0.8), p200=available(0.3), p300=missing)
    assert ThresholdProbabilities.model_validate_json(valid.model_dump_json()) == valid
    for changes in ({"p100": missing}, {"p200": available(0.9)}, {"p300": available(0.4)}):
        with pytest.raises(ValidationError, match="nested"):
            ThresholdProbabilities.model_validate({**valid.model_dump(), **changes})
    for value in (-0.1, 1.1, float("nan"), float("inf")):
        with pytest.raises(ValidationError):
            available(value)
    with pytest.raises(ValidationError):
        MissingMetric(
            missing_reason="required_inputs_missing", confidence=available(0.1).confidence
        )
    with pytest.raises(ValidationError):
        Confidence(level="high", note="Large probability", reason_codes=("baseline_model",))
    with pytest.raises(ValidationError):
        MissingMetric(missing_reason=" ")


def explanation_payload():
    policy, _ = load_policy()
    return {
        "stage": "p100",
        "baseline_logit": 0.0,
        "decision_logit": 0.0,
        "probability": 0.5,
        "groups": tuple(
            {
                "stage": "p100",
                "group_id": group.group_id,
                "kind": group.kind,
                "direction": "zero",
                "contribution_logit": 0.0,
                "source_feature_ids": (),
                "message_code": "no_distinct_driver",
                "message_params": {},
            }
            for group in policy.groups
        ),
        "top_group_ids": (),
    }


def test_explanations_validate_stage_reconstruction_and_deterministic_ranking():
    payload = explanation_payload()
    assert StageExplanation.model_validate(payload).top_group_ids == ()
    groups = [dict(group) for group in payload["groups"]]
    for index, value in ((0, 1.0), (1, -1.0)):
        groups[index].update(
            contribution_logit=value,
            direction="raises" if value > 0 else "lowers",
            message_code="group_supports" if value > 0 else "group_reduces",
        )
    payload.update(groups=tuple(groups), top_group_ids=("humidity", "surface_temperature"))
    assert StageExplanation.model_validate(payload).probability == 0.5
    for change in (
        {"decision_logit": 1.0},
        {"probability": 0.9},
        {"top_group_ids": ("surface_temperature", "humidity")},
        {"stage": "q200"},
    ):
        with pytest.raises(ValidationError):
            StageExplanation.model_validate({**payload, **change})


@pytest.mark.parametrize("name", ["../report.md", "C:report.md", "a/b", "a\\b", "manifest.json"])
def test_manifest_rejects_unsafe_files(name):
    with pytest.raises(ValidationError):
        ArtifactManifest(
            kind="study",
            artifact_id="a" * 64,
            policy_sha256="b" * 64,
            parents=(),
            files={
                "report.md": {"sha256": "c" * 64, "byte_count": 1},
                name: {"sha256": "c" * 64, "byte_count": 1},
            },
            numerical_versions={"python": "3.12"},
            created_at_utc="2026-11-02T10:00:00Z",
        )
