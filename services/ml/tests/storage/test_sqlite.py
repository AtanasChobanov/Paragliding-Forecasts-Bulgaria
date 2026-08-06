from __future__ import annotations

import sqlite3

import pytest

from paragliding_forecasts_ml.storage.sqlite import (
    DEFAULT_DATABASE_URL,
    DatabaseConfigurationError,
    configured_database_url,
    load_site_country_codes,
    open_read_only_database,
    resolve_database_path,
)


def create_sites_database(tmp_path, rows: list[tuple[str, int]]) -> tuple[object, object]:
    project_root = tmp_path / "project"
    database_path = project_root / "data" / "local" / "paragliding.db"
    database_path.parent.mkdir(parents=True)
    connection = sqlite3.connect(database_path)
    connection.execute(
        "CREATE TABLE sites (country_code_iso2 TEXT NOT NULL, is_active INTEGER NOT NULL)"
    )
    connection.executemany("INSERT INTO sites (country_code_iso2, is_active) VALUES (?, ?)", rows)
    connection.commit()
    connection.close()
    return project_root, database_path


def test_configured_database_url_uses_explicit_then_environment_then_default(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "file:./data/from-env.db")

    assert configured_database_url("file:./data/explicit.db") == "file:./data/explicit.db"
    assert configured_database_url() == "file:./data/from-env.db"

    monkeypatch.delenv("DATABASE_URL")
    assert configured_database_url() == DEFAULT_DATABASE_URL


@pytest.mark.parametrize(
    "database_url",
    (
        "./data/local/paragliding.db",
        "https://example.test/paragliding.db",
        "file:./data/local/paragliding.db?mode=rw",
        "file:./data/local/paragliding.db#fragment",
        "file:/tmp/paragliding.db",
        r"file:C:\outside\paragliding.db",
        "file:./outside/paragliding.db",
        "file:./data",
    ),
)
def test_resolve_database_path_rejects_unsafe_or_unsupported_urls(tmp_path, database_url) -> None:
    with pytest.raises(DatabaseConfigurationError):
        resolve_database_path(database_url, tmp_path)


def test_read_only_open_rejects_missing_database_without_creating_it(tmp_path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    database_url = "file:./data/local/missing.db"

    with pytest.raises(DatabaseConfigurationError, match="does not exist"):
        open_read_only_database(database_url, project_root)

    assert not (project_root / "data" / "local" / "missing.db").exists()


def test_load_site_country_codes_includes_inactive_sites_and_is_sorted_unique(tmp_path) -> None:
    project_root, _database_path = create_sites_database(
        tmp_path,
        [("RS", 0), ("BG", 1), ("RS", 1)],
    )

    assert load_site_country_codes("file:./data/local/paragliding.db", project_root) == (
        "BG",
        "RS",
    )


def test_open_read_only_database_enables_foreign_keys(tmp_path) -> None:
    project_root, _database_path = create_sites_database(tmp_path, [("BG", 1)])

    connection = open_read_only_database("file:./data/local/paragliding.db", project_root)
    try:
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
    finally:
        connection.close()


def test_load_site_country_codes_fails_closed_for_empty_or_missing_schema(tmp_path) -> None:
    project_root, database_path = create_sites_database(tmp_path, [])

    with pytest.raises(DatabaseConfigurationError, match="did not provide any country codes"):
        load_site_country_codes("file:./data/local/paragliding.db", project_root)

    connection = sqlite3.connect(database_path)
    connection.execute("DROP TABLE sites")
    connection.commit()
    connection.close()

    with pytest.raises(DatabaseConfigurationError, match="sites table"):
        load_site_country_codes("file:./data/local/paragliding.db", project_root)


@pytest.mark.parametrize("country_code", ("bg", "BGR", "B1", "БГ"))
def test_load_site_country_codes_rejects_invalid_iso2_values(tmp_path, country_code) -> None:
    project_root, _database_path = create_sites_database(tmp_path, [(country_code, 1)])

    with pytest.raises(DatabaseConfigurationError, match="invalid ISO2"):
        load_site_country_codes("file:./data/local/paragliding.db", project_root)
