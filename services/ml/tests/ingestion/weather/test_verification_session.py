from __future__ import annotations

import os
from pathlib import Path

import pytest

from paragliding_forecasts_ml.ingestion.atmosphere.catalogue import load_catalogue
from paragliding_forecasts_ml.ingestion.atmosphere.contracts import (
    ArtifactReference,
    RawManifest,
    RequestPlan,
)
from paragliding_forecasts_ml.ingestion.weather import artifacts
from paragliding_forecasts_ml.ingestion.weather.artifacts import (
    ArtifactError,
    WeatherArtifactStore,
)

RUN_KEY = "123e4567-e89b-42d3-a456-426614174000"
UTC = "2026-08-21T12:00:00Z"


def write_raw_boundary(tmp_path) -> tuple[ArtifactReference, ArtifactReference]:
    catalogue = load_catalogue()
    store = WeatherArtifactStore.create_fresh(RUN_KEY, project_root=tmp_path)
    plan = store.write_request_plan(
        RequestPlan(
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
    )
    payload = store.write_raw_bytes(
        "gfs_surface",
        "gfs-surface.grib2",
        b"synthetic raw payload",
        media_type="application/x-grib2",
    )
    manifest = store.write_raw_manifest(
        RawManifest(
            run_key=RUN_KEY,
            source_id="noaa_gfs_0p25_aws_grib2",
            source_kind="forecast",
            collector_version="gfs-collector/1",
            request_plan=plan,
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
    )
    return manifest, payload


def test_effective_boundary_hashes_each_preexisting_file_once(tmp_path) -> None:
    manifest, payload = write_raw_boundary(tmp_path)
    store = WeatherArtifactStore(RUN_KEY, project_root=tmp_path)

    store.verify_boundary(manifest)
    first = store.verification.verification_summary()
    store.verify_boundary(manifest)
    second = store.verification.verification_summary()

    assert first["files_hashed"] == 3
    assert first["manifests_parsed"] == 1
    assert first["boundaries_verified"] == 1
    assert second["files_hashed"] == 3
    assert second["boundaries_verified"] == 1
    assert second["cache_hits"] > first["cache_hits"]
    assert Path(tmp_path / payload.relative_path).stat().st_size <= first["bytes_hashed"]


def test_stat_change_invalidates_and_rehashes_the_exact_file(tmp_path) -> None:
    manifest, payload = write_raw_boundary(tmp_path)
    store = WeatherArtifactStore(RUN_KEY, project_root=tmp_path)
    store.verify_boundary(manifest)
    payload_path = tmp_path / payload.relative_path
    stat = payload_path.stat()
    os.utime(payload_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

    store.verify_boundary(manifest)

    assert store.verification.verification_summary()["files_hashed"] == 4


def test_same_sha_at_another_path_does_not_bypass_file_verification(tmp_path) -> None:
    store = WeatherArtifactStore.create_fresh(RUN_KEY, project_root=tmp_path)
    first = store.write_raw_bytes(
        "first",
        "first.bin",
        b"same bytes",
        media_type="application/octet-stream",
    )
    second = store.write_raw_bytes(
        "second",
        "second.bin",
        b"same bytes",
        media_type="application/octet-stream",
    )
    fresh = WeatherArtifactStore(RUN_KEY, project_root=tmp_path)

    fresh.verify_reference(first)
    fresh.verify_reference(second)

    assert fresh.verification.verification_summary()["files_hashed"] == 2


def test_just_written_stage_output_is_not_reread_for_verification(tmp_path) -> None:
    store = WeatherArtifactStore.create_fresh(RUN_KEY, project_root=tmp_path)
    directory = store.begin_stage("parser", "gfs-parser/1", "a" * 64)
    output = store.write_stage_bytes(
        directory,
        "values.bin",
        "values",
        b"values",
        media_type="application/octet-stream",
    )

    store.verify_reference(output)

    summary = store.verification.verification_summary()
    assert summary["files_hashed"] == 0
    assert summary["files_registered"] == 1
    assert summary["cache_hits"] == 1


def test_interrupted_atomic_publication_leaves_no_completed_artifact(tmp_path, monkeypatch) -> None:
    store = WeatherArtifactStore.create_fresh(RUN_KEY, project_root=tmp_path)
    directory = store.begin_stage("parser", "gfs-parser/1", "a" * 64)

    def fail_publication(_source, _destination):
        raise OSError("synthetic publication interruption")

    monkeypatch.setattr(artifacts.os, "link", fail_publication)

    with pytest.raises(OSError, match="interruption"):
        store.write_stage_bytes(
            directory,
            "values.bin",
            "values",
            b"values",
            media_type="application/octet-stream",
        )

    assert not (directory / "values.bin").exists()
    assert not tuple(directory.glob(".values.bin.*.tmp"))


def test_changed_content_with_unchanged_size_fails_after_cache_invalidation(tmp_path) -> None:
    manifest, payload = write_raw_boundary(tmp_path)
    store = WeatherArtifactStore(RUN_KEY, project_root=tmp_path)
    store.verify_boundary(manifest)
    payload_path = tmp_path / payload.relative_path
    payload_path.write_bytes(b"x" * payload.byte_count)

    with pytest.raises(ArtifactError, match="SHA-256"):
        store.verify_boundary(manifest)
