from paragliding_forecasts_ml.ingestion.igra.station import parse_station_list


def test_station_parser_requires_one_fixed_width_match() -> None:
    row = f"{'BUM00015614':<11} {'42.6500':>8} {'23.3833':>9} {'595':>6} {'Sofia':<30} {'1955':>4} {'2026':>4} {'45850':>5}"
    station = parse_station_list((row + "\n").encode("ascii"), "BUM00015614")
    assert station.latitude_deg == 42.65