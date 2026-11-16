"""Plan the exact NOAA horizon and resume retained weather ingestion stages."""

import json
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from sqlite3 import Row
from uuid import uuid4

from ...ingestion.atmosphere.contracts import RequestPlan
from ...ingestion.gfs.collector import GfsCollector
from ...ingestion.gfs.models import (
    GFS_SOURCE_ID,
    SOFIA_FLYING_WINDOW_VERSION,
    GfsRequest,
    GfsResolvedPlan,
)
from ...ingestion.gfs.parser import raw_manifest_reference
from ...ingestion.gfs.planner import GfsPlanner
from ...ingestion.gfs.transport import HttpTransport
from ...ingestion.weather.artifacts import WeatherArtifactStore
from ...ingestion.weather.pipeline import WeatherPreflight
from ...ingestion.weather.services import (
    WeatherRunContext,
    build_features,
    parse_and_normalize,
    persist_run,
    sample_sites,
    validate_run,
)
from ...ingestion.weather.state import RunStateLedger
from ...storage.sqlite import open_read_only_database
from .checkpoints import Checkpoints
from .store import Publication, existing_publication
from .weather import ForecastHorizon, candidate_weather_runs, read_weather, utc_text

# Compact stage writes run concurrently and use temporary files. This matches
# the conservative per-job scratch allowance in the existing GFS backfill.
WEATHER_SCRATCH_BYTES = 2 * 2**30


class ForecastJobError(RuntimeError):
    def __init__(self, kind: str, message: str) -> None:
        self.kind = kind
        super().__init__(message)


@dataclass(frozen=True)
class Admission:
    run_key: str
    horizon: ForecastHorizon
    reserved_bytes: int = 0
    weather_needed: bool = False
    plan: RequestPlan | None = None
    publication: Publication | None = None
    reuse: tuple[str, ...] = ()


@dataclass
class WeatherJobs:
    root: Path
    preflight: WeatherPreflight
    policy: Path | None
    checkpoints: Checkpoints
    model_id: str
    maximum_total_bytes: int
    metadata: HttpTransport | None
    download: HttpTransport | None
    clock: Callable[[], datetime]
    progress: Callable[[str], None] = lambda _: None

    def _connection(self):
        connection = open_read_only_database(self.preflight.database_url, self.root)
        connection.row_factory = Row
        return closing(connection)

    def _existing(self, connection, run_key: str) -> Admission:
        weather = read_weather(connection, run_key)
        result = existing_publication(connection, weather, self.model_id)
        if result is not None:
            return Admission(run_key, weather.horizon, publication=result, reuse=("publication",))
        store = WeatherArtifactStore(run_key, project_root=self.root)
        event = RunStateLedger(store).load_state().effective_event("persisted")
        if event is not None and event.disposition == "persisted":
            return Admission(run_key, weather.horizon, reuse=("weather",))
        return Admission(run_key, weather.horizon, WEATHER_SCRATCH_BYTES, True, reuse=("raw",))

    def select_run(self, run_key: str) -> Admission:
        with self._connection() as connection:
            return self._existing(connection, run_key)

    def visible(self, target: date) -> Admission | None:
        with self._connection() as connection:
            for row in connection.execute(
                """SELECT r.run_key FROM prediction_runs AS publication
                   JOIN weather_ingestion_runs AS r ON r.id = publication.weather_ingestion_run_id
                   JOIN weather_product_runs AS p ON p.id = r.product_run_id
                   WHERE r.target_local_date = ? AND publication.xc_model_id = ?
                   ORDER BY p.reference_at_utc DESC, publication.id DESC""",
                (target.isoformat(), self.model_id),
            ):
                weather = read_weather(connection, row[0])
                publication = existing_publication(connection, weather, self.model_id)
                return Admission(
                    weather.run_key,
                    weather.horizon,
                    publication=publication,
                    reuse=("publication",),
                )
        return None

    def probe(self, horizon: ForecastHorizon) -> Admission:
        with self._connection() as connection:
            candidates = candidate_weather_runs(connection, horizon)
            if candidates:
                # A completed pair takes precedence over an unfinished later local
                # attempt for the same operational cycle and target date.
                for key in candidates:
                    weather = read_weather(connection, key)
                    result = existing_publication(connection, weather, self.model_id)
                    if result is not None:
                        return Admission(key, horizon, publication=result, reuse=("publication",))
                return self._existing(connection, candidates[0])

        saved = self.checkpoints.load_plan(horizon)
        if saved is not None:
            self._eligible_plan(horizon, saved)
            path = self.root / "data" / "raw" / "weather" / saved.run_key / "manifest.json"
            if path.exists() or path.is_symlink():
                return Admission(
                    saved.run_key, horizon, WEATHER_SCRATCH_BYTES, True, saved, reuse=("raw",)
                )

        if self.metadata is None:
            raise ForecastJobError(
                "live_network_not_allowed", "Pass --allow-live-network for NOAA requests."
            )

        request = GfsRequest(
            run_key=str(uuid4()),
            request_purpose="operational_forecast",
            valid_at_utc=horizon.hours,
            explicit_run_at_utc=horizon.cycle,
            maximum_total_bytes=self.maximum_total_bytes,
            target_local_date=horizon.target_date.isoformat(),
            flying_window_version=SOFIA_FLYING_WINDOW_VERSION,
            site_config_sha256=self.preflight.site_config_sha256,
            sampling_policy_sha256=self.preflight.sampling_policy_sha256,
            compact_selection_version=self.preflight.compact_selection_version,
        )
        proposed = GfsPlanner(self.metadata).plan(request, created_at_utc=utc_text(self.clock()))
        resolved = self._eligible_plan(horizon, proposed)
        reused = ()
        if saved is not None:
            previous_identity = proposed.model_copy(
                update={
                    "run_key": saved.run_key,
                    "created_at_utc": saved.created_at_utc,
                }
            )
            if previous_identity == saved:
                proposed = saved
                reused = ("request_plan",)
        sizes = [item.byte_end - item.byte_start + 1 for item in resolved.ranges]
        # Temporary writes of a range use a hard link in the existing collector.
        return Admission(
            proposed.run_key,
            horizon,
            sum(sizes) + WEATHER_SCRATCH_BYTES,
            True,
            proposed,
            reuse=reused,
        )

    @staticmethod
    def _eligible_plan(horizon: ForecastHorizon, plan: RequestPlan) -> GfsResolvedPlan:
        resolved = GfsResolvedPlan.model_validate_json(
            json.dumps(plan.adapter_request), strict=True
        )
        if (
            plan.source_id != GFS_SOURCE_ID
            or plan.request_purpose != "operational_forecast"
            or resolved.resolved_run_at_utc != horizon.cycle
            or resolved.target_local_date != horizon.target_date.isoformat()
            or resolved.selection_mode != "explicit"
            or resolved.gfs_request_schema_version != 3
        ):
            raise ForecastJobError(
                "invalid_plan", "GFS request plan differs from the job's cycle or date."
            )
        stamps = [
            stamp
            for item in resolved.ranges
            for stamp in (item.object_last_modified_utc, item.index_last_modified_utc)
        ]
        if any(stamp is None or stamp < horizon.cycle for stamp in stamps) or any(
            not item.object_etag or item.object_etag.startswith("W/") for item in resolved.ranges
        ):
            raise ForecastJobError(
                "source_contract_mismatch", "GFS plan requires timestamps and a strong GRIB ETag."
            )
        if max(stamps) > horizon.cutoff:
            raise ForecastJobError(
                "late_source", "At least one required GRIB or .idx was modified after 16:00 Sofia."
            )
        if resolved.available_at_utc != max(stamps):
            raise ForecastJobError(
                "invalid_plan", "GFS readiness does not match its object timestamps."
            )
        return resolved

    def admit(self, admission: Admission) -> None:
        if admission.plan is not None:
            self.checkpoints.set_plan(admission.horizon, admission.plan)
        self.checkpoints.mark_managed(admission.horizon, admission.run_key)

    def prepare(self, admission: Admission) -> tuple[WeatherRunContext, tuple[str, ...]]:
        key = admission.run_key
        root = self.root
        url = self.preflight.database_url
        reused = []
        if admission.plan is not None:
            # The durable plan owns this UUID. These two mkdirs also recover a
            # crash between reserving the raw and interim directories.
            for zone in ("raw", "interim"):
                directory = root / "data" / zone / "weather" / key
                if directory.is_symlink():
                    raise ValueError("Managed weather run directory cannot be a symbolic link.")
                directory.mkdir(parents=True, exist_ok=True)
            store = WeatherArtifactStore(key, project_root=root)
            ledger = RunStateLedger(store)
            snapshot = ledger.load_state()
            if not snapshot.events:
                ledger.initialize(occurred_at_utc=utc_text(self.clock()))
                snapshot = ledger.load_state()
            if snapshot.effective_event("raw_complete") is None:
                if (store.raw_dir / "manifest.json").exists():
                    reference = raw_manifest_reference(store)
                    manifest = store.verify_raw_manifest(reference)
                    plan_path = store.verify_reference(
                        manifest.request_plan, expected_root=store.raw_dir
                    )
                    if (
                        RequestPlan.model_validate_json(plan_path.read_bytes(), strict=True)
                        != admission.plan
                    ):
                        raise ValueError(
                            "Retained raw manifest differs from the managed request plan."
                        )
                    reused.append("raw")
                else:
                    if self.download is None:
                        raise ForecastJobError(
                            "live_network_not_allowed",
                            "NOAA download requires --allow-live-network.",
                        )
                    reference = GfsCollector(
                        self.download, clock=lambda: utc_text(self.clock())
                    ).fetch_resumable(
                        admission.plan,
                        store,
                        progress=lambda done, total: self.progress(
                            f"{admission.horizon.target_date} GRIB ranges {done}/{total}"
                        ),
                    )
                ledger.append_to(
                    snapshot,
                    invocation_mode="resume",
                    stage="raw_complete",
                    disposition="complete",
                    occurred_at_utc=utc_text(self.clock()),
                    evidence=reference,
                    detail="managed operational GFS forecast collection",
                )
        context = WeatherRunContext.open(key, project_root=root, database_url=url)
        parser, context.snapshot = parse_and_normalize(context)
        sample, context.snapshot = sample_sites(context)
        validation, context.snapshot = validate_run(context)
        if validation.disposition == "quarantined":
            raise ForecastJobError(
                "weather_quarantined", "Weather samples did not pass validation."
            )
        features, context.snapshot = build_features(context)
        for name, disposition in (
            ("parser", parser.parser_disposition),
            ("normalizer", parser.normalizer_disposition),
            ("sampling", sample.disposition),
            ("validation", validation.boundary_disposition),
            ("features", features.boundary_disposition),
        ):
            if disposition == "reused":
                reused.append(name)
        return context, tuple(reused)

    def persist(self, context: WeatherRunContext) -> bool:
        result, _ = persist_run(context, self.policy)
        with self._connection() as connection:
            read_weather(connection, context.run_key)
        return result.report["status"] in {"revalidated_no_op", "recovered_committed_write"}
