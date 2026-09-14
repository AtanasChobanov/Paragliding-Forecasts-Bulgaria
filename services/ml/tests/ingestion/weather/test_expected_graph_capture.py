from __future__ import annotations

import sqlite3

from paragliding_forecasts_ml.ingestion.weather.persistence import (
    _ExpectedGraphCapture,
    _insert,
)


def test_expected_graph_capture_records_the_shared_insert_sql_shape() -> None:
    source = sqlite3.connect(":memory:")
    try:
        source.execute(
            "CREATE TABLE weather_ingestion_runs (id INTEGER PRIMARY KEY, run_key TEXT, status TEXT)"
        )
        capture = _ExpectedGraphCapture(source)

        row_id = _insert(
            capture,
            "weather_ingestion_runs",
            {"run_key": "test-run", "status": "running"},
        )

        assert row_id == -1
        assert len(capture.rows) == 1
        assert capture.rows[0].table == "weather_ingestion_runs"
        assert capture.rows[0].values == {"run_key": "test-run", "status": "running"}
        assert source.execute("SELECT count(*) FROM weather_ingestion_runs").fetchone()[0] == 0
    finally:
        source.close()
