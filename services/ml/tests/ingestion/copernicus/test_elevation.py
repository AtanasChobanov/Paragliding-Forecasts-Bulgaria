from __future__ import annotations

import json
from io import BytesIO

import numpy as np
import pytest
from tifffile import imwrite

from paragliding_forecasts_ml.ingestion.copernicus.elevation import (
    PROCESS_ENDPOINT,
    TOKEN_ENDPOINT,
    CopernicusElevationClient,
    CopernicusElevationError,
    HttpResponse,
    HttpTransport,
    decode_elevation_tiff,
    process_request,
)
from paragliding_forecasts_ml.ingestion.weather.sites import SiteSamplingConfig


class FakeTransport(HttpTransport):
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, str, dict[str, str], bytes]] = []

    def request(self, url, *, method, headers, body):
        self.requests.append((url, method, dict(headers), body))
        return self.responses.pop(0)


def _site() -> SiteSamplingConfig:
    return SiteSamplingConfig(
        site_id=7,
        site_slug="dobrich-region",
        site_name="Dobrich region",
        site_time_zone="Europe/Sofia",
        latitude_deg=43.746321,
        longitude_deg=28.074025,
        coordinate_reference="kardam_accepted_flight_centroid_v1",
        reference_elevation_msl_m=None,
        elevation_reference=None,
    )


def _tiff(elevation: float, data_mask: float = 1) -> bytes:
    output = BytesIO()
    imwrite(
        output,
        np.array([[[elevation, data_mask]]], dtype=np.float32),
        photometric="minisblack",
        planarconfig="contig",
        metadata=None,
    )
    return output.getvalue()


def test_process_request_centres_one_bilinear_orthometric_pixel() -> None:
    request = process_request(_site())

    assert request["input"]["data"][0] == {
        "type": "dem",
        "dataFilter": {"demInstance": "COPERNICUS_30"},
        "processing": {
            "upsampling": "BILINEAR",
            "downsampling": "BILINEAR",
            "egm": False,
        },
    }
    assert request["output"]["width"] == 1
    assert request["output"]["height"] == 1
    west, south, east, north = request["input"]["bounds"]["bbox"]
    assert (west + east) / 2 == pytest.approx(_site().longitude_deg)
    assert (south + north) / 2 == pytest.approx(_site().latitude_deg)


def test_client_authenticates_once_and_returns_deterministic_site_proposal() -> None:
    transport = FakeTransport(
        [
            HttpResponse(200, {}, json.dumps({"access_token": "token"}).encode()),
            HttpResponse(200, {"Content-Type": "image/tiff"}, _tiff(151.23456)),
        ]
    )
    client = CopernicusElevationClient(
        transport, client_id="client-id", client_secret="client-secret"
    )

    proposal = client.fetch([_site()])

    assert proposal["schema_version"] == "copernicus-site-elevations-v1"
    assert proposal["sites"] == [
        {
            "site_id": 7,
            "site_slug": "dobrich-region",
            "latitude_deg": 43.746321,
            "longitude_deg": 28.074025,
            "coordinate_reference": "kardam_accepted_flight_centroid_v1",
            "reference_elevation_msl_m": 151.235,
            "elevation_reference": "copernicus_dem_glo30_egm2008_orthometric_bilinear_v1",
        }
    ]
    assert [request[0] for request in transport.requests] == [TOKEN_ENDPOINT, PROCESS_ENDPOINT]
    assert transport.requests[1][2]["Authorization"] == "Bearer token"
    assert b"client-secret" in transport.requests[0][3]
    assert b"client-secret" not in transport.requests[1][3]


def test_decoder_and_client_fail_closed_for_missing_or_invalid_payloads() -> None:
    with pytest.raises(CopernicusElevationError, match="missing"):
        decode_elevation_tiff(_tiff(100, data_mask=0))
    with pytest.raises(CopernicusElevationError, match="valid TIFF"):
        decode_elevation_tiff(b"not-a-tiff")

    transport = FakeTransport([HttpResponse(401, {}, b'{"error":"invalid_client"}')])
    client = CopernicusElevationClient(transport, client_id="client", client_secret="secret")
    with pytest.raises(CopernicusElevationError, match="HTTP 401"):
        client.fetch([_site()])
