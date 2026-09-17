"""Source-aware IGRA validation: classify evidence without profile repair or reordering."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from .models import (
    CanonicalSounding,
    CanonicalSoundingLevel,
    ProviderDerivedSoundingLevel,
    ProviderDerivedSoundingParameters,
)


@dataclass(frozen=True)
class IgraValidationResult:
    accepted_soundings: tuple[CanonicalSounding, ...]
    quarantined_soundings: tuple[CanonicalSounding, ...]
    accepted_levels: tuple[CanonicalSoundingLevel, ...]
    excluded_levels: tuple[dict[str, object], ...]
    invalid_values: tuple[dict[str, object], ...]
    accepted_provider_parameters: tuple[ProviderDerivedSoundingParameters, ...]
    accepted_provider_levels: tuple[ProviderDerivedSoundingLevel, ...]
    rejected_derived_associations: tuple[dict[str, object], ...]
    missing_evidence: tuple[dict[str, object], ...]
    report: dict[str, object]


def validate(
    soundings: tuple[CanonicalSounding, ...],
    levels: tuple[CanonicalSoundingLevel, ...],
    provider_parameters: tuple[ProviderDerivedSoundingParameters, ...],
    provider_levels: tuple[ProviderDerivedSoundingLevel, ...],
    *,
    requested_dates_utc: tuple[str, ...],
    requested_nominal_hours: tuple[int, ...],
) -> IgraValidationResult:
    """Validate hard ranges/identity/usefulness without interpolation or value substitution."""

    by_sounding: dict[str, list[CanonicalSoundingLevel]] = defaultdict(list)
    for level in levels:
        normalized, _invalid = _invalidated_level(level)
        by_sounding[normalized.sounding_key].append(normalized)
    invalid_values = [
        item
        for values in by_sounding.values()
        for level in values
        for item in _invalid_evidence(level)
    ]
    duplicates = {
        key for key, count in Counter(item.sounding_key for item in soundings).items() if count > 1
    }
    accepted: list[CanonicalSounding] = []
    quarantined: list[CanonicalSounding] = []
    accepted_levels: list[CanonicalSoundingLevel] = []
    excluded: list[dict[str, object]] = []
    reasons: Counter[str] = Counter()
    for sounding in soundings:
        candidates = by_sounding.get(sounding.sounding_key, [])
        usable: list[CanonicalSoundingLevel] = []
        for level in candidates:
            if level.pressure_pa is None and level.geopotential_height_msl_m is None:
                excluded.append(
                    {
                        "sounding_key": sounding.sounding_key,
                        "ordinal": level.ordinal,
                        "reason": "no_vertical_coordinate",
                    }
                )
                continue
            if not _has_measurement(level):
                excluded.append(
                    {
                        "sounding_key": sounding.sounding_key,
                        "ordinal": level.ordinal,
                        "reason": "no_usable_measurement",
                    }
                )
                continue
            usable.append(level)
        reason = _quarantine_reason(sounding, usable, duplicates)
        if reason is not None:
            quarantined.append(sounding)
            reasons[reason] += 1
            continue
        accepted.append(sounding)
        accepted_levels.extend(usable)
    accepted_keys = {item.sounding_key for item in accepted}
    associations, association_rejections = _derived_associations(
        provider_parameters, provider_levels, accepted_keys
    )
    missing = _missing_evidence(
        soundings,
        provider_parameters,
        requested_dates_utc=requested_dates_utc,
        requested_nominal_hours=requested_nominal_hours,
    )
    report = {
        "soundings_seen": len(soundings),
        "soundings_accepted": len(accepted),
        "soundings_quarantined": len(quarantined),
        "levels_seen": len(levels),
        "levels_accepted": len(accepted_levels),
        "levels_excluded": len(excluded),
        "invalid_values": len(invalid_values),
        "quarantine_reasons": dict(sorted(reasons.items())),
        "missing_evidence": len(missing),
        "rejected_derived_associations": len(association_rejections),
    }
    return IgraValidationResult(
        accepted_soundings=tuple(
            sorted(accepted, key=lambda item: (item.nominal_at_utc or "", item.record_sha256))
        ),
        quarantined_soundings=tuple(
            sorted(quarantined, key=lambda item: (item.nominal_at_utc or "", item.record_sha256))
        ),
        accepted_levels=tuple(
            sorted(accepted_levels, key=lambda item: (item.sounding_key, item.ordinal))
        ),
        excluded_levels=tuple(
            sorted(excluded, key=lambda item: (str(item["sounding_key"]), int(item["ordinal"])))
        ),
        invalid_values=tuple(
            sorted(
                invalid_values,
                key=lambda item: (
                    str(item["sounding_key"]),
                    int(item["ordinal"]),
                    str(item["field"]),
                ),
            )
        ),
        accepted_provider_parameters=associations[0],
        accepted_provider_levels=associations[1],
        rejected_derived_associations=tuple(
            sorted(
                association_rejections,
                key=lambda item: (str(item["sounding_key"]), str(item["reason"])),
            )
        ),
        missing_evidence=tuple(
            sorted(
                missing,
                key=lambda item: (
                    str(item["date_utc"]),
                    str(item.get("hour_utc", "")),
                    str(item["reason"]),
                ),
            )
        ),
        report=report,
    )


def _invalidated_level(
    level: CanonicalSoundingLevel,
) -> tuple[CanonicalSoundingLevel, tuple[dict[str, object], ...]]:
    updates: dict[str, object] = {}
    provenance = {name: dict(value) for name, value in level.provenance.items()}
    checks = {
        "pressure_pa": lambda value: value > 0,
        "relative_humidity_percent": lambda value: 0 <= value <= 100,
        "wind_speed_m_s": lambda value: value >= 0,
        "wind_direction_degrees": lambda value: 0 <= value <= 360,
    }
    invalid: list[dict[str, object]] = []
    for field, predicate in checks.items():
        value = getattr(level, field)
        if value is not None and not predicate(value):
            updates[field] = None
            provenance[field] = {
                **provenance.get(field, {}),
                "quality_state": "invalid_payload",
                "invalid_reason": "hard_range",
            }
            invalid.append(
                {
                    "sounding_key": level.sounding_key,
                    "ordinal": level.ordinal,
                    "field": field,
                    "native_value": value,
                    "reason": "hard_range",
                }
            )
    if updates:
        updates["provenance"] = provenance
        return level.model_copy(update=updates), tuple(invalid)
    return level, ()


def _invalid_evidence(level: CanonicalSoundingLevel) -> tuple[dict[str, object], ...]:
    evidence: list[dict[str, object]] = []
    for field, provenance in level.provenance.items():
        if provenance.get("quality_state") == "invalid_payload":
            evidence.append(
                {
                    "sounding_key": level.sounding_key,
                    "ordinal": level.ordinal,
                    "field": field,
                    "reason": provenance.get("invalid_reason", "invalid_payload"),
                }
            )
    return tuple(evidence)


def _has_measurement(level: CanonicalSoundingLevel) -> bool:
    return any(
        value is not None
        for value in (
            level.temperature_k,
            level.dew_point_k,
            level.relative_humidity_percent,
            level.wind_speed_m_s,
            level.wind_direction_degrees,
            level.u_wind_m_s,
            level.v_wind_m_s,
        )
    )


def _quarantine_reason(
    sounding: CanonicalSounding,
    usable: list[CanonicalSoundingLevel],
    duplicates: set[str],
) -> str | None:
    if sounding.nominal_at_utc is None or sounding.nominal_hour_utc is None:
        return "missing_nominal_time"
    if sounding.sounding_key in duplicates:
        return "duplicate_logical_identity"
    if sounding.latitude_deg is not None and not -90 <= sounding.latitude_deg <= 90:
        return "invalid_latitude"
    if sounding.longitude_deg is not None and not -180 <= sounding.longitude_deg <= 180:
        return "invalid_longitude"
    if not usable:
        return "no_usable_vertical_coordinate"
    thermodynamic = any(
        level.temperature_k is not None
        or level.dew_point_k is not None
        or level.relative_humidity_percent is not None
        for level in usable
    )
    wind = any(
        level.wind_speed_m_s is not None and level.wind_direction_degrees is not None
        for level in usable
    )
    if not thermodynamic and not wind:
        return "no_usable_profile_family"
    return None


def _derived_associations(
    parameters: tuple[ProviderDerivedSoundingParameters, ...],
    levels: tuple[ProviderDerivedSoundingLevel, ...],
    accepted_keys: set[str],
) -> tuple[
    tuple[tuple[ProviderDerivedSoundingParameters, ...], tuple[ProviderDerivedSoundingLevel, ...]],
    list[dict[str, object]],
]:
    counts = Counter(item.sounding_key for item in parameters)
    rejected: list[dict[str, object]] = []
    accepted_parameters: list[ProviderDerivedSoundingParameters] = []
    for parameter in parameters:
        if parameter.sounding_key not in accepted_keys:
            rejected.append(
                {"sounding_key": parameter.sounding_key, "reason": "unmatched_or_quarantined_raw"}
            )
        elif counts[parameter.sounding_key] > 1:
            rejected.append(
                {"sounding_key": parameter.sounding_key, "reason": "duplicate_derived_identity"}
            )
        else:
            accepted_parameters.append(parameter)
    accepted_parameter_keys = {item.sounding_key for item in accepted_parameters}
    accepted_levels = tuple(item for item in levels if item.sounding_key in accepted_parameter_keys)
    return (tuple(accepted_parameters), accepted_levels), rejected


def _missing_evidence(
    soundings: tuple[CanonicalSounding, ...],
    parameters: tuple[ProviderDerivedSoundingParameters, ...],
    *,
    requested_dates_utc: tuple[str, ...],
    requested_nominal_hours: tuple[int, ...],
) -> list[dict[str, object]]:
    observed = {(item.nominal_date_utc, item.nominal_hour_utc) for item in soundings}
    with_derived = {item.sounding_key for item in parameters}
    evidence: list[dict[str, object]] = []
    if requested_nominal_hours:
        for requested_date in requested_dates_utc:
            for requested_hour in requested_nominal_hours:
                if (requested_date, requested_hour) not in observed:
                    evidence.append(
                        {
                            "date_utc": requested_date,
                            "hour_utc": requested_hour,
                            "reason": "no_observation_for_selection",
                        }
                    )
    else:
        for requested_date in requested_dates_utc:
            if not any(date == requested_date for date, _hour in observed):
                evidence.append(
                    {"date_utc": requested_date, "reason": "no_observation_for_selection"}
                )
    for sounding in soundings:
        if sounding.sounding_key not in with_derived:
            evidence.append(
                {
                    "date_utc": sounding.nominal_date_utc,
                    "hour_utc": sounding.nominal_hour_utc,
                    "reason": "missing_provider_derived_record",
                }
            )
    return evidence
