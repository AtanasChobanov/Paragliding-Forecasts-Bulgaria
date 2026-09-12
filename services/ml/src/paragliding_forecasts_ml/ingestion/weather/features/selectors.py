"""Exact canonical selectors for source-neutral weather feature inputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


class CanonicalSelectorError(ValueError):
    """A feature policy identity cannot select one unambiguous canonical input."""


class _CanonicalField(Protocol):
    field_code: str
    grain: str
    dimension: str | None


@dataclass(frozen=True, slots=True)
class CanonicalFieldSelector:
    """One exact source-neutral field identity at the S05/S06 boundary."""

    diagnostic_key: str
    field_code: str
    grain: Literal["surface", "convection"]
    dimension: str | None


TWO_METRE_TEMPERATURE = CanonicalFieldSelector(
    "two_metre_temperature", "air_temperature_k", "surface", "2m_above_ground"
)
TWO_METRE_DEW_POINT = CanonicalFieldSelector(
    "two_metre_dew_point", "dew_point_temperature_k", "surface", "2m_above_ground"
)
TWO_METRE_RELATIVE_HUMIDITY = CanonicalFieldSelector(
    "two_metre_relative_humidity", "relative_humidity_percent", "surface", "2m_above_ground"
)
TWO_METRE_SPECIFIC_HUMIDITY = CanonicalFieldSelector(
    "two_metre_specific_humidity", "specific_humidity_kg_per_kg", "surface", "2m_above_ground"
)
SURFACE_PRESSURE = CanonicalFieldSelector(
    "surface_pressure", "air_pressure_pa", "surface", "surface"
)
MEAN_SEA_LEVEL_PRESSURE = CanonicalFieldSelector(
    "mean_sea_level_pressure", "air_pressure_pa", "surface", "mean_sea_level"
)
TEN_METRE_WIND_U = CanonicalFieldSelector(
    "ten_metre_wind_u", "wind_u_m_s", "surface", "10m_above_ground"
)
TEN_METRE_WIND_V = CanonicalFieldSelector(
    "ten_metre_wind_v", "wind_v_m_s", "surface", "10m_above_ground"
)
PROVIDER_BOUNDARY_LAYER_HEIGHT = CanonicalFieldSelector(
    "provider_boundary_layer_height", "provider_boundary_layer_height_agl_m", "surface", None
)
PROVIDER_CLOUD_BASE = CanonicalFieldSelector(
    "provider_cloud_base", "provider_cloud_base_agl_m", "surface", None
)
TOTAL_COLUMN_WATER_VAPOUR = CanonicalFieldSelector(
    "total_column_water_vapour", "total_column_water_vapour_kg_m2", "surface", None
)
SURFACE_CAPE = CanonicalFieldSelector(
    "surface_cape", "convective_available_potential_energy_j_per_kg", "convection", "surface"
)
SURFACE_CIN = CanonicalFieldSelector(
    "surface_cin", "convective_inhibition_magnitude_j_per_kg", "convection", "surface"
)
TOTAL_CLOUD_COVER = CanonicalFieldSelector(
    "total_cloud_cover", "cloud_cover_percent", "surface", "total"
)
LOW_CLOUD_COVER = CanonicalFieldSelector("low_cloud_cover", "cloud_cover_percent", "surface", "low")
MID_CLOUD_COVER = CanonicalFieldSelector("mid_cloud_cover", "cloud_cover_percent", "surface", "mid")
HIGH_CLOUD_COVER = CanonicalFieldSelector(
    "high_cloud_cover", "cloud_cover_percent", "surface", "high"
)


_POINT_SELECTOR_BY_IDENTITY: dict[tuple[str, str | None], CanonicalFieldSelector] = {
    (selector.field_code, variant): selector
    for selector, variant in (
        (TWO_METRE_TEMPERATURE, "2m"),
        (TWO_METRE_DEW_POINT, "2m"),
        (TWO_METRE_RELATIVE_HUMIDITY, "2m"),
        (TWO_METRE_SPECIFIC_HUMIDITY, "2m"),
        (SURFACE_PRESSURE, "surface"),
        (MEAN_SEA_LEVEL_PRESSURE, "mean_sea_level"),
        (TEN_METRE_WIND_U, "10m"),
        (TEN_METRE_WIND_V, "10m"),
        (PROVIDER_BOUNDARY_LAYER_HEIGHT, None),
        (PROVIDER_CLOUD_BASE, None),
        (TOTAL_COLUMN_WATER_VAPOUR, None),
        (SURFACE_CAPE, "surface_parcel"),
        (SURFACE_CIN, "surface_parcel"),
        (TOTAL_CLOUD_COVER, "total"),
        (LOW_CLOUD_COVER, "low"),
        (MID_CLOUD_COVER, "mid"),
        (HIGH_CLOUD_COVER, "high"),
    )
}


def selector_for_point_feature(field_code: str, variant: str | None) -> CanonicalFieldSelector:
    """Return the sole canonical source selector for one policy identity."""

    try:
        return _POINT_SELECTOR_BY_IDENTITY[(field_code, variant)]
    except KeyError as error:
        raise CanonicalSelectorError(
            f"No canonical selector is registered for ({field_code}, {variant!r})."
        ) from error


def resolve_canonical_field[FieldT: _CanonicalField](
    fields: tuple[FieldT, ...], selector: CanonicalFieldSelector
) -> FieldT | None:
    """Return one exact identity match; never fall back across dimensions or grains."""

    matches = tuple(
        field
        for field in fields
        if field.field_code == selector.field_code
        and field.grain == selector.grain
        and field.dimension == selector.dimension
    )
    if len(matches) > 1:
        raise CanonicalSelectorError(
            f"Canonical selector {selector.diagnostic_key} matched multiple inputs."
        )
    return matches[0] if matches else None
