from __future__ import annotations

import hashlib
from uuid import UUID

from paragliding_forecasts_ml.ingestion.atmosphere.catalogue import load_catalogue
from paragliding_forecasts_ml.ingestion.atmosphere.contracts import RequestPlan
from paragliding_forecasts_ml.ingestion.gfs.collector import GfsCollector
from paragliding_forecasts_ml.ingestion.gfs.models import GfsPlannedRange, GfsResolvedPlan
from paragliding_forecasts_ml.ingestion.gfs.transport import HttpResponse, HttpTransport
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
