"""Resolve explicit or newest complete GFS cycles from official object inventories."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

from ..atmosphere.catalogue import load_catalogue
from ..atmosphere.contracts import RequestPlan
from .inventory import DEFAULT_SELECTORS, InventoryError, parse_index, select_ranges
from .models import GFS_BUCKET_URL, GFS_SOURCE_ID, GfsPlannedRange, GfsRequest, GfsResolvedPlan
from .transport import GfsTransportError, HttpTransport


class GfsPlanningError(RuntimeError):
    """A GFS source plan cannot be safely resolved."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


def _parse_http_time(value: str | None) -> str:
    if not value:
        raise GfsPlanningError("invalid_inventory", "GFS object is missing Last-Modified metadata.")
    try:
        return parsedate_to_datetime(value).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, IndexError) as error:
        raise GfsPlanningError(
            "invalid_inventory", "GFS Last-Modified metadata is invalid."
        ) from error


def _object_urls(run_at_utc: str, lead: int) -> tuple[str, str, str]:
    run = datetime.strptime(run_at_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    key = f"gfs.{run:%Y%m%d}/{run:%H}/atmos/gfs.t{run:%H}z.pgrb2.0p25.f{lead:03d}"
    url = f"{GFS_BUCKET_URL}/{key}"
    return key, url, f"{url}.idx"


class GfsPlanner:
    """Checks candidate GRIB/index coverage before any raw payload is written."""

    def __init__(self, transport: HttpTransport, *, selectors=DEFAULT_SELECTORS) -> None:
        self.selectors = selectors
        self.transport = transport

    def plan(self, request: GfsRequest, *, created_at_utc: str) -> RequestPlan:
        mode = request.selection_mode()
        candidates = self._candidates(request)
        last_incomplete: GfsPlanningError | None = None
        for run_at_utc in candidates:
            try:
                resolved = self._probe_complete_run(request, mode, run_at_utc)
            except GfsPlanningError as error:
                if mode == "explicit" or error.kind not in {"absent_file", "incomplete_run"}:
                    raise
                last_incomplete = error
                continue
            catalogue = load_catalogue()
            keys = tuple(
                [
                    f"gfs_grib_f{item.lead_hours:03d}_r{index:03d}"
                    for index, item in enumerate(resolved.ranges, start=1)
                ]
                + ["gfs_collection_record"]
            )
            return RequestPlan(
                run_key=request.run_key,
                source_id=GFS_SOURCE_ID,
                source_kind="forecast",
                ingestion_method="public_object_archive",
                request_purpose=request.request_purpose,
                catalogue_version=catalogue.version,
                catalogue_sha256=catalogue.sha256,
                adapter_request_schema_version=1,
                adapter_request=resolved.model_dump(mode="json"),
                expected_artifact_keys=keys,
                created_at_utc=created_at_utc,
            )
        raise last_incomplete or GfsPlanningError(
            "incomplete_run", "No complete GFS candidate before cutoff."
        )

    def _candidates(self, request: GfsRequest) -> tuple[str, ...]:
        if request.explicit_run_at_utc:
            return (request.explicit_run_at_utc,)
        assert request.newest_complete_before_utc is not None
        cutoff = datetime.strptime(
            request.newest_complete_before_utc, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=UTC)
        first = cutoff.replace(minute=0, second=0, microsecond=0) - timedelta(hours=cutoff.hour % 6)
        return tuple(
            (first - timedelta(hours=6 * item)).strftime("%Y-%m-%dT%H:%M:%SZ")
            for item in range(request.maximum_cycles_back)
        )

    def _probe_complete_run(
        self, request: GfsRequest, mode: str, run_at_utc: str
    ) -> GfsResolvedPlan:
        run_at = datetime.strptime(run_at_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        grouped: dict[int, str] = {}
        for valid_at_utc in request.valid_at_utc:
            valid = datetime.strptime(valid_at_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            delta = valid - run_at
            if delta.total_seconds() < 0 or delta.total_seconds() % 3600:
                raise GfsPlanningError(
                    "incomplete_run", "GFS valid time does not map to an hourly forecast lead."
                )
            lead = int(delta.total_seconds() // 3600)
            if lead > 384:
                raise GfsPlanningError("incomplete_run", "GFS valid time exceeds f384.")
            grouped[lead] = valid_at_utc
        planned: list[GfsPlannedRange] = []
        availability: list[str] = []
        for lead, valid_at_utc in sorted(grouped.items()):
            _key, grib_url, index_url = _object_urls(run_at_utc, lead)
            try:
                head = self.transport.request(grib_url, method="HEAD")
                index = self.transport.request(index_url)
            except GfsTransportError as error:
                raise GfsPlanningError(
                    "network_failure", "GFS inventory transport failed."
                ) from error
            if head.status == 404 or index.status == 404:
                raise GfsPlanningError(
                    "absent_file", f"GFS lead f{lead:03d} object or index is absent."
                )
            if head.status != 200 or index.status != 200:
                raise GfsPlanningError(
                    "network_failure", f"GFS inventory returned HTTP {head.status}/{index.status}."
                )
            try:
                length = int(head.header("Content-Length") or "")
                entries = parse_index(index.body)
                ranges = select_ranges(
                    entries,
                    content_length=length,
                    selectors=self.selectors,
                    maximum_range_bytes=request.maximum_range_bytes,
                )
            except (ValueError, InventoryError) as error:
                raise GfsPlanningError(
                    "incomplete_run", f"GFS f{lead:03d} inventory is incomplete: {error}"
                ) from error
            modified = _parse_http_time(head.header("Last-Modified"))
            availability.append(modified)
            for byte_range in ranges:
                planned.append(
                    GfsPlannedRange(
                        lead_hours=lead,
                        valid_at_utc=valid_at_utc,
                        grib_url=grib_url,
                        index_url=index_url,
                        index_sha256=hashlib.sha256(index.body).hexdigest(),
                        object_content_length=length,
                        object_etag=head.header("ETag"),
                        object_last_modified_utc=modified,
                        byte_start=byte_range.start,
                        byte_end=byte_range.end,
                        selector_keys=byte_range.selector_keys,
                        message_numbers=byte_range.message_numbers,
                    )
                )
        if (
            sum(item.byte_end - item.byte_start + 1 for item in planned)
            > request.maximum_total_bytes
        ):
            raise GfsPlanningError(
                "incomplete_run", "GFS requested scope exceeds the configured total byte cap."
            )
        available_at = max(availability)
        if request.newest_complete_before_utc and available_at > request.newest_complete_before_utc:
            raise GfsPlanningError(
                "incomplete_run", "GFS candidate became available after the requested cutoff."
            )
        key, _url, _idx = _object_urls(run_at_utc, 0)
        return GfsResolvedPlan(
            selection_mode=mode,
            resolved_run_at_utc=run_at_utc,
            available_at_utc=available_at,
            source_product_key=key.rsplit("/", maxsplit=1)[0],
            ranges=tuple(planned),
        )
