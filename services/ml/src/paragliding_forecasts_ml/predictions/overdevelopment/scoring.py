"""One daily score and explicit critical overrides from exact-window evidence."""

from datetime import datetime
from zoneinfo import ZoneInfo

from ...ingestion.weather.serialization import canonical_json_bytes, sha256_bytes
from .models import FIELD_UNITS, FieldKey, ForecastDay, Observation
from .policy import Policy


def _clock(timestamp: str) -> str:
    return datetime.fromisoformat(timestamp).astimezone(ZoneInfo("Europe/Sofia")).strftime("%H:%M")


def _interval(observation: Observation) -> str:
    assert observation.interval_end_utc is not None
    return f"{_clock(observation.valid_at_utc)}–{_clock(observation.interval_end_utc)} Sofia"


def _evidence(observation: Observation) -> dict:
    return observation.model_dump(
        include={"key", "valid_at_utc", "interval_end_utc", "unit", "value"}
    )


def _override_results(
    day: ForecastDay,
    by_field: dict[FieldKey, tuple[Observation, ...]],
    rain_total: float,
    rain_complete: bool,
    policy: Policy,
) -> tuple[list[dict], list[dict]]:
    overrides = []
    reasons = []
    rain_hours = [
        rain
        for rain in by_field["rain"]
        if rain.value is not None and rain.value >= policy.override_hourly_rain_mm
    ]
    rain_evidence = [_evidence(rain) for rain in rain_hours]
    if rain_total >= policy.override_total_rain_mm:
        rain_evidence.append(
            {
                "key": "rain_total",
                "valid_at_utc": day.window_start_utc,
                "interval_end_utc": day.window_end_utc,
                "unit": "mm",
                "value": rain_total,
                "lower_bound": not rain_complete,
            }
        )
    if rain_evidence:
        if rain_hours:
            peak = rain_hours[0]
            text = f"Forecast precipitation of {peak.value} mm at {_interval(peak)}."
        else:
            qualifier = "" if rain_complete else "at least "
            text = f"Forecast precipitation of {qualifier}{rain_total} mm in the flying window."
        overrides.append({"code": "high_precipitation", "evidence": rain_evidence})
        reasons.append(
            {"code": "high_precipitation", "message": text, "evidence": rain_evidence[0]}
        )

    convective = [
        (rain, cape, cin)
        for rain, cape, cin in zip(by_field["rain"], by_field["cape"], by_field["cin"], strict=True)
        if rain.value is not None
        and cape.value is not None
        and cin.value is not None
        and rain.value >= policy.override_convective_rain_mm
        and cape.value >= policy.override_convective_cape_j_per_kg
        and cin.value <= policy.override_convective_cin_j_per_kg
    ]
    if convective:
        evidence = [[_evidence(observation) for observation in group] for group in convective]
        rain, cape, cin = convective[0]
        overrides.append({"code": "strong_convective_signal", "evidence": evidence})
        reasons.append(
            {
                "code": "strong_convective_signal",
                "message": (
                    f"Convective signal at {_interval(rain)} with CAPE {cape.value} J/kg, "
                    f"CIN magnitude {cin.value} J/kg and precipitation {rain.value} mm."
                ),
                "evidence": evidence[0],
            }
        )

    winds = [
        wind
        for wind in by_field["wind"]
        if wind.value is not None and wind.value > policy.override_wind_m_s
    ]
    if winds:
        peak = max(winds, key=lambda wind: _value(wind))
        overrides.append(
            {"code": "strong_near_surface_wind", "evidence": [_evidence(wind) for wind in winds]}
        )
        reasons.append(
            {
                "code": "strong_near_surface_wind",
                "message": (
                    f"Forecast 10 m wind speed of {peak.value} m/s "
                    f"at {_clock(peak.valid_at_utc)} Sofia."
                ),
                "evidence": _evidence(peak),
            }
        )
    return overrides, reasons


def _value(observation: Observation) -> float:
    assert observation.value is not None
    return observation.value


def _instability(cape: Observation, cin: Observation, policy: Policy) -> float:
    cape_factor = policy.cape.apply(_value(cape))
    if cape_factor == 0:
        return 0.0
    return cape_factor * (1 - policy.cin_discount * policy.cin.apply(_value(cin)))


def _contributions(
    day: ForecastDay,
    by_field: dict[FieldKey, tuple[Observation, ...]],
    rain_total: float,
    policy: Policy,
) -> list[dict]:
    rain_peak = max(by_field["rain"], key=_value)
    peak_factor = policy.rain_peak.apply(_value(rain_peak))
    total_factor = policy.rain_total.apply(rain_total)
    if peak_factor >= total_factor:
        rain_text = (
            f"Peak forecast precipitation of {rain_peak.value} mm at {_interval(rain_peak)}."
        )
        rain_evidence = _evidence(rain_peak)
    else:
        rain_text = f"Forecast precipitation of {rain_total} mm across the flying window."
        rain_evidence = {
            "key": "rain_total",
            "value": rain_total,
            "unit": "mm",
            "valid_at_utc": day.window_start_utc,
            "interval_end_utc": day.window_end_utc,
        }
    cape, cin = max(
        zip(by_field["cape"], by_field["cin"], strict=True),
        key=lambda pair: _instability(*pair, policy),
    )
    instability_points = policy.instability_weight * _instability(cape, cin, policy)
    low_cloud = sum(map(_value, by_field["low_cloud"])) / len(by_field["low_cloud"])
    humidity = sum(map(_value, by_field["humidity"])) / len(by_field["humidity"])
    cloud_factor = policy.low_cloud.apply(low_cloud) * (
        1 - policy.humidity_weight + policy.humidity_weight * policy.humidity.apply(humidity)
    )
    return [
        {
            "code": "precipitation",
            "points": policy.rain_weight * max(peak_factor, total_factor),
            "message": rain_text,
            "evidence": rain_evidence,
        },
        {
            "code": "instability",
            "points": instability_points,
            "message": (
                f"Surface CAPE {cape.value} J/kg and CIN magnitude {cin.value} J/kg "
                f"at {_clock(cape.valid_at_utc)} Sofia."
                if instability_points
                else "Surface instability contributed zero points."
            ),
            "evidence": [_evidence(cape), _evidence(cin)],
        },
        {
            "code": "moist_low_cloud",
            "points": policy.cloud_weight * cloud_factor,
            "message": (
                f"Mean low-cloud cover {low_cloud:.2f}% and 2 m RH {humidity:.2f}% "
                "in the flying window."
            ),
            "evidence": {
                "mean_low_cloud_percent": low_cloud,
                "mean_humidity_percent": humidity,
                "valid_at_utc": day.window_start_utc,
                "interval_end_utc": day.window_end_utc,
            },
        },
    ]


def _score_level(score: float, policy: Policy) -> str:
    if score >= policy.high_threshold:
        return "high"
    if score >= policy.medium_threshold:
        return "medium"
    return "low"


def evaluate_day(day: ForecastDay, policy: Policy, policy_sha256: str) -> dict:
    """Classify the site-day and keep enough evidence to explain each outcome."""
    by_field = {
        key: tuple(item for item in day.observations if item.key == key) for key in FIELD_UNITS
    }
    cape_at = {item.valid_at_utc: item.value for item in by_field["cape"]}
    gaps = []
    for item in day.observations:
        if item.value is not None:
            continue
        cape = cape_at.get(item.valid_at_utc)
        optional_cin = item.key == "cin" and (cape is None or cape <= policy.cape.lower)
        gaps.append(
            {
                "key": item.key,
                "valid_at_utc": item.valid_at_utc,
                "interval_end_utc": item.interval_end_utc,
                "missing_reason": item.missing_reason,
                "required": not optional_cin,
            }
        )
    coverage = {
        "complete": not any(gap["required"] for gap in gaps),
        "fields": {
            key: {
                "expected": len(items),
                "valid": sum(item.value is not None for item in items),
            }
            for key, items in by_field.items()
        },
        "gaps": gaps,
    }
    rain_total = sum(item.value for item in by_field["rain"] if item.value is not None)
    overrides, reasons = _override_results(
        day, by_field, rain_total, not any(gap["key"] == "rain" for gap in gaps), policy
    )
    score = None
    level = None
    contributions = None
    if coverage["complete"]:
        contributions = _contributions(day, by_field, rain_total, policy)
        score = min(100.0, sum(item["points"] for item in contributions))
        level = _score_level(score, policy)
        if not overrides:
            reasons = sorted(
                (item for item in contributions if item["points"] > 0),
                key=lambda item: -item["points"],
            ) or [
                {
                    "code": "weak_modelled_signals",
                    "message": "Weak signals in the modelled flying window.",
                }
            ]
    if overrides:
        level = "high"
    if level is None:
        reasons = [
            {
                "code": "insufficient_weather_evidence",
                "message": "Required forecast evidence is missing in the flying window.",
                "evidence": gaps,
            }
        ]
    return {
        **day.model_dump(mode="json", exclude={"observations", "hourly_source_ready_at_utc"}),
        "input_sha256": sha256_bytes(canonical_json_bytes(day)),
        "risk_level": level,
        "score": score,
        "data_status": "baseline" if level is not None else "missing",
        "confidence": "low" if level is not None else None,
        "validation_status": "not_observationally_calibrated",
        "coverage": coverage,
        "contributions": contributions,
        "overrides": overrides,
        "reasons": reasons,
        "policy_version": policy.policy_version,
        "policy_sha256": policy_sha256,
    }
