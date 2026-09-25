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


def resume_collect_run(
    run_key: str,
    *,
    project_root=None,
    driver_factory: Callable[..., PlaywrightFlightListDriver] = PlaywrightFlightListDriver,
) -> CollectionReport:
    """Resume only from hash-verified state, without user-selectable source dates."""

    try:
        artifacts = RawArtifactStore.resume(run_key, project_root=project_root)
        context = artifacts.collection_context
        config = CollectorConfig(
            seasons=tuple(context["seasons"]),
            country_codes=tuple(context["country_codes"]),
            headed=bool(context["headed"]),
            slow_mo_ms=int(context["slow_mo_ms"]),
            timeout_seconds=int(context["timeout_seconds"]),
            max_views=int(context["max_views"]),
            delay_seconds=float(context["delay_seconds"]),
            acknowledge_rate_limit_risk=bool(context["acknowledge_rate_limit_risk"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise CollectionExecutionError(
            f"XCContest resume could not verify its checkpoint: {error}"
        ) from error
    return collect_run(config, artifact_store=artifacts, driver_factory=driver_factory)
