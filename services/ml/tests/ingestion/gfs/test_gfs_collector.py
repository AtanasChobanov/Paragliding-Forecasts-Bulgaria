from __future__ import annotations

import hashlib
from uuid import UUID

import pytest

from paragliding_forecasts_ml.ingestion.atmosphere.catalogue import load_catalogue
from paragliding_forecasts_ml.ingestion.atmosphere.contracts import RequestPlan
from paragliding_forecasts_ml.ingestion.gfs.collector import GfsCollectionError, GfsCollector
from paragliding_forecasts_ml.ingestion.gfs.models import GfsPlannedRange, GfsResolvedPlan
from paragliding_forecasts_ml.ingestion.gfs.transport import (
    GfsTransportError,
    HttpResponse,
    HttpTransport,
)
from paragliding_forecasts_ml.ingestion.weather.artifacts import WeatherArtifactStore


class FakeTransport(HttpTransport):
    def __init__(self, responses: dict[tuple[str, str | None], HttpResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str | None]] = []

    def request(self, url: str, *, method: str = "GET", headers=None) -> HttpResponse:
        range_header = (headers or {}).get("Range")
        self.calls.append((url, range_header))
        return self.responses[(url, range_header)]


def test_collector_persists_bounded_range_evidence(tmp_path) -> None:
    run_key = str(UUID("123e4567-e89b-42d3-a456-426614174000"))
    index_url = "https://example.test/gfs.idx"
    grib_url = "https://example.test/gfs"
    index_body = b"1:0:d=2025080100:TMP:2 m above ground:anl:\\n"
    resolved = GfsResolvedPlan(
        selection_mode="explicit",
        resolved_run_at_utc="2025-08-01T00:00:00Z",
        available_at_utc="2025-08-01T01:00:00Z",
        source_product_key="gfs.20250801/00/atmos",
        ranges=(
            GfsPlannedRange(
                lead_hours=0,
                valid_at_utc="2025-08-01T00:00:00Z",
                grib_url=grib_url,
                index_url=index_url,
                index_sha256=hashlib.sha256(index_body).hexdigest(),
                object_content_length=100,
                object_last_modified_utc="2025-08-01T01:00:00Z",
                byte_start=0,
                byte_end=3,
                selector_keys=("tmp_2m",),
                message_numbers=(1,),
                forecast_descriptors=("anl",),
            ),
        ),
    )
    catalogue = load_catalogue()
    plan = RequestPlan(
        run_key=run_key,
        source_id="noaa_gfs_0p25_aws_grib2",
        source_kind="forecast",
        ingestion_method="public_object_archive",
        request_purpose="historical_forecast",
        catalogue_version=catalogue.version,
        catalogue_sha256=catalogue.sha256,
        adapter_request_schema_version=1,
        adapter_request=resolved.model_dump(mode="json"),
        expected_artifact_keys=("gfs_grib_f000_r001", "gfs_collection_record"),
        created_at_utc="2025-08-01T01:01:00Z",
    )
    transport = FakeTransport(
        {
            (index_url, None): HttpResponse(200, {}, index_body),
            (grib_url, "bytes=0-3"): HttpResponse(206, {"Content-Range": "bytes 0-3/100"}, b"GRIB"),
        }
    )
    store = WeatherArtifactStore.create_fresh(run_key, project_root=tmp_path)

    manifest_reference = GfsCollector(transport, clock=lambda: "2025-08-01T01:02:00Z").fetch(
        plan, store
    )

    manifest = store.verify_raw_manifest(manifest_reference)
    assert transport.calls == [(index_url, None), (grib_url, "bytes=0-3")]
    assert [item.artifact_key for item in manifest.artifacts] == [
        "gfs_idx_f000",
        "gfs_grib_f000_r001",
        "gfs_collection_record",
    ]
    assert manifest.status == "complete"


def test_resumable_collector_skips_verified_range_after_interruption(tmp_path) -> None:
    run_key = "123e4567-e89b-42d3-a456-426614174001"
    index_url = "https://example.test/gfs.idx"
    grib_url = "https://example.test/gfs"
    index_body = b"fixture-index\n"
    ranges = tuple(
        GfsPlannedRange(
            lead_hours=0,
            valid_at_utc="2025-08-01T00:00:00Z",
            grib_url=grib_url,
            index_url=index_url,
            index_sha256=hashlib.sha256(index_body).hexdigest(),
            object_content_length=100,
            object_etag='"fixture"',
            object_last_modified_utc="2025-08-01T01:00:00Z",
            index_last_modified_utc="2025-08-01T01:00:01Z",
            byte_start=start,
            byte_end=start + 3,
            selector_keys=("tmp_2m",),
            message_numbers=(ordinal,),
            forecast_descriptors=("anl",),
        )
        for ordinal, start in enumerate((0, 4), start=1)
    )
    resolved = GfsResolvedPlan(
        selection_mode="explicit",
        resolved_run_at_utc="2025-08-01T00:00:00Z",
        available_at_utc="2025-08-01T01:00:01Z",
        source_product_key="gfs.20250801/00/atmos",
        ranges=ranges,
    )
    catalogue = load_catalogue()
    plan = RequestPlan(
        run_key=run_key,
        source_id="noaa_gfs_0p25_aws_grib2",
        source_kind="forecast",
        ingestion_method="public_object_archive",
        request_purpose="historical_forecast",
        catalogue_version=catalogue.version,
        catalogue_sha256=catalogue.sha256,
        adapter_request_schema_version=1,
        adapter_request=resolved.model_dump(mode="json"),
        expected_artifact_keys=(
            "gfs_grib_f000_r001",
            "gfs_grib_f000_r002",
            "gfs_collection_record",
        ),
        created_at_utc="2025-08-01T01:01:00Z",
    )

    class InterruptingTransport(HttpTransport):
        def __init__(self) -> None:
            self.fail_second = True
            self.head_etag = '"fixture"'
            self.range_calls: list[str] = []

        def request(self, url: str, *, method: str = "GET", headers=None) -> HttpResponse:
            if method == "HEAD":
                return HttpResponse(
                    200,
                    {
                        "Content-Length": "100",
                        "ETag": self.head_etag,
                        "Last-Modified": "Fri, 01 Aug 2025 01:00:00 GMT",
                    },
                    b"",
                )
            if url == index_url:
                return HttpResponse(
                    200, {"Last-Modified": "Fri, 01 Aug 2025 01:00:01 GMT"}, index_body
                )
            value = headers["Range"]
            self.range_calls.append(value)
            if value == "bytes=4-7" and self.fail_second:
                raise GfsTransportError("simulated disconnect")
            payload = b"GRIB" if value == "bytes=0-3" else b"DATA"
            return HttpResponse(206, {"Content-Range": f"{value.replace('=', ' ')}/100"}, payload)

    transport = InterruptingTransport()
    store = WeatherArtifactStore.create_fresh(run_key, project_root=tmp_path)
    collector = GfsCollector(transport, clock=lambda: "2025-08-01T01:02:00Z")
    with pytest.raises(GfsTransportError):
        collector.fetch_resumable(plan, store)
    assert len(list((store.raw_dir / "checkpoints").glob("*.json"))) == 1
    assert not (store.raw_dir / "manifest.json").exists()
    transport.fail_second = False
    transport.head_etag = '"changed"'
    with pytest.raises(GfsCollectionError, match="identity changed"):
        collector.fetch_resumable(plan, store)
    assert transport.range_calls == ["bytes=0-3", "bytes=4-7"]
    transport.head_etag = '"fixture"'
    reference = collector.fetch_resumable(plan, store)
    assert store.verify_raw_manifest(reference).status == "complete"
    assert transport.range_calls == ["bytes=0-3", "bytes=4-7", "bytes=4-7"]
