from __future__ import annotations

import pytest

from paragliding_forecasts_ml.ingestion.gfs.inventory import GfsSelector
from paragliding_forecasts_ml.ingestion.gfs.models import (
    SOFIA_FLYING_WINDOW_VERSION,
    GfsRequest,
    sofia_window_instants,
)
from paragliding_forecasts_ml.ingestion.gfs.planner import GfsPlanner, GfsPlanningError
from paragliding_forecasts_ml.ingestion.gfs.transport import HttpResponse, HttpTransport


class FakeTransport(HttpTransport):
    def __init__(self, index_body: bytes) -> None:
        self.index_body = index_body

    def request(self, url: str, *, method: str = "GET", headers=None) -> HttpResponse:
        if method == "HEAD":
            return HttpResponse(
                200,
                {
                    "Content-Length": "20",
                    "Last-Modified": "Fri, 21 Aug 2026 01:00:00 GMT",
                    "ETag": '"fixture"',
                },
                b"",
            )
        return HttpResponse(200, {}, self.index_body)


class LeadAwareFakeTransport(FakeTransport):
    def request(self, url: str, *, method: str = "GET", headers=None) -> HttpResponse:
        if method == "HEAD":
            return super().request(url, method=method, headers=headers)
        lead = int(url.rsplit(".f", maxsplit=1)[1].split(".", maxsplit=1)[0])
        body = (
            f"1:0:d=2026082100:TMP:2 m above ground:{lead} hour fcst:\n"
            f"2:10:d=2026082100:VGRD:10 m above ground:{lead} hour fcst:\n"
        ).encode()
        return HttpResponse(200, {}, body)


def _request() -> GfsRequest:
    return GfsRequest(
        run_key="123e4567-e89b-42d3-a456-426614174000",
        request_purpose="operational_forecast",
        valid_at_utc=("2026-08-21T07:00:00Z",),
        explicit_run_at_utc="2026-08-21T00:00:00Z",
    )


def test_planner_persists_selected_forecast_descriptor() -> None:
    index = (
        b"1:0:d=2026082100:TMP:2 m above ground:7 hour fcst:\n"
        b"2:10:d=2026082100:VGRD:10 m above ground:7 hour fcst:\n"
    )
    plan = GfsPlanner(
        FakeTransport(index), selectors=(GfsSelector("tmp_2m", "TMP", "2 m above ground"),)
    ).plan(_request(), created_at_utc="2026-08-21T01:01:00Z")

    planned_range = plan.adapter_request["ranges"][0]
    assert plan.adapter_request["selector_set_version"] == 2
    assert planned_range["forecast_descriptors"] == ["7 hour fcst"]


def test_weather_ingest_plan_binds_compact_acquisition_identity() -> None:
    request = GfsRequest(
        run_key="123e4567-e89b-42d3-a456-426614174000",
        request_purpose="historical_forecast",
        valid_at_utc=sofia_window_instants("2026-08-21"),
        explicit_run_at_utc="2026-08-21T00:00:00Z",
        target_local_date="2026-08-21",
        flying_window_version=SOFIA_FLYING_WINDOW_VERSION,
        site_config_sha256="a" * 64,
        sampling_policy_sha256="b" * 64,
        compact_selection_version="regular-grid-footprint-crop/1",
    )

    plan = GfsPlanner(
        LeadAwareFakeTransport(b""),
        selectors=(GfsSelector("tmp_2m", "TMP", "2 m above ground"),),
    ).plan(request, created_at_utc="2026-08-21T01:01:00Z")

    assert plan.adapter_request_schema_version == 2
    assert plan.adapter_request["gfs_request_schema_version"] == 3
    assert plan.adapter_request["site_config_sha256"] == "a" * 64
    assert plan.adapter_request["sampling_policy_sha256"] == "b" * 64
    assert plan.adapter_request["compact_selection_version"] == "regular-grid-footprint-crop/1"


def test_planner_classifies_selector_mismatch_separately() -> None:
    index = (
        b"1:0:d=2026082100:HPBL:surface:7 hour fcst:\n"
        b"2:10:d=2026082100:VGRD:10 m above ground:7 hour fcst:\n"
    )
    planner = GfsPlanner(
        FakeTransport(index),
        selectors=(GfsSelector("hpbl", "HPBL", "planetary boundary layer"),),
    )

    with pytest.raises(GfsPlanningError) as captured:
        planner.plan(_request(), created_at_utc="2026-08-21T01:01:00Z")

    assert captured.value.kind == "source_contract_mismatch"
    assert "available HPBL forms" in str(captured.value)
