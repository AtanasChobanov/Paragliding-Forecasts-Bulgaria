"""Source-neutral S07 feature reductions over validated canonical site samples."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite

from ...gfs.models import GFS_SOURCE_ID
from ..spatial import (
    NeighbourhoodNodeRecord,
    SampledField,
    SamplingFootprint,
    SiteAlignedSample,
    SiteConfigSnapshot,
)
from .aggregation import (
    IntervalValue,
    TimedValue,
    hourly_amount_maximum,
    interval_maximum,
    interval_total,
    interval_weighted_mean,
    strict_hourly_reduction,
)
from .contracts import FeatureLayer, FeatureValue
from .neighbourhood import (
    NeighbourhoodCoverageError,
    NeighbourhoodObservation,
    fit_neighbourhood_metrics,
)
from .policy import FeatureLayerPolicy, FeaturePolicyEntry
from .selectors import (
    MEAN_SEA_LEVEL_PRESSURE,
    PROVIDER_BOUNDARY_LAYER_HEIGHT,
    SURFACE_PRESSURE,
    TEN_METRE_WIND_U,
    TEN_METRE_WIND_V,
    TWO_METRE_RELATIVE_HUMIDITY,
    TWO_METRE_SPECIFIC_HUMIDITY,
    TWO_METRE_TEMPERATURE,
    CanonicalFieldSelector,
    CanonicalSelectorError,
    resolve_canonical_field,
    selector_for_point_feature,
)
from .thermodynamics import (
    HeightProfilePoint,
    PressureProfilePoint,
    ThermodynamicError,
    mixed_layer_lcl_agl_m,
    thermal_strength_from_surface_fluxes,
)
from .vertical import (
    VerticalCoverageError,
    VerticalPoint,
    bounded_profile,
    bulk_vector_shear_m_s_per_km,
    endpoint_lapse_rate_k_per_km,
    meteorological_direction_from_uv,
    scalar_speed_profile,
    trapezoidal_mean,
)


@dataclass(frozen=True)
class FeatureResult:
    """One scalar intermediate result before it is materialized as a contract value."""

    value: float | None
    missing_reason: str | None = None


@dataclass(frozen=True)
class ThermalFeatureResult:
    """The coupled signed buoyancy and non-negative convective-scale values."""

    values: tuple[float, float] | None
    missing_reason: str | None = None


class FeatureBuildError(ValueError):
    """Validated evidence cannot be reduced under the S07 feature policy."""


class CanonicalFeatureSelectionError(FeatureBuildError):
    """A canonical selector was ambiguous or does not map an input identity."""


def build_hourly_point_features(
    sample: SiteAlignedSample,
    entries: tuple[FeaturePolicyEntry, ...],
    *,
    source_id: str | None = None,
) -> tuple[FeatureValue, ...]:
    """Materialize policy-ordered hourly provider and project-derived features."""

    values: list[FeatureValue] = []
    for entry in entries:
        if entry.feature_key == "wind_direction_10m_degrees_from_north":
            u_value = _point_hour_value(sample, _entry_for(entries, "wind_u_10m_m_s"))
            v_value = _point_hour_value(sample, _entry_for(entries, "wind_v_10m_m_s"))
            direction = (
                None
                if u_value is None or v_value is None
                else meteorological_direction_from_uv(u_value, v_value)
            )
            values.append(
                _missing_feature(entry, "wind_components_missing")
                if direction is None
                else _derived_feature(entry, direction)
            )
            continue
        if entry.feature_key in _HOURLY_DERIVED_KEYS:
            result = _derived_hour_value(sample, entry.feature_key)
            values.append(
                _missing_feature(entry, result.missing_reason or "derived_feature_missing")
                if result.value is None
                else _derived_feature(entry, result.value)
            )
            continue
        if entry.feature_key == "provider_cloud_base_agl_m" and source_id == GFS_SOURCE_ID:
            values.append(_unsupported_feature(entry, "source_field_unavailable"))
            continue
        value = _point_hour_value(sample, entry)
        values.append(
            _missing_feature(entry, "hour_value_missing")
            if value is None
            else _source_feature(entry, value)
        )
    return tuple(values)


_HOURLY_DERIVED_KEYS = frozenset(
    {
        "mixed_layer_lcl_agl_m",
        "pbl_minus_lcl_m",
        "surface_buoyancy_flux_kinematic_m2_s3",
        "convective_velocity_scale_m_s",
    }
)


def _derived_hour_value(sample: SiteAlignedSample, feature_key: str) -> FeatureResult:
    if feature_key == "mixed_layer_lcl_agl_m":
        return _mixed_layer_lcl_result(sample)
    if feature_key == "pbl_minus_lcl_m":
        lcl = _mixed_layer_lcl_result(sample)
        if lcl.value is None:
            return lcl
        provider_pbl = _surface_field(sample, PROVIDER_BOUNDARY_LAYER_HEIGHT)
        if provider_pbl is None:
            return FeatureResult(None, "provider_boundary_layer_height_missing")
        return FeatureResult(provider_pbl - lcl.value)
    thermal = _thermal_strength_result(sample)
    if thermal.values is None:
        return FeatureResult(None, thermal.missing_reason)
    buoyancy, convective_velocity = thermal.values
    return FeatureResult(
        buoyancy if feature_key == "surface_buoyancy_flux_kinematic_m2_s3" else convective_velocity
    )


def _mixed_layer_lcl_result(sample: SiteAlignedSample) -> FeatureResult:
    surface_pressure = _surface_field(sample, SURFACE_PRESSURE)
    surface_temperature = _surface_field(sample, TWO_METRE_TEMPERATURE)
    surface_humidity = _surface_field(sample, TWO_METRE_SPECIFIC_HUMIDITY)
    if surface_pressure is None or surface_temperature is None or surface_humidity is None:
        return FeatureResult(None, "mixed_layer_surface_input_missing")
    profile: list[PressureProfilePoint] = []
    for level in sample.profile_levels:
        temperature = _profile_field(level.fields, "air_temperature_k")
        humidity = _profile_field(level.fields, "specific_humidity_kg_per_kg")
        if temperature is None or humidity is None:
            return FeatureResult(None, "mixed_layer_profile_input_missing")
        profile.append(PressureProfilePoint(level.pressure_pa, temperature, humidity))
    try:
        return FeatureResult(
            mixed_layer_lcl_agl_m(
                surface_pressure_pa=surface_pressure,
                surface_temperature_k=surface_temperature,
                surface_specific_humidity_kg_per_kg=surface_humidity,
                profile=tuple(profile),
            )
        )
    except ThermodynamicError as error:
        return FeatureResult(None, str(error))


def _thermal_strength_result(sample: SiteAlignedSample) -> ThermalFeatureResult:
    surface_pressure = _surface_field(sample, SURFACE_PRESSURE)
    surface_temperature = _surface_field(sample, TWO_METRE_TEMPERATURE)
    surface_humidity = _surface_field(sample, TWO_METRE_SPECIFIC_HUMIDITY)
    provider_pbl = _surface_field(sample, PROVIDER_BOUNDARY_LAYER_HEIGHT)
    sensible = _interval_field_ending(sample, "surface_sensible_heat_flux_upward_w_m2")
    latent = _interval_field_ending(sample, "surface_latent_heat_flux_upward_w_m2")
    if (
        surface_pressure is None
        or surface_temperature is None
        or surface_humidity is None
        or provider_pbl is None
        or sensible is None
        or latent is None
    ):
        return ThermalFeatureResult(None, "thermal_strength_input_missing")
    if (
        sensible.interval_start_utc != latent.interval_start_utc
        or sensible.interval_end_utc != latent.interval_end_utc
    ):
        return ThermalFeatureResult(None, "thermal_flux_interval_mismatch")
    profile: list[HeightProfilePoint] = []
    for level in sample.profile_levels:
        temperature = _profile_field(level.fields, "air_temperature_k")
        humidity = _profile_field(level.fields, "specific_humidity_kg_per_kg")
        if temperature is None or humidity is None:
            return ThermalFeatureResult(None, "thermal_profile_input_missing")
        profile.append(
            HeightProfilePoint(level.level_height_agl_m, level.pressure_pa, temperature, humidity)
        )
    try:
        thermal = thermal_strength_from_surface_fluxes(
            surface_pressure_pa=surface_pressure,
            surface_temperature_k=surface_temperature,
            surface_specific_humidity_kg_per_kg=surface_humidity,
            sensible_heat_flux_upward_w_m2=sensible.canonical_value,
            latent_heat_flux_upward_w_m2=latent.canonical_value,
            provider_boundary_layer_height_agl_m=provider_pbl,
            profile=tuple(profile),
        )
    except ThermodynamicError as error:
        return ThermalFeatureResult(None, str(error))
    return ThermalFeatureResult(
        (
            thermal.surface_buoyancy_flux_kinematic_m2_s3,
            thermal.convective_velocity_scale_m_s,
        )
    )


def _interval_field_ending(sample: SiteAlignedSample, field_code: str) -> SampledField | None:
    matches = [
        field
        for field in sample.fields
        if field.grain == "interval"
        and field.field_code == field_code
        and field.interval_end_utc == sample.valid_at_utc
        and _available_value(field) is not None
    ]
    if len(matches) != 1:
        return None
    field = matches[0]
    if field.interval_start_utc is None:
        return None
    try:
        start = datetime.strptime(field.interval_start_utc, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        )
        end = datetime.strptime(field.interval_end_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None
    return field if (end - start).total_seconds() == 3600 else None


def _entry_for(entries: tuple[FeaturePolicyEntry, ...], feature_key: str) -> FeaturePolicyEntry:
    matches = [entry for entry in entries if entry.feature_key == feature_key]
    if len(matches) != 1:
        raise FeatureBuildError(f"Hourly policy is missing {feature_key}.")
    return matches[0]


def build_daily_point_features(
    samples: tuple[SiteAlignedSample, ...],
    entries: tuple[FeaturePolicyEntry, ...],
    *,
    expected_instants_utc: tuple[str, ...],
    source_id: str | None = None,
) -> tuple[FeatureValue, ...]:
    """Reduce strict instantaneous point/provider evidence; interval and neighbourhood facts stay separate."""
    deferred = {
        "precipitation_total_mm",
        "precipitation_max_hourly_mm",
        "shortwave_radiation_mean_w_m2",
        "shortwave_radiation_max_w_m2",
        "surface_sensible_heat_flux_mean_w_m2",
        "surface_latent_heat_flux_mean_w_m2",
        "surface_buoyancy_flux_kinematic_mean_m2_s3",
        "surface_buoyancy_flux_kinematic_max_m2_s3",
        "convective_velocity_scale_mean_m_s",
        "convective_velocity_scale_max_m_s",
        "neighbourhood_pressure_gradient_mean_pa_per_km",
        "neighbourhood_pressure_gradient_max_pa_per_km",
        "neighbourhood_low_level_divergence_mean_s_inverse",
        "neighbourhood_low_level_divergence_min_s_inverse",
        *_DAILY_DERIVED_POINT_KEYS,
    }
    computed: dict[str, FeatureValue] = {}
    for entry in entries:
        if (
            entry.feature_key in deferred
            or entry.feature_key == "wind_direction_10m_mean_degrees_from_north"
            or (
                entry.feature_key.startswith("provider_cloud_base_agl_")
                and source_id == GFS_SOURCE_ID
            )
        ):
            continue
        reduction = strict_hourly_reduction(
            tuple(
                TimedValue(sample.valid_at_utc, _point_hour_value(sample, entry))
                for sample in samples
            ),
            _window(expected_instants_utc),
            _reducer(entry),
        )
        computed[entry.feature_key] = (
            _missing_feature(entry, reduction.missing_reason or "point_feature_missing")
            if reduction.value is None
            else _derived_feature(entry, reduction.value)
        )
    values: list[FeatureValue] = []
    for entry in entries:
        if entry.feature_key in deferred:
            continue
        if entry.feature_key.startswith("provider_cloud_base_agl_") and source_id == GFS_SOURCE_ID:
            values.append(_unsupported_feature(entry, "source_field_unavailable"))
            continue
        if entry.feature_key != "wind_direction_10m_mean_degrees_from_north":
            values.append(computed[entry.feature_key])
            continue
        u_value = computed["wind_u_10m_mean_m_s"].canonical_value
        v_value = computed["wind_v_10m_mean_m_s"].canonical_value
        direction = (
            None
            if u_value is None or v_value is None
            else meteorological_direction_from_uv(u_value, v_value)
        )
        values.append(
            _missing_feature(
                entry,
                "wind_components_missing" if direction is None else "wind_direction_undefined",
            )
            if direction is None
            else _derived_feature(entry, direction)
        )
    values.extend(_build_daily_derived_point_features(samples, entries, expected_instants_utc))
    return tuple(values)


_DAILY_DERIVED_POINT_KEYS = frozenset(
    {
        "mixed_layer_lcl_agl_mean_m",
        "mixed_layer_lcl_agl_min_m",
        "mixed_layer_lcl_agl_max_m",
        "pbl_minus_lcl_mean_m",
        "pbl_minus_lcl_max_m",
    }
)

_SOURCE_BACKED_POINT_METHODS = frozenset(
    {
        "identity/1",
        "hourly-arithmetic-mean/1",
        "hourly-maximum/1",
        "hourly-minimum/1",
        "surface-parcel-day-reduction/1",
    }
)


def validate_point_policy_selectors(entries: tuple[FeaturePolicyEntry, ...]) -> None:
    """Fail closed when a source-backed point policy lacks an exact selector."""

    for entry in entries:
        if (
            entry.feature_key in _DAILY_DERIVED_POINT_KEYS
            or entry.derivation_method not in _SOURCE_BACKED_POINT_METHODS
        ):
            continue
        selector_for_point_feature(entry.field_code, entry.variant)


def _build_daily_derived_point_features(
    samples: tuple[SiteAlignedSample, ...],
    entries: tuple[FeaturePolicyEntry, ...],
    expected_instants_utc: tuple[str, ...],
) -> tuple[FeatureValue, ...]:
    hourly_key = {
        "mixed_layer_lcl_agl_mean_m": "mixed_layer_lcl_agl_m",
        "mixed_layer_lcl_agl_min_m": "mixed_layer_lcl_agl_m",
        "mixed_layer_lcl_agl_max_m": "mixed_layer_lcl_agl_m",
        "pbl_minus_lcl_mean_m": "pbl_minus_lcl_m",
        "pbl_minus_lcl_max_m": "pbl_minus_lcl_m",
    }
    values: list[FeatureValue] = []
    for entry in entries:
        source_key = hourly_key.get(entry.feature_key)
        if source_key is None:
            continue
        reduction = strict_hourly_reduction(
            tuple(
                TimedValue(sample.valid_at_utc, _derived_hour_value(sample, source_key).value)
                for sample in samples
            ),
            _window(expected_instants_utc),
            _reducer(entry),
        )
        values.append(
            _missing_feature(entry, reduction.missing_reason or "derived_feature_missing")
            if reduction.value is None
            else _derived_feature(entry, reduction.value)
        )
    return tuple(values)


def build_daily_interval_features(
    samples: tuple[SiteAlignedSample, ...],
    entries: tuple[FeaturePolicyEntry, ...],
    *,
    expected_instants_utc: tuple[str, ...],
) -> tuple[FeatureValue, ...]:
    """Reduce interval evidence only after exact half-open flying-window coverage."""

    window = _window(expected_instants_utc)
    values: list[FeatureValue] = []
    direct_mean_keys = {
        "shortwave_radiation_mean_w_m2",
        "surface_sensible_heat_flux_mean_w_m2",
        "surface_latent_heat_flux_mean_w_m2",
    }
    thermal_mean_keys = {
        "surface_buoyancy_flux_kinematic_mean_m2_s3",
        "convective_velocity_scale_mean_m_s",
    }
    thermal_max_keys = {
        "surface_buoyancy_flux_kinematic_max_m2_s3",
        "convective_velocity_scale_max_m_s",
    }
    for entry in entries:
        if entry.feature_key in {
            "surface_buoyancy_flux_kinematic_mean_m2_s3",
            "surface_buoyancy_flux_kinematic_max_m2_s3",
        }:
            intervals = _thermal_intervals(samples, component_index=0, window=window)
        elif entry.feature_key in {
            "convective_velocity_scale_mean_m_s",
            "convective_velocity_scale_max_m_s",
        }:
            intervals = _thermal_intervals(samples, component_index=1, window=window)
        elif entry.feature_key in {
            "precipitation_total_mm",
            "precipitation_max_hourly_mm",
            "shortwave_radiation_mean_w_m2",
            "shortwave_radiation_max_w_m2",
            "surface_sensible_heat_flux_mean_w_m2",
            "surface_latent_heat_flux_mean_w_m2",
        }:
            intervals = _field_intervals(samples, entry.field_code, window)
        else:
            continue
        if entry.feature_key == "precipitation_total_mm":
            result = interval_total(intervals, window)
        elif entry.feature_key == "precipitation_max_hourly_mm":
            result = hourly_amount_maximum(intervals, window)
        elif entry.feature_key in direct_mean_keys | thermal_mean_keys:
            result = interval_weighted_mean(intervals, window)
        elif (
            entry.feature_key == "shortwave_radiation_max_w_m2"
            or entry.feature_key in thermal_max_keys
        ):
            result = interval_maximum(intervals, window)
        else:
            raise FeatureBuildError(f"Unsupported interval policy key: {entry.feature_key}")
        values.append(
            _missing_feature(entry, result.missing_reason or "interval_feature_missing")
            if result.value is None
            else _derived_feature(entry, result.value)
        )
    return tuple(values)


def _field_intervals(
    samples: tuple[SiteAlignedSample, ...], field_code: str, window
) -> tuple[IntervalValue, ...]:
    return tuple(
        IntervalValue(
            field.interval_start_utc or "",
            field.interval_end_utc or "",
            _available_value(field),
        )
        for sample in samples
        for field in sample.fields
        if field.grain == "interval"
        and field.field_code == field_code
        and _intersects_flying_window(field.interval_start_utc, field.interval_end_utc, window)
    )


def _thermal_intervals(
    samples: tuple[SiteAlignedSample, ...], *, component_index: int, window
) -> tuple[IntervalValue, ...]:
    intervals: list[IntervalValue] = []
    for sample in samples:
        sensible_fields = tuple(
            field
            for field in sample.fields
            if field.grain == "interval"
            and field.field_code == "surface_sensible_heat_flux_upward_w_m2"
            and field.interval_end_utc == sample.valid_at_utc
            and _intersects_flying_window(field.interval_start_utc, field.interval_end_utc, window)
        )
        thermal = _thermal_strength_result(sample)
        value = None if thermal.values is None else thermal.values[component_index]
        intervals.extend(
            IntervalValue(field.interval_start_utc or "", field.interval_end_utc or "", value)
            for field in sensible_fields
        )
    return tuple(intervals)


def _intersects_flying_window(
    interval_start_utc: str | None, interval_end_utc: str | None, window
) -> bool:
    """Exclude only a disjoint baseline; preserve malformed/overlapping evidence for validation."""

    if interval_start_utc is None or interval_end_utc is None:
        return True
    try:
        start = datetime.strptime(interval_start_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        end = datetime.strptime(interval_end_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        window_start = datetime.strptime(window.interval_start_utc, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        )
        window_end = datetime.strptime(window.interval_end_utc, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        )
    except ValueError:
        return True
    return start < window_end and end > window_start


def build_daily_neighbourhood_features(
    samples: tuple[SiteAlignedSample, ...],
    records: tuple[NeighbourhoodNodeRecord, ...],
    footprints: tuple[SamplingFootprint, ...],
    sites: tuple[SiteConfigSnapshot, ...],
    entries: tuple[FeaturePolicyEntry, ...],
    *,
    expected_instants_utc: tuple[str, ...],
) -> tuple[FeatureValue, ...]:
    """Fit complete S05 neighbourhood evidence once per hour, then reduce strictly."""

    values: list[FeatureValue] = []
    for entry in entries:
        if entry.feature_key not in {
            "neighbourhood_pressure_gradient_mean_pa_per_km",
            "neighbourhood_pressure_gradient_max_pa_per_km",
            "neighbourhood_low_level_divergence_mean_s_inverse",
            "neighbourhood_low_level_divergence_min_s_inverse",
        }:
            continue
        metric_index = 0 if "pressure_gradient" in entry.feature_key else 1
        reduction = strict_hourly_reduction(
            tuple(
                TimedValue(
                    sample.valid_at_utc,
                    _neighbourhood_metric_value(sample, records, footprints, sites, metric_index),
                )
                for sample in samples
            ),
            _window(expected_instants_utc),
            _reducer(entry),
        )
        values.append(
            _missing_feature(entry, reduction.missing_reason or "neighbourhood_feature_missing")
            if reduction.value is None
            else _derived_feature(entry, reduction.value)
        )
    return tuple(values)


def _neighbourhood_metric_value(
    sample: SiteAlignedSample,
    records: tuple[NeighbourhoodNodeRecord, ...],
    footprints: tuple[SamplingFootprint, ...],
    sites: tuple[SiteConfigSnapshot, ...],
    metric_index: int,
) -> float | None:
    matching_records = [
        item
        for item in records
        if item.site_id == sample.site_id
        and item.footprint_key == sample.neighbourhood_footprint_key
        and item.valid_at_utc == sample.valid_at_utc
    ]
    matching_footprints = [
        item
        for item in footprints
        if item.footprint_key == sample.neighbourhood_footprint_key
        and item.site_id == sample.site_id
        and item.purpose == "neighbourhood"
    ]
    matching_sites = [item for item in sites if item.site_id == sample.site_id]
    if len(matching_records) != 1 or len(matching_footprints) != 1 or len(matching_sites) != 1:
        return None
    record, footprint, site = matching_records[0], matching_footprints[0], matching_sites[0]
    pressure = _neighbourhood_field(record, MEAN_SEA_LEVEL_PRESSURE)
    wind_u = _neighbourhood_field(record, TEN_METRE_WIND_U)
    wind_v = _neighbourhood_field(record, TEN_METRE_WIND_V)
    if pressure is None or wind_u is None or wind_v is None:
        return None
    if not (len(pressure) == len(wind_u) == len(wind_v) == len(footprint.nodes)):
        return None
    try:
        metrics = fit_neighbourhood_metrics(
            site.latitude_deg,
            site.longitude_deg,
            tuple(
                NeighbourhoodObservation(
                    node_key=f"{node.row_index}:{node.column_index}",
                    latitude_deg=node.latitude_deg,
                    longitude_deg=node.longitude_deg,
                    mean_sea_level_pressure_pa=pressure[index],
                    wind_u_m_s=wind_u[index],
                    wind_v_m_s=wind_v[index],
                )
                for index, node in enumerate(footprint.nodes)
            ),
        )
    except (NeighbourhoodCoverageError, TypeError):
        return None
    return (
        metrics.pressure_gradient_pa_per_km
        if metric_index == 0
        else metrics.low_level_divergence_s_inverse
    )


def _neighbourhood_field(
    record: NeighbourhoodNodeRecord, selector: CanonicalFieldSelector
) -> tuple[float, ...] | None:
    try:
        field = resolve_canonical_field(record.fields, selector)
    except CanonicalSelectorError as error:
        raise CanonicalFeatureSelectionError(str(error)) from error
    if field is None or any(value is None or not isfinite(value) for value in field.values):
        return None
    return tuple(float(value) for value in field.values if value is not None)


def _point_hour_value(sample: SiteAlignedSample, entry: FeaturePolicyEntry) -> float | None:
    if entry.field_code == "wind_speed_m_s":
        u_value, v_value = (
            _surface_field(sample, TEN_METRE_WIND_U),
            _surface_field(sample, TEN_METRE_WIND_V),
        )
        return None if u_value is None or v_value is None else (u_value**2 + v_value**2) ** 0.5
    try:
        field = resolve_canonical_field(
            sample.fields, selector_for_point_feature(entry.field_code, entry.variant)
        )
    except CanonicalSelectorError as error:
        raise CanonicalFeatureSelectionError(str(error)) from error
    return _available_value(field) if field is not None else None


def build_profile_layer(
    samples: tuple[SiteAlignedSample, ...],
    layer: FeatureLayerPolicy,
    entries: tuple[FeaturePolicyEntry, ...],
    *,
    expected_instants_utc: tuple[str, ...],
) -> FeatureLayer:
    """Build one strict daily AGL layer from complete, source-neutral hourly evidence."""

    computed: dict[str, FeatureValue] = {}
    for entry in entries:
        if entry.feature_key == "wind_direction_mean_degrees_from_north":
            continue
        computed[entry.feature_key] = _profile_feature(samples, layer, entry, expected_instants_utc)
    fields: list[FeatureValue] = []
    for entry in entries:
        if entry.feature_key != "wind_direction_mean_degrees_from_north":
            fields.append(computed[entry.feature_key])
            continue
        u_value = computed["wind_u_mean_m_s"].canonical_value
        v_value = computed["wind_v_mean_m_s"].canonical_value
        if u_value is None or v_value is None:
            fields.append(_missing_feature(entry, "wind_components_missing"))
        else:
            direction = meteorological_direction_from_uv(u_value, v_value)
            fields.append(
                _missing_feature(entry, "wind_direction_undefined")
                if direction is None
                else _derived_feature(entry, direction)
            )
    return FeatureLayer(
        layer_base_agl_m=layer.layer_base_agl_m,
        layer_top_agl_m=layer.layer_top_agl_m,
        fields=tuple(fields),
    )


def _profile_feature(
    samples: tuple[SiteAlignedSample, ...],
    layer: FeatureLayerPolicy,
    entry: FeaturePolicyEntry,
    expected_instants_utc: tuple[str, ...],
) -> FeatureValue:
    if entry.feature_key in {"vertical_velocity_mean_pa_s", "vertical_velocity_min_pa_s"} and (
        layer.layer_base_agl_m == 0.0
    ):
        return _missing_feature(entry, "lower_boundary_not_bracketed")
    hourly = tuple(
        TimedValue(
            sample.valid_at_utc,
            _profile_hour_value(sample, layer, entry.feature_key).value,
        )
        for sample in samples
    )
    reduction = strict_hourly_reduction(hourly, _window(expected_instants_utc), _reducer(entry))
    if reduction.value is None:
        return _missing_feature(entry, reduction.missing_reason or "profile_feature_missing")
    return _derived_feature(entry, reduction.value)


def _profile_hour_value(
    sample: SiteAlignedSample, layer: FeatureLayerPolicy, feature_key: str
) -> FeatureResult:
    try:
        if feature_key.startswith("temperature_lapse_rate"):
            return FeatureResult(
                endpoint_lapse_rate_k_per_km(
                    _temperature_profile(sample, layer),
                    _effective_lower(layer, "temperature"),
                    layer.layer_top_agl_m,
                )
            )
        if feature_key == "relative_humidity_mean_percent":
            return FeatureResult(
                trapezoidal_mean(
                    _scalar_profile(
                        sample, "relative_humidity_percent", layer, TWO_METRE_RELATIVE_HUMIDITY, 2.0
                    ),
                    _effective_lower(layer, "humidity"),
                    layer.layer_top_agl_m,
                )
            )
        if feature_key == "specific_humidity_mean_kg_per_kg":
            return FeatureResult(
                trapezoidal_mean(
                    _scalar_profile(
                        sample,
                        "specific_humidity_kg_per_kg",
                        layer,
                        TWO_METRE_SPECIFIC_HUMIDITY,
                        2.0,
                    ),
                    _effective_lower(layer, "humidity"),
                    layer.layer_top_agl_m,
                )
            )
        if feature_key in {"wind_u_mean_m_s", "wind_v_mean_m_s"}:
            field = "wind_u_m_s" if feature_key == "wind_u_mean_m_s" else "wind_v_m_s"
            selector = TEN_METRE_WIND_U if field == "wind_u_m_s" else TEN_METRE_WIND_V
            return FeatureResult(
                trapezoidal_mean(
                    _scalar_profile(sample, field, layer, selector, 10.0),
                    _effective_lower(layer, "wind"),
                    layer.layer_top_agl_m,
                )
            )
        if feature_key in {"wind_speed_mean_m_s", "wind_speed_max_m_s"}:
            speed = scalar_speed_profile(
                _scalar_profile(sample, "wind_u_m_s", layer, TEN_METRE_WIND_U, 10.0),
                _scalar_profile(sample, "wind_v_m_s", layer, TEN_METRE_WIND_V, 10.0),
            )
            lower = _effective_lower(layer, "wind")
            if feature_key == "wind_speed_mean_m_s":
                return FeatureResult(trapezoidal_mean(speed, lower, layer.layer_top_agl_m))
            return FeatureResult(
                max(point.value for point in bounded_profile(speed, lower, layer.layer_top_agl_m))
            )
        if feature_key.startswith("wind_shear_"):
            return FeatureResult(
                bulk_vector_shear_m_s_per_km(
                    _scalar_profile(sample, "wind_u_m_s", layer, TEN_METRE_WIND_U, 10.0),
                    _scalar_profile(sample, "wind_v_m_s", layer, TEN_METRE_WIND_V, 10.0),
                    _effective_lower(layer, "wind"),
                    layer.layer_top_agl_m,
                )
            )
        if feature_key.startswith("vertical_velocity_"):
            omega = _scalar_profile(sample, "vertical_velocity_pa_s", layer, None, None)
            if feature_key == "vertical_velocity_mean_pa_s":
                return FeatureResult(
                    trapezoidal_mean(omega, layer.layer_base_agl_m, layer.layer_top_agl_m)
                )
            return FeatureResult(
                min(
                    point.value
                    for point in bounded_profile(
                        omega, layer.layer_base_agl_m, layer.layer_top_agl_m
                    )
                )
            )
    except CanonicalFeatureSelectionError:
        raise
    except FeatureBuildError as error:
        return FeatureResult(None, str(error))
    except VerticalCoverageError:
        return FeatureResult(None, "profile_boundary_not_bracketed")
    raise FeatureBuildError(f"Unsupported profile policy key: {feature_key}")


def _temperature_profile(
    sample: SiteAlignedSample, layer: FeatureLayerPolicy
) -> tuple[VerticalPoint, ...]:
    return _scalar_profile(sample, "air_temperature_k", layer, TWO_METRE_TEMPERATURE, 2.0)


def _scalar_profile(
    sample: SiteAlignedSample,
    field_code: str,
    layer: FeatureLayerPolicy,
    surface_selector: CanonicalFieldSelector | None,
    surface_anchor_agl_m: float | None,
) -> tuple[VerticalPoint, ...]:
    if (surface_selector is None) != (surface_anchor_agl_m is None):
        raise FeatureBuildError(
            "Profile surface selector and anchor height must be supplied together."
        )
    points: list[VerticalPoint] = []
    lower = _effective_lower(layer, "wind" if surface_anchor_agl_m == 10.0 else "humidity")
    if surface_anchor_agl_m is not None and layer.layer_base_agl_m == 0.0:
        assert surface_selector is not None
        surface = _surface_field(sample, surface_selector)
        if surface is None:
            raise FeatureBuildError("surface_anchor_missing")
        points.append(VerticalPoint(surface_anchor_agl_m, surface))
    for profile in sample.profile_levels:
        height = profile.level_height_agl_m
        if not isfinite(height):
            raise FeatureBuildError("profile_height_missing")
        field = _profile_field(profile.fields, field_code)
        if field is None:
            if lower <= height <= layer.layer_top_agl_m:
                raise FeatureBuildError("profile_field_missing")
            continue
        points.append(VerticalPoint(height, field))
    return tuple(sorted(points, key=lambda point: point.height_agl_m))


def _surface_field(sample: SiteAlignedSample, selector: CanonicalFieldSelector) -> float | None:
    try:
        field = resolve_canonical_field(sample.fields, selector)
    except CanonicalSelectorError as error:
        raise CanonicalFeatureSelectionError(str(error)) from error
    return _available_value(field) if field is not None else None


def _profile_field(fields: tuple[SampledField, ...], field_code: str) -> float | None:
    matches = [field for field in fields if field.field_code == field_code]
    if len(matches) != 1:
        return None
    return _available_value(matches[0])


def _available_value(field: SampledField) -> float | None:
    value = field.canonical_value
    return value if value is not None and field.quality_state in {"real", "derived"} else None


def _effective_lower(layer: FeatureLayerPolicy, family: str) -> float:
    if layer.layer_base_agl_m != 0.0:
        return layer.layer_base_agl_m
    return 10.0 if family == "wind" else 2.0


def _window(expected_instants_utc: tuple[str, ...]):
    from datetime import date

    from .aggregation import FlyingWindow

    if len(expected_instants_utc) != 11 or len(expected_instants_utc) != len(
        set(expected_instants_utc)
    ):
        raise FeatureBuildError("S07 requires exactly eleven unique flying-window instants.")
    return FlyingWindow(
        local_date=date.fromisoformat(expected_instants_utc[0][:10]),
        expected_instants_utc=expected_instants_utc,
        interval_start_utc=expected_instants_utc[0],
        interval_end_utc=expected_instants_utc[-1],
    )


def _reducer(entry: FeaturePolicyEntry) -> Callable[[tuple[float, ...]], float]:
    if entry.statistic == "mean":
        return lambda values: sum(values) / len(values)
    if entry.statistic == "min":
        return min
    if entry.statistic == "max":
        return max
    raise FeatureBuildError(f"Profile feature has unsupported statistic: {entry.statistic}")


def _source_feature(entry: FeaturePolicyEntry, value: float) -> FeatureValue:
    from ...atmosphere.catalogue import load_catalogue

    return FeatureValue(
        feature_key=entry.feature_key,
        field_code=entry.field_code,
        canonical_unit=load_catalogue().field_unit(entry.field_code),
        variant=entry.variant,
        statistic=entry.statistic,
        canonical_value=value,
        quality_state="real",
        derivation_method=entry.derivation_method,
        derivation_version=entry.derivation_method,
        input_field_codes=(entry.field_code,),
    )


def _derived_feature(entry: FeaturePolicyEntry, value: float) -> FeatureValue:
    from ...atmosphere.catalogue import load_catalogue

    return FeatureValue(
        feature_key=entry.feature_key,
        field_code=entry.field_code,
        canonical_unit=load_catalogue().field_unit(entry.field_code),
        variant=entry.variant,
        statistic=entry.statistic,
        canonical_value=value,
        quality_state="derived",
        derivation_method=entry.derivation_method,
        derivation_version=entry.derivation_method,
        input_field_codes=(entry.field_code,),
    )


def _unsupported_feature(entry: FeaturePolicyEntry, reason: str) -> FeatureValue:
    from ...atmosphere.catalogue import load_catalogue

    return FeatureValue(
        feature_key=entry.feature_key,
        field_code=entry.field_code,
        canonical_unit=load_catalogue().field_unit(entry.field_code),
        variant=entry.variant,
        statistic=entry.statistic,
        canonical_value=None,
        quality_state="unsupported",
        missing_reason=reason,
        derivation_method=entry.derivation_method,
        derivation_version=entry.derivation_method,
        input_field_codes=(entry.field_code,),
    )


def _missing_feature(entry: FeaturePolicyEntry, reason: str) -> FeatureValue:
    from ...atmosphere.catalogue import load_catalogue

    return FeatureValue(
        feature_key=entry.feature_key,
        field_code=entry.field_code,
        canonical_unit=load_catalogue().field_unit(entry.field_code),
        variant=entry.variant,
        statistic=entry.statistic,
        canonical_value=None,
        quality_state="missing",
        missing_reason=reason,
        derivation_method=entry.derivation_method,
        derivation_version=entry.derivation_method,
        input_field_codes=(entry.field_code,),
    )
