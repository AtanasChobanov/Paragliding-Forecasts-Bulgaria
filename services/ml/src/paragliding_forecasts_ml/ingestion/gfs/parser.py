"""Offline parsing of hash-verified NOAA GFS GRIB artifacts."""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import eccodes
import numpy as np
from pydantic import Field, ValidationError, field_validator, model_validator

from ..atmosphere.contracts import (
    ArtifactReference,
    AtmosphericContract,
    RawManifest,
    StageManifest,
    validate_component_version,
    validate_utc_timestamp,
)
from ..weather.artifacts import WeatherArtifactStore, stage_input_fingerprint
from ..weather.grid import site_config_fingerprint, snapshot_site_configs
from ..weather.sampling_policy import SamplingPolicy, load_sampling_policy
from ..weather.sites import SiteSamplingConfig, load_site_sampling_configs
from .compact import (
    COMPACT_SELECTION_VERSION,
    CompactGridDescriptor,
    MatrixSliceReference,
    PackedMaskReference,
    plan_compact_grid,
    regular_latlon_geometry,
    write_float64_matrix,
    write_packed_missing_mask,
)
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

GFS_PARSER_VERSION = "gfs-parser/6"


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
    """Legacy v5 full-grid parser output retained for historical verification."""

    gfs_native_grid_batch_schema_version: Literal[2] = 2
    run_key: str
    source_id: Literal["noaa_gfs_0p25_aws_grib2"] = GFS_SOURCE_ID
    parser_version: str = "gfs-parser/5"
    raw_manifest: ArtifactReference
    eccodes_version: str
    grib_profile_version: str = GFS_GRIB_PROFILE_VERSION
    messages: tuple[GfsNativeGridMessage, ...] = Field(min_length=1)

    @field_validator("parser_version")
    @classmethod
    def parser_version_must_be_valid(cls, value: str) -> str:
        return validate_component_version(value)


class GfsCompactNativeGridMessage(AtmosphericContract):
    """One native message mapped to a row in the consolidated compact matrix."""

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
    native_missing_count: int = Field(ge=0)
    compact_missing_count: int = Field(ge=0)
    values: MatrixSliceReference
    quality_state: Literal["real", "sentinel_missing"]

    @field_validator("reference_at_utc", "valid_at_utc")
    @classmethod
    def timestamps_must_be_utc(cls, value: str) -> str:
        return validate_utc_timestamp(value)

    @model_validator(mode="after")
    def missing_counts_and_quality_must_agree(self) -> GfsCompactNativeGridMessage:
        if self.compact_missing_count > self.native_missing_count:
            raise ValueError("Compact missing count cannot exceed the native message count.")
        expected_quality = "sentinel_missing" if self.native_missing_count else "real"
        if self.quality_state != expected_quality:
            raise ValueError("Native message quality does not match its full-grid missing count.")
        return self


class GfsCompactNativeGridBatch(AtmosphericContract):
    """Lossless native values cropped to the complete reviewed sampling footprint."""

    gfs_native_grid_batch_schema_version: Literal[3] = 3
    run_key: str
    source_id: Literal["noaa_gfs_0p25_aws_grib2"] = GFS_SOURCE_ID
    parser_version: Literal["gfs-parser/6"] = GFS_PARSER_VERSION
    raw_manifest: ArtifactReference
    eccodes_version: str
    grib_profile_version: str = GFS_GRIB_PROFILE_VERSION
    descriptor: CompactGridDescriptor
    values_matrix: ArtifactReference
    missing_mask: PackedMaskReference
    messages: tuple[GfsCompactNativeGridMessage, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def consolidated_storage_must_be_consistent(self) -> GfsCompactNativeGridBatch:
        shape = (self.descriptor.compact_row_count, self.descriptor.compact_column_count)
        if any(
            item.values.artifact != self.values_matrix
            or item.values.matrix_row != matrix_row
            or item.values.expected_shape != shape
            or item.values.selection_sha256 != self.descriptor.selection_sha256
            for matrix_row, item in enumerate(self.messages)
        ):
            raise ValueError("Compact parser matrix-row mapping is inconsistent.")
        if self.missing_mask.matrix_shape != (len(self.messages), *shape) or (
            self.missing_mask.selection_sha256 != self.descriptor.selection_sha256
        ):
            raise ValueError("Compact parser missing-mask mapping is inconsistent.")
        return self


@dataclass(frozen=True, slots=True)
class _ParsedCompactMessage:
    metadata: dict[str, object]
    selector_key: str
    message_number: int
    artifact_key: str
    reference_at_utc: str
    valid_at_utc: str
    lead_hours: int
    native_unit: str
    native_missing_count: int
    values: np.ndarray
    missing_mask: np.ndarray


def raw_manifest_reference(store: WeatherArtifactStore) -> ArtifactReference:
    """Reference the immutable raw boundary after deriving its current hash evidence."""

    path = store.raw_dir / "manifest.json"
    if not path.is_file():
        raise GfsParserError("GFS raw manifest does not exist.")
    return store.verification.reference_for_existing(
        path,
        artifact_key="raw_manifest",
        relative_path=path.relative_to(store.project_root).as_posix(),
        media_type="application/json",
    )


def parse(
    store: WeatherArtifactStore,
    *,
    database_url: str,
    occurred_at_utc: str,
    project_root: Path | None = None,
) -> ArtifactReference:
    """Parse one complete S03 GFS boundary into compact native grid artifacts."""

    raw_reference = raw_manifest_reference(store)
    manifest = store.verify_raw_manifest(raw_reference)
    _require_gfs_manifest(manifest)
    collection = _load_collection_record(store, manifest)
    expected = _expected_messages(collection)
    sites = load_site_sampling_configs(
        database_url,
        project_root or store.project_root,
        require_elevation=True,
    )
    policy, policy_sha256 = load_sampling_policy()
    site_config_sha256 = site_config_fingerprint(snapshot_site_configs(sites))
    configuration = {
        "eccodes_version": eccodes.codes_get_api_version(),
        "grib_profile_version": GFS_GRIB_PROFILE_VERSION,
        "compact_selection_version": COMPACT_SELECTION_VERSION,
        "site_config_sha256": site_config_sha256,
        "sampling_policy_sha256": policy_sha256,
    }
    fingerprint = stage_input_fingerprint(
        stage="parser",
        producer_version=GFS_PARSER_VERSION,
        inputs=(raw_reference,),
        configuration=configuration,
    )
    existing = store.existing_stage_manifest("parser", GFS_PARSER_VERSION, fingerprint)
    if existing is not None:
        return existing
    directory = store.begin_stage("parser", GFS_PARSER_VERSION, fingerprint)
    parsed_messages: list[_ParsedCompactMessage] = []
    descriptor: CompactGridDescriptor | None = None
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
        artifact_messages, descriptor = _parse_artifact_compact(
            path,
            artifact_key=artifact_key,
            expected=tuple((item[0], item[1]) for item in artifact_expected),
            reference_at_utc=collection.run_at_utc,
            valid_at_utc=valid_at_utc,
            lead_hours=lead_hours,
            descriptor=descriptor,
            sites=sites,
            policy=policy,
            policy_sha256=policy_sha256,
        )
        parsed_messages.extend(artifact_messages)
    active_expected = tuple(
        item for item in expected if item[1] not in LEGACY_IGNORED_PROFILE_BY_SELECTOR
    )
    if len(parsed_messages) != len(active_expected):
        raise GfsParserError("GFS parser message count differs from active collection evidence.")
    if descriptor is None:
        raise GfsParserError("GFS parser found no active native grid geometry.")
    values = np.stack([item.values for item in parsed_messages]).astype("<f8", copy=False)
    missing_mask = np.stack([item.missing_mask for item in parsed_messages]).astype(
        bool, copy=False
    )
    values_reference = write_float64_matrix(
        store,
        directory,
        "compact-native-values.npy",
        "gfs_compact_native_values",
        values,
    )
    mask_reference = write_packed_missing_mask(
        store,
        directory,
        "compact-native-missing-mask.npy",
        "gfs_compact_native_missing_mask",
        missing_mask,
        selection_sha256=descriptor.selection_sha256,
    )
    matrix_shape = (descriptor.compact_row_count, descriptor.compact_column_count)
    messages = tuple(
        _compact_message_contract(
            item,
            matrix_row=matrix_row,
            matrix_artifact=values_reference,
            matrix_shape=matrix_shape,
            selection_sha256=descriptor.selection_sha256,
        )
        for matrix_row, item in enumerate(parsed_messages)
    )
    batch = GfsCompactNativeGridBatch(
        run_key=manifest.run_key,
        raw_manifest=raw_reference,
        eccodes_version=eccodes.codes_get_api_version(),
        descriptor=descriptor,
        values_matrix=values_reference,
        missing_mask=mask_reference,
        messages=messages,
    )
    batch_reference = store.write_stage_model(
        directory,
        "compact-native-grid-batch.json",
        "gfs_compact_native_grid_batch",
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
            outputs=(values_reference, mask_reference.artifact, batch_reference),
            configuration=configuration,
            disposition="complete",
            started_at_utc=occurred_at_utc,
            completed_at_utc=occurred_at_utc,
        ),
    )
    return stage_reference


def load_batch(
    store: WeatherArtifactStore, stage_reference: ArtifactReference
) -> GfsNativeGridBatch | GfsCompactNativeGridBatch:
    """Verify and load either a legacy full-grid or current compact native batch."""

    store.verify_boundary(stage_reference)
    stage_path = store.verify_reference(stage_reference, expected_root=store.interim_dir)
    stage = StageManifest.model_validate_json(stage_path.read_bytes(), strict=True)
    if stage.stage != "parser" or stage.disposition != "complete":
        raise GfsParserError("Expected a complete parser stage manifest.")
    batch_reference = next(
        (
            item
            for item in stage.outputs
            if item.artifact_key in {"gfs_native_grid_batch", "gfs_compact_native_grid_batch"}
        ),
        None,
    )
    if batch_reference is None:
        raise GfsParserError("Parser stage does not contain native grid output.")
    batch_path = store.verify_reference(batch_reference, expected_root=store.interim_dir)
    payload = batch_path.read_bytes()
    try:
        decoded = GfsCompactNativeGridBatch.model_validate_json(payload, strict=True)
    except ValidationError:
        try:
            return GfsNativeGridBatch.model_validate_json(payload, strict=True)
        except ValidationError as error:
            raise GfsParserError("Parser batch does not satisfy a supported schema.") from error
    if decoded.values_matrix != decoded.messages[0].values.artifact or any(
        item.values.artifact != decoded.values_matrix for item in decoded.messages
    ):
        raise GfsParserError("Compact parser message slices do not share the owning matrix.")
    if any(
        item.values.matrix_row != matrix_row
        or item.values.expected_shape
        != (decoded.descriptor.compact_row_count, decoded.descriptor.compact_column_count)
        or item.values.selection_sha256 != decoded.descriptor.selection_sha256
        for matrix_row, item in enumerate(decoded.messages)
    ):
        raise GfsParserError("Compact parser matrix-row mapping is not deterministic.")
    if (
        decoded.missing_mask.matrix_shape
        != (
            len(decoded.messages),
            decoded.descriptor.compact_row_count,
            decoded.descriptor.compact_column_count,
        )
        or decoded.missing_mask.selection_sha256 != decoded.descriptor.selection_sha256
    ):
        raise GfsParserError("Compact parser missing-mask mapping is inconsistent.")
    return decoded


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


def _parse_artifact_compact(
    path: Path,
    *,
    artifact_key: str,
    expected: tuple[tuple[str, int], ...],
    reference_at_utc: str,
    valid_at_utc: str,
    lead_hours: int,
    descriptor: CompactGridDescriptor | None,
    sites: tuple[SiteSamplingConfig, ...],
    policy: SamplingPolicy,
    policy_sha256: str,
) -> tuple[tuple[_ParsedCompactMessage, ...], CompactGridDescriptor | None]:
    messages: list[_ParsedCompactMessage] = []
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
                    message, descriptor = _parse_compact_message(
                        handle_id,
                        selector_key=selector_key,
                        message_number=message_number,
                        artifact_key=artifact_key,
                        reference_at_utc=reference_at_utc,
                        valid_at_utc=valid_at_utc,
                        lead_hours=lead_hours,
                        descriptor=descriptor,
                        sites=sites,
                        policy=policy,
                        policy_sha256=policy_sha256,
                    )
                    messages.append(message)
            finally:
                eccodes.codes_release(handle_id)
        extra_handle = eccodes.codes_grib_new_from_file(handle)
        if extra_handle is not None:
            eccodes.codes_release(extra_handle)
            raise GfsParserError(f"{artifact_key} contains an unexpected extra GRIB message.")
    return tuple(messages), descriptor


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


def _parse_compact_message(
    handle_id: int,
    *,
    selector_key: str,
    message_number: int,
    artifact_key: str,
    reference_at_utc: str,
    valid_at_utc: str,
    lead_hours: int,
    descriptor: CompactGridDescriptor | None,
    sites: tuple[SiteSamplingConfig, ...],
    policy: SamplingPolicy,
    policy_sha256: str,
) -> tuple[_ParsedCompactMessage, CompactGridDescriptor]:
    profile = PROFILE_BY_SELECTOR.get(selector_key)
    if profile is None:
        raise GfsParserError(f"No pinned GFS profile exists for selector {selector_key}.")
    metadata = _metadata(handle_id)
    _validate_identity(metadata, profile, selector_key, reference_at_utc, valid_at_utc, lead_hours)
    _validate_regular_latlon(metadata, selector_key)
    native_geometry = regular_latlon_geometry(
        row_count=int(metadata["Nj"]),
        column_count=int(metadata["Ni"]),
        first_latitude_deg=float(metadata["latitudeOfFirstGridPointInDegrees"]),
        first_longitude_deg=float(metadata["longitudeOfFirstGridPointInDegrees"]) % 360.0,
        last_latitude_deg=float(metadata["latitudeOfLastGridPointInDegrees"]),
        last_longitude_deg=float(metadata["longitudeOfLastGridPointInDegrees"]) % 360.0,
        latitude_step_deg=-float(metadata["jDirectionIncrementInDegrees"]),
        longitude_step_deg=float(metadata["iDirectionIncrementInDegrees"]),
        i_scans_negatively=bool(metadata["iScansNegatively"]),
        j_scans_positively=bool(metadata["jScansPositively"]),
        j_points_are_consecutive=bool(metadata["jPointsAreConsecutive"]),
        alternative_row_scanning=bool(metadata["alternativeRowScanning"]),
    )
    if descriptor is None:
        descriptor = plan_compact_grid(native_geometry, sites, policy, policy_sha256)
    elif descriptor.native_geometry != native_geometry:
        raise GfsParserError("GFS native messages do not share one exact grid geometry.")
    values = np.asarray(eccodes.codes_get_array(handle_id, "values"), dtype="<f8")
    compact_values, compact_mask, native_missing_count = _crop_validated_values(
        values,
        metadata,
        descriptor,
        selector_key=selector_key,
    )
    return (
        _ParsedCompactMessage(
            metadata=metadata,
            selector_key=selector_key,
            message_number=message_number,
            artifact_key=artifact_key,
            reference_at_utc=reference_at_utc,
            valid_at_utc=valid_at_utc,
            lead_hours=lead_hours,
            native_unit=profile.native_unit_override or str(metadata["units"]),
            native_missing_count=native_missing_count,
            values=compact_values,
            missing_mask=compact_mask,
        ),
        descriptor,
    )


def _crop_validated_values(
    values: np.ndarray,
    metadata: dict[str, object],
    descriptor: CompactGridDescriptor,
    *,
    selector_key: str,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Validate the complete decoded message, then retain only the lossless crop."""

    ni, nj = int(metadata["Ni"]), int(metadata["Nj"])
    if values.size != ni * nj:
        raise GfsParserError(f"{selector_key} value count does not match Ni*Nj.")
    missing_value = float(metadata["missingValue"])
    missing_mask = np.isclose(values, missing_value, rtol=0.0, atol=0.0)
    native_missing_count = int(metadata["numberOfMissing"])
    if native_missing_count != int(missing_mask.sum()):
        raise GfsParserError(
            f"{selector_key} bitmap/sentinel metadata does not match parsed values."
        )
    native_values = values.reshape(nj, ni)
    native_mask = missing_mask.reshape(nj, ni)
    rows = slice(descriptor.crop_min_row, descriptor.crop_max_row + 1)
    columns = slice(descriptor.crop_min_column, descriptor.crop_max_column + 1)
    compact_values = np.array(native_values[rows, columns], dtype="<f8", order="C", copy=True)
    compact_mask = np.array(native_mask[rows, columns], dtype=bool, order="C", copy=True)
    compact_values[compact_mask] = np.nan
    return compact_values, compact_mask, native_missing_count


def _compact_message_contract(
    message: _ParsedCompactMessage,
    *,
    matrix_row: int,
    matrix_artifact: ArtifactReference,
    matrix_shape: tuple[int, int],
    selection_sha256: str,
) -> GfsCompactNativeGridMessage:
    metadata = message.metadata
    return GfsCompactNativeGridMessage(
        values=MatrixSliceReference(
            artifact=matrix_artifact,
            matrix_row=matrix_row,
            expected_shape=matrix_shape,
            selection_sha256=selection_sha256,
        ),
        native_missing_count=message.native_missing_count,
        compact_missing_count=int(message.missing_mask.sum()),
        quality_state="sentinel_missing" if message.native_missing_count else "real",
        selector_key=message.selector_key,
        message_number=message.message_number,
        raw_artifact_key=message.artifact_key,
        native_message_reference=(f"{message.artifact_key}:message-{message.message_number}"),
        reference_at_utc=message.reference_at_utc,
        valid_at_utc=message.valid_at_utc,
        lead_hours=message.lead_hours,
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
        native_unit=message.native_unit,
        step_type=str(metadata["stepType"]),
        step_start_hours=float(metadata["startStep"]),
        step_end_hours=float(metadata["endStep"]),
        statistic_type=_statistic_type(metadata),
        quantization_step=_quantization_step(metadata),
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
