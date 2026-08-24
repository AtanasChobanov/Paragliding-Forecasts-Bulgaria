from __future__ import annotations

import sqlite3

import pytest

from paragliding_forecasts_ml.ingestion.weather.sites import (
    SiteSamplingConfigError,
    load_site_sampling_configs,
)


def _database(tmp_path, *, include_second_config: bool = True):
    project_root = tmp_path / "project"
    database_path = project_root / "data" / "local" / "weather.db"
    database_path.parent.mkdir(parents=True)
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE sites (
          id INTEGER PRIMARY KEY,
          slug TEXT NOT NULL,
          name TEXT NOT NULL,
          is_active INTEGER NOT NULL
        );
        CREATE TABLE weather_site_sampling_configs (
          site_id INTEGER PRIMARY KEY,
          latitude_deg REAL NOT NULL,
          longitude_deg REAL NOT NULL,
          coordinate_reference TEXT NOT NULL,
          reference_elevation_msl_m REAL,
          elevation_reference TEXT
        );
        INSERT INTO sites VALUES
          (1, 'first', 'First', 1),
          (2, 'second', 'Second', 1),
          (3, 'inactive', 'Inactive', 0);
        INSERT INTO weather_site_sampling_configs VALUES
          (1, 42.5, 23.5, 'canonical-v1', 800, 'dem-v1');
        """
    )
    if include_second_config:
        connection.execute(
            "INSERT INTO weather_site_sampling_configs VALUES (?, ?, ?, ?, ?, ?)",
            (2, 43.5, 24.5, "proxy-v1", None, None),
        )
    connection.commit()
    connection.close()
    return project_root, "file:./data/local/weather.db"


def test_load_site_sampling_configs_is_sorted_read_only_and_keeps_null_elevation(tmp_path) -> None:
    project_root, database_url = _database(tmp_path)

    configs = load_site_sampling_configs(database_url, project_root)

    assert [config.site_slug for config in configs] == ["first", "second"]
    assert configs[0].reference_elevation_msl_m == 800
    assert configs[1].reference_elevation_msl_m is None

    connection = sqlite3.connect(project_root / "data" / "local" / "weather.db")
    try:
        assert connection.execute("SELECT count(*) FROM sites").fetchone() == (3,)
    finally:
        connection.close()


def test_load_site_sampling_configs_fails_when_active_config_is_missing(tmp_path) -> None:
    project_root, database_url = _database(tmp_path, include_second_config=False)

    with pytest.raises(SiteSamplingConfigError, match="second"):
        load_site_sampling_configs(database_url, project_root)


def test_load_site_sampling_configs_can_require_reviewed_elevation(tmp_path) -> None:
    project_root, database_url = _database(tmp_path)

    with pytest.raises(SiteSamplingConfigError, match="second"):
        load_site_sampling_configs(database_url, project_root, require_elevation=True)
