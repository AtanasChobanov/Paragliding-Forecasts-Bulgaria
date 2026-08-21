from __future__ import annotations

import pytest

from paragliding_forecasts_ml.ingestion.atmosphere.catalogue import load_catalogue
from paragliding_forecasts_ml.ingestion.atmosphere.contracts import (
    RawManifest,
    RequestPlan,
    StageManifest,
)
from paragliding_forecasts_ml.ingestion.weather.artifacts import (
    ArtifactError,
    WeatherArtifactStore,
    stage_input_fingerprint,
)

RUN_KEY = "123e4567-e89b-42d3-a456-426614174000"
UTC = "2026-08-21T12:00:00Z"


def make_plan() -> RequestPlan:
    catalogue = load_catalogue()
    return RequestPlan(
        run_key=RUN_KEY,
        source_id="noaa_gfs_0p25_aws_grib2",
        source_kind="forecast",
        ingestion_method="public_object_archive",
        request_purpose="historical_forecast",
        catalogue_version=catalogue.version,
        catalogue_sha256=catalogue.sha256,
        adapter_request_schema_version=1,
        adapter_request={"cycle": "00"},
        expected_artifact_keys=("gfs_surface",),
        created_at_utc=UTC,
    )


def complete_raw(store: WeatherArtifactStore):
    plan_reference = store.write_request_plan(make_plan())
    payload = store.write_raw_bytes(
        "gfs_surface", "gfs-surface.grib2", b"synthetic grib", media_type="application/x-grib2"
    )
    manifest = RawManifest(
        run_key=RUN_KEY,
        source_id="noaa_gfs_0p25_aws_grib2",
        source_kind="forecast",
        collector_version="gfs-collector/1",
        request_plan=plan_reference,
        source_product_key="gfs.t00z.pgrb2.0p25.f024",
        source_url="https://example.invalid/gfs",
        permission_basis="public-data",
        permission_reference="NOAA-open-data",
        retrieved_at_utc=UTC,
        valid_from_utc=UTC,
        valid_to_utc=UTC,
        artifacts=(payload,),
        status="complete",
        completed_at_utc=UTC,
    )
    return store.write_raw_manifest(manifest)


def test_model_artifacts_are_human_readable_and_hash_verified(tmp_path) -> None:
    store = WeatherArtifactStore.create_fresh(RUN_KEY, project_root=tmp_path)
    reference = store.write_request_plan(make_plan())
    text = (tmp_path / reference.relative_path).read_text(encoding="utf-8")

    assert text.startswith("{\n")
    assert '\n  "adapter_request": {' in text
    assert text.endswith("\n")
    assert store.verify_reference(reference).is_file()


def test_raw_artifacts_are_immutable_and_hash_verified(tmp_path) -> None:
    store = WeatherArtifactStore.create_fresh(RUN_KEY, project_root=tmp_path)
    raw_manifest = complete_raw(store)

    with pytest.raises(FileExistsError, match="overwrite"):
        store.write_request_plan(make_plan())

    payload_path = tmp_path / "data/raw/weather" / RUN_KEY / "payloads/gfs-surface.grib2"
    payload_path.write_bytes(b"tampered")
    with pytest.raises(ArtifactError, match="byte count|SHA-256"):
        store.verify_raw_manifest(raw_manifest)


def test_stage_manifest_chains_verified_raw_input(tmp_path) -> None:
    store = WeatherArtifactStore.create_fresh(RUN_KEY, project_root=tmp_path)
    raw_manifest = complete_raw(store)
    fingerprint = stage_input_fingerprint(
        stage="parser",
        producer_version="gfs-parser/1",
        inputs=(raw_manifest,),
    )
    directory = store.begin_stage("parser", "gfs-parser/1", fingerprint)
    native_batch = store.write_stage_model(
        directory,
        "native-batch.json",
        "native_batch",
        make_plan(),
    )
    stage_manifest = StageManifest(
        run_key=RUN_KEY,
        stage="parser",
        producer_version="gfs-parser/1",
        input_fingerprint_sha256=fingerprint,
        inputs=(raw_manifest,),
        outputs=(native_batch,),
        disposition="complete",
        started_at_utc=UTC,
        completed_at_utc=UTC,
    )
    written_manifest = store.write_stage_manifest(directory, stage_manifest)

    assert store.verify_boundary(written_manifest).is_file()
    native_path = directory / "native-batch.json"
    native_path.write_text("tampered", encoding="utf-8")
    with pytest.raises(ArtifactError, match="byte count|SHA-256"):
        store.verify_boundary(written_manifest)
    with pytest.raises(FileExistsError):
        store.begin_stage("parser", "gfs-parser/1", fingerprint)
