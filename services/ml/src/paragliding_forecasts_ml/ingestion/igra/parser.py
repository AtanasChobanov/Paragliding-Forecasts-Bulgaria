"""Strict ASCII fixed-width IGRA raw and derived parsers; no transport or repair."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable

from .models import (
    NativeIgraDerivedLevel,
    NativeIgraDerivedSounding,
    NativeIgraLevel,
    NativeIgraSounding,
)


class IgraParseError(ValueError):
    """An IGRA ZIP member is structurally malformed, truncated, or desynchronized."""


@dataclass(frozen=True)
class IgraParseResult:
    raw_soundings: tuple[NativeIgraSounding, ...]
    derived_soundings: tuple[NativeIgraDerivedSounding, ...]
    raw_scanned: int
    derived_scanned: int
    raw_selected: int
    derived_selected: int
    archive_minimum_nominal: str | None
    archive_maximum_nominal: str | None


def parse_members(
    *,
    raw_content: bytes,
    derived_content: bytes,
    station_id: str,
    dates_utc: tuple[str, ...],
    nominal_hours: tuple[int, ...],
    raw_artifact_key: str = "raw_zip",
    derived_artifact_key: str = "derived_zip",
) -> IgraParseResult:
    """Decode complete raw/derived members and retain only selected logical observations."""

    raw_all = _parse_raw(raw_content, raw_artifact_key)
    derived_all = _parse_derived(derived_content, derived_artifact_key)
    selected_raw = tuple(record for record in raw_all if _selected(record, station_id, dates_utc, nominal_hours))
    selected_derived = tuple(
        record for record in derived_all if _selected(record, station_id, dates_utc, nominal_hours)
    )
    all_nominals = sorted(
        f"{record.nominal_date_utc}T{record.nominal_hour_utc:02d}:00:00Z"
        for record in (*raw_all, *derived_all)
        if record.nominal_hour_utc is not None
    )
    return IgraParseResult(
        raw_soundings=selected_raw,
        derived_soundings=selected_derived,
        raw_scanned=len(raw_all),
        derived_scanned=len(derived_all),
        raw_selected=len(selected_raw),
        derived_selected=len(selected_derived),
        archive_minimum_nominal=all_nominals[0] if all_nominals else None,
        archive_maximum_nominal=all_nominals[-1] if all_nominals else None,
    )


def _parse_raw(content: bytes, artifact_key: str) -> tuple[NativeIgraSounding, ...]:
    lines = _ascii_lines(content, "raw")
    records: list[NativeIgraSounding] = []
    index = 0
    ordinal = 0
    while index < len(lines):
        body, original, line_number = lines[index]
        if not body:
            index += 1
            continue
        if not body.startswith("#"):
            raise IgraParseError(f"Raw IGRA line {line_number} is not a header.")
        _width(body, 71, "raw header", line_number)
        level_count = _integer(body[32:36], "NUMLEV", line_number)
        if level_count < 0:
            raise IgraParseError("Raw NUMLEV cannot be negative.")
        if index + level_count >= len(lines):
            raise IgraParseError("Raw IGRA record is truncated before NUMLEV level rows.")
        level_rows = lines[index + 1 : index + 1 + level_count]
        levels: list[NativeIgraLevel] = []
        record_digest = sha256(original + b"".join(item[1] for item in level_rows)).hexdigest()
        for level_ordinal, (level_body, _level_original, level_line) in enumerate(level_rows, start=1):
            if level_body.startswith("#"):
                raise IgraParseError("Raw IGRA record has fewer level rows than its NUMLEV.")
            _width(level_body, 51, "raw level", level_line)
            levels.append(
                NativeIgraLevel(
                    sounding_record_sha256=record_digest,
                    ordinal=level_ordinal,
                    level_type_major=level_body[0:1],
                    level_type_minor=level_body[1:2],
                    elapsed_time=_integer(level_body[3:8], "ETIME", level_line),
                    pressure=_integer(level_body[9:15], "PRESS", level_line),
                    pressure_flag=level_body[15:16],
                    geopotential_height=_integer(level_body[16:21], "GPH", level_line),
                    geopotential_height_flag=level_body[21:22],
                    temperature=_integer(level_body[22:27], "TEMP", level_line),
                    temperature_flag=level_body[27:28],
                    relative_humidity=_integer(level_body[28:33], "RH", level_line),
                    dew_point_depression=_integer(level_body[34:39], "DPDP", level_line),
                    wind_direction=_integer(level_body[40:45], "WDIR", level_line),
                    wind_speed=_integer(level_body[46:51], "WSPD", level_line),
                    raw_artifact_key=artifact_key,
                    line_number=level_line,
                )
            )
        ordinal += 1
        hour = _integer(body[24:26], "HOUR", line_number)
        records.append(
            NativeIgraSounding(
                station_id=body[1:12],
                nominal_date_utc=_date(body[13:17], body[18:20], body[21:23], line_number),
                nominal_hour_utc=None if hour == 99 else _hour(hour, line_number),
                release_time_hhmm=body[27:31],
                level_count=level_count,
                pressure_source=body[37:45].rstrip(),
                nonpressure_source=body[46:54].rstrip(),
                latitude_native=_integer(body[55:62], "LAT", line_number),
                longitude_native=_integer(body[63:71], "LON", line_number),
                record_ordinal=ordinal,
                record_sha256=record_digest,
                raw_artifact_key=artifact_key,
                header_line_number=line_number,
                levels=tuple(levels),
            )
        )
        index += level_count + 1
    return tuple(records)


def _parse_derived(content: bytes, artifact_key: str) -> tuple[NativeIgraDerivedSounding, ...]:
    lines = _ascii_lines(content, "derived")
    records: list[NativeIgraDerivedSounding] = []
    index = 0
    ordinal = 0
    parameter_names = (
        "pw", "invpress", "invhgt", "invtempdif", "mixpress", "mixhgt", "frzpress", "frzhgt",
        "lclpress", "lclhgt", "lfcpress", "lfchgt", "lnbpress", "lnbhgt", "li", "si", "ki",
        "tti", "cape", "cin",
    )
    level_names = (
        "pressure", "reported_geopotential_height", "calculated_geopotential_height", "temperature",
        "temperature_gradient", "potential_temperature", "potential_temperature_gradient",
        "virtual_temperature", "virtual_potential_temperature", "vapor_pressure", "saturation_vapor_pressure",
        "reported_relative_humidity", "calculated_relative_humidity", "relative_humidity_gradient",
        "u_wind", "u_wind_gradient", "v_wind", "v_wind_gradient", "refractivity",
    )
    while index < len(lines):
        body, original, line_number = lines[index]
        if not body:
            index += 1
            continue
        if not body.startswith("#"):
            raise IgraParseError(f"Derived IGRA line {line_number} is not a header.")
        _width(body, 157, "derived header", line_number)
        level_count = _integer(body[31:36], "NUMLEV", line_number)
        if level_count < 0 or index + level_count >= len(lines):
            raise IgraParseError("Derived IGRA record is truncated before NUMLEV level rows.")
        level_rows = lines[index + 1 : index + 1 + level_count]
        digest = sha256(original + b"".join(item[1] for item in level_rows)).hexdigest()
        levels: list[NativeIgraDerivedLevel] = []
        for level_ordinal, (level_body, _level_original, level_line) in enumerate(level_rows, start=1):
            if level_body.startswith("#"):
                raise IgraParseError("Derived IGRA record has fewer level rows than its NUMLEV.")
            _width(level_body, 151, "derived level", level_line)
            values = {
                name: _integer(level_body[offset : offset + 7], name, level_line)
                for name, offset in zip(level_names, range(0, 151, 8), strict=True)
            }
            levels.append(
                NativeIgraDerivedLevel(
                    derived_record_sha256=digest,
                    ordinal=level_ordinal,
                    values=values,
                    raw_artifact_key=artifact_key,
                    line_number=level_line,
                )
            )
        ordinal += 1
        hour = _integer(body[24:26], "HOUR", line_number)
        parameters = {
            name: _integer(body[offset : offset + 6], name, line_number)
            for name, offset in zip(parameter_names, range(37, 157, 6), strict=True)
        }
        records.append(
            NativeIgraDerivedSounding(
                station_id=body[1:12],
                nominal_date_utc=_date(body[13:17], body[18:20], body[21:23], line_number),
                nominal_hour_utc=None if hour == 99 else _hour(hour, line_number),
                release_time_hhmm=body[27:31],
                level_count=level_count,
                parameters=parameters,
                record_ordinal=ordinal,
                record_sha256=digest,
                raw_artifact_key=artifact_key,
                header_line_number=line_number,
                levels=tuple(levels),
            )
        )
        index += level_count + 1
    return tuple(records)


def _ascii_lines(content: bytes, label: str) -> list[tuple[str, bytes, int]]:
    try:
        raw_lines = content.splitlines(keepends=True)
        return [(_strip_newline(line).decode("ascii"), line, index) for index, line in enumerate(raw_lines, start=1)]
    except UnicodeDecodeError as error:
        raise IgraParseError(f"IGRA {label} member must be strict ASCII.") from error


def _strip_newline(line: bytes) -> bytes:
    if line.endswith(b"\r\n"):
        return line[:-2]
    if line.endswith(b"\n") or line.endswith(b"\r"):
        return line[:-1]
    return line


def _width(value: str, expected: int, label: str, line_number: int) -> None:
    if len(value) != expected:
        raise IgraParseError(f"IGRA {label} at line {line_number} has width {len(value)}, expected {expected}.")


def _integer(value: str, field: str, line_number: int) -> int:
    try:
        return int(value.strip())
    except ValueError as error:
        raise IgraParseError(f"IGRA {field} is not an integer at line {line_number}.") from error


def _date(year: str, month: str, day: str, line_number: int) -> str:
    try:
        from datetime import date

        return date(int(year), int(month), int(day)).isoformat()
    except ValueError as error:
        raise IgraParseError(f"IGRA header date is invalid at line {line_number}.") from error


def _hour(value: int, line_number: int) -> int:
    if value < 0 or value > 23:
        raise IgraParseError(f"IGRA nominal hour is invalid at line {line_number}.")
    return value


def _selected(record: NativeIgraSounding | NativeIgraDerivedSounding, station_id: str, dates: tuple[str, ...], hours: tuple[int, ...]) -> bool:
    return (
        record.station_id == station_id
        and record.nominal_date_utc in dates
        and (not hours or record.nominal_hour_utc in hours)
    )