"""Offline parsing of hash-verified NOAA GFS GRIB artifacts."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import eccodes
import numpy as np
from pydantic import Field, field_validator

from ..atmosphere.contracts import (
    ArtifactReference,
    AtmosphericContract,
    RawManifest,
    StageManifest,
    validate_component_version,
    validate_utc_timestamp,
)
from ..weather.artifacts import WeatherArtifactStore, stage_input_fingerprint
from ..weather.serialization import sha256_file
from .models import GFS_SOURCE_ID, GfsCollectionRecord
from .profile import (
    GFS_CENTRE,
    GFS_GRIB_PROFILE_VERSION,
    GFS_LOCAL_TABLES_VERSION,
    GFS_TABLES_VERSION,
    LEGACY_IGNORED_PROFILE_BY_SELECTOR,
    PROFILE_BY_SELECTOR,
    GfsMessageProfile,
)

GFS_PARSER_VERSION = "gfs-parser/5"


class GfsParserError(RuntimeError):
    """An invalid_payload cannot satisfy the pinned GFS parser contract."""

    quality_state = "invalid_payload"


class GfsNativeGridMessage(AtmosphericContract):
    """One globally gridded native message, with values retained as an immutable array."""

    selector_key: str
    message_number: int = Field(ge=1)
    raw_artifact_key: str
    native_message_reference: str
    reference_at_utc: str
    valid_at_utc: str
    lead_hours: int = Field(ge=0, le=384)
    discipline: int = Field(ge=0)
    parameter_category: int = Field(ge=0)
    parameter_number: int = Field(ge=0)
    centre: str
    sub_centre: int = Field(ge=0)
    tables_version: int = Field(ge=0)
    local_tables_version: int = Field(ge=0)
    type_of_level: str
    level: float
    native_field_name: str
    native_unit: str
    step_type: str
    step_start_hours: float = Field(ge=0)
    step_end_hours: float = Field(ge=0)
    statistic_type: str | None = None
    quantization_step: float | None = Field(default=None, ge=0)
    grid_type: str
    ni: int = Field(gt=0)
    nj: int = Field(gt=0)
    latitude_of_first_grid_point_deg: float
    longitude_of_first_grid_point_deg: float
    latitude_of_last_grid_point_deg: float
    longitude_of_last_grid_point_deg: float
    i_direction_increment_deg: float
    j_direction_increment_deg: float
    i_scans_negatively: bool
    j_scans_positively: bool
    j_points_are_consecutive: bool
    alternative_row_scanning: bool
    values: ArtifactReference
    missing_mask: ArtifactReference
    quality_state: Literal["real", "sentinel_missing"]

    @field_validator("reference_at_utc", "valid_at_utc")
    @classmethod
    def timestamps_must_be_utc(cls, value: str) -> str:
        return validate_utc_timestamp(value)


class GfsNativeGridBatch(AtmosphericContract):
    """Immutable parser output before canonical normalization or spatial sampling."""

    gfs_native_grid_batch_schema_version: Literal[2] = 2
    run_key: str
    source_id: Literal["noaa_gfs_0p25_aws_grib2"] = GFS_SOURCE_ID
    parser_version: str = GFS_PARSER_VERSION
    raw_manifest: ArtifactReference
    eccodes_version: str
    grib_profile_version: str = GFS_GRIB_PROFILE_VERSION
    messages: tuple[GfsNativeGridMessage, ...] = Field(min_length=1)

    @field_validator("parser_version")
    @classmethod
    def parser_version_must_be_valid(cls, value: str) -> str:
        return validate_component_version(value)


def raw_manifest_reference(store: WeatherArtifactStore) -> ArtifactReference:
    """Reference the immutable raw boundary after deriving its current hash evidence."""

    path = store.raw_dir / "manifest.json"
    if not path.is_file():
        raise GfsParserError("GFS raw manifest does not exist.")
    return ArtifactReference(
        artifact_key="raw_manifest",
        relative_path=path.relative_to(store.project_root).as_posix(),
        sha256=sha256_file(path),
        byte_count=path.stat().st_size,
        media_type="application/json",
    )


def parse(store: WeatherArtifactStore, *, occurred_at_utc: str) -> ArtifactReference:
    """Parse one complete S03 GFS raw boundary into immutable native grid artifacts."""

    raw_reference = raw_manifest_reference(store)
    manifest = store.verify_raw_manifest(raw_reference)
    _require_gfs_manifest(manifest)
    collection = _load_collection_record(store, manifest)
    expected = _expected_messages(collection)
    fingerprint = stage_input_fingerprint(
        stage="parser",
        producer_version=GFS_PARSER_VERSION,
        inputs=(raw_reference,),
        configuration={
            "eccodes_version": eccodes.codes_get_api_version(),
            "grib_profile_version": GFS_GRIB_PROFILE_VERSION,
        },
    )
    existing = store.existing_stage_manifest("parser", GFS_PARSER_VERSION, fingerprint)
    if existing is not None:
        return existing
    directory = store.begin_stage("parser", GFS_PARSER_VERSION, fingerprint)
    messages: list[GfsNativeGridMessage] = []
    grouped: dict[str, list[tuple[str, int, str, int]]] = {}
    for artifact_key, selector_key, message_number, valid_at_utc, lead_hours in expected:
        grouped.setdefault(artifact_key, []).append(
            (selector_key, message_number, valid_at_utc, lead_hours)
        )
    for artifact_key, artifact_expected in grouped.items():
        artifact = next(item for item in manifest.artifacts if item.artifact_key == artifact_key)
        path = store.verify_reference(artifact, expected_root=store.raw_dir)
        valid_at_utc = artifact_expected[0][2]
        lead_hours = artifact_expected[0][3]
        if any(item[2:] != (valid_at_utc, lead_hours) for item in artifact_expected):
            raise GfsParserError("One GFS range cannot mix valid times or leads.")
        messages.extend(
            _parse_artifact(
                store,
                directory,
                path,
                artifact_key=artifact_key,
                expected=tuple((item[0], item[1]) for item in artifact_expected),
                reference_at_utc=collection.run_at_utc,
                valid_at_utc=valid_at_utc,
                lead_hours=lead_hours,
            )
        )
    active_expected = tuple(
        item for item in expected if item[1] not in LEGACY_IGNORED_PROFILE_BY_SELECTOR
    )
    if len(messages) != len(active_expected):
        raise GfsParserError("GFS parser message count differs from active collection evidence.")
    batch = GfsNativeGridBatch(
        run_key=manifest.run_key,
        raw_manifest=raw_reference,
        eccodes_version=eccodes.codes_get_api_version(),
        messages=tuple(messages),
    )
    batch_reference = store.write_stage_model(
        directory,
        "native-grid-batch.json",
        "gfs_native_grid_batch",
        batch,
        record_count=len(messages),
    )
    stage_reference = store.write_stage_manifest(
        directory,
        StageManifest(
            run_key=manifest.run_key,
            stage="parser",
            producer_version=GFS_PARSER_VERSION,
            input_fingerprint_sha256=fingerprint,
            inputs=(raw_reference,),
            outputs=tuple(
                [item.values for item in messages]
                + [item.missing_mask for item in messages]
                + [batch_reference]
            ),
            configuration={
                "eccodes_version": eccodes.codes_get_api_version(),
                "grib_profile_version": GFS_GRIB_PROFILE_VERSION,
            },
            disposition="complete",
            started_at_utc=occurred_at_utc,
            completed_at_utc=occurred_at_utc,
        ),
    )
    return stage_reference


def load_batch(
    store: WeatherArtifactStore, stage_reference: ArtifactReference
) -> GfsNativeGridBatch:
    """Verify and load a native batch from a completed parser stage."""

    store.verify_boundary(stage_reference)
    stage_path = store.verify_reference(stage_reference, expected_root=store.interim_dir)
    stage = StageManifest.model_validate_json(stage_path.read_bytes(), strict=True)
    if stage.stage != "parser" or stage.disposition != "complete":
        raise GfsParserError("Expected a complete parser stage manifest.")
    batch_reference = next(
        (item for item in stage.outputs if item.artifact_key == "gfs_native_grid_batch"), None
    )
    if batch_reference is None:
        raise GfsParserError("Parser stage does not contain native grid output.")
    batch_path = store.verify_reference(batch_reference, expected_root=store.interim_dir)
    return GfsNativeGridBatch.model_validate_json(batch_path.read_bytes(), strict=True)


def _require_gfs_manifest(manifest: RawManifest) -> None:
    if manifest.source_id != GFS_SOURCE_ID or manifest.status != "complete":
        raise GfsParserError("GFS parser accepts only a complete NOAA GFS raw manifest.")


def _load_collection_record(
    store: WeatherArtifactStore, manifest: RawManifest
) -> GfsCollectionRecord:
    reference = next(
        (item for item in manifest.artifacts if item.artifact_key == "gfs_collection_record"), None
    )
    if reference is None:
        raise GfsParserError("GFS raw manifest is missing gfs_collection_record evidence.")
    path = store.verify_reference(reference, expected_root=store.raw_dir)
    record = GfsCollectionRecord.model_validate_json(path.read_bytes(), strict=True)
    if record.run_key != manifest.run_key or record.outcome != "complete":
        raise GfsParserError("GFS collection record does not describe a complete matching run.")
    return record


def _expected_messages(
    collection: GfsCollectionRecord,
) -> tuple[tuple[str, str, int, str, int], ...]:
    expected: list[tuple[str, str, int, str, int]] = []
    for evidence in collection.artifacts:
        if not evidence.artifact.artifact_key.startswith("gfs_grib_"):
            continue
        if evidence.valid_at_utc is None or evidence.lead_hours is None:
            raise GfsParserError("GFS GRIB evidence is missing valid time or lead.")
        if not (
            len(evidence.selector_keys)
            == len(evidence.message_numbers)
            == len(evidence.forecast_descriptors)
        ):
            raise GfsParserError(
                "GFS collection evidence has inconsistent message identity arrays."
            )
        expected.extend(
            (
                evidence.artifact.artifact_key,
                selector,
                number,
                evidence.valid_at_utc,
                evidence.lead_hours,
            )
            for selector, number in zip(
                evidence.selector_keys, evidence.message_numbers, strict=True
            )
        )
    if not expected:
        raise GfsParserError("GFS collection record contains no GRIB message evidence.")
    return tuple(expected)


def _parse_artifact(
    store: WeatherArtifactStore,
    directory: Path,
    path: Path,
    *,
    artifact_key: str,
    expected: tuple[tuple[str, int], ...],
    reference_at_utc: str,
    valid_at_utc: str,
    lead_hours: int,
) -> tuple[GfsNativeGridMessage, ...]:
    messages: list[GfsNativeGridMessage] = []
    with path.open("rb") as handle:
        for ordinal, (selector_key, message_number) in enumerate(expected, start=1):
            handle_id = eccodes.codes_grib_new_from_file(handle)
            if handle_id is None:
                raise GfsParserError(f"{artifact_key} is truncated before message {ordinal}.")
            try:
                if selector_key in LEGACY_IGNORED_PROFILE_BY_SELECTOR:
                    _validate_legacy_ignored_message(
                        handle_id,
                        selector_key=selector_key,
                        reference_at_utc=reference_at_utc,
                        valid_at_utc=valid_at_utc,
                        lead_hours=lead_hours,
                    )
                else:
                    messages.append(
                        _parse_message(
                            store,
                            directory,
                            handle_id,
                            selector_key=selector_key,
                            message_number=message_number,
                            artifact_key=artifact_key,
                            reference_at_utc=reference_at_utc,
                            valid_at_utc=valid_at_utc,
                            lead_hours=lead_hours,
                        )
                    )
            finally:
                eccodes.codes_release(handle_id)
        extra_handle = eccodes.codes_grib_new_from_file(handle)
        if extra_handle is not None:
            eccodes.codes_release(extra_handle)
            raise GfsParserError(f"{artifact_key} contains an unexpected extra GRIB message.")
    return tuple(messages)


def _validate_legacy_ignored_message(
    handle_id: int,
    *,
    selector_key: str,
    reference_at_utc: str,
    valid_at_utc: str,
    lead_hours: int,
) -> None:
    """Verify a removed selector while intentionally emitting no new parser fact."""

    profile = LEGACY_IGNORED_PROFILE_BY_SELECTOR[selector_key]
    metadata = _metadata(handle_id)
    _validate_identity(metadata, profile, selector_key, reference_at_utc, valid_at_utc, lead_hours)
    _validate_regular_latlon(metadata, selector_key)


def _parse_message(
    store: WeatherArtifactStore,
    directory: Path,
    handle_id: int,
    *,
    selector_key: str,
    message_number: int,
    artifact_key: str,
    reference_at_utc: str,
    valid_at_utc: str,
    lead_hours: int,
) -> GfsNativeGridMessage:
    profile = PROFILE_BY_SELECTOR.get(selector_key)
    if profile is None:
        raise GfsParserError(f"No pinned GFS profile exists for selector {selector_key}.")
    metadata = _metadata(handle_id)
    _validate_identity(metadata, profile, selector_key, reference_at_utc, valid_at_utc, lead_hours)
    _validate_regular_latlon(metadata, selector_key)
    values = np.asarray(eccodes.codes_get_array(handle_id, "values"), dtype="<f8")
    if values.size != int(metadata["Ni"]) * int(metadata["Nj"]):
        raise GfsParserError(f"{selector_key} value count does not match Ni*Nj.")
    missing_value = float(metadata["missingValue"])
    missing_mask = np.isclose(values, missing_value, rtol=0.0, atol=0.0)
    missing_count = int(metadata["numberOfMissing"])
    if missing_count != int(missing_mask.sum()):
        raise GfsParserError(
            f"{selector_key} bitmap/sentinel metadata does not match parsed values."
        )
    values[missing_mask] = np.nan
    value_reference = _write_array(
        store, directory, f"{artifact_key}-{message_number}-values", values
    )
    mask_reference = _write_array(
        store, directory, f"{artifact_key}-{message_number}-missing-mask", missing_mask
    )
    return GfsNativeGridMessage(
        selector_key=selector_key,
        message_number=message_number,
        raw_artifact_key=artifact_key,
        native_message_reference=f"{artifact_key}:message-{message_number}",
        reference_at_utc=reference_at_utc,
        valid_at_utc=valid_at_utc,
        lead_hours=lead_hours,
        discipline=int(metadata["discipline"]),
        parameter_category=int(metadata["parameterCategory"]),
        parameter_number=int(metadata["parameterNumber"]),
        centre=str(metadata["centre"]),
        sub_centre=int(metadata["subCentre"]),
        tables_version=int(metadata["tablesVersion"]),
        local_tables_version=int(metadata["localTablesVersion"]),
        type_of_level=str(metadata["typeOfLevel"]),
        level=float(metadata["level"]),
        native_field_name=str(metadata["shortName"]),
        native_unit=profile.native_unit_override or str(metadata["units"]),
        step_type=str(metadata["stepType"]),
        step_start_hours=float(metadata["startStep"]),
        step_end_hours=float(metadata["endStep"]),
        statistic_type=_statistic_type(metadata),
        quantization_step=_quantization_step(metadata),
        grid_type=str(metadata["gridType"]),
        ni=int(metadata["Ni"]),
        nj=int(metadata["Nj"]),
        latitude_of_first_grid_point_deg=float(metadata["latitudeOfFirstGridPointInDegrees"]),
        longitude_of_first_grid_point_deg=float(metadata["longitudeOfFirstGridPointInDegrees"]),
        latitude_of_last_grid_point_deg=float(metadata["latitudeOfLastGridPointInDegrees"]),
        longitude_of_last_grid_point_deg=float(metadata["longitudeOfLastGridPointInDegrees"]),
        i_direction_increment_deg=float(metadata["iDirectionIncrementInDegrees"]),
        j_direction_increment_deg=float(metadata["jDirectionIncrementInDegrees"]),
        i_scans_negatively=bool(metadata["iScansNegatively"]),
        j_scans_positively=bool(metadata["jScansPositively"]),
        j_points_are_consecutive=bool(metadata["jPointsAreConsecutive"]),
        alternative_row_scanning=bool(metadata["alternativeRowScanning"]),
        values=value_reference,
        missing_mask=mask_reference,
        quality_state="sentinel_missing" if missing_count else "real",
    )


def _write_array(
    store: WeatherArtifactStore, directory: Path, artifact_key: str, array: np.ndarray
) -> ArtifactReference:
    buffer = io.BytesIO()
    np.save(buffer, array, allow_pickle=False)
    return store.write_stage_bytes(
        directory,
        f"{artifact_key}.npy",
        artifact_key,
        buffer.getvalue(),
        media_type="application/x-npy",
        record_count=int(array.size),
    )


def load_array(store: WeatherArtifactStore, reference: ArtifactReference) -> np.ndarray:
    """Load an immutable parser or normalizer array after hash verification."""

    path = store.verify_reference(reference, expected_root=store.interim_dir)
    return np.load(path, allow_pickle=False)


def _metadata(handle_id: int) -> dict[str, object]:
    keys = (
        "shortName",
        "units",
        "discipline",
        "parameterCategory",
        "parameterNumber",
        "centre",
        "subCentre",
        "tablesVersion",
        "localTablesVersion",
        "typeOfLevel",
        "level",
        "stepType",
        "startStep",
        "endStep",
        "missingValue",
        "numberOfMissing",
        "gridType",
        "Ni",
        "Nj",
        "latitudeOfFirstGridPointInDegrees",
        "longitudeOfFirstGridPointInDegrees",
        "latitudeOfLastGridPointInDegrees",
        "longitudeOfLastGridPointInDegrees",
        "iDirectionIncrementInDegrees",
        "jDirectionIncrementInDegrees",
        "iScansNegatively",
        "jScansPositively",
        "jPointsAreConsecutive",
        "alternativeRowScanning",
        "bitsPerValue",
        "binaryScaleFactor",
        "decimalScaleFactor",
        "dataDate",
        "dataTime",
        "validityDate",
        "validityTime",
    )
    result: dict[str, object] = {}
    for key in keys:
        try:
            result[key] = eccodes.codes_get(handle_id, key)
        except eccodes.KeyValueNotFoundError as error:
            raise GfsParserError(f"GRIB message omits required key {key}.") from error
    try:
        result["typeOfStatisticalProcessing"] = eccodes.codes_get(
            handle_id, "typeOfStatisticalProcessing"
        )
    except eccodes.KeyValueNotFoundError:
        result["typeOfStatisticalProcessing"] = None
    return result


def _validate_identity(
    metadata: dict[str, object],
    profile: GfsMessageProfile,
    selector_key: str,
    reference_at_utc: str,
    valid_at_utc: str,
    lead_hours: int,
) -> None:
    checks = {
        "discipline": profile.discipline,
        "parameterCategory": profile.category,
        "parameterNumber": profile.number,
        "typeOfLevel": profile.type_of_level,
        "centre": GFS_CENTRE,
        "tablesVersion": GFS_TABLES_VERSION,
        "localTablesVersion": GFS_LOCAL_TABLES_VERSION,
    }
    if profile.level is not None:
        checks["level"] = profile.level
    for key, expected in checks.items():
        if metadata[key] != expected:
            raise GfsParserError(
                f"{selector_key} GRIB identity mismatch for {key}: {metadata[key]!r} != {expected!r}."
            )
    if str(metadata["stepType"]) == "accum" and metadata["typeOfStatisticalProcessing"] != 1:
        raise GfsParserError(f"{selector_key} accumulation statistic is not accumulation.")
    if str(metadata["stepType"]) == "avg" and metadata["typeOfStatisticalProcessing"] != 0:
        raise GfsParserError(f"{selector_key} average statistic is not average.")
    start = float(metadata["startStep"])
    end = float(metadata["endStep"])
    if end != lead_hours or start > end:
        raise GfsParserError(
            f"{selector_key} has invalid step range {start}-{end} for f{lead_hours:03d}."
        )
    if _grib_utc(metadata["dataDate"], metadata["dataTime"]) != reference_at_utc:
        raise GfsParserError(f"{selector_key} reference time does not match collection evidence.")
    if _grib_utc(metadata["validityDate"], metadata["validityTime"]) != valid_at_utc:
        raise GfsParserError(f"{selector_key} valid time does not match collection evidence.")


def _validate_regular_latlon(metadata: dict[str, object], selector_key: str) -> None:
    """Pin the NOAA GFS scan order that makes flat values canonical row-major grids."""

    if metadata["gridType"] != "regular_ll":
        raise GfsParserError(f"{selector_key} must use the regular_ll grid.")
    scan_flags = (
        int(metadata["iScansNegatively"]),
        int(metadata["jScansPositively"]),
        int(metadata["jPointsAreConsecutive"]),
        int(metadata["alternativeRowScanning"]),
    )
    if scan_flags != (0, 0, 0, 0):
        raise GfsParserError(
            f"{selector_key} has unsupported GFS scan flags {scan_flags}; expected (0, 0, 0, 0)."
        )
    ni, nj = int(metadata["Ni"]), int(metadata["Nj"])
    first_lat = float(metadata["latitudeOfFirstGridPointInDegrees"])
    last_lat = float(metadata["latitudeOfLastGridPointInDegrees"])
    first_lon = float(metadata["longitudeOfFirstGridPointInDegrees"])
    last_lon = float(metadata["longitudeOfLastGridPointInDegrees"])
    i_step = float(metadata["iDirectionIncrementInDegrees"])
    j_step = float(metadata["jDirectionIncrementInDegrees"])
    if i_step <= 0 or j_step <= 0:
        raise GfsParserError(f"{selector_key} grid increments must be positive.")
    expected_last_lat = first_lat - (nj - 1) * j_step
    expected_last_lon = (first_lon + (ni - 1) * i_step) % 360.0
    if not np.isclose(last_lat, expected_last_lat, rtol=0.0, atol=1e-9):
        raise GfsParserError(f"{selector_key} latitude endpoints disagree with Nj and j step.")
    if not np.isclose(last_lon % 360.0, expected_last_lon, rtol=0.0, atol=1e-9):
        raise GfsParserError(f"{selector_key} longitude endpoints disagree with Ni and i step.")


def _statistic_type(metadata: dict[str, object]) -> str | None:
    value = metadata["typeOfStatisticalProcessing"]
    return None if value is None else str(value)


def _quantization_step(metadata: dict[str, object]) -> float:
    """Return the decoded GRIB packing increment in native canonical units."""

    bits = int(metadata["bitsPerValue"])
    if bits == 0:
        return 0.0
    return float(
        2.0 ** int(metadata["binaryScaleFactor"]) * 10.0 ** -int(metadata["decimalScaleFactor"])
    )


def _grib_utc(date_value: object, time_value: object) -> str:
    """Convert GRIB integer date/time keys to the pipeline's strict UTC timestamp."""

    return (
        datetime.strptime(f"{int(date_value):08d}{int(time_value):04d}", "%Y%m%d%H%M")
        .replace(tzinfo=UTC)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )
