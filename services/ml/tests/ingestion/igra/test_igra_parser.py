from io import BytesIO
from pathlib import Path

from paragliding_forecasts_ml.ingestion.igra.parser import parse_members

FIXTURES = Path(__file__).parents[2] / "fixtures" / "igra"


def test_parser_streams_binary_members_and_keeps_selected_rows() -> None:
    result = parse_members(
        raw_content=BytesIO((FIXTURES / "raw-selected-soundings.txt").read_bytes()),
        derived_content=BytesIO((FIXTURES / "derived-selected-soundings.txt").read_bytes()),
        station_id="BUM00015614",
        dates_utc=("2025-08-02",),
        nominal_hours=(),
    )
    assert result.raw_selected == 1
    assert result.raw_soundings[0].levels[1].pressure == -9999
    assert result.derived_soundings[0].parameters["cin"] == -45
