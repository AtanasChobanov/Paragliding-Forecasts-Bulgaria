from pathlib import Path

import pytest

from paragliding_forecasts_ml.ingestion.igra.normalizer import normalize
from paragliding_forecasts_ml.ingestion.igra.parser import parse_members

FIXTURES = Path(__file__).parents[2] / "fixtures" / "igra"


def _raw_member() -> bytes:
    lines = (FIXTURES / "raw-selected-soundings.txt").read_bytes().splitlines()
    return b"\n".join(line if line.startswith(b"#") else line + b" " for line in lines) + b"\n"


def test_normalizer_derives_dew_point_relative_humidity_and_wind_components() -> None:
    parsed = parse_members(
        raw_content=_raw_member(),
        derived_content=(FIXTURES / "derived-selected-soundings.txt").read_bytes(),
        station_id="BUM00015614",
        dates_utc=("2025-08-02",),
        nominal_hours=(),
    )
    result = normalize(
        parsed.raw_soundings,
        parsed.derived_soundings,
        source_snapshot_id="0" * 64,
        inventory_latitude_deg=42.65,
        inventory_longitude_deg=23.3833,
    )
    assert result.levels[0].dew_point_k is not None
    assert result.levels[0].u_wind_m_s is not None
    assert result.provider_parameters[0].values["cin_magnitude_j_kg"] == 45


def test_reported_relative_humidity_keeps_its_measured_provenance() -> None:
    parsed = parse_members(
        raw_content=_raw_member(),
        derived_content=(FIXTURES / "derived-selected-soundings.txt").read_bytes(),
        station_id="BUM00015614",
        dates_utc=("2025-08-02",),
        nominal_hours=(),
    )
    raw = parsed.raw_soundings[0]
    reported_level = raw.levels[0].model_copy(update={"relative_humidity": 650})
    raw = raw.model_copy(update={"levels": (reported_level, *raw.levels[1:])})

    result = normalize(
        (raw,),
        (),
        source_snapshot_id="0" * 64,
        inventory_latitude_deg=42.65,
        inventory_longitude_deg=23.3833,
    )
    level = result.levels[0]

    assert level.relative_humidity_percent == 65.0
    assert level.provenance["relative_humidity_percent"]["quality_state"] == "real"
    assert (
        level.provenance["relative_humidity_percent"]["native_field"]
        == "reported_relative_humidity_tenth_percent"
    )


@pytest.mark.parametrize(
    ("temperature", "depression", "state", "reason"),
    [
        (None, 30, "missing", "blank_native"),
        (-8888, 30, "sentinel_missing", "source_removed_by_qa"),
        (250, None, "missing", "blank_native"),
        (250, -9999, "sentinel_missing", "source_missing_before_qa"),
    ],
)
def test_dew_point_provenance_follows_missing_dependency(
    temperature: int | None, depression: int | None, state: str, reason: str
) -> None:
    parsed = parse_members(
        raw_content=_raw_member(),
        derived_content=(FIXTURES / "derived-selected-soundings.txt").read_bytes(),
        station_id="BUM00015614",
        dates_utc=("2025-08-02",),
        nominal_hours=(),
    )
    raw = parsed.raw_soundings[0]
    first = raw.levels[0].model_copy(
        update={"temperature": temperature, "dew_point_depression": depression}
    )
    raw = raw.model_copy(update={"levels": (first, *raw.levels[1:])})
    result = normalize(
        (raw,),
        (),
        source_snapshot_id="0" * 64,
        inventory_latitude_deg=42.65,
        inventory_longitude_deg=23.3833,
    )
    level = result.levels[0]
    assert level.dew_point_k is None
    assert level.provenance["dew_point_k"]["quality_state"] == state
    assert level.provenance["dew_point_k"]["missing_reason"] == reason


@pytest.mark.parametrize(
    ("native", "signed", "magnitude", "state"),
    [(-45, -45, 45, "real"), (0, 0, 0, "real"), (-8888, None, None, "sentinel_missing")],
)
def test_cin_values_and_provenance_share_published_keys(
    native: int, signed: int | None, magnitude: int | None, state: str
) -> None:
    parsed = parse_members(
        raw_content=_raw_member(),
        derived_content=(FIXTURES / "derived-selected-soundings.txt").read_bytes(),
        station_id="BUM00015614",
        dates_utc=("2025-08-02",),
        nominal_hours=(),
    )
    derived = parsed.derived_soundings[0]
    derived = derived.model_copy(update={"parameters": {**derived.parameters, "cin": native}})
    result = normalize(
        (),
        (derived,),
        source_snapshot_id="0" * 64,
        inventory_latitude_deg=42.65,
        inventory_longitude_deg=23.3833,
    )
    parameters = result.provider_parameters[0]
    assert parameters.values["native_cin_j_kg"] == signed
    assert parameters.values["cin_magnitude_j_kg"] == magnitude
    assert set(parameters.values) == set(parameters.provenance)
    assert parameters.provenance["native_cin_j_kg"]["quality_state"] == state
    assert parameters.provenance["cin_magnitude_j_kg"]["quality_state"] == (
        "derived" if state == "real" else state
    )
