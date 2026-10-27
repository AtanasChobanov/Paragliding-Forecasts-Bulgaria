"""Deterministic cloud regimes and max-over-estimated-hours aggregation."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ...ingestion.weather.features.aggregation import sofia_flying_window
from ...ingestion.weather.features.thermodynamics import (
    ThermodynamicError,
    liquid_relative_humidity,
    romps_liquid_lcl_agl_m,
)
from ...ingestion.weather.serialization import canonical_json_bytes, sha256_bytes
from .models import DailyResult, Height, HourlyInput, HourlyResult, Regime
from .physics import buoyancy_flux, condensations, parcel
from .policy import POLICY, CloudbasePolicy


def formation(
    *,
    rh: float,
    low_cloud: float | None,
    height_gap: float | None,
    temperature_margin: float | None,
    b0: float | None,
    ccl_count: int,
    base_in_profile: bool = True,
    policy: CloudbasePolicy = POLICY,
) -> tuple[Regime, str]:
    if rh >= policy.near_saturation_fraction:
        return "other_cloud", "near_saturated_surface"
    if low_cloud is not None and 0 <= low_cloud <= 100:
        if low_cloud >= policy.widespread_low_cloud_percent:
            return "other_cloud", "widespread_low_cloud"
    else:
        return "indeterminate", "low_cloud_input_missing_or_invalid"
    if not base_in_profile:
        return "indeterminate", "potential_base_outside_profile"
    if ccl_count != 1:
        return (
            "indeterminate",
            "ccl_not_found_in_profile" if ccl_count == 0 else "multiple_ccl_intersections",
        )
    if height_gap is None or temperature_margin is None:
        return "indeterminate", "formation_input_missing"
    if height_gap >= policy.height_margin_m and temperature_margin >= policy.temperature_margin_k:
        if b0 is not None and b0 > 0:
            return "cumulus", "heating_and_condensation_supported"
        return "indeterminate", "positive_heating_not_established"
    if (
        height_gap <= -policy.height_margin_m
        and temperature_margin <= -policy.temperature_margin_k
        and low_cloud <= policy.blue_max_low_cloud_percent
    ):
        return "blue", "local_cumulus_formation_not_supported"
    return "indeterminate", "transition_or_conflicting_evidence"


def calculate_hour(hour: HourlyInput, policy: CloudbasePolicy = POLICY) -> HourlyResult:
    identity = {
        name: getattr(hour, name)
        for name in (
            "run_key",
            "site_id",
            "site_slug",
            "target_local_date",
            "valid_at_utc",
            "reference_at_utc",
            "horizon_days",
        )
    }
    identity["valid_at_local"] = (
        datetime.fromisoformat(hour.valid_at_utc).astimezone(ZoneInfo("Europe/Sofia")).isoformat()
    )
    identity["input_sha256"] = sha256_bytes(canonical_json_bytes(hour))
    diagnostics: dict = {}
    limitations = ["uncalibrated_baseline", "model_column_not_terrain_corrected"]
    try:
        central = parcel(hour, policy.mixed_depth_pa)
        assert hour.surface_pressure_pa is not None and hour.temperature_2m_k is not None
        assert hour.specific_humidity_2m_kg_kg is not None
        rh = liquid_relative_humidity(
            hour.surface_pressure_pa, hour.temperature_2m_k, hour.specific_humidity_2m_kg_kg
        )
    except ThermodynamicError as error:
        return HourlyResult(
            **identity,
            data_status="missing",
            regime="missing",
            potential_base=None,
            estimated_cloudbase=None,
            confidence=None,
            reason_codes=tuple(dict.fromkeys((str(error), *hour.input_issues))),
            limitations=tuple(limitations),
            diagnostics=diagnostics,
        )
    assert hour.model_elevation_msl_m is not None
    potential = Height(
        msl_m=hour.model_elevation_msl_m + central.lcl_agl_m,
        model_agl_m=central.lcl_agl_m,
        site_agl_m=hour.model_elevation_msl_m + central.lcl_agl_m - hour.site_elevation_msl_m,
    )
    mismatch = hour.site_elevation_msl_m - hour.model_elevation_msl_m
    if abs(mismatch) >= policy.terrain_warning_m:
        limitations.append("model_site_terrain_mismatch")
    if potential.site_agl_m < 0:
        limitations.append("potential_base_below_site")
    b0, flux_reason = buoyancy_flux(hour)
    reasons = list(hour.input_issues)
    if flux_reason:
        reasons.append(flux_reason)
    try:
        ccls = condensations(hour, central.specific_humidity)
    except (ValueError, IndexError) as error:
        ccls = ()
        reasons.append(f"ccl_calculation_unavailable:{type(error).__name__}")
    ccl = ccls[0] if len(ccls) == 1 else None
    gap = (
        None
        if hour.pbl_model_agl_m is None or hour.pbl_model_agl_m <= 0
        else hour.pbl_model_agl_m - central.lcl_agl_m
    )
    margin = None if ccl is None else hour.temperature_2m_k - ccl.convective_temperature_k
    in_profile = potential.msl_m <= hour.profile[-1].height_msl_m
    regime, reason = formation(
        rh=rh,
        low_cloud=hour.low_cloud_percent,
        height_gap=gap,
        temperature_margin=margin,
        b0=b0,
        ccl_count=len(ccls),
        base_in_profile=in_profile,
        policy=policy,
    )
    reasons.append(reason)
    diagnostics.update(
        surface_relative_humidity_fraction=rh,
        mixed_parcel_temperature_k=central.temperature_k,
        mixed_specific_humidity_kg_kg=central.specific_humidity,
        ccl_pressures_pa=[c.pressure_pa for c in ccls],
        ccl_model_agl_m=None if ccl is None else ccl.height_model_agl_m,
        convective_temperature_k=None if ccl is None else ccl.convective_temperature_k,
        pbl_minus_lcl_m=gap,
        temperature_margin_k=margin,
        surface_buoyancy_flux_m2_s3=b0,
        site_minus_model_terrain_m=mismatch,
        low_cloud_percent=hour.low_cloud_percent,
        total_cloud_percent=hour.total_cloud_percent,
        profile_top_msl_m=hour.profile[-1].height_msl_m,
        stored_lcl_difference_m=None
        if hour.stored_lcl_model_agl_m is None
        else central.lcl_agl_m - hour.stored_lcl_model_agl_m,
        surface_lcl_model_agl_m=romps_liquid_lcl_agl_m(
            hour.surface_pressure_pa, hour.temperature_2m_k, rh
        ),
    )
    sensitivity = []
    for depth in (policy.mixed_depth_pa, policy.sensitivity_depth_pa):
        try:
            mixed = parcel(hour, depth)
            alternatives = (
                ccls
                if depth == policy.mixed_depth_pa
                else condensations(hour, mixed.specific_humidity)
            )
            alt_ccl = alternatives[0] if len(alternatives) == 1 else None
            for offset in policy.sensitivity_temperature_offsets_k:
                alternative = parcel(hour, depth, offset)
                alt_gap = (
                    None
                    if hour.pbl_model_agl_m is None or hour.pbl_model_agl_m <= 0
                    else hour.pbl_model_agl_m - alternative.lcl_agl_m
                )
                alt_margin = (
                    None
                    if alt_ccl is None
                    else hour.temperature_2m_k + offset - alt_ccl.convective_temperature_k
                )
                alt_regime, _ = formation(
                    rh=rh,
                    low_cloud=hour.low_cloud_percent,
                    height_gap=alt_gap,
                    temperature_margin=alt_margin,
                    b0=b0,
                    ccl_count=len(alternatives),
                    base_in_profile=hour.model_elevation_msl_m + alternative.lcl_agl_m
                    <= hour.profile[-1].height_msl_m,
                    policy=policy,
                )
                sensitivity.append(
                    {
                        "depth_pa": depth,
                        "offset_k": offset,
                        "lcl_model_agl_m": alternative.lcl_agl_m,
                        "regime": alt_regime,
                    }
                )
        except (ThermodynamicError, ValueError, IndexError):
            limitations.append("sensitivity_variant_unavailable")
    diagnostics["sensitivity"] = sensitivity
    if any(variant["regime"] != regime for variant in sensitivity):
        limitations.append("sensitive_to_parcel_assumptions")
    return HourlyResult(
        **identity,
        data_status="baseline",
        regime=regime,
        potential_base=potential,
        estimated_cloudbase=potential if regime == "cumulus" else None,
        confidence="low",
        reason_codes=tuple(dict.fromkeys(reasons)),
        limitations=tuple(dict.fromkeys(limitations)),
        diagnostics=diagnostics,
    )


def aggregate_day(hours: list[HourlyResult]) -> DailyResult:
    if not hours:
        raise ValueError("Daily aggregation requires the eleven explicit hours.")
    first = hours[0]
    keys = (
        "run_key",
        "site_id",
        "site_slug",
        "target_local_date",
        "reference_at_utc",
        "horizon_days",
    )
    if any(any(getattr(h, key) != getattr(first, key) for key in keys) for h in hours):
        raise ValueError("Daily aggregation cannot mix site, run, date or horizon.")
    expected = sofia_flying_window(
        date.fromisoformat(first.target_local_date)
    ).expected_instants_utc
    if sorted(h.valid_at_utc for h in hours) != list(expected):
        raise ValueError("Daily aggregation requires eleven unique flying-window instants.")
    counts = Counter(h.regime for h in hours)
    classified = sum(counts[key] for key in ("cumulus", "blue", "other_cloud"))
    candidates = sorted(
        (h for h in hours if h.estimated_cloudbase is not None),
        key=lambda h: (-h.estimated_cloudbase.msl_m, h.valid_at_utc),
    )
    maximum = candidates[0] if candidates else None
    if maximum:
        state = "cloudbase_available"
    elif counts["blue"] == 11:
        state = "blue"
    elif counts["other_cloud"] == 11:
        state = "other_cloud"
    elif counts["missing"] == 11:
        state = "missing"
    else:
        state = "indeterminate"
    limitations = {limitation for hour in hours for limitation in hour.limitations}
    if classified < 11:
        limitations.add("incomplete_cloud_regime_coverage")
    return DailyResult(
        **{key: getattr(first, key) for key in keys},
        summary_state=state,
        max_cloudbase=None if maximum is None else maximum.estimated_cloudbase,
        max_at_utc=None if maximum is None else maximum.valid_at_utc,
        max_at_local=None if maximum is None else maximum.valid_at_local,
        regime_counts={
            key: counts[key]
            for key in ("cumulus", "blue", "other_cloud", "indeterminate", "missing")
        },
        present_hours=11 - counts["missing"],
        classified_hours=classified,
        coverage_complete=classified == 11,
        confidence=None if state == "missing" else "low",
        limitations=tuple(sorted(limitations)),
    )
