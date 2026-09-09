from __future__ import annotations

import pytest

from paragliding_forecasts_ml.ingestion.gfs.inventory import (
    DEFAULT_SELECTORS,
    GfsSelector,
    InventoryError,
    SelectorContractError,
    parse_index,
    select_ranges,
)

INDEX = b"\n".join(
    (
        b"1:0:d=2025080100:TMP:2 m above ground:24 hour fcst:",
        b"2:10:d=2025080100:UGRD:10 m above ground:24 hour fcst:",
        b"3:30:d=2025080100:VGRD:10 m above ground:24 hour fcst:",
    )
)


def _default_selector(key: str) -> GfsSelector:
    return next(item for item in DEFAULT_SELECTORS if item.key == key)


def test_parses_native_index_and_plans_coalesced_ranges() -> None:
    entries = parse_index(INDEX)
    ranges = select_ranges(
        entries,
        content_length=50,
        lead_hours=24,
        selectors=(
            GfsSelector("temperature", "TMP", "2 m above ground"),
            GfsSelector("wind_u", "UGRD", "10 m above ground"),
        ),
        maximum_range_bytes=32,
    )

    assert entries[0].reference_at_utc == "2025-08-01T00:00:00Z"
    assert len(ranges) == 1
    assert ranges[0].start == 0
    assert ranges[0].end == 29
    assert ranges[0].message_numbers == (1, 2)
    assert ranges[0].forecast_descriptors == ("24 hour fcst", "24 hour fcst")


def test_rejects_missing_selector_and_non_monotonic_offsets() -> None:
    entries = parse_index(INDEX)
    with pytest.raises(SelectorContractError, match="available CAPE forms"):
        select_ranges(
            entries,
            content_length=50,
            lead_hours=24,
            selectors=(GfsSelector("missing", "CAPE", "surface"),),
            maximum_range_bytes=32,
        )
    with pytest.raises(InventoryError, match="strictly increasing"):
        parse_index(
            b"1:10:d=2025080100:TMP:2 m above ground:24 hour fcst:\n"
            b"2:9:d=2025080100:RH:2 m above ground:24 hour fcst:\n"
        )


def test_f007_selectors_use_native_levels_and_temporal_semantics() -> None:
    entries = parse_index(
        b"1:0:d=2026082100:HPBL:surface:7 hour fcst:\n"
        b"2:10:d=2026082100:PWAT:entire atmosphere (considered as a single layer):7 hour fcst:\n"
        b"3:20:d=2026082100:TCDC:entire atmosphere:7 hour fcst:\n"
        b"4:30:d=2026082100:TCDC:entire atmosphere:6-7 hour ave fcst:\n"
        b"5:40:d=2026082100:APCP:surface:6-7 hour acc fcst:\n"
        b"6:50:d=2026082100:APCP:surface:0-7 hour acc fcst:\n"
        b"7:60:d=2026082100:DSWRF:surface:6-7 hour ave fcst:\n"
    )

    ranges = select_ranges(
        entries,
        content_length=70,
        lead_hours=7,
        selectors=tuple(
            _default_selector(key) for key in ("hpbl", "pwat", "tcdc", "apcp", "dswrf")
        ),
        maximum_range_bytes=64,
    )

    assert tuple(number for item in ranges for number in item.message_numbers) == (1, 2, 3, 5, 7)
    assert _default_selector("hpbl").level == "surface"
    assert _default_selector("pwat").level.endswith("(considered as a single layer)")


def test_feature_profile_selectors_cover_the_common_pgrb2_1000_to_500_hpa_band() -> None:
    expected_pressures = {
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
    }
    profile_fields = ("hgt", "tmp", "rh", "spfh", "ugrd", "vgrd", "vvel")
    selected_pressures = {
        field: {
            int(selector.key.rsplit("_", 1)[1])
            for selector in DEFAULT_SELECTORS
            if selector.key.startswith(f"{field}_") and selector.key.rsplit("_", 1)[1].isdigit()
        }
        for field in profile_fields
    }

    assert selected_pressures == {field: expected_pressures for field in profile_fields}
    assert all(875 not in pressures for pressures in selected_pressures.values())


def test_specific_humidity_and_turbulent_flux_selectors_pin_native_semantics() -> None:
    specific_humidity = _default_selector("spfh_2m")
    sensible = _default_selector("shtfl")
    latent = _default_selector("lhtfl")

    assert (specific_humidity.parameter, specific_humidity.level) == ("SPFH", "2 m above ground")
    assert (sensible.parameter, sensible.level, sensible.temporal_kind) == (
        "SHTFL",
        "surface",
        "average",
    )
    assert (latent.parameter, latent.level, latent.minimum_lead_hours) == ("LHTFL", "surface", 1)


def test_apcp_collects_indistinguishable_shortest_interval_ties() -> None:
    entries = parse_index(
        b"1:0:d=2026082100:APCP:surface:0-1 hour acc fcst:\n"
        b"2:10:d=2026082100:APCP:surface:0-1 hour acc fcst:\n"
        b"3:20:d=2026082100:APCP:surface:0-6 hour acc fcst:\n"
    )

    ranges = select_ranges(
        entries,
        content_length=30,
        lead_hours=1,
        selectors=(_default_selector("apcp"),),
        maximum_range_bytes=32,
    )

    assert len(ranges) == 1
    assert ranges[0].message_numbers == (1, 2)


def test_interval_fields_are_not_applicable_at_analysis_lead() -> None:
    entries = parse_index(b"1:0:d=2026082100:TMP:2 m above ground:anl:\n")

    ranges = select_ranges(
        entries,
        content_length=10,
        lead_hours=0,
        selectors=(
            GfsSelector("tmp", "TMP", "2 m above ground"),
            _default_selector("apcp"),
            _default_selector("dswrf"),
        ),
        maximum_range_bytes=16,
    )

    assert ranges[0].selector_keys == ("tmp",)


def test_rejects_ambiguous_point_selector() -> None:
    entries = parse_index(
        b"1:0:d=2026082100:TCDC:entire atmosphere:7 hour fcst:\n"
        b"2:10:d=2026082100:TCDC:entire atmosphere:7 hour fcst:\n"
    )

    with pytest.raises(SelectorContractError, match="ambiguous"):
        select_ranges(
            entries,
            content_length=20,
            lead_hours=7,
            selectors=(_default_selector("tcdc"),),
            maximum_range_bytes=16,
        )
