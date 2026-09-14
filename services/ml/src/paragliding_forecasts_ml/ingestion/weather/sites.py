"""Canonical weather-site configuration loaded through the read-only SQLite boundary."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ...storage.sqlite import DatabaseConfigurationError, open_read_only_database


class SiteSamplingConfigError(RuntimeError):
    """Canonical sites cannot be sampled from the configured database."""


@dataclass(frozen=True)
class SiteSamplingConfig:
    site_id: int
    site_slug: str
    site_name: str
    site_time_zone: str
    latitude_deg: float
    longitude_deg: float
    coordinate_reference: str
    reference_elevation_msl_m: float | None
    elevation_reference: str | None


def load_site_sampling_configs(
    database_url: str,
    project_root: Path | None = None,
    *,
    require_elevation: bool = False,
) -> tuple[SiteSamplingConfig, ...]:
    """Return every active canonical site with one reviewed sampling configuration."""

    try:
        connection = open_read_only_database(database_url, project_root)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """
                SELECT
                  s.id AS site_id,
                  s.slug AS site_slug,
                  s.name AS site_name,
                  s.time_zone AS site_time_zone,
                  c.latitude_deg,
                  c.longitude_deg,
                  c.coordinate_reference,
                  c.reference_elevation_msl_m,
                  c.elevation_reference
                FROM sites AS s
                LEFT JOIN weather_site_sampling_configs AS c ON c.site_id = s.id
                WHERE s.is_active = 1
                ORDER BY s.id
                """
            ).fetchall()
        finally:
            connection.close()
    except (DatabaseConfigurationError, sqlite3.Error) as error:
        raise SiteSamplingConfigError(
            "DATABASE_URL must identify a migrated database with canonical site sampling configs."
        ) from error

    if not rows:
        raise SiteSamplingConfigError("The migrated database has no active canonical sites.")

    missing = tuple(str(row["site_slug"]) for row in rows if row["latitude_deg"] is None)
    if missing:
        raise SiteSamplingConfigError(
            "Missing weather_site_sampling_configs for active sites: " + ", ".join(missing)
        )

    configs: list[SiteSamplingConfig] = []
    for row in rows:
        latitude = float(row["latitude_deg"])
        longitude = float(row["longitude_deg"])
        coordinate_reference = str(row["coordinate_reference"]).strip()
        elevation_value = row["reference_elevation_msl_m"]
        elevation_reference_value = row["elevation_reference"]
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise SiteSamplingConfigError(
                f"Invalid sampling coordinate for site {row['site_slug']}."
            )
        if not coordinate_reference:
            raise SiteSamplingConfigError(
                f"Missing coordinate reference for site {row['site_slug']}."
            )
        if (elevation_value is None) != (elevation_reference_value is None):
            raise SiteSamplingConfigError(
                f"Incomplete elevation reference pair for site {row['site_slug']}."
            )
        if require_elevation and elevation_value is None:
            raise SiteSamplingConfigError(
                f"Missing reviewed reference elevation for site {row['site_slug']}."
            )
        configs.append(
            SiteSamplingConfig(
                site_id=int(row["site_id"]),
                site_slug=str(row["site_slug"]),
                site_name=str(row["site_name"]),
                site_time_zone=str(row["site_time_zone"]),
                latitude_deg=latitude,
                longitude_deg=longitude,
                coordinate_reference=coordinate_reference,
                reference_elevation_msl_m=(
                    None if elevation_value is None else float(elevation_value)
                ),
                elevation_reference=(
                    None if elevation_reference_value is None else str(elevation_reference_value)
                ),
            )
        )
    return tuple(configs)
