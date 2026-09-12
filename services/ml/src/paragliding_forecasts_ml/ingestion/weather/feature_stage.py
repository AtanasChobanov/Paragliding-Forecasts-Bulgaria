"""Immutable S07 feature artifacts from one complete S06 validation boundary."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from ..atmosphere.contracts import ArtifactReference, StageManifest
from .artifacts import ArtifactError, WeatherArtifactStore, stage_input_fingerprint
from .features.aggregation import sofia_flying_window
from .features.builder import (
    build_daily_interval_features,
    build_daily_neighbourhood_features,
    build_daily_point_features,
    build_hourly_point_features,
    build_profile_layer,
)
from .features.contracts import (
    DailyFeatureSnapshot,
    DailyFeatureSnapshotBatch,
    FeatureLayer,
    FeatureQualityReport,
    FeatureQualitySummary,
    FeatureValue,
    HourlyFeatureSnapshot,
    HourlyFeatureSnapshotBatch,
    MissingFeatureLocator,
)
from .features.policy import FeaturePolicy, load_feature_policy
from .spatial import CanonicalSiteSampleBatch, NeighbourhoodNodeBatch, SiteAlignedSample
from .validation import (
    AcceptedWeatherSamples,
    MissingWeatherEvidence,
    ValidationSnapshot,
    validation_upstream_boundary,
)

FEATURE_BUILDER_VERSION = "weather-feature-builder/2"


class WeatherFeatureBuildError(RuntimeError):
    """A verified S06 boundary cannot produce a deterministic S07 artifact."""


def build_weather_features(
    store: WeatherArtifactStore,
    validation_manifest_reference: ArtifactReference,
    *,
    occurred_at_utc: str,
) -> ArtifactReference:
    """Build or reuse all S07 v2 artifacts for one complete validator boundary."""

    store.verify_boundary(validation_manifest_reference)
    validation_manifest = store.read_stage_manifest(validation_manifest_reference)
    if validation_manifest.stage != "validator" or validation_manifest.disposition != "complete":
        raise WeatherFeatureBuildError(
            "weather-build-features requires a complete validator boundary."
        )
    validation_snapshot = _load_output(
        store, validation_manifest, "validation_snapshot", ValidationSnapshot
    )
    accepted = _load_output(
        store, validation_manifest, "accepted_weather_samples", AcceptedWeatherSamples
    )
    missing_reference = _output_reference(validation_manifest, "missing_weather_evidence")
    _load_model(store, missing_reference, MissingWeatherEvidence)
    spatial_reference = validation_upstream_boundary(store, validation_manifest_reference)
    spatial_batch = _load_model(
        store, _spatial_samples_reference(store, spatial_reference), CanonicalSiteSampleBatch
    )
    neighbourhood_reference = _neighbourhood_reference(store, spatial_reference)
    neighbourhood_batch = _load_model(store, neighbourhood_reference, NeighbourhoodNodeBatch)
    if accepted.run_key != store.run_key or spatial_batch.run_key != store.run_key:
        raise WeatherFeatureBuildError("S05/S06 feature inputs belong to another weather run.")
    if neighbourhood_batch.run_key != store.run_key:
        raise WeatherFeatureBuildError("S05 neighbourhood input belongs to another weather run.")
    raw_manifest = store.verify_raw_manifest(validation_snapshot.raw_manifest)
    policy, policy_sha256 = load_feature_policy()
    configuration = {
        "feature_contract_version": policy.feature_contract_version,
        "feature_builder_version": policy.feature_builder_version,
        "policy_version": policy.policy_version,
        "policy_sha256": policy_sha256,
        "validator_manifest_sha256": validation_manifest_reference.sha256,
    }
    inputs = (
        validation_manifest_reference,
        _output_reference(validation_manifest, "accepted_weather_samples"),
        missing_reference,
        neighbourhood_reference,
    )
    fingerprint = stage_input_fingerprint(
        stage="feature_builder",
        producer_version=FEATURE_BUILDER_VERSION,
        inputs=inputs,
        configuration=configuration,
    )
    if existing := store.existing_stage_manifest(
        "feature_builder", FEATURE_BUILDER_VERSION, fingerprint
    ):
        return existing
    hourly = _build_hourly_snapshots(
        accepted.samples, policy, store.run_key, fingerprint, raw_manifest.source_id
    )
    daily = _build_daily_snapshots(
        accepted.samples,
        spatial_batch,
        neighbourhood_batch,
        policy,
        store.run_key,
        raw_manifest.source_product_key,
        fingerprint,
        raw_manifest.source_id,
    )
    report = _quality_report(store.run_key, policy, policy_sha256, hourly, daily)
    directory = store.begin_stage("feature_builder", FEATURE_BUILDER_VERSION, fingerprint)
    hourly_reference = store.write_stage_model(
        directory,
        "feature-snapshots.json",
        "hourly_feature_snapshot_batch",
        HourlyFeatureSnapshotBatch(run_key=store.run_key, snapshots=hourly),
        record_count=len(hourly),
    )
    daily_reference = store.write_stage_model(
        directory,
        "day-feature-snapshots.json",
        "daily_feature_snapshot_batch",
        DailyFeatureSnapshotBatch(run_key=store.run_key, snapshots=daily),
        record_count=len(daily),
    )
    report_reference = store.write_stage_model(
        directory,
        "feature-quality-report.json",
        "feature_quality_report",
        report,
    )
    return store.write_stage_manifest(
        directory,
        StageManifest(
            run_key=store.run_key,
            stage="feature_builder",
            producer_version=FEATURE_BUILDER_VERSION,
            input_fingerprint_sha256=fingerprint,
            inputs=inputs,
            outputs=(hourly_reference, daily_reference, report_reference),
            configuration=configuration,
            disposition="complete",
            started_at_utc=occurred_at_utc,
            completed_at_utc=occurred_at_utc,
        ),
    )


def _build_hourly_snapshots(
    samples: tuple[SiteAlignedSample, ...],
    policy: FeaturePolicy,
    run_key: str,
    fingerprint: str,
    source_id: str,
) -> tuple[HourlyFeatureSnapshot, ...]:
    return tuple(
        HourlyFeatureSnapshot(
            run_key=run_key,
            sample_identity_key=sample.sample_identity_key,
            site_id=sample.site_id,
            point_footprint_key=sample.point_footprint_key,
            neighbourhood_footprint_key=sample.neighbourhood_footprint_key,
            valid_at_utc=sample.valid_at_utc,
            valid_local_date=sample.valid_local_date,
            feature_contract_version=policy.feature_contract_version,
            input_fingerprint_sha256=fingerprint,
            fields=(
                fields := build_hourly_point_features(
                    sample, policy.hourly_fields, source_id=source_id
                )
            ),
            missing_features=_missing_locators(fields, ()),
            quality_summary=_quality_summary(fields, ()),
        )
        for sample in sorted(
            samples, key=lambda item: (item.site_id, item.valid_at_utc, item.sample_identity_key)
        )
    )


def _build_daily_snapshots(
    samples: tuple[SiteAlignedSample, ...],
    spatial: CanonicalSiteSampleBatch,
    neighbourhood: NeighbourhoodNodeBatch,
    policy: FeaturePolicy,
    run_key: str,
    source_product_key: str,
    fingerprint: str,
    source_id: str,
) -> tuple[DailyFeatureSnapshot, ...]:
    grouped: dict[tuple[int, str], list[SiteAlignedSample]] = defaultdict(list)
    for sample in samples:
        grouped[(sample.site_id, sample.valid_local_date)].append(sample)
    snapshots: list[DailyFeatureSnapshot] = []
    for (site_id, local_date), group in sorted(grouped.items()):
        ordered = tuple(
            sorted(group, key=lambda item: (item.valid_at_utc, item.sample_identity_key))
        )
        window = sofia_flying_window(date.fromisoformat(local_date))
        point = build_daily_point_features(
            ordered,
            policy.daily_fields,
            expected_instants_utc=window.expected_instants_utc,
            source_id=source_id,
        )
        interval = build_daily_interval_features(
            ordered, policy.daily_fields, expected_instants_utc=window.expected_instants_utc
        )
        neighbourhood_values = build_daily_neighbourhood_features(
            ordered,
            neighbourhood.records,
            spatial.neighbourhood_footprints,
            spatial.site_configs,
            policy.daily_fields,
            expected_instants_utc=window.expected_instants_utc,
        )
        by_key = {value.feature_key: value for value in (*point, *interval, *neighbourhood_values)}
        daily_fields = tuple(by_key[entry.feature_key] for entry in policy.daily_fields)
        layers = tuple(
            build_profile_layer(
                ordered,
                layer,
                policy.entries_for_layer(layer),
                expected_instants_utc=window.expected_instants_utc,
            )
            for layer in policy.profile_layers
        )
        snapshots.append(
            DailyFeatureSnapshot(
                run_key=run_key,
                site_id=site_id,
                point_footprint_key=_single_identity(ordered, "point_footprint_key"),
                neighbourhood_footprint_key=_single_identity(
                    ordered, "neighbourhood_footprint_key"
                ),
                source_product_key=source_product_key,
                local_date=local_date,
                feature_contract_version=policy.feature_contract_version,
                input_fingerprint_sha256=fingerprint,
                input_sample_identity_keys=tuple(item.sample_identity_key for item in ordered),
                daily_fields=daily_fields,
                profile_layers=layers,
                missing_features=_missing_locators(daily_fields, layers),
                quality_summary=_quality_summary(daily_fields, layers),
            )
        )
    return tuple(snapshots)


def _single_identity(samples: tuple[SiteAlignedSample, ...], attribute: str) -> str:
    values = {getattr(sample, attribute) for sample in samples}
    if len(values) != 1:
        raise WeatherFeatureBuildError(f"Daily feature group has conflicting {attribute} values.")
    return values.pop()


def _quality_summary(
    daily_fields: tuple[FeatureValue, ...], layers: tuple[FeatureLayer, ...]
) -> FeatureQualitySummary:
    values = (*daily_fields, *(field for layer in layers for field in layer.fields))
    return FeatureQualitySummary(
        total_features=len(values),
        quality_counts=dict(Counter(value.quality_state for value in values)),
    )


def _missing_locators(
    daily_fields: tuple[FeatureValue, ...], layers: tuple[FeatureLayer, ...]
) -> tuple[MissingFeatureLocator, ...]:
    return tuple(
        [
            MissingFeatureLocator(
                feature_key=value.feature_key, missing_reason=value.missing_reason or "unknown"
            )
            for value in daily_fields
            if value.canonical_value is None
        ]
        + [
            MissingFeatureLocator(
                feature_key=value.feature_key,
                layer_base_agl_m=layer.layer_base_agl_m,
                layer_top_agl_m=layer.layer_top_agl_m,
                missing_reason=value.missing_reason or "unknown",
            )
            for layer in layers
            for value in layer.fields
            if value.canonical_value is None
        ]
    )


def _quality_report(
    run_key: str,
    policy: FeaturePolicy,
    policy_sha256: str,
    hourly: tuple[HourlyFeatureSnapshot, ...],
    daily: tuple[DailyFeatureSnapshot, ...],
) -> FeatureQualityReport:
    values = [
        *(field for snapshot in hourly for field in snapshot.fields),
        *(field for snapshot in daily for field in snapshot.daily_fields),
        *(
            field
            for snapshot in daily
            for layer in snapshot.profile_layers
            for field in layer.fields
        ),
    ]
    return FeatureQualityReport(
        run_key=run_key,
        feature_contract_version=policy.feature_contract_version,
        policy_version=policy.policy_version,
        policy_sha256=policy_sha256,
        hourly_snapshot_count=len(hourly),
        daily_snapshot_count=len(daily),
        total_features=len(values),
        quality_counts=dict(Counter(value.quality_state for value in values)),
        missing_feature_count=sum(value.canonical_value is None for value in values),
    )


def _output_reference(manifest: StageManifest, artifact_key: str) -> ArtifactReference:
    matches = [item for item in manifest.outputs if item.artifact_key == artifact_key]
    if len(matches) != 1:
        raise WeatherFeatureBuildError(f"Stage must expose exactly one {artifact_key} artifact.")
    return matches[0]


def _load_output(
    store: WeatherArtifactStore, manifest: StageManifest, artifact_key: str, model_type
):
    return _load_model(store, _output_reference(manifest, artifact_key), model_type)


def _load_model(store: WeatherArtifactStore, reference: ArtifactReference, model_type):
    try:
        return model_type.model_validate_json(
            store.verify_reference(reference).read_bytes(), strict=True
        )
    except (ArtifactError, OSError, ValueError) as error:
        raise WeatherFeatureBuildError(
            "Feature input does not satisfy its versioned contract."
        ) from error


def _spatial_samples_reference(
    store: WeatherArtifactStore, reference: ArtifactReference
) -> ArtifactReference:
    manifest = store.read_stage_manifest(reference)
    if manifest.stage != "spatial" or manifest.disposition != "complete":
        raise WeatherFeatureBuildError("Validator must lead to a complete S05 spatial boundary.")
    return _output_reference(manifest, "canonical_site_sample_batch")


def _neighbourhood_reference(
    store: WeatherArtifactStore, reference: ArtifactReference
) -> ArtifactReference:
    manifest = store.read_stage_manifest(reference)
    if manifest.stage != "spatial" or manifest.disposition != "complete":
        raise WeatherFeatureBuildError("Validator must lead to a complete S05 spatial boundary.")
    return _output_reference(manifest, "neighbourhood_node_batch")
