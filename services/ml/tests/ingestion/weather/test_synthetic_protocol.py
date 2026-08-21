from __future__ import annotations

from paragliding_forecasts_ml.ingestion.atmosphere.catalogue import load_catalogue
from paragliding_forecasts_ml.ingestion.atmosphere.contracts import (
    CanonicalFieldValue,
    CanonicalSample,
    FeatureSnapshot,
    FieldProvenance,
    NativeBatch,
    NativeRecord,
    PersistenceReceipt,
    ProfileLevel,
    RawManifest,
    RequestPlan,
    StageManifest,
    ValidationReport,
)
from paragliding_forecasts_ml.ingestion.weather.artifacts import (
    WeatherArtifactStore,
    stage_input_fingerprint,
)
from paragliding_forecasts_ml.ingestion.weather.state import RunStateLedger
from paragliding_forecasts_ml.ingestion.weather.versions import PipelineVersions

RUN_KEY = "123e4567-e89b-42d3-a456-426614174000"
UTC = "2026-08-21T12:00:00Z"


def temperature(value: float) -> CanonicalFieldValue:
    return CanonicalFieldValue(
        field_code="air_temperature_k",
        canonical_unit="K",
        canonical_value=value,
        provenance=FieldProvenance(
            quality_state="real",
            native_field_name="TMP",
            native_unit="K",
            native_value=value,
            raw_artifact_key="gfs_surface",
        ),
    )


def stage(
    store: WeatherArtifactStore,
    ledger: RunStateLedger,
    *,
    stage_name: str,
    ledger_stage: str,
    version: str,
    input_reference,
    output_model,
    filename: str,
    artifact_key: str,
    disposition: str = "complete",
):
    fingerprint = stage_input_fingerprint(
        stage=stage_name,
        producer_version=version,
        inputs=(input_reference,),
    )
    directory = store.begin_stage(stage_name, version, fingerprint)
    output = store.write_stage_model(directory, filename, artifact_key, output_model)
    manifest = StageManifest(
        run_key=RUN_KEY,
        stage=stage_name,
        producer_version=version,
        input_fingerprint_sha256=fingerprint,
        inputs=(input_reference,),
        outputs=(output,),
        disposition=disposition,
        started_at_utc=UTC,
        completed_at_utc=UTC,
    )
    manifest_reference = store.write_stage_manifest(directory, manifest)
    ledger.append(
        invocation_mode="resume",
        stage=ledger_stage,
        disposition="persisted" if ledger_stage == "persisted" else "complete",
        occurred_at_utc=UTC,
        evidence=manifest_reference,
    )
    return manifest_reference


def test_synthetic_stage_protocol_proves_the_entire_hash_chain(tmp_path) -> None:
    catalogue = load_catalogue()
    versions = PipelineVersions(
        collector="gfs-collector/1",
        parser="gfs-parser/1",
        normalizer="weather-normalizer/1",
        spatial="weather-spatial/1",
        validator="weather-validator/1",
        feature_builder="weather-feature-builder/1",
        persistence="weather-persistence/1",
    )
    assert versions.pipe_delimited == (
        "gfs-collector/1|gfs-parser/1|weather-normalizer/1|weather-spatial/1|"
        "weather-validator/1|weather-feature-builder/1|weather-persistence/1"
    )

    store = WeatherArtifactStore.create_fresh(RUN_KEY, project_root=tmp_path)
    ledger = RunStateLedger(store)
    ledger.initialize(occurred_at_utc=UTC)
    plan = RequestPlan(
        run_key=RUN_KEY,
        source_id="noaa_gfs_0p25_aws_grib2",
        source_kind="forecast",
        ingestion_method="public_object_archive",
        request_purpose="historical_forecast",
        catalogue_version=catalogue.version,
        catalogue_sha256=catalogue.sha256,
        adapter_request_schema_version=1,
        adapter_request={"cycle": "00", "lead_hours": [24]},
        expected_artifact_keys=("gfs_surface",),
        created_at_utc=UTC,
    )
    plan_reference = store.write_request_plan(plan)
    payload_reference = store.write_raw_bytes(
        "gfs_surface",
        "gfs-surface.grib2",
        b"synthetic grib payload",
        media_type="application/x-grib2",
    )
    raw_reference = store.write_raw_manifest(
        RawManifest(
            run_key=RUN_KEY,
            source_id="noaa_gfs_0p25_aws_grib2",
            source_kind="forecast",
            collector_version=versions.collector,
            request_plan=plan_reference,
            source_product_key="gfs.t00z.pgrb2.0p25.f024",
            source_url="https://example.invalid/gfs",
            permission_basis="public-data",
            permission_reference="NOAA-open-data",
            retrieved_at_utc=UTC,
            valid_from_utc=UTC,
            valid_to_utc=UTC,
            artifacts=(payload_reference,),
            status="complete",
            completed_at_utc=UTC,
        )
    )
    store.verify_raw_manifest(raw_reference)
    ledger.append(
        invocation_mode="resume",
        stage="raw_complete",
        disposition="complete",
        occurred_at_utc=UTC,
        evidence=raw_reference,
    )

    native = NativeBatch(
        run_key=RUN_KEY,
        source_id="noaa_gfs_0p25_aws_grib2",
        parser_version=versions.parser,
        raw_manifest=raw_reference,
        records=(
            NativeRecord(
                source_product_key="gfs.t00z.pgrb2.0p25.f024",
                valid_at_utc=UTC,
                grid_latitude_deg=42.6977,
                grid_longitude_deg=23.3219,
                native_field_name="TMP",
                native_unit="K",
                native_value=293.15,
                missing_state="present",
                native_message_reference="1:TMP:surface",
                raw_artifact_key="gfs_surface",
            ),
        ),
    )
    parser_manifest = stage(
        store,
        ledger,
        stage_name="parser",
        ledger_stage="parsed",
        version=versions.parser,
        input_reference=raw_reference,
        output_model=native,
        filename="native-batch.json",
        artifact_key="native_batch",
    )

    sample = CanonicalSample(
        sample_key="sample-1",
        source_product_key="gfs.t00z.pgrb2.0p25.f024",
        point_footprint_key="vitosha-point-v1",
        valid_at_utc=UTC,
        valid_local_date="2026-08-21",
        lead_hours=24.0,
        coverage_status="complete",
        fields=(temperature(293.15),),
    )
    profile = ProfileLevel(
        sample_key="sample-1", pressure_pa=85000.0, fields=(temperature(286.15),)
    )
    normalizer_manifest = stage(
        store,
        ledger,
        stage_name="normalizer",
        ledger_stage="normalized",
        version=versions.normalizer,
        input_reference=parser_manifest,
        output_model=sample,
        filename="canonical-samples.json",
        artifact_key="canonical_samples",
    )
    spatial_manifest = stage(
        store,
        ledger,
        stage_name="spatial",
        ledger_stage="spatially_aligned",
        version=versions.spatial,
        input_reference=normalizer_manifest,
        output_model=profile,
        filename="aligned-profile-levels.json",
        artifact_key="aligned_profile_levels",
    )

    validation_directory_fingerprint = stage_input_fingerprint(
        stage="validator",
        producer_version=versions.validator,
        inputs=(spatial_manifest,),
    )
    validation_directory = store.begin_stage(
        "validator", versions.validator, validation_directory_fingerprint
    )
    accepted = store.write_stage_model(
        validation_directory,
        "accepted-samples.json",
        "accepted_samples",
        sample,
        record_count=1,
    )
    validation = ValidationReport(
        run_key=RUN_KEY,
        validator_version=versions.validator,
        policy_version="weather-validation-policy/1",
        policy_sha256="a" * 64,
        input_stage_manifest=spatial_manifest,
        accepted=accepted,
        samples_seen=1,
        samples_accepted=1,
        samples_rejected=0,
        samples_quarantined=0,
        disposition="accepted",
    )
    validation_reference = store.write_stage_model(
        validation_directory,
        "validation-report.json",
        "validation_report",
        validation,
    )
    validator_manifest = store.write_stage_manifest(
        validation_directory,
        StageManifest(
            run_key=RUN_KEY,
            stage="validator",
            producer_version=versions.validator,
            input_fingerprint_sha256=validation_directory_fingerprint,
            inputs=(spatial_manifest,),
            outputs=(accepted, validation_reference),
            disposition="complete",
            started_at_utc=UTC,
            completed_at_utc=UTC,
        ),
    )
    ledger.append(
        invocation_mode="resume",
        stage="validated",
        disposition="complete",
        occurred_at_utc=UTC,
        evidence=validator_manifest,
    )

    feature = FeatureSnapshot(
        sample_key="sample-1",
        neighbourhood_footprint_key="vitosha-neighbourhood-v1",
        feature_contract_version="weather-feature-contract/1",
        input_fingerprint_sha256=validator_manifest.sha256,
        fields=(temperature(293.15),),
    )
    feature_manifest = stage(
        store,
        ledger,
        stage_name="feature_builder",
        ledger_stage="features_built",
        version=versions.feature_builder,
        input_reference=validator_manifest,
        output_model=feature,
        filename="feature-snapshots.json",
        artifact_key="feature_snapshots",
    )
    receipt = PersistenceReceipt(
        run_key=RUN_KEY,
        persistence_version=versions.persistence,
        validation_report=validation_reference,
        feature_stage_manifest=feature_manifest,
        input_fingerprint_sha256=feature_manifest.sha256,
        status="persisted",
        samples_persisted=1,
        completed_at_utc=UTC,
    )
    persistence_manifest = stage(
        store,
        ledger,
        stage_name="persistence",
        ledger_stage="persisted",
        version=versions.persistence,
        input_reference=feature_manifest,
        output_model=receipt,
        filename="persistence-receipt.json",
        artifact_key="persistence_receipt",
        disposition="persisted",
    )

    assert store.verify_reference(persistence_manifest).is_file()
    assert [event.stage for event in ledger.load_events()] == [
        "planned",
        "raw_complete",
        "parsed",
        "normalized",
        "spatially_aligned",
        "validated",
        "features_built",
        "persisted",
    ]
