from __future__ import annotations

import pytest

from paragliding_forecasts_ml.ingestion.gfs.inventory import GfsSelector
from paragliding_forecasts_ml.ingestion.gfs.models import GfsRequest
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
