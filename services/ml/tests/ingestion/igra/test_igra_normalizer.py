from pathlib import Path

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
