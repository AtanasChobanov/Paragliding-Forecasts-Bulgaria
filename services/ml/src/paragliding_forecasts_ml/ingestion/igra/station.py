"""Strict fixed-width IGRA station-list parsing for the one supported station."""

from __future__ import annotations

from dataclasses import dataclass

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
    """Read documented fixed columns and require exactly one station row."""

    try:
        lines = content.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise IgraStationError("IGRA station list must be strict ASCII.") from error
    matches: list[IgraStation] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        if len(line) < 84:
            raise IgraStationError(f"IGRA station-list row {line_number} is truncated.")
        if line[0:11] != station_id:
            continue
        try:
            latitude = float(line[12:20])
            longitude = float(line[21:30])
        except ValueError as error:
            raise IgraStationError("IGRA station coordinates are not fixed-width numbers.") from error
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise IgraStationError("IGRA station coordinates are outside physical ranges.")
        matches.append(
            IgraStation(
                station_id=line[0:11],
                latitude_deg=latitude,
                longitude_deg=longitude,
                elevation_m=_optional_int(line[31:37]),
                name=line[38:68].rstrip(),
                first_year=_optional_int(line[69:73]),
                last_year=_optional_int(line[74:78]),
                observation_count=_optional_int(line[79:84]),
                line_number=line_number,
                line_sha256=sha256_bytes((line + "\n").encode("ascii")),
            )
        )
    if len(matches) != 1:
        raise IgraStationError(f"Expected exactly one IGRA station row; found {len(matches)}.")
    return matches[0]


def _optional_int(value: str) -> int | None:
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError as error:
        raise IgraStationError("IGRA station integer field is malformed.") from error