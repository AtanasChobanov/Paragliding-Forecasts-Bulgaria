"""IGRA selector validation, approved URL resolution, and HEAD-only inventory."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from importlib.resources import files
from math import ceil
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from ..weather.serialization import sha256_bytes
from .models import IgraInventoryResult, IgraRemoteObject
from .transport import IgraHttpResponse, IgraTransport
from .versions import IGRA_STATION_ID, SOURCE_POLICY_RESOURCE, SOURCE_POLICY_VERSION


class IgraInventoryError(ValueError):
    """A selection or provider HEAD response cannot safely authorize collection."""


_APPROVED_HOSTS = frozenset({"ncei.noaa.gov", "www.ncei.noaa.gov"})


def load_source_policy() -> tuple[dict[str, object], str]:
    """Load and hash the one packaged policy; no mutable runtime configuration exists."""

    content = files("paragliding_forecasts_ml.ingestion.igra.resources").joinpath(
        SOURCE_POLICY_RESOURCE
    ).read_bytes()
    policy = json.loads(content)
    if policy.get("policy_version") != SOURCE_POLICY_VERSION:
        raise IgraInventoryError("Packaged IGRA source policy version is inconsistent.")
    return policy, sha256_bytes(content)


def parse_selection(
    *,
    dates: tuple[str, ...],
    start_date: str | None,
    end_date: str | None,
    nominal_hours: tuple[int, ...],
) -> tuple[tuple[str, ...], tuple[int, ...]]:
    """Enforce exclusive date selectors and a bounded sorted UTC selection."""

    if dates and (start_date is not None or end_date is not None):
        raise IgraInventoryError("Use repeatable --date or the complete date range, never both.")
    if (start_date is None) != (end_date is None):
        raise IgraInventoryError("Both --start-date and --end-date are required together.")
    if not dates and start_date is None:
        raise IgraInventoryError("At least one nominal UTC date is required.")
    try:
        if dates:
            values = tuple(date.fromisoformat(value).isoformat() for value in dates)
        else:
            start = date.fromisoformat(start_date or "")
            end = date.fromisoformat(end_date or "")
            if end < start:
                raise IgraInventoryError("IGRA date range end precedes its start.")
            values = tuple(date.fromordinal(day).isoformat() for day in range(start.toordinal(), end.toordinal() + 1))
    except ValueError as error:
        raise IgraInventoryError("Dates must be real YYYY-MM-DD UTC dates.") from error
    if len(values) != len(set(values)):
        raise IgraInventoryError("Duplicate dates are not permitted.")
    if len(values) > 366:
        raise IgraInventoryError("At most 366 unique UTC dates are permitted per run.")
    if len(nominal_hours) != len(set(nominal_hours)) or any(hour < 0 or hour > 23 for hour in nominal_hours):
        raise IgraInventoryError("Nominal hours must be unique values from 0 through 23.")
    return tuple(sorted(values)), tuple(sorted(nominal_hours))


def resolve_archive_mode(
    requested: Literal["auto", "recent", "period-of-record"],
    dates_utc: tuple[str, ...],
    *,
    now: datetime | None = None,
) -> Literal["recent", "period-of-record"]:
    """Resolve auto once; a current-year archive is never a silent historical fallback."""

    current_year = (now or datetime.now(UTC)).year
    all_current = all(date.fromisoformat(value).year == current_year for value in dates_utc)
    if requested == "auto":
        return "recent" if all_current else "period-of-record"
    if requested == "recent" and not all_current:
        raise IgraInventoryError("Recent archive selection requires only current UTC-year dates.")
    return requested


def resolved_object_templates(
    *,
    station_id: str,
    archive_mode: Literal["recent", "period-of-record"],
    dates_utc: tuple[str, ...],
    policy: dict[str, object],
) -> tuple[tuple[str, str, str, str | None], ...]:
    """Return exactly the five provider objects allowed for a single collection."""

    if station_id != IGRA_STATION_ID:
        raise IgraInventoryError("T-019 supports only station BUM00015614.")
    templates = policy["archive_templates"]
    expected = policy["expected_members"]
    format_urls = policy["format_urls"]
    assert isinstance(templates, dict) and isinstance(expected, dict) and isinstance(format_urls, dict)
    year = date.fromisoformat(dates_utc[0]).year
    raw_key = "recent_zip" if archive_mode == "recent" else "period_of_record_zip"
    raw_template_key = "recent" if archive_mode == "recent" else "period_of_record"
    raw_url = str(templates[raw_template_key]).format(station_id=station_id, year=year)
    raw_member = str(expected["recent_zip" if archive_mode == "recent" else "period_of_record_zip"]).format(
        station_id=station_id, year=year
    )
    derived_url = str(templates["derived_period_of_record"]).format(station_id=station_id)
    derived_member = str(expected["derived_zip"]).format(station_id=station_id)
    return (
        ("station_list", str(format_urls["station_list"]), "text", None),
        (raw_key, raw_url, "zip", raw_member),
        ("derived_zip", derived_url, "zip", derived_member),
        ("raw_format", str(format_urls["raw_format"]), "text", None),
        ("derived_format", str(format_urls["derived_format"]), "text", None),
    )


def inventory(
    transport: IgraTransport,
    *,
    station_id: str,
    dates_utc: tuple[str, ...],
    nominal_hours: tuple[int, ...],
    requested_archive_mode: Literal["auto", "recent", "period-of-record"],
    now: datetime | None = None,
) -> tuple[IgraInventoryResult, str]:
    """Make only five HEAD requests and return the source-policy hash for the request plan."""

    policy, policy_sha256 = load_source_policy()
    resolved = resolve_archive_mode(requested_archive_mode, dates_utc, now=now)
    objects: list[IgraRemoteObject] = []
    for key, url, media_class, expected_member in resolved_object_templates(
        station_id=station_id, archive_mode=resolved, dates_utc=dates_utc, policy=policy
    ):
        response = transport.request(url, method="HEAD")
        try:
            objects.append(_validated_head(response, key, url, media_class, expected_member))
        finally:
            response.close()
    total = sum(item.content_length for item in objects)
    return (
        IgraInventoryResult(
            station_id=station_id,
            requested_dates_utc=dates_utc,
            requested_nominal_hours=nominal_hours,
            resolved_archive_mode=resolved,
            remote_objects=tuple(objects),
            total_compressed_bytes=total,
            minimum_required_mib=ceil(total / (1024 * 1024)),
        ),
        policy_sha256,
    )


def _validated_head(
    response: IgraHttpResponse,
    key: str,
    requested_url: str,
    media_class: str,
    expected_member: str | None,
) -> IgraRemoteObject:
    if response.status < 200 or response.status >= 300:
        raise IgraInventoryError(f"IGRA HEAD failed for {key}: HTTP {response.status}.")
    requested_host = urlparse(requested_url).hostname
    final = urlparse(response.final_url)
    if final.scheme != "https" or final.hostname not in _APPROVED_HOSTS or requested_host not in _APPROVED_HOSTS:
        raise IgraInventoryError("IGRA redirect host or scheme is not approved.")
    encoding = response.header("Content-Encoding")
    if encoding not in {None, "", "identity"}:
        raise IgraInventoryError("IGRA source response must use identity content encoding.")
    try:
        length = int(response.header("Content-Length") or "")
    except ValueError as error:
        raise IgraInventoryError("IGRA Content-Length is not an integer.") from error
    if length < 1:
        raise IgraInventoryError("IGRA Content-Length must be positive.")
    basename = Path(final.path).name
    if not basename:
        raise IgraInventoryError("IGRA final URL has no safe filename.")
    content_type = (response.header("Content-Type") or "").split(";", 1)[0].lower()
    if media_class == "zip" and content_type not in {"application/zip", "application/octet-stream", "application/x-zip-compressed"}:
        raise IgraInventoryError("IGRA ZIP response has an unexpected Content-Type.")
    if media_class == "text" and content_type not in {"text/plain", "application/octet-stream"}:
        raise IgraInventoryError("IGRA text response has an unexpected Content-Type.")
    return IgraRemoteObject(
        artifact_key=key,
        url=requested_url,
        final_url=response.final_url,
        safe_basename=basename,
        media_class=media_class,
        expected_member_name=expected_member,
        head_status=response.status,
        content_length=length,
        etag=response.header("ETag"),
        last_modified=response.header("Last-Modified"),
    )