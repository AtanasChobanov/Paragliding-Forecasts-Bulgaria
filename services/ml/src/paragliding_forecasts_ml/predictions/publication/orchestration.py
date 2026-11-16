"""Schedule ready horizons and keep metadata polling independent of occupied workers."""

from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, wait
from contextlib import ExitStack
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from sqlite3 import Error as SqliteError

from ...storage.file_lock import file_lock, weather_run_lock
from .predictors import PREDICTORS, run_predictor
from .store import BundleIds, Publication, publish_date
from .weather import SOFIA, ForecastHorizon, utc_text
from .weather_jobs import Admission, WeatherJobs

TERMINAL = {"published", "already_published", "covered", "failed", "unavailable", "blocked"}
RETRYABLE_PROBES = {"absent_file", "incomplete_run", "network_failure"}
JOB_ERRORS = (OSError, RuntimeError, SqliteError, ValueError)


@dataclass(eq=False)
class Job:
    horizon: ForecastHorizon | None
    role: str
    run_key: str | None = None
    state: str = "waiting"
    reason: str | None = None
    detail: str | None = None
    admission: Admission | None = None
    checks: list[dict] = field(default_factory=list)
    timings: dict[str, list[dict]] = field(default_factory=dict)
    reused: set[str] = field(default_factory=set)
    predictor_ids: dict[str, str] = field(default_factory=dict)
    started_predictors: set[str] = field(default_factory=set)
    publication: Publication | None = None
    prepared: object = None
    lock: ExitStack | None = None
    reserved_bytes: int = 0
    replacement_checks: int = 0
    force_probe: bool = False

    def accept(self, admission: Admission) -> None:
        self.admission = admission
        self.horizon = admission.horizon
        self.run_key = admission.run_key
        self.reused.update(admission.reuse)
        self.reason = self.detail = None
        if admission.publication:
            self.complete(admission.publication)
        else:
            self.state = "ready"

    def complete(self, publication: Publication) -> None:
        self.publication = publication
        self.state = "already_published" if publication.reused else "published"
        self.reason = self.detail = None
        if publication.reused:
            self.reused.add("publication")

    def error(self, state: str, error: Exception) -> None:
        self.state = state
        self.reason = getattr(error, "kind", type(error).__name__)
        self.detail = str(error)

    def report(self) -> dict:
        horizon = self.horizon
        return {
            "role": self.role,
            "target_local_date": horizon.target_date.isoformat() if horizon else None,
            "cycle_reference_utc": horizon.cycle if horizon else None,
            "horizon_days": horizon.days if horizon else None,
            "run_key": self.run_key,
            "status": self.state,
            "reason": self.reason,
            "detail": self.detail,
            "publication": asdict(self.publication) if self.publication else None,
            "deadline_met": (
                datetime.fromisoformat(self.publication.created_at_utc) <= horizon.deadline
                if self.publication and horizon
                else None
            ),
            "predictor_ids": self.predictor_ids,
            "reused_stages": sorted(self.reused),
            "checks": self.checks,
            "stage_times": self.timings,
        }


def _wait(futures, seconds: float | None) -> None:
    if futures:
        wait(futures, timeout=seconds, return_when=FIRST_COMPLETED)
    elif seconds is not None and seconds > 0:
        from time import sleep

        sleep(seconds)


class ForecastSchedule:
    """Drive one fixed Sofia issue date with injectable time and transport boundaries."""

    def __init__(
        self,
        weather: WeatherJobs,
        *,
        started: datetime,
        clock: Callable[[], datetime],
        max_workers: int,
        free_bytes: Callable[[], int],
        wait_for_progress=_wait,
        progress: Callable[[str], None] = lambda _: None,
    ) -> None:
        self.weather = weather
        self.started = started
        self.clock = clock
        self.max_workers = max_workers
        self.free_bytes = free_bytes
        self.wait_for_progress = wait_for_progress
        self.progress = progress
        self.today = started.astimezone(SOFIA).date()
        self.opening = datetime.combine(self.today, time(13), SOFIA)
        self.last_check = datetime.combine(self.today, time(16), SOFIA)
        self.jobs: list[Job] = []
        self.pending: dict[Future, tuple[Job, str, datetime]] = {}
        self.visible: dict[date, Admission] = {}
        self.primary: dict[date, Job] = {}
        self.next_poll: datetime | None = None

    def _add_primary(self, issue: date) -> None:
        for days in (1, 2, 3):
            horizon = ForecastHorizon(issue, days)
            job = Job(horizon, "primary")
            self.primary[horizon.target_date] = job
            self.jobs.append(job)

    def _start(self, issue_date: date | None, run_keys: tuple[str, ...]) -> str:
        if run_keys:
            for key in run_keys:
                job = Job(None, "explicit", run_key=key)
                self.jobs.append(job)
                try:
                    job.accept(self.weather.select_run(key))
                except JOB_ERRORS as error:
                    job.error("failed", error)
            return "run_keys"

        if issue_date:
            self._add_primary(issue_date)
            self.next_poll = self.started
            return "issue_date"

        if self.started >= self.opening:
            self._add_primary(self.today)
            self.next_poll = self.started
        for days in (1, 2, 3):
            horizon = ForecastHorizon(self.today - timedelta(days=1), days)
            job = Job(horizon, "visible_fallback")
            self.jobs.append(job)
            try:
                result = self.weather.visible(horizon.target_date)
            except JOB_ERRORS as error:
                job.error("failed", error)
                continue
            if result is not None:
                self.visible[horizon.target_date] = result
                job.state = "covered"
                job.reason = "already_has_publication"
        return "automatic"

    def _source_check(self, job: Job, *, repeat: bool) -> None:
        checked = self.clock()
        try:
            job.accept(self.weather.probe(job.horizon))
            job.checks.append({"at_utc": utc_text(checked), "outcome": job.state})
        except JOB_ERRORS as error:
            kind = getattr(error, "kind", None)
            may_wait = repeat and kind in RETRYABLE_PROBES
            job.error(
                "waiting"
                if may_wait
                else ("unavailable" if kind in RETRYABLE_PROBES else "failed"),
                error,
            )
            job.checks.append({"at_utc": utc_text(checked), "outcome": job.reason})

    def _check_primary(self, now: datetime, *, repeating: bool) -> None:
        due = self.next_poll is not None and now >= self.next_poll
        for job in self.primary.values():
            if job.state == "waiting" and (due or job.force_probe):
                job.force_probe = False
                self._source_check(job, repeat=repeating and now < self.last_check)
        if due:
            self.next_poll = (
                min(now + timedelta(minutes=15), self.last_check)
                if (
                    repeating
                    and now < self.last_check
                    and any(job.state == "waiting" for job in self.primary.values())
                )
                else None
            )

    def _covered(self, job: Job) -> bool:
        target = job.horizon.target_date
        primary = self.primary.get(target)
        return target in self.visible or (primary is not None and primary.publication is not None)

    def _newer_active(self, job: Job) -> bool:
        primary = self.primary.get(job.horizon.target_date)
        return primary is not None and primary.state not in TERMINAL | {"waiting"}

    def _check_fallback(self) -> None:
        for job in self.jobs:
            if job.role != "visible_fallback" or job.state not in {"waiting", "ready"}:
                continue
            if self._covered(job):
                job.state, job.reason, job.detail = "covered", "already_has_publication", None
            elif job.state == "waiting" and not self._newer_active(job):
                self._source_check(job, repeat=False)
                job.force_probe = False

    def _submit(self, pool, job, name, function, *args, **kwargs):
        started = self.clock()
        future = pool.submit(function, *args, **kwargs)
        self.pending[future] = (job, name, started)
        self.progress(f"{job.horizon.target_date} D+{job.horizon.days} {name} {job.run_key}")

    def _dispatch_ready(self, job, threads) -> None:
        admission = job.admission
        reserve = admission.reserved_bytes
        if reserve:
            free = self.free_bytes()
            held = sum(other.reserved_bytes for other in self.jobs)
            if held and free < held + reserve:
                return
            if free < reserve:
                job.state = "blocked"
                job.reason = "insufficient_disk_space"
                job.detail = f"Requires {reserve} bytes with {free} bytes free."
                return
        locks = ExitStack()
        try:
            locks.enter_context(file_lock(weather_run_lock(self.weather.root, job.run_key)))
            self.weather.admit(admission)
            job.lock = locks
            job.reserved_bytes = reserve
            if admission.weather_needed:
                self._submit(threads, job, "weather", self.weather.prepare, admission)
                job.state = "preparing"
            else:
                job.state = "predicting"
        except JOB_ERRORS as error:
            locks.close()
            job.lock = None
            job.reserved_bytes = 0
            job.error("failed", error)

    def _dispatch(self, threads, processes, writer) -> None:
        # The executor queues never exceed the shared limit. SQLite writes have a
        # single slot and take precedence once their prerequisite stages finish.
        priority = {"assembled": 0, "prepared": 1, "predicting": 2, "ready": 3}
        ordered = sorted(
            self.jobs, key=lambda job: (priority.get(job.state, 4), job.role == "visible_fallback")
        )
        writer_busy = any(
            stage in {"weather_commit", "publication_commit"}
            for _, stage, _ in self.pending.values()
        )
        for job in ordered:
            if len(self.pending) >= self.max_workers:
                return
            if job.state == "assembled" and not writer_busy:
                self._submit(
                    writer,
                    job,
                    "publication_commit",
                    publish_date,
                    project_root=self.weather.root,
                    database_url=self.weather.preflight.database_url,
                    run_key=job.run_key,
                    model_id=self.weather.model_id,
                    ids=BundleIds(**job.predictor_ids),
                    clock=self.clock,
                )
                job.state, writer_busy = "publishing", True
            elif job.state == "prepared" and not writer_busy:
                self._submit(writer, job, "weather_commit", self.weather.persist, job.prepared)
                job.state, writer_busy = "persisting", True
            elif job.state == "predicting":
                for kind in PREDICTORS:
                    if kind not in job.started_predictors and len(self.pending) < self.max_workers:
                        self._submit(
                            processes,
                            job,
                            kind,
                            run_predictor,
                            kind,
                            job.run_key,
                            self.weather.model_id,
                            self.weather.root,
                            self.weather.preflight.database_url,
                            self.weather.checkpoints,
                        )
                        job.started_predictors.add(kind)
            elif job.state == "ready" and (
                job.role != "visible_fallback" or not self._newer_active(job)
            ):
                self._dispatch_ready(job, threads)

    def _drain(self, mode: str) -> None:
        for future, (job, stage, started) in list(self.pending.items()):
            if not future.done():
                continue
            del self.pending[future]
            ended = self.clock()
            job.timings.setdefault(stage, []).append(
                {
                    "started_at_utc": utc_text(started),
                    "finished_at_utc": utc_text(ended),
                    "elapsed_seconds": (ended - started).total_seconds(),
                }
            )
            try:
                result = future.result()
            except Exception as error:  # noqa: BLE001 - keep independent worker failures per date
                if (
                    stage == "weather"
                    and mode != "run_keys"
                    and getattr(error, "kind", None) == "source_changed"
                    and job.replacement_checks < 1
                ):
                    job.replacement_checks += 1
                    job.force_probe = True
                    job.error("waiting", error)
                elif job.state not in TERMINAL:
                    job.error("failed", error)
                continue
            if job.state in TERMINAL:
                continue
            if stage == "weather":
                job.prepared, reused = result
                job.reused.update(reused)
                job.state = "prepared"
            elif stage == "weather_commit":
                job.prepared = None
                job.reserved_bytes = 0
                if result:
                    job.reused.add("weather_commit")
                job.state = "predicting"
            elif stage == "publication_commit":
                job.complete(result)
            else:
                artifact_id, reused = result
                job.predictor_ids[stage] = artifact_id
                if reused:
                    job.reused.add(stage)
                if len(job.predictor_ids) == len(PREDICTORS):
                    job.state = "assembled"
        self._release_finished()

    def _release_finished(self) -> None:
        active = {job for job, _, _ in self.pending.values()}
        for job in self.jobs:
            if job.lock is not None and job not in active and job.state in TERMINAL | {"waiting"}:
                job.lock.close()
                job.lock = None
                job.reserved_bytes = 0

    def run(self, threads, processes, writer, *, issue_date=None, run_keys=()) -> tuple[int, dict]:
        mode = self._start(issue_date, run_keys)
        try:
            while True:
                now = self.clock()
                if (
                    mode == "automatic"
                    and not self.primary
                    and now >= self.opening
                    and any(job.state not in TERMINAL for job in self.jobs)
                ):
                    self._add_primary(self.today)
                    self.next_poll = now
                self._drain(mode)
                self._check_primary(now, repeating=mode == "automatic")
                self._check_fallback()
                self._dispatch(threads, processes, writer)
                if not self.pending and all(job.state in TERMINAL for job in self.jobs):
                    break
                wake = self.next_poll
                if mode == "automatic" and not self.primary:
                    wake = self.opening
                if self.pending or wake is not None:
                    seconds = max(0.0, (wake - self.clock()).total_seconds()) if wake else None
                    # Re-enter dispatch immediately when a weather-free admission
                    # changed a ready job into a predictor job.
                    can_dispatch = (
                        any(
                            job.state == "predicting" and not job.started_predictors
                            for job in self.jobs
                        )
                        and len(self.pending) < self.max_workers
                    )
                    if not can_dispatch:
                        self.wait_for_progress(tuple(self.pending), seconds)
        finally:
            # Normally no futures remain. On interruption wait for raw users to
            # exit their worker before dropping its per-run lock.
            if self.pending:
                wait(tuple(self.pending))
            for job in self.jobs:
                if job.lock is not None:
                    job.lock.close()
        primary_ok = all(job.publication is not None for job in self.primary.values())
        explicit_ok = all(
            job.publication is not None for job in self.jobs if job.role == "explicit"
        )
        visible_ok = all(
            job.publication is not None or self._covered(job)
            for job in self.jobs
            if job.role == "visible_fallback"
        )
        finished = self.clock()
        status = 0 if primary_ok and explicit_ok and visible_ok else 1
        return status, {
            "mode": mode,
            "status": "complete" if status == 0 else "incomplete",
            "model_id": self.weather.model_id,
            "started_at_utc": utc_text(self.started),
            "finished_at_utc": utc_text(finished),
            "elapsed_seconds": (finished - self.started).total_seconds(),
            "issue_local_date": (issue_date or self.today).isoformat()
            if mode != "run_keys"
            else None,
            "jobs": [job.report() for job in self.jobs],
            "visible_publications_at_start": {
                target.isoformat(): {
                    "run_key": admission.run_key,
                    "cycle_reference_utc": admission.horizon.cycle,
                    **asdict(admission.publication),
                }
                for target, admission in self.visible.items()
            },
        }
