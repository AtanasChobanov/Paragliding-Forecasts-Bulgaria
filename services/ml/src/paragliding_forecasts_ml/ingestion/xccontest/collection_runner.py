"""Reusable authorized XCContest collection execution boundary."""

from __future__ import annotations

import time
from collections.abc import Callable

from playwright.sync_api import Error as PlaywrightError

from .artifacts import RawArtifactStore, safe_failure_summary
from .browser import BrowserCollectionError, PlaywrightFlightListDriver
from .collector import CollectionError, FlightListCollector
from .models import CollectionReport, CollectorConfig


class CollectionExecutionError(RuntimeError):
    """The browser collection stage did not finish with immutable raw evidence."""


def collect_run(
    config: CollectorConfig,
    *,
    artifact_store: RawArtifactStore | None = None,
    driver_factory: Callable[..., PlaywrightFlightListDriver] = PlaywrightFlightListDriver,
) -> CollectionReport:
    """Collect one source run and retain a local failure report on browser errors."""

    artifacts = artifact_store or RawArtifactStore()
    try:
        with driver_factory(config, sleeper=time.sleep) as driver:
            return FlightListCollector(config=config, driver=driver, artifacts=artifacts).collect()
    except (BrowserCollectionError, CollectionError, PlaywrightError) as error:
        artifacts.write_failure_report(error=safe_failure_summary(error))
        raise CollectionExecutionError(
            "XCContest collection did not complete. Review the local failure report; "
            "use --headed for a manual browser check."
        ) from error
