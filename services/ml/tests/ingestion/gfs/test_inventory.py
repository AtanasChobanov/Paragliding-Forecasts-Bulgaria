from __future__ import annotations

import pytest

from paragliding_forecasts_ml.ingestion.gfs.inventory import (
    DEFAULT_SELECTORS,
    GfsSelector,
    InventoryError,
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


def test_parses_native_index_and_plans_coalesced_ranges() -> None:
    entries = parse_index(INDEX)
    ranges = select_ranges(
        entries,
        content_length=50,
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


def test_rejects_missing_selector_and_non_monotonic_offsets() -> None:
    entries = parse_index(INDEX)
    with pytest.raises(InventoryError, match="expected"):
        select_ranges(
            entries,
            content_length=50,
            selectors=(GfsSelector("missing", "CAPE", "surface"),),
            maximum_range_bytes=32,
        )
    with pytest.raises(InventoryError, match="strictly increasing"):
        parse_index(
            b"1:10:d=2025080100:TMP:2 m above ground:24 hour fcst:\n"
            b"2:9:d=2025080100:RH:2 m above ground:24 hour fcst:\n"
        )


def test_default_hpbl_selector_uses_native_hgt_parameter() -> None:
    entries = parse_index(
        b"1:0:d=2025080100:HGT:planetary boundary layer:anl:\n"
        b"2:10:d=2025080100:TMP:2 m above ground:anl:\n"
    )
    hpbl = next(item for item in DEFAULT_SELECTORS if item.key == "hpbl")

    ranges = select_ranges(
        entries,
        content_length=20,
        selectors=(hpbl,),
        maximum_range_bytes=32,
    )

    assert hpbl.parameter == "HGT"
    assert ranges[0].message_numbers == (1,)
