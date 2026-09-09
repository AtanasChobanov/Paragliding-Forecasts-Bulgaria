from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from paragliding_forecasts_ml.ingestion.gfs.normalizer import _add_hours, _derived_quality, _unit
from paragliding_forecasts_ml.ingestion.gfs.parser import (
    GfsParserError,
    _grib_utc,
    _validate_identity,
    _validate_regular_latlon,
)
from paragliding_forecasts_ml.ingestion.gfs.profile import PROFILE_BY_SELECTOR


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
    assert len(PROFILE_BY_SELECTOR) == 99
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
    assert normalizer["source_unsupported_selectors"] == ["gust_surface"]
    assert normalizer["model_elevation_selector"] == "orog"
    assert normalizer["quality_states"] == [
        "real",
        "derived",
        "missing",
        "sentinel_missing",
        "invalid_payload",
    ]
    assert GfsParserError.quality_state == "invalid_payload"
