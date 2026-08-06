from __future__ import annotations

import pytest

from paragliding_forecasts_ml.ingestion.xccontest.cli import parse_config
from paragliding_forecasts_ml.ingestion.xccontest.models import (
    DEFAULT_DELAY_SECONDS,
    PRIMARY_GLIDER_CATEGORY,
    CollectorConfig,
    FlightListScope,
)


def test_config_requires_unique_seasons_and_normal_user_delay() -> None:
    with pytest.raises(ValueError, match="only once"):
        CollectorConfig(seasons=(2025, 2025))
    with pytest.raises(ValueError, match="at least 3"):
        CollectorConfig(seasons=(2025,), delay_seconds=DEFAULT_DELAY_SECONDS - 0.1)
    with pytest.raises(ValueError, match="max_views"):
        CollectorConfig(seasons=(2025,), max_views=0)


def test_scope_rejects_unknown_source_sort() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        FlightListScope(PRIMARY_GLIDER_CATEGORY, sort_key="unknown")


def test_cli_config_keeps_headless_default_and_supports_multiple_seasons() -> None:
    config = parse_config(["--season", "2025", "--season", "2024", "--max-views", "5"])

    assert config.seasons == (2025, 2024)
    assert config.headed is False
    assert config.max_views == 5


def test_cli_does_not_accept_permission_reference_or_legacy_page_cap() -> None:
    with pytest.raises(SystemExit):
        parse_config(["--season", "2025", "--permission-reference", "not-used"])
    with pytest.raises(SystemExit):
        parse_config(["--season", "2025", "--max-pages", "5"])
