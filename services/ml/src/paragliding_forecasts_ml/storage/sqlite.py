"""Read-only SQLite access for Python batch orchestration."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path, PurePosixPath, PureWindowsPath

DEFAULT_DATABASE_URL = "file:./data/local/paragliding.db"


class DatabaseConfigurationError(RuntimeError):
    """The local database cannot safely provide collector configuration."""


def repository_root() -> Path:
    """Locate the repository from the installed source-tree package layout."""

    return Path(__file__).resolve().parents[5]


def configured_database_url(explicit_database_url: str | None = None) -> str:
    """Use the explicit option, then environment, then the documented default."""

    return explicit_database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def resolve_database_path(
    database_url: str,
    project_root: Path | None = None,
) -> Path:
    """Mirror the repository's safe ``DATABASE_URL`` file-path contract."""

    if not database_url.startswith("file:"):
        raise DatabaseConfigurationError("DATABASE_URL must use the file: scheme.")

    raw_path = database_url.removeprefix("file:")
    if not raw_path or "?" in raw_path or "#" in raw_path:
        raise DatabaseConfigurationError(
            "DATABASE_URL must identify a local file without query or fragment components."
        )
    if PureWindowsPath(raw_path).is_absolute() or PurePosixPath(raw_path).is_absolute():
        raise DatabaseConfigurationError("DATABASE_URL must be relative to the repository root.")

    root = (project_root or repository_root()).resolve()
    database_path = (root / Path(raw_path)).resolve()
    data_root = (root / "data").resolve()
    try:
        database_path.relative_to(data_root)
    except ValueError as error:
        raise DatabaseConfigurationError(
            "DATABASE_URL must resolve below the repository data directory."
        ) from error
    if database_path == data_root:
        raise DatabaseConfigurationError("DATABASE_URL must identify a database file below data/.")
    return database_path


def open_read_only_database(
    database_url: str,
    project_root: Path | None = None,
) -> sqlite3.Connection:
    """Open an existing migrated database without allowing file creation or writes."""

    database_path = resolve_database_path(database_url, project_root)
    if not database_path.is_file():
        raise DatabaseConfigurationError(
            f"DATABASE_URL database file does not exist: {database_path}"
        )
    try:
        connection = sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True)
        connection.execute("PRAGMA foreign_keys = ON")
    except sqlite3.Error as error:
        raise DatabaseConfigurationError(
            "DATABASE_URL database could not be opened read-only."
        ) from error
    return connection


def load_site_country_codes(
    database_url: str,
    project_root: Path | None = None,
) -> tuple[str, ...]:
    """Return every distinct site country, including inactive historical sites."""

    connection = open_read_only_database(database_url, project_root)
    try:
        rows = connection.execute(
            "SELECT DISTINCT country_code_iso2 FROM sites ORDER BY country_code_iso2"
        ).fetchall()
    except sqlite3.Error as error:
        raise DatabaseConfigurationError(
            "DATABASE_URL must point to a migrated database with a sites table."
        ) from error
    finally:
        connection.close()

    country_codes = tuple(row[0] for row in rows)
    if not country_codes:
        raise DatabaseConfigurationError("The sites table did not provide any country codes.")
    if any(
        not isinstance(country_code, str)
        or len(country_code) != 2
        or any(character < "A" or character > "Z" for character in country_code)
        for country_code in country_codes
    ):
        raise DatabaseConfigurationError("The sites table contains an invalid ISO2 country code.")
    return country_codes
