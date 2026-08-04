from __future__ import annotations

import pytest

from paragliding_forecasts_ml.ingestion.xccontest.cli import parse_config
from paragliding_forecasts_ml.ingestion.xccontest.models import (
    DEFAULT_DELAY_SECONDS,
    CollectorConfig,
)


def test_config_requires_unique_seasons_and_normal_user_delay() -> None:
    with pytest.raises(ValueError, match="only once"):
        CollectorConfig(seasons=(2025, 2025))
    with pytest.raises(ValueError, match="at least 3"):
        CollectorConfig(seasons=(2025,), delay_seconds=DEFAULT_DELAY_SECONDS - 0.1)


def test_cli_config_keeps_headless_default_and_supports_multiple_seasons() -> None:
    config = parse_config(["--season", "2025", "--season", "2024", "--max-pages", "5"])

    assert config.seasons == (2025, 2024)
    assert config.headed is False
    assert config.max_pages == 5


def test_cli_does_not_accept_permission_reference() -> None:
    with pytest.raises(SystemExit):
        parse_config(["--season", "2025", "--permission-reference", "not-used"])
