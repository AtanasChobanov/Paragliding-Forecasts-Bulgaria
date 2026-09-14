from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from paragliding_forecasts_ml.ingestion.gfs.compact import (
    plan_compact_grid,
    regular_latlon_geometry,
)
from paragliding_forecasts_ml.ingestion.gfs.normalizer import _add_hours, _derived_quality, _unit
from paragliding_forecasts_ml.ingestion.gfs.parser import (
    GfsParserError,
    _crop_validated_values,
    _grib_utc,
    _validate_identity,
    _validate_regular_latlon,
)
from paragliding_forecasts_ml.ingestion.gfs.profile import PROFILE_BY_SELECTOR
from paragliding_forecasts_ml.ingestion.weather.sampling_policy import load_sampling_policy
from paragliding_forecasts_ml.ingestion.weather.sites import SiteSamplingConfig


def _metadata() -> dict[str, object]:
    return {
        "discipline": 0,
        "parameterCategory": 3,
        "parameterNumber": 196,
        "typeOfLevel": "surface",
        "centre": "kwbc",
        "tablesVersion": 2,
        "localTablesVersion": 1,
        "level": 0,
        "stepType": "instant",
        "typeOfStatisticalProcessing": None,
        "startStep": 7,
        "endStep": 7,
        "dataDate": 20260821,
        "dataTime": 0,
        "validityDate": 20260821,
        "validityTime": 700,
    }


def test_profile_pins_every_collected_selector_and_numeric_hpbl_identity() -> None:
    assert len(PROFILE_BY_SELECTOR) == 114
    assert PROFILE_BY_SELECTOR["hpbl"].number == 196
    assert PROFILE_BY_SELECTOR["hpbl"].native_unit_override == "m"


def test_parser_accepts_real_f007_hpbl_identity_without_short_name() -> None:
    _validate_identity(
        _metadata(),
        PROFILE_BY_SELECTOR["hpbl"],
        "hpbl",
        "2026-08-21T00:00:00Z",
        "2026-08-21T07:00:00Z",
        7,
    )


def test_parser_rejects_wrong_grib_table_and_valid_time() -> None:
    wrong_table = _metadata() | {"tablesVersion": 3}
    with pytest.raises(GfsParserError, match="tablesVersion"):
        _validate_identity(
            wrong_table,
            PROFILE_BY_SELECTOR["hpbl"],
            "hpbl",
            "2026-08-21T00:00:00Z",
            "2026-08-21T07:00:00Z",
            7,
        )
    wrong_time = _metadata() | {"validityTime": 600}
    with pytest.raises(GfsParserError, match="valid time"):
        _validate_identity(
            wrong_time,
            PROFILE_BY_SELECTOR["hpbl"],
            "hpbl",
            "2026-08-21T00:00:00Z",
            "2026-08-21T07:00:00Z",
            7,
        )


def test_parser_pins_specific_humidity_and_upward_flux_identities() -> None:
    _validate_identity(
        _metadata()
        | {
            "parameterCategory": 1,
            "parameterNumber": 0,
            "typeOfLevel": "heightAboveGround",
            "level": 2,
        },
        PROFILE_BY_SELECTOR["spfh_2m"],
        "spfh_2m",
        "2026-08-21T00:00:00Z",
        "2026-08-21T07:00:00Z",
        7,
    )
    for selector_key, parameter_number in (("shtfl", 11), ("lhtfl", 10)):
        _validate_identity(
            _metadata()
            | {
                "parameterCategory": 0,
                "parameterNumber": parameter_number,
                "typeOfLevel": "surface",
                "level": 0,
                "stepType": "avg",
                "typeOfStatisticalProcessing": 0,
                "startStep": 6,
            },
            PROFILE_BY_SELECTOR[selector_key],
            selector_key,
            "2026-08-21T00:00:00Z",
            "2026-08-21T07:00:00Z",
            7,
        )


def test_parser_pins_canonical_gfs_regular_latlon_scan_order() -> None:
    grid = {
        "gridType": "regular_ll",
        "Ni": 1440,
        "Nj": 721,
        "latitudeOfFirstGridPointInDegrees": 90.0,
        "longitudeOfFirstGridPointInDegrees": 0.0,
        "latitudeOfLastGridPointInDegrees": -90.0,
        "longitudeOfLastGridPointInDegrees": 359.75,
        "iDirectionIncrementInDegrees": 0.25,
        "jDirectionIncrementInDegrees": 0.25,
        "iScansNegatively": 0,
        "jScansPositively": 0,
        "jPointsAreConsecutive": 0,
        "alternativeRowScanning": 0,
    }

    _validate_regular_latlon(grid, "tmp_2m")

    with pytest.raises(GfsParserError, match="scan flags"):
        _validate_regular_latlon(grid | {"jScansPositively": 1}, "tmp_2m")
    with pytest.raises(GfsParserError, match="latitude endpoints"):
        _validate_regular_latlon(grid | {"latitudeOfLastGridPointInDegrees": -89.75}, "tmp_2m")


def test_full_message_missing_validation_precedes_lossless_compact_crop() -> None:
    geometry = regular_latlon_geometry(
        row_count=721,
        column_count=1440,
        first_latitude_deg=90.0,
        first_longitude_deg=0.0,
        last_latitude_deg=-90.0,
        last_longitude_deg=359.75,
        latitude_step_deg=-0.25,
        longitude_step_deg=0.25,
    )
    site = SiteSamplingConfig(
        site_id=1,
        site_slug="test-site",
        site_name="Test site",
        site_time_zone="Europe/Sofia",
        latitude_deg=42.6013,
        longitude_deg=23.2844,
        coordinate_reference="test-v1",
        reference_elevation_msl_m=1793.929,
        elevation_reference="test-dem-v1",
    )
    policy, policy_sha256 = load_sampling_policy()
    descriptor = plan_compact_grid(geometry, (site,), policy, policy_sha256)
    sentinel = -9_999.0
    values = np.arange(geometry.row_count * geometry.column_count, dtype="<f8")
    outside_index = 0
    inside_index = descriptor.crop_min_row * geometry.column_count + descriptor.crop_min_column
    values[[outside_index, inside_index]] = sentinel
    metadata = {
        "Ni": geometry.column_count,
        "Nj": geometry.row_count,
        "missingValue": sentinel,
        "numberOfMissing": 2,
    }

    compact, mask, native_missing_count = _crop_validated_values(
        values, metadata, descriptor, selector_key="tmp_2m"
    )

    assert compact.shape == (descriptor.compact_row_count, descriptor.compact_column_count)
    assert compact.dtype == np.dtype("<f8")
    assert mask.shape == compact.shape
    assert native_missing_count == 2
    assert int(mask.sum()) == 1
    assert np.isnan(compact[0, 0])
    assert compact.flags.c_contiguous
    expected = values.reshape(geometry.row_count, geometry.column_count)[
        descriptor.crop_min_row : descriptor.crop_max_row + 1,
        descriptor.crop_min_column : descriptor.crop_max_column + 1,
    ].copy()
    expected[expected == sentinel] = np.nan
    assert np.array_equal(compact, expected, equal_nan=True)
    with pytest.raises(GfsParserError, match="bitmap/sentinel"):
        _crop_validated_values(
            values,
            metadata | {"numberOfMissing": 1},
            descriptor,
            selector_key="tmp_2m",
        )


def test_time_and_missing_quality_helpers_preserve_explicit_states() -> None:
    assert _grib_utc(20260821, 700) == "2026-08-21T07:00:00Z"
    assert _derived_quality(np.array([1.0]), np.array([2.0])) == "derived"
    assert _derived_quality(np.array([1.0]), np.array([np.nan])) == "sentinel_missing"
    assert _add_hours("2026-08-21T00:00:00Z", 6) == "2026-08-21T06:00:00Z"
    assert _unit("convective_inhibition_magnitude_j_per_kg") == "J/kg"


def test_offline_f007_golden_contract_locks_parser_and_normalizer_outputs() -> None:
    fixture_path = Path(__file__).parents[2] / "fixtures" / "gfs" / "f007-golden-contract.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    parser = fixture["parser"]
    normalizer = fixture["normalizer"]
    assert parser["selected_selector_count"] == len(PROFILE_BY_SELECTOR)
    assert parser["hpbl"]["parameter_number"] == PROFILE_BY_SELECTOR["hpbl"].number
    assert parser["hpbl"]["native_unit"] == PROFILE_BY_SELECTOR["hpbl"].native_unit_override
    assert normalizer["canonical_grain_count"] == (
        normalizer["surface_grain_count"] + normalizer["pressure_level_grain_count"]
    )
    assert normalizer["model_elevation_selector"] == "orog"
    assert normalizer["quality_states"] == [
        "real",
        "derived",
        "missing",
        "sentinel_missing",
        "invalid_payload",
        "unsupported",
    ]
    assert GfsParserError.quality_state == "invalid_payload"
