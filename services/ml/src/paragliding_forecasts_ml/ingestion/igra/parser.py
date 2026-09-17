"""Strict streaming ASCII fixed-width IGRA raw and derived parsers."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from hashlib import sha256

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


@dataclass(frozen=True)
class _RawMemberResult:
    records: tuple[NativeIgraSounding, ...]
    scanned: int
    minimum_nominal: str | None
    maximum_nominal: str | None


@dataclass(frozen=True)
class _DerivedMemberResult:
    records: tuple[NativeIgraDerivedSounding, ...]
    scanned: int
    minimum_nominal: str | None
    maximum_nominal: str | None


_MEMBER_CONTENT = bytes | Iterable[bytes]


def parse_members(
    *,
    raw_content: _MEMBER_CONTENT,
    derived_content: _MEMBER_CONTENT,
    station_id: str,
    dates_utc: tuple[str, ...],
    nominal_hours: tuple[int, ...],
    raw_artifact_key: str = "raw_zip",
    derived_artifact_key: str = "derived_zip",
) -> IgraParseResult:
    """Decode complete members while retaining only selected logical observations.

    Each ZIP member is consumed one physical line at a time. Memory is bounded by
    the selected logical records and the current provider record, not archive size.
    """

    raw = _parse_raw(
        raw_content,
        raw_artifact_key,
        station_id=station_id,
        dates_utc=dates_utc,
        nominal_hours=nominal_hours,
    )
    derived = _parse_derived(
        derived_content,
        derived_artifact_key,
        station_id=station_id,
        dates_utc=dates_utc,
        nominal_hours=nominal_hours,
    )
    bounds = tuple(
        value
        for value in (
            raw.minimum_nominal,
            raw.maximum_nominal,
            derived.minimum_nominal,
            derived.maximum_nominal,
        )
        if value is not None
    )
    return IgraParseResult(
        raw_soundings=raw.records,
        derived_soundings=derived.records,
        raw_scanned=raw.scanned,
        derived_scanned=derived.scanned,
        raw_selected=len(raw.records),
        derived_selected=len(derived.records),
        archive_minimum_nominal=min(bounds) if bounds else None,
        archive_maximum_nominal=max(bounds) if bounds else None,
    )


def _parse_raw(
    content: _MEMBER_CONTENT,
    artifact_key: str,
    *,
    station_id: str,
    dates_utc: tuple[str, ...],
    nominal_hours: tuple[int, ...],
) -> _RawMemberResult:
    records: list[NativeIgraSounding] = []
    scanned = 0
    minimum_nominal: str | None = None
    maximum_nominal: str | None = None
    lines = iter(_ascii_lines(content, "raw"))

    while True:
        try:
            body, original, line_number = next(lines)
        except StopIteration:
            break
        if not body:
            continue
        if not body.startswith("#"):
            raise IgraParseError(f"Raw IGRA line {line_number} is not a header.")
        _width(body, 71, "raw header", line_number)
        level_count = _integer(body[32:36], "NUMLEV", line_number)
        if level_count < 0:
            raise IgraParseError("Raw NUMLEV cannot be negative.")

        scanned += 1
        record_station_id = body[1:12]
        nominal_date = _date(body[13:17], body[18:20], body[21:23], line_number)
        hour = _integer(body[24:26], "HOUR", line_number)
        nominal_hour = None if hour == 99 else _hour(hour, line_number)
        minimum_nominal, maximum_nominal = _include_nominal(
            minimum_nominal,
            maximum_nominal,
            nominal_date,
            nominal_hour,
        )
        latitude_native = _integer(body[55:62], "LAT", line_number)
        longitude_native = _integer(body[63:71], "LON", line_number)
        selected = _selected_values(
            record_station_id,
            nominal_date,
            nominal_hour,
            station_id,
            dates_utc,
            nominal_hours,
        )
        digest = sha256(original)
        selected_level_values: list[tuple[dict[str, int | str], int]] = []

        for level_ordinal in range(1, level_count + 1):
            level_body, level_original, level_line = _next_level(lines, "Raw")
            if level_body.startswith("#"):
                raise IgraParseError("Raw IGRA record has fewer level rows than its NUMLEV.")
            _width(level_body, 52, "raw level", level_line)
            values = _raw_level_values(level_body, level_line)
            digest.update(level_original)
            if selected:
                selected_level_values.append((values, level_line))

        if selected:
            record_sha256 = digest.hexdigest()
            levels = tuple(
                NativeIgraLevel(
                    sounding_record_sha256=record_sha256,
                    ordinal=level_ordinal,
                    level_type_major=values["level_type_major"],
                    level_type_minor=values["level_type_minor"],
                    elapsed_time=values["elapsed_time"],
                    pressure=values["pressure"],
                    pressure_flag=values["pressure_flag"],
                    geopotential_height=values["geopotential_height"],
                    geopotential_height_flag=values["geopotential_height_flag"],
                    temperature=values["temperature"],
                    temperature_flag=values["temperature_flag"],
                    relative_humidity=values["relative_humidity"],
                    dew_point_depression=values["dew_point_depression"],
                    wind_direction=values["wind_direction"],
                    wind_speed=values["wind_speed"],
                    raw_artifact_key=artifact_key,
                    line_number=level_line,
                )
                for level_ordinal, (values, level_line) in enumerate(selected_level_values, start=1)
            )
            records.append(
                NativeIgraSounding(
                    station_id=record_station_id,
                    nominal_date_utc=nominal_date,
                    nominal_hour_utc=nominal_hour,
                    release_time_hhmm=body[27:31],
                    level_count=level_count,
                    pressure_source=body[37:45].rstrip(),
                    nonpressure_source=body[46:54].rstrip(),
                    latitude_native=latitude_native,
                    longitude_native=longitude_native,
                    record_ordinal=scanned,
                    record_sha256=record_sha256,
                    raw_artifact_key=artifact_key,
                    header_line_number=line_number,
                    levels=levels,
                )
            )

    return _RawMemberResult(tuple(records), scanned, minimum_nominal, maximum_nominal)


def _parse_derived(
    content: _MEMBER_CONTENT,
    artifact_key: str,
    *,
    station_id: str,
    dates_utc: tuple[str, ...],
    nominal_hours: tuple[int, ...],
) -> _DerivedMemberResult:
    parameter_names = (
        "pw",
        "invpress",
        "invhgt",
        "invtempdif",
        "mixpress",
        "mixhgt",
        "frzpress",
        "frzhgt",
        "lclpress",
        "lclhgt",
        "lfcpress",
        "lfchgt",
        "lnbpress",
        "lnbhgt",
        "li",
        "si",
        "ki",
        "tti",
        "cape",
        "cin",
    )
    level_names = (
        "pressure",
        "reported_geopotential_height",
        "calculated_geopotential_height",
        "temperature",
        "temperature_gradient",
        "potential_temperature",
        "potential_temperature_gradient",
        "virtual_temperature",
        "virtual_potential_temperature",
        "vapor_pressure",
        "saturation_vapor_pressure",
        "reported_relative_humidity",
        "calculated_relative_humidity",
        "relative_humidity_gradient",
        "u_wind",
        "u_wind_gradient",
        "v_wind",
        "v_wind_gradient",
        "refractivity",
    )
    records: list[NativeIgraDerivedSounding] = []
    scanned = 0
    minimum_nominal: str | None = None
    maximum_nominal: str | None = None
    lines = iter(_ascii_lines(content, "derived"))

    while True:
        try:
            body, original, line_number = next(lines)
        except StopIteration:
            break
        if not body:
            continue
        if not body.startswith("#"):
            raise IgraParseError(f"Derived IGRA line {line_number} is not a header.")
        _width(body, 157, "derived header", line_number)
        level_count = _integer(body[31:36], "NUMLEV", line_number)
        if level_count < 0:
            raise IgraParseError("Derived NUMLEV cannot be negative.")

        scanned += 1
        record_station_id = body[1:12]
        nominal_date = _date(body[13:17], body[18:20], body[21:23], line_number)
        hour = _integer(body[24:26], "HOUR", line_number)
        nominal_hour = None if hour == 99 else _hour(hour, line_number)
        minimum_nominal, maximum_nominal = _include_nominal(
            minimum_nominal,
            maximum_nominal,
            nominal_date,
            nominal_hour,
        )
        selected = _selected_values(
            record_station_id,
            nominal_date,
            nominal_hour,
            station_id,
            dates_utc,
            nominal_hours,
        )
        digest = sha256(original)
        selected_level_values: list[tuple[dict[str, int], int]] = []
        parameters = {
            name: _integer(body[offset : offset + 6], name, line_number)
            for name, offset in zip(parameter_names, range(37, 157, 6), strict=True)
        }

        for _level_ordinal in range(1, level_count + 1):
            level_body, level_original, level_line = _next_level(lines, "Derived")
            if level_body.startswith("#"):
                raise IgraParseError("Derived IGRA record has fewer level rows than its NUMLEV.")
            _width(level_body, 151, "derived level", level_line)
            values = {
                name: _integer(level_body[offset : offset + 7], name, level_line)
                for name, offset in zip(level_names, range(0, 151, 8), strict=True)
            }
            digest.update(level_original)
            if selected:
                selected_level_values.append((values, level_line))

        if selected:
            record_sha256 = digest.hexdigest()
            levels = tuple(
                NativeIgraDerivedLevel(
                    derived_record_sha256=record_sha256,
                    ordinal=level_ordinal,
                    values=values,
                    raw_artifact_key=artifact_key,
                    line_number=level_line,
                )
                for level_ordinal, (values, level_line) in enumerate(selected_level_values, start=1)
            )
            records.append(
                NativeIgraDerivedSounding(
                    station_id=record_station_id,
                    nominal_date_utc=nominal_date,
                    nominal_hour_utc=nominal_hour,
                    release_time_hhmm=body[27:31],
                    level_count=level_count,
                    parameters=parameters,
                    record_ordinal=scanned,
                    record_sha256=record_sha256,
                    raw_artifact_key=artifact_key,
                    header_line_number=line_number,
                    levels=levels,
                )
            )

    return _DerivedMemberResult(tuple(records), scanned, minimum_nominal, maximum_nominal)


def _raw_level_values(body: str, line_number: int) -> dict[str, int | str]:
    return {
        "level_type_major": body[0:1],
        "level_type_minor": body[1:2],
        "elapsed_time": _integer(body[3:8], "ETIME", line_number),
        "pressure": _integer(body[9:15], "PRESS", line_number),
        "pressure_flag": body[15:16],
        "geopotential_height": _integer(body[16:21], "GPH", line_number),
        "geopotential_height_flag": body[21:22],
        "temperature": _integer(body[22:27], "TEMP", line_number),
        "temperature_flag": body[27:28],
        "relative_humidity": _integer(body[28:33], "RH", line_number),
        "dew_point_depression": _integer(body[34:39], "DPDP", line_number),
        "wind_direction": _integer(body[40:45], "WDIR", line_number),
        "wind_speed": _integer(body[46:51], "WSPD", line_number),
    }


def _ascii_lines(content: _MEMBER_CONTENT, label: str) -> Iterator[tuple[str, bytes, int]]:
    lines = content.splitlines(keepends=True) if isinstance(content, bytes) else content
    for line_number, line in enumerate(lines, start=1):
        try:
            yield _strip_newline(line).decode("ascii"), line, line_number
        except UnicodeDecodeError as error:
            raise IgraParseError(f"IGRA {label} member must be strict ASCII.") from error


def _next_level(lines: Iterator[tuple[str, bytes, int]], label: str) -> tuple[str, bytes, int]:
    try:
        return next(lines)
    except StopIteration as error:
        raise IgraParseError(
            f"{label} IGRA record is truncated before NUMLEV level rows."
        ) from error


def _include_nominal(
    minimum: str | None,
    maximum: str | None,
    nominal_date: str,
    nominal_hour: int | None,
) -> tuple[str | None, str | None]:
    if nominal_hour is None:
        return minimum, maximum
    nominal = f"{nominal_date}T{nominal_hour:02d}:00:00Z"
    return (
        nominal if minimum is None or nominal < minimum else minimum,
        nominal if maximum is None or nominal > maximum else maximum,
    )


def _selected_values(
    record_station_id: str,
    nominal_date: str,
    nominal_hour: int | None,
    station_id: str,
    dates_utc: tuple[str, ...],
    nominal_hours: tuple[int, ...],
) -> bool:
    return (
        record_station_id == station_id
        and nominal_date in dates_utc
        and (not nominal_hours or nominal_hour in nominal_hours)
    )


def _strip_newline(line: bytes) -> bytes:
    if line.endswith(b"\r\n"):
        return line[:-2]
    if line.endswith((b"\n", b"\r")):
        return line[:-1]
    return line


def _width(value: str, expected: int, label: str, line_number: int) -> None:
    if len(value) != expected:
        raise IgraParseError(
            f"IGRA {label} at line {line_number} has width {len(value)}, expected {expected}."
        )


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
