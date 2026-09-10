"""Source-neutral S07 feature reductions over validated canonical site samples."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite

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
    """One intermediate feature result before it is materialized as a v2 contract value."""

    value: float | None
    missing_reason: str | None = None


class FeatureBuildError(ValueError):
    """Validated evidence cannot be reduced under the S07 feature policy."""


def build_daily_point_features(
    samples: tuple[SiteAlignedSample, ...],
    entries: tuple[FeaturePolicyEntry, ...],
    *,
    expected_instants_utc: tuple[str, ...],
) -> tuple[FeatureValue, ...]:
    """Reduce strict instantaneous point/provider evidence; interval and neighbourhood facts stay separate."""
    deferred = {
        "precipitation_total_mm",
        "precipitation_max_hourly_mm",
        "shortwave_radiation_mean_w_m2",
        "shortwave_radiation_max_w_m2",
        "surface_sensible_heat_flux_mean_w_m2",
        "surface_latent_heat_flux_mean_w_m2",
        "neighbourhood_pressure_gradient_mean_pa_per_km",
        "neighbourhood_pressure_gradient_max_pa_per_km",
        "neighbourhood_low_level_divergence_mean_s_inverse",
        "neighbourhood_low_level_divergence_min_s_inverse",
    }
    computed: dict[str, FeatureValue] = {}
    for entry in entries:
        if (
            entry.feature_key in deferred
            or entry.feature_key == "wind_direction_10m_mean_degrees_from_north"
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
    for entry in entries:
        intervals = tuple(
            IntervalValue(
                field.interval_start_utc or "",
                field.interval_end_utc or "",
                _available_value(field),
            )
            for sample in samples
            for field in sample.fields
            if field.grain == "interval" and field.field_code == entry.field_code
        )
        if entry.feature_key == "precipitation_total_mm":
            result = interval_total(intervals, window)
        elif entry.feature_key == "precipitation_max_hourly_mm":
            result = hourly_amount_maximum(intervals, window)
        elif entry.feature_key in {
            "shortwave_radiation_mean_w_m2",
            "surface_sensible_heat_flux_mean_w_m2",
            "surface_latent_heat_flux_mean_w_m2",
        }:
            result = interval_weighted_mean(intervals, window)
        elif entry.feature_key == "shortwave_radiation_max_w_m2":
            result = interval_maximum(intervals, window)
        else:
            continue
        values.append(
            _missing_feature(entry, result.missing_reason or "interval_feature_missing")
            if result.value is None
            else _derived_feature(entry, result.value)
        )
    return tuple(values)


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
    pressure = _neighbourhood_field(record, "air_pressure_pa", "mean_sea_level")
    wind_u = _neighbourhood_field(record, "wind_u_m_s", None)
    wind_v = _neighbourhood_field(record, "wind_v_m_s", None)
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
    record: NeighbourhoodNodeRecord, field_code: str, dimension: str | None
) -> tuple[float, ...] | None:
    matches = [
        field
        for field in record.fields
        if field.field_code == field_code and field.dimension == dimension and field.grain == "surface"
    ]
    if len(matches) != 1 or any(value is None or not isfinite(value) for value in matches[0].values):
        return None
    return tuple(float(value) for value in matches[0].values if value is not None)
def _point_hour_value(sample: SiteAlignedSample, entry: FeaturePolicyEntry) -> float | None:
    if entry.field_code == "wind_speed_m_s":
        u_value, v_value = (
            _surface_field(sample, "wind_u_m_s"),
            _surface_field(sample, "wind_v_m_s"),
        )
        return None if u_value is None or v_value is None else (u_value**2 + v_value**2) ** 0.5
    dimension = {
        "2m": None,
        "10m": None,
        "surface": "surface",
        "mean_sea_level": "mean_sea_level",
        "surface_parcel": "surface",
        "total": "total",
        "low": "low",
        "mid": "mid",
        "high": "high",
    }.get(entry.variant)
    matches = [
        field
        for field in sample.fields
        if field.field_code == entry.field_code
        and field.dimension == dimension
        and (entry.variant != "surface_parcel" or field.grain == "convection")
    ]
    return _available_value(matches[0]) if len(matches) == 1 else None


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
                    _scalar_profile(sample, "relative_humidity_percent", layer, 2.0),
                    _effective_lower(layer, "humidity"),
                    layer.layer_top_agl_m,
                )
            )
        if feature_key == "specific_humidity_mean_kg_per_kg":
            return FeatureResult(
                trapezoidal_mean(
                    _scalar_profile(sample, "specific_humidity_kg_per_kg", layer, 2.0),
                    _effective_lower(layer, "humidity"),
                    layer.layer_top_agl_m,
                )
            )
        if feature_key in {"wind_u_mean_m_s", "wind_v_mean_m_s"}:
            field = "wind_u_m_s" if feature_key == "wind_u_mean_m_s" else "wind_v_m_s"
            return FeatureResult(
                trapezoidal_mean(
                    _scalar_profile(sample, field, layer, 10.0),
                    _effective_lower(layer, "wind"),
                    layer.layer_top_agl_m,
                )
            )
        if feature_key in {"wind_speed_mean_m_s", "wind_speed_max_m_s"}:
            speed = scalar_speed_profile(
                _scalar_profile(sample, "wind_u_m_s", layer, 10.0),
                _scalar_profile(sample, "wind_v_m_s", layer, 10.0),
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
                    _scalar_profile(sample, "wind_u_m_s", layer, 10.0),
                    _scalar_profile(sample, "wind_v_m_s", layer, 10.0),
                    _effective_lower(layer, "wind"),
                    layer.layer_top_agl_m,
                )
            )
        if feature_key.startswith("vertical_velocity_"):
            omega = _scalar_profile(sample, "vertical_velocity_pa_s", layer, None)
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
    except FeatureBuildError as error:
        return FeatureResult(None, str(error))
    except VerticalCoverageError:
        return FeatureResult(None, "profile_boundary_not_bracketed")
    raise FeatureBuildError(f"Unsupported profile policy key: {feature_key}")


def _temperature_profile(
    sample: SiteAlignedSample, layer: FeatureLayerPolicy
) -> tuple[VerticalPoint, ...]:
    return _scalar_profile(sample, "air_temperature_k", layer, 2.0)


def _scalar_profile(
    sample: SiteAlignedSample,
    field_code: str,
    layer: FeatureLayerPolicy,
    surface_anchor_agl_m: float | None,
) -> tuple[VerticalPoint, ...]:
    points: list[VerticalPoint] = []
    lower = _effective_lower(layer, "wind" if surface_anchor_agl_m == 10.0 else "humidity")
    if surface_anchor_agl_m is not None and layer.layer_base_agl_m == 0.0:
        surface = _surface_field(sample, field_code)
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


def _surface_field(sample: SiteAlignedSample, field_code: str) -> float | None:
    matches = [field for field in sample.fields if field.field_code == field_code]
    if len(matches) != 1:
        return None
    return _available_value(matches[0])


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
