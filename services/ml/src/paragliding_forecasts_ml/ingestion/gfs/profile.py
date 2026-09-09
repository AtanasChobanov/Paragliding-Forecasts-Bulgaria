"""Pinned numeric GRIB identity profile for NOAA GFS 0.25-degree messages."""

from __future__ import annotations

from dataclasses import dataclass

GFS_GRIB_PROFILE_VERSION = "noaa-gfs-grib2-table-v2"
GFS_CENTRE = "kwbc"
GFS_TABLES_VERSION = 2
GFS_LOCAL_TABLES_VERSION = 1
# The common pgrb2.0p25 object does not publish 875 hPa. Keep this exact
# contract in descending pressure order; collector, parser, and normalizer all
# consume it, while source-aware validation is parity-tested against it.
GFS_FEATURE_PROFILE_PRESSURES_HPA = (
    1000,
    975,
    950,
    925,
    900,
    850,
    800,
    750,
    700,
    650,
    600,
    550,
    500,
)


@dataclass(frozen=True)
class GfsMessageProfile:
    """Stable numeric identity; do not trust ecCodes short-name labels alone."""

    selector_key: str
    discipline: int
    category: int
    number: int
    type_of_level: str
    level: float | None = None
    native_unit_override: str | None = None


def _pressure(selector: str, category: int, number: int, pressure: int) -> GfsMessageProfile:
    return GfsMessageProfile(selector, 0, category, number, "isobaricInhPa", pressure)


PROFILES: tuple[GfsMessageProfile, ...] = (
    GfsMessageProfile("tmp_2m", 0, 0, 0, "heightAboveGround", 2),
    GfsMessageProfile("dpt_2m", 0, 0, 6, "heightAboveGround", 2),
    GfsMessageProfile("rh_2m", 0, 1, 1, "heightAboveGround", 2),
    GfsMessageProfile("ugrd_10m", 0, 2, 2, "heightAboveGround", 10),
    GfsMessageProfile("vgrd_10m", 0, 2, 3, "heightAboveGround", 10),
    GfsMessageProfile("gust_surface", 0, 2, 22, "surface"),
    GfsMessageProfile("pres_surface", 0, 3, 0, "surface"),
    GfsMessageProfile("prmsl", 0, 3, 1, "meanSea"),
    GfsMessageProfile("orog", 0, 3, 5, "surface"),
    GfsMessageProfile("hpbl", 0, 3, 196, "surface", native_unit_override="m"),
    GfsMessageProfile("tcdc", 0, 6, 1, "atmosphere"),
    GfsMessageProfile("lcdc", 0, 6, 3, "lowCloudLayer"),
    GfsMessageProfile("mcdc", 0, 6, 4, "middleCloudLayer"),
    GfsMessageProfile("hcdc", 0, 6, 5, "highCloudLayer"),
    GfsMessageProfile("apcp", 0, 1, 8, "surface"),
    GfsMessageProfile("dswrf", 0, 4, 192, "surface"),
    GfsMessageProfile("pwat", 0, 1, 3, "atmosphereSingleLayer"),
    GfsMessageProfile("cape_surface", 0, 7, 6, "surface"),
    GfsMessageProfile("cin_surface", 0, 7, 7, "surface"),
    GfsMessageProfile("cape_layer", 0, 7, 6, "pressureFromGroundLayer", 18000),
    GfsMessageProfile("cin_layer", 0, 7, 7, "pressureFromGroundLayer", 18000),
    *(
        _pressure(f"{name.lower()}_{pressure}", category, number, pressure)
        for pressure in GFS_FEATURE_PROFILE_PRESSURES_HPA
        for name, category, number in (
            ("HGT", 3, 5),
            ("TMP", 0, 0),
            ("RH", 1, 1),
            ("UGRD", 2, 2),
            ("VGRD", 2, 3),
            ("VVEL", 2, 8),
        )
    ),
)

PROFILE_BY_SELECTOR = {profile.selector_key: profile for profile in PROFILES}
