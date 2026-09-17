from pathlib import Path

from paragliding_forecasts_ml.ingestion.igra.parser import parse_members


FIXTURES = Path(__file__).parents[2] / "fixtures" / "igra"


def test_parser_keeps_height_only_raw_levels_and_independent_derived_rows() -> None:
    result = parse_members(
        raw_content=(FIXTURES / "raw-selected-soundings.txt").read_bytes(),
        derived_content=(FIXTURES / "derived-selected-soundings.txt").read_bytes(),
        station_id="BUM00015614",
        dates_utc=("2025-08-02",),
        nominal_hours=(),
    )
    assert result.raw_selected == 1
    assert result.raw_soundings[0].levels[1].pressure == -9999
    assert result.derived_soundings[0].parameters["cin"] == -45