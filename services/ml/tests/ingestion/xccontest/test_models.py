from __future__ import annotations

import pytest

from paragliding_forecasts_ml.ingestion.xccontest.cli import build_parser
from paragliding_forecasts_ml.ingestion.xccontest.models import (
    DEFAULT_DELAY_SECONDS,
    PRIMARY_GLIDER_CATEGORY,
    CollectorConfig,
    FlightListScope,
)


def test_config_requires_unique_seasons_countries_and_normal_user_delay() -> None:
    with pytest.raises(ValueError, match="only once"):
        CollectorConfig(seasons=(2025, 2025), country_codes=("BG",))
    with pytest.raises(ValueError, match="country code"):
        CollectorConfig(seasons=(2025,), country_codes=())
    with pytest.raises(ValueError, match="only once"):
        CollectorConfig(seasons=(2025,), country_codes=("BG", "BG"))
    with pytest.raises(ValueError, match="ISO2"):
        CollectorConfig(seasons=(2025,), country_codes=("bg",))
    with pytest.raises(ValueError, match="at least 3"):
        CollectorConfig(
            seasons=(2025,),
            country_codes=("BG",),
            delay_seconds=DEFAULT_DELAY_SECONDS - 0.1,
        )
    with pytest.raises(ValueError, match="max_views"):
        CollectorConfig(seasons=(2025,), country_codes=("BG",), max_views=0)


def test_scope_rejects_unknown_source_sort() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        FlightListScope(PRIMARY_GLIDER_CATEGORY, sort_key="unknown")


def test_cli_parser_keeps_headless_default_and_supports_multiple_seasons() -> None:
    namespace = build_parser().parse_args(
        ["--season", "2025", "--season", "2024", "--max-views", "5"]
    )

    assert namespace.season == [2025, 2024]
    assert namespace.headed is False
    assert namespace.max_views == 5


def test_cli_parser_accepts_database_url_but_not_permission_reference_or_legacy_page_cap() -> None:
    namespace = build_parser().parse_args(
        ["--season", "2025", "--database-url", "file:./data/local/test.db"]
    )
    assert namespace.database_url == "file:./data/local/test.db"

    with pytest.raises(SystemExit):
        build_parser().parse_args(["--season", "2025", "--permission-reference", "not-used"])
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--season", "2025", "--max-pages", "5"])
