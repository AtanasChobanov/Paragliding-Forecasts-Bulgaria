from pathlib import Path

from paragliding_forecasts_ml.ingestion.igra.normalizer import normalize
from paragliding_forecasts_ml.ingestion.igra.parser import parse_members
from paragliding_forecasts_ml.ingestion.igra.validation import validate


FIXTURES = Path(__file__).parents[2] / "fixtures" / "igra"


def test_height_only_wind_level_does_not_quarantine_an_otherwise_usable_sounding() -> None:
    parsed = parse_members(
        raw_content=(FIXTURES / "raw-selected-soundings.txt").read_bytes(),
        derived_content=(FIXTURES / "derived-selected-soundings.txt").read_bytes(),
        station_id="BUM00015614",
        dates_utc=("2025-08-02",),
        nominal_hours=(),
    )
    normalized = normalize(
        parsed.raw_soundings,
        parsed.derived_soundings,
        source_snapshot_id="0" * 64,
        inventory_latitude_deg=42.65,
        inventory_longitude_deg=23.3833,
    )
    result = validate(
        normalized.soundings,
        normalized.levels,
        normalized.provider_parameters,
        normalized.provider_levels,
        requested_dates_utc=("2025-08-02",),
        requested_nominal_hours=(),
    )
    assert len(result.accepted_soundings) == 1
    assert len(result.quarantined_soundings) == 0


def test_empty_selection_publishes_missing_evidence() -> None:
    result = validate((), (), (), (), requested_dates_utc=("2025-08-11",), requested_nominal_hours=(12,))
    assert result.missing_evidence[0]["reason"] == "no_observation_for_selection"