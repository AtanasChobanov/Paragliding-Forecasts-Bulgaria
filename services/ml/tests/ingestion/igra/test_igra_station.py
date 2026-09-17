from paragliding_forecasts_ml.ingestion.igra.station import parse_station_list

SOFIA_ROW = (
    b"BUM00015614  42.6500   23.3833  595.0    SOFIA (OBSERV.)                1955 2026  45854"
)


def test_station_parser_uses_actual_noaa_columns_despite_utf8_other_rows() -> None:
    other_station = "RIM00013275  44.7714   20.4244  203.0    BEOGRAD/KOŠUTNJAK              1971 2026  40041".encode()

    station = parse_station_list(other_station + b"\n" + SOFIA_ROW + b"\n", "BUM00015614")

    assert station.latitude_deg == 42.65
    assert station.longitude_deg == 23.3833
    assert station.elevation_m == 595
    assert station.name == "SOFIA (OBSERV.)"
    assert station.first_year == 1955
    assert station.last_year == 2026
    assert station.observation_count == 45854
