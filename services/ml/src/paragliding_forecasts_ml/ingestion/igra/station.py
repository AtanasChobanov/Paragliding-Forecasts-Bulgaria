"""Fixed-column IGRA station-list parsing for the one supported station."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from ..weather.serialization import sha256_bytes


class IgraStationError(ValueError):
    """Station inventory evidence is malformed, absent, or ambiguous."""


@dataclass(frozen=True)
class IgraStation:
    station_id: str
    latitude_deg: float
    longitude_deg: float
    elevation_m: int | None
    name: str
    first_year: int | None
    last_year: int | None
    observation_count: int | None
    line_number: int
    line_sha256: str


def parse_station_list(content: bytes, station_id: str) -> IgraStation:
    """Read the selected documented fixed-column row from NOAA's UTF-8 list.

    NOAA's complete station list contains UTF-8 names. Field offsets stay byte
    based, so non-selected rows are never decoded or allowed to shift Sofia's
    fixed-column numeric fields.
    """

    try:
        station_bytes = station_id.encode("ascii")
    except UnicodeEncodeError as error:
        raise IgraStationError("IGRA station identifiers must be ASCII.") from error
    matches: list[IgraStation] = []
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        if not raw_line.strip():
            continue
        if len(raw_line) < 88:
            raise IgraStationError(f"IGRA station-list row {line_number} is truncated.")
        if raw_line[0:11] != station_bytes:
            continue
        try:
            latitude = float(raw_line[12:20].decode("ascii"))
            longitude = float(raw_line[21:30].decode("ascii"))
        except (UnicodeDecodeError, ValueError) as error:
            raise IgraStationError(
                "IGRA station coordinates are not fixed-width numbers."
            ) from error
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise IgraStationError("IGRA station coordinates are outside physical ranges.")
        matches.append(
            IgraStation(
                station_id=raw_line[0:11].decode("ascii"),
                latitude_deg=latitude,
                longitude_deg=longitude,
                elevation_m=_optional_elevation(raw_line[31:37]),
                name=_utf8_text(raw_line[40:70], "name"),
                first_year=_optional_int(raw_line[72:76]),
                last_year=_optional_int(raw_line[77:81]),
                observation_count=_optional_int(raw_line[83:88]),
                line_number=line_number,
                line_sha256=sha256_bytes(raw_line + b"\n"),
            )
        )
    if len(matches) != 1:
        raise IgraStationError(f"Expected exactly one IGRA station row; found {len(matches)}.")
    return matches[0]


def _utf8_text(value: bytes, field: str) -> str:
    try:
        return value.decode("utf-8").strip()
    except UnicodeDecodeError as error:
        raise IgraStationError(f"IGRA station {field} is not valid UTF-8.") from error


def _optional_elevation(value: bytes) -> int | None:
    try:
        text = value.decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise IgraStationError("IGRA station elevation is malformed.") from error
    if not text:
        return None
    try:
        elevation = float(text)
    except ValueError as error:
        raise IgraStationError("IGRA station elevation is malformed.") from error
    if elevation == -999.9:
        return None
    if not isfinite(elevation) or not elevation.is_integer():
        raise IgraStationError("IGRA station elevation must be an integral number of metres.")
    return int(elevation)


def _optional_int(value: bytes) -> int | None:
    try:
        stripped = value.decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise IgraStationError("IGRA station integer field is malformed.") from error
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError as error:
        raise IgraStationError("IGRA station integer field is malformed.") from error
