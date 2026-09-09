"""Strict parsing and bounded byte-range planning for GFS ``.idx`` files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from .profile import GFS_FEATURE_PROFILE_PRESSURES_HPA


class InventoryError(ValueError):
    """An official GFS inventory cannot safely define byte ranges."""


class SelectorContractError(InventoryError):
    """The configured selector contract does not resolve against a valid inventory."""


@dataclass(frozen=True)
class GfsIndexEntry:
    """One native wgrib2-style inventory line."""

    message_number: int
    offset: int
    reference_at_utc: str
    parameter: str
    level: str
    forecast_descriptor: str
    raw_line: str


@dataclass(frozen=True)
class GfsSelector:
    """One parameter/level/temporal semantic required by the raw collector."""

    key: str
    parameter: str
    level: str
    temporal_kind: Literal["point", "average", "accumulation"] = "point"
    minimum_lead_hours: int = 0
    allow_tied_matches: bool = False


@dataclass(frozen=True)
class GfsByteRange:
    """One inclusive HTTP byte range containing whole GRIB messages."""

    start: int
    end: int
    selector_keys: tuple[str, ...]
    message_numbers: tuple[int, ...]
    forecast_descriptors: tuple[str, ...]

    @property
    def byte_count(self) -> int:
        return self.end - self.start + 1


# This set is source-native. S04 maps these messages to the T-017 catalogue.
DEFAULT_SELECTORS: tuple[GfsSelector, ...] = (
    GfsSelector("tmp_2m", "TMP", "2 m above ground"),
    GfsSelector("dpt_2m", "DPT", "2 m above ground"),
    GfsSelector("rh_2m", "RH", "2 m above ground"),
    GfsSelector("spfh_2m", "SPFH", "2 m above ground"),
    GfsSelector("ugrd_10m", "UGRD", "10 m above ground"),
    GfsSelector("vgrd_10m", "VGRD", "10 m above ground"),
    GfsSelector("gust_surface", "GUST", "surface"),
    GfsSelector("pres_surface", "PRES", "surface"),
    GfsSelector("prmsl", "PRMSL", "mean sea level"),
    GfsSelector("orog", "HGT", "surface"),
    GfsSelector("hpbl", "HPBL", "surface"),
    GfsSelector("tcdc", "TCDC", "entire atmosphere"),
    GfsSelector("lcdc", "LCDC", "low cloud layer"),
    GfsSelector("mcdc", "MCDC", "middle cloud layer"),
    GfsSelector("hcdc", "HCDC", "high cloud layer"),
    GfsSelector(
        "apcp",
        "APCP",
        "surface",
        temporal_kind="accumulation",
        minimum_lead_hours=1,
        allow_tied_matches=True,
    ),
    GfsSelector(
        "dswrf",
        "DSWRF",
        "surface",
        temporal_kind="average",
        minimum_lead_hours=1,
    ),
    GfsSelector(
        "shtfl",
        "SHTFL",
        "surface",
        temporal_kind="average",
        minimum_lead_hours=1,
    ),
    GfsSelector(
        "lhtfl",
        "LHTFL",
        "surface",
        temporal_kind="average",
        minimum_lead_hours=1,
    ),
    GfsSelector("pwat", "PWAT", "entire atmosphere (considered as a single layer)"),
    GfsSelector("cape_surface", "CAPE", "surface"),
    GfsSelector("cin_surface", "CIN", "surface"),
    GfsSelector("cape_layer", "CAPE", "180-0 mb above ground"),
    GfsSelector("cin_layer", "CIN", "180-0 mb above ground"),
    *(
        GfsSelector(f"{name.lower()}_{pressure}", name, f"{pressure} mb")
        for pressure in GFS_FEATURE_PROFILE_PRESSURES_HPA
        for name in ("HGT", "TMP", "RH", "SPFH", "UGRD", "VGRD", "VVEL")
    ),
)


def parse_index(content: bytes) -> tuple[GfsIndexEntry, ...]:
    """Parse an index without guessing malformed fields or offsets."""

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise InventoryError("GFS index is not UTF-8 text.") from error
    entries: list[GfsIndexEntry] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        parts = raw.split(":")
        if len(parts) < 6 or not parts[2].startswith("d="):
            raise InventoryError(f"Malformed GFS index line {line_number}.")
        try:
            message_number = int(parts[0])
            offset = int(parts[1])
            reference = datetime.strptime(parts[2][2:12], "%Y%m%d%H").replace(tzinfo=UTC)
        except ValueError as error:
            raise InventoryError(f"Invalid GFS index number/time on line {line_number}.") from error
        if message_number < 1 or offset < 0 or not parts[3] or not parts[4]:
            raise InventoryError(f"Invalid GFS index identity on line {line_number}.")
        entry = GfsIndexEntry(
            message_number=message_number,
            offset=offset,
            reference_at_utc=reference.strftime("%Y-%m-%dT%H:%M:%SZ"),
            parameter=parts[3],
            level=parts[4],
            forecast_descriptor=":".join(parts[5:]).rstrip(":"),
            raw_line=raw,
        )
        if entries and (
            entry.message_number <= entries[-1].message_number or entry.offset <= entries[-1].offset
        ):
            raise InventoryError(
                "GFS index message numbers and offsets must be strictly increasing."
            )
        entries.append(entry)
    if not entries:
        raise InventoryError("GFS index has no records.")
    return tuple(entries)


_INTERVAL_RE = re.compile(
    r"^(?P<start>\d+)-(?P<end>\d+) (?P<unit>hour|day) (?P<kind>ave|acc) fcst$"
)


def _point_descriptor(lead_hours: int) -> str:
    return "anl" if lead_hours == 0 else f"{lead_hours} hour fcst"


def _interval_hours(descriptor: str, *, kind: str, lead_hours: int) -> tuple[int, int] | None:
    match = _INTERVAL_RE.fullmatch(descriptor)
    if match is None or match.group("kind") != kind:
        return None
    multiplier = 24 if match.group("unit") == "day" else 1
    start = int(match.group("start")) * multiplier
    end = int(match.group("end")) * multiplier
    if end != lead_hours or start >= end:
        return None
    return start, end


def _selector_hits(
    entries: tuple[GfsIndexEntry, ...], selector: GfsSelector, *, lead_hours: int
) -> list[tuple[int, GfsIndexEntry]]:
    candidates = [
        (index, entry)
        for index, entry in enumerate(entries)
        if entry.parameter == selector.parameter and entry.level == selector.level
    ]
    if selector.temporal_kind == "point":
        descriptor = _point_descriptor(lead_hours)
        return [
            (index, entry) for index, entry in candidates if entry.forecast_descriptor == descriptor
        ]

    interval_kind = "ave" if selector.temporal_kind == "average" else "acc"
    intervals = [
        (index, entry, interval)
        for index, entry in candidates
        if (
            interval := _interval_hours(
                entry.forecast_descriptor,
                kind=interval_kind,
                lead_hours=lead_hours,
            )
        )
        is not None
    ]
    if not intervals:
        return []
    shortest = min(end - start for _index, _entry, (start, end) in intervals)
    return [(index, entry) for index, entry, (start, end) in intervals if end - start == shortest]


def select_ranges(
    entries: tuple[GfsIndexEntry, ...],
    *,
    content_length: int,
    lead_hours: int,
    selectors: tuple[GfsSelector, ...] = DEFAULT_SELECTORS,
    maximum_range_bytes: int,
) -> tuple[GfsByteRange, ...]:
    """Return exact whole-message ranges selected by native temporal semantics."""

    if content_length < 1 or maximum_range_bytes < 1 or lead_hours < 0:
        raise InventoryError("GFS object, lead and range byte limits must be valid.")
    matched: list[tuple[GfsIndexEntry, str, int, int]] = []
    for selector in selectors:
        if lead_hours < selector.minimum_lead_hours:
            continue
        hits = _selector_hits(entries, selector, lead_hours=lead_hours)
        if not hits:
            available = sorted(
                {
                    f"{entry.level} [{entry.forecast_descriptor}]"
                    for entry in entries
                    if entry.parameter == selector.parameter
                }
            )
            raise SelectorContractError(
                f"Selector {selector.key} found no matching message at f{lead_hours:03d}; "
                f"available {selector.parameter} forms: {available or ['none']}."
            )
        if len(hits) > 1 and not selector.allow_tied_matches:
            descriptors = [entry.forecast_descriptor for _index, entry in hits]
            raise SelectorContractError(
                f"Selector {selector.key} is ambiguous at f{lead_hours:03d}: {descriptors}."
            )
        for index, entry in hits:
            end = entries[index + 1].offset - 1 if index + 1 < len(entries) else content_length - 1
            if end < entry.offset or end >= content_length:
                raise InventoryError("GFS index offsets exceed the GRIB object length.")
            if end - entry.offset + 1 > maximum_range_bytes:
                raise InventoryError(
                    f"Selected GFS message {entry.message_number} exceeds range cap."
                )
            matched.append((entry, selector.key, entry.offset, end))
    matched.sort(key=lambda item: item[2])
    ranges: list[GfsByteRange] = []
    for entry, selector_key, start, end in matched:
        if (
            ranges
            and start == ranges[-1].end + 1
            and ranges[-1].byte_count + end - start + 1 <= maximum_range_bytes
        ):
            previous = ranges.pop()
            ranges.append(
                GfsByteRange(
                    previous.start,
                    end,
                    previous.selector_keys + (selector_key,),
                    previous.message_numbers + (entry.message_number,),
                    previous.forecast_descriptors + (entry.forecast_descriptor,),
                )
            )
        else:
            ranges.append(
                GfsByteRange(
                    start,
                    end,
                    (selector_key,),
                    (entry.message_number,),
                    (entry.forecast_descriptor,),
                )
            )
    return tuple(ranges)
