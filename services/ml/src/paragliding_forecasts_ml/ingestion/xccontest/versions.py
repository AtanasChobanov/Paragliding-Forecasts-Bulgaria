"""Version identifiers for durable XCContest ingestion-stage interfaces."""

from __future__ import annotations

from .models import SOURCE_CODE

RAW_MANIFEST_SCHEMA_VERSION = 2

COLLECTOR_REVISION = 2
COLLECTOR_VERSION = f"{SOURCE_CODE}-collector/{COLLECTOR_REVISION}"

PARSER_REVISION = 2
PARSER_VERSION = f"{SOURCE_CODE}-parser/{PARSER_REVISION}"
PARSER_OUTPUT_DIRECTORY = f"parser-v{PARSER_REVISION}"
