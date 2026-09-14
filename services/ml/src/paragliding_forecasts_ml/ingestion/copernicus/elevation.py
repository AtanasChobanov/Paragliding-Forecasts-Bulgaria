"""Repeatable Copernicus DEM GLO-30 point-elevation proposals."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
from tifffile import TiffFileError, imread

from ..weather.sites import SiteSamplingConfig

TOKEN_ENDPOINT = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
)
PROCESS_ENDPOINT = "https://sh.dataspace.copernicus.eu/api/v1/process"
ELEVATION_REFERENCE = "copernicus_dem_glo30_egm2008_orthometric_bilinear_v1"
EVALSCRIPT = """//VERSION=3
function setup() {
  return {
    input: ["DEM", "dataMask"],
    output: { bands: 2, sampleType: SampleType.FLOAT32 }
  };
}
function evaluatePixel(sample) {
  return [sample.DEM, sample.dataMask];
}
"""


class CopernicusElevationError(RuntimeError):
    """Authentication, request, or DEM decoding failed closed."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


class HttpTransport:
    def request(
        self,
        url: str,
        *,
        method: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> HttpResponse:
        raise NotImplementedError


class UrllibTransport(HttpTransport):
    def request(
        self,
        url: str,
        *,
        method: str,
        headers: Mapping[str, str],
        body: bytes,
    ) -> HttpResponse:
        request = Request(url, method=method, headers=dict(headers), data=body)
        try:
            with urlopen(request, timeout=30) as response:
                return HttpResponse(
                    status=response.status,
                    headers=dict(response.headers.items()),
                    body=response.read(),
                )
        except HTTPError as error:
            return HttpResponse(
                status=error.code,
                headers=dict(error.headers.items()) if error.headers else {},
                body=error.read(),
            )
        except (TimeoutError, URLError, OSError) as error:
            raise CopernicusElevationError("Copernicus network request failed.") from error


def process_request(site: SiteSamplingConfig) -> dict[str, object]:
    """Build the fixed one-pixel request whose centre is the approved coordinate."""

    half_span_deg = 0.000005
    return {
        "input": {
            "bounds": {
                "bbox": [
                    site.longitude_deg - half_span_deg,
                    site.latitude_deg - half_span_deg,
                    site.longitude_deg + half_span_deg,
                    site.latitude_deg + half_span_deg,
                ],
                "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
            },
            "data": [
                {
                    "type": "dem",
                    "dataFilter": {"demInstance": "COPERNICUS_30"},
                    "processing": {
                        "upsampling": "BILINEAR",
                        "downsampling": "BILINEAR",
                        "egm": False,
                    },
                }
            ],
        },
        "output": {
            "width": 1,
            "height": 1,
            "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}],
        },
        "evalscript": EVALSCRIPT,
    }


def decode_elevation_tiff(payload: bytes) -> float:
    try:
        values = np.asarray(imread(BytesIO(payload)), dtype=np.float64).reshape(-1)
    except (TiffFileError, ValueError, TypeError, OSError) as error:
        raise CopernicusElevationError("Copernicus DEM response is not a valid TIFF.") from error
    if values.size != 2:
        raise CopernicusElevationError("Copernicus DEM response must contain DEM and dataMask.")
    elevation, data_mask = (float(values[0]), float(values[1]))
    if data_mask != 1 or not math.isfinite(elevation):
        raise CopernicusElevationError("Copernicus DEM returned missing or invalid point data.")
    return elevation


class CopernicusElevationClient:
    def __init__(
        self,
        transport: HttpTransport,
        *,
        client_id: str,
        client_secret: str,
    ) -> None:
        if not client_id.strip() or not client_secret.strip():
            raise CopernicusElevationError(
                "CDSE_CLIENT_ID and CDSE_CLIENT_SECRET must both be configured."
            )
        self._transport = transport
        self._client_id = client_id
        self._client_secret = client_secret

    def _access_token(self) -> str:
        response = self._transport.request(
            TOKEN_ENDPOINT,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body=urlencode(
                {
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                }
            ).encode("utf-8"),
        )
        if response.status != 200:
            raise CopernicusElevationError(
                f"Copernicus authentication returned HTTP {response.status}."
            )
        try:
            payload = json.loads(response.body)
            token = payload["access_token"]
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise CopernicusElevationError(
                "Copernicus authentication response omitted access_token."
            ) from error
        if not isinstance(token, str) or not token:
            raise CopernicusElevationError(
                "Copernicus authentication response omitted access_token."
            )
        return token

    def fetch(self, sites: Sequence[SiteSamplingConfig]) -> dict[str, object]:
        token = self._access_token()
        results: list[dict[str, object]] = []
        for site in sites:
            response = self._transport.request(
                PROCESS_ENDPOINT,
                method="POST",
                headers={
                    "Accept": "image/tiff",
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                body=json.dumps(
                    process_request(site), sort_keys=True, separators=(",", ":")
                ).encode("utf-8"),
            )
            if response.status != 200:
                raise CopernicusElevationError(
                    f"Copernicus DEM request for {site.site_slug} returned HTTP {response.status}."
                )
            elevation = round(decode_elevation_tiff(response.body), 3)
            results.append(
                {
                    "site_id": site.site_id,
                    "site_slug": site.site_slug,
                    "latitude_deg": site.latitude_deg,
                    "longitude_deg": site.longitude_deg,
                    "coordinate_reference": site.coordinate_reference,
                    "reference_elevation_msl_m": elevation,
                    "elevation_reference": ELEVATION_REFERENCE,
                }
            )
        return {
            "schema_version": "copernicus-site-elevations-v1",
            "source": {
                "dataset": "COP-DEM GLO-30 Public with GLO-90 fill",
                "dem_instance": "COPERNICUS_30",
                "vertical_reference": "EGM2008 orthometric height",
                "unit": "m",
                "upsampling": "BILINEAR",
                "downsampling": "BILINEAR",
                "egm": False,
            },
            "sites": results,
        }
