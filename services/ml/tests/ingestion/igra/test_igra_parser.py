from io import BytesIO
from pathlib import Path

import pytest

from paragliding_forecasts_ml.ingestion.igra.parser import IgraParseError, parse_members

FIXTURES = Path(__file__).parents[2] / "fixtures" / "igra"


def _raw_member() -> bytes:
    lines = (FIXTURES / "raw-selected-soundings.txt").read_bytes().splitlines()
    return b"\n".join(line if line.startswith(b"#") else line + b" " for line in lines) + b"\n"


def test_parser_streams_binary_members_and_keeps_selected_rows() -> None:
    result = parse_members(
        raw_content=BytesIO(_raw_member()),
        derived_content=BytesIO((FIXTURES / "derived-selected-soundings.txt").read_bytes()),
        station_id="BUM00015614",
        dates_utc=("2025-08-02",),
        nominal_hours=(),
    )
    assert result.raw_selected == 1
    assert result.raw_soundings[0].levels[1].pressure == -9999
    assert result.derived_soundings[0].parameters["cin"] == -45


def test_parser_rejects_a_raw_level_missing_the_provider_padding_column() -> None:
    with pytest.raises(IgraParseError, match="width 51, expected 52"):
        parse_members(
            raw_content=(FIXTURES / "raw-selected-soundings.txt").read_bytes(),
            derived_content=(FIXTURES / "derived-selected-soundings.txt").read_bytes(),
            station_id="BUM00015614",
            dates_utc=("2025-08-02",),
            nominal_hours=(),
        )
