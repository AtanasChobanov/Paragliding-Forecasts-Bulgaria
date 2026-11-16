"""Exercise the forecast coordinator against a synthetic time and source inventory."""

import json
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.utils import format_datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from paragliding_forecasts_ml.ingestion.gfs.inventory import GfsSelector
from paragliding_forecasts_ml.ingestion.gfs.planner import GfsPlanner, GfsPlanningError
from paragliding_forecasts_ml.ingestion.gfs.transport import HttpResponse, HttpTransport
from paragliding_forecasts_ml.ingestion.weather.pipeline import WeatherPreflight
from paragliding_forecasts_ml.predictions.publication import orchestration, predictors, weather_jobs
from paragliding_forecasts_ml.predictions.publication.checkpoints import Checkpoints
from paragliding_forecasts_ml.predictions.publication.store import Publication
from paragliding_forecasts_ml.predictions.publication.weather import (
    SOFIA,
    ForecastHorizon,
    utc_text,
)
from paragliding_forecasts_ml.predictions.publication.weather_jobs import (
    Admission,
    ForecastJobError,
    WeatherJobs,
)

MODEL = "a" * 64
TODAY = date(2026, 6, 2)
YESTERDAY = TODAY - timedelta(days=1)


def run_key(horizon):
    return str(UUID(int=horizon.issue_date.toordinal() * 3 + horizon.days, version=4))


@dataclass
class Clock:
    now: datetime

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


class Backend:
    model_id = MODEL
    checkpoints = None
    preflight = SimpleNamespace(database_url="sqlite-test")

    def __init__(self, root, clock):
        self.root = root
        self.clock = clock
        self.calls = []
        self.checks = []
        self.finished_weather = set()
        self.preexisting = {}
        self.delayed = set()
        self.missing = set()
        self.disk_by_horizon = {}
        self.replace = None
        self.live_calls = 0

    def visible(self, target):
        return self.preexisting.get(target)

    def select_run(self, key):
        if key not in self.preexisting:
            raise ValueError("unknown test run")
        return self.preexisting[key]

    def probe(self, horizon):
        self.checks.append((horizon, self.clock()))
        if horizon in self.preexisting:
            return self.preexisting[horizon]
        self.live_calls += 1
        if horizon in self.missing or (
            horizon in self.delayed and self.clock().strftime("%H:%M") < "16:00"
        ):
            raise ForecastJobError("absent_file", "A required GRIB is missing.")
        return Admission(run_key(horizon), horizon, self.disk_by_horizon.get(horizon, 1), True)

    def admit(self, admission):
        self.calls.append(("admit", admission.run_key))

    def prepare(self, admission):
        self.calls.append(("weather", admission.run_key))
        if self.replace == admission.horizon:
            self.replace = None
            raise ForecastJobError("source_changed", "Pinned ETag was replaced.")
        return admission.run_key, ()

    def persist(self, key):
        self.calls.append(("weather_commit", key))
        self.finished_weather.add(key)
        return False

    def predict(self, kind, key, *args):
        assert key in self.finished_weather
        self.calls.append((kind, key))
        return kind, False

    def publish(self, **kwargs):
        key = kwargs["run_key"]
        for kind in predictors.PREDICTORS:
            assert (kind, key) in self.calls
        self.calls.append(("publication_commit", key))
        return Publication(len(self.calls), utc_text(self.clock()), False)


class FakePool:
    """Complete synthetic work immediately or hold its result until the clock is advanced."""

    def __init__(self):
        self.hold = {}
        self.results = {}

    def submit(self, function, *args, **kwargs):
        future = Future()

        def apply():
            try:
                future.set_result(function(*args, **kwargs))
            except (RuntimeError, ValueError) as error:
                future.set_exception(error)

        name = function.__name__
        key = args[0].run_key if name == "prepare" else None
        delay = self.hold.get(key)
        if delay is not None:
            self.results[future] = delay, apply
        else:
            apply()
        return future


def setup(tmp_path, monkeypatch, start, *, max_workers=5, free=100):
    clock = Clock(datetime.fromisoformat(f"{TODAY}T{start}").replace(tzinfo=SOFIA))
    backend = Backend(tmp_path, clock)
    pool = FakePool()
    max_active = []

    def wait(futures, timeout):
        max_active.append(len(futures))
        assert len(futures) <= max_workers
        if any(future.done() for future in futures):
            return
        delay = min(
            (
                (done - clock()).total_seconds()
                for future in futures
                for done, _ in [pool.results[future]]
            ),
            default=float("inf"),
        )
        pause = min(delay, timeout if timeout is not None else float("inf"))
        assert pause != float("inf")
        clock.advance(pause)
        for future in futures:
            if future in pool.results and pool.results[future][0] <= clock():
                _, apply = pool.results.pop(future)
                apply()

    monkeypatch.setattr(orchestration, "run_predictor", backend.predict)
    monkeypatch.setattr(orchestration, "publish_date", backend.publish)
    schedule = orchestration.ForecastSchedule(
        backend,
        started=clock(),
        clock=clock,
        max_workers=max_workers,
        free_bytes=lambda: free,
        wait_for_progress=wait,
    )
    return clock, backend, pool, schedule, max_active


def test_before_13_fills_visible_dates_and_exits_when_finished(tmp_path, monkeypatch):
    clock, backend, pool, schedule, _ = setup(tmp_path, monkeypatch, "11:00:00")
    status, report = schedule.run(pool, pool, pool)
    assert status == 0 and clock().hour == 11
    assert [horizon for horizon, _ in backend.checks] == [
        ForecastHorizon(YESTERDAY, days) for days in (1, 2, 3)
    ]
    assert all(job["status"] == "published" for job in report["jobs"])


def test_active_morning_work_crosses_13_and_newer_jobs_get_priority(tmp_path, monkeypatch):
    clock, backend, pool, schedule, _ = setup(tmp_path, monkeypatch, "12:59:00", max_workers=1)
    first = ForecastHorizon(YESTERDAY, 1)
    pool.hold[run_key(first)] = clock() + timedelta(minutes=2)
    status, report = schedule.run(pool, pool, pool)
    assert status == 0
    assert (
        ForecastHorizon(TODAY, 1),
        datetime.combine(TODAY, orchestration.time(13), SOFIA),
    ) in backend.checks
    assert [job["status"] for job in report["jobs"][:3]] == ["published", "covered", "covered"]
    assert [stage for stage, key in backend.calls if key == run_key(first)][
        -1
    ] == "publication_commit"


def test_afternoon_polls_during_busy_work_and_checks_at_16(tmp_path, monkeypatch):
    clock, backend, pool, schedule, active = setup(tmp_path, monkeypatch, "15:21:00", max_workers=2)
    first = ForecastHorizon(TODAY, 1)
    delayed = ForecastHorizon(TODAY, 2)
    pool.hold[run_key(first)] = clock() + timedelta(minutes=45)
    backend.delayed.add(delayed)
    status, report = schedule.run(pool, pool, pool)
    assert status == 0
    assert [stamp.strftime("%H:%M") for horizon, stamp in backend.checks if horizon == delayed] == [
        "15:21",
        "15:36",
        "15:51",
        "16:00",
    ]
    assert max(active) == 2
    assert any(job["cycle_reference_utc"] == f"{YESTERDAY}T06:00:00Z" for job in report["jobs"])


def test_after_16_checks_today_once_then_only_uncovered_visible_dates(tmp_path, monkeypatch):
    _, backend, pool, schedule, _ = setup(tmp_path, monkeypatch, "20:11:00")
    status, report = schedule.run(pool, pool, pool)
    assert status == 0
    assert [horizon for horizon, _ in backend.checks] == [
        ForecastHorizon(TODAY, 1),
        ForecastHorizon(TODAY, 2),
        ForecastHorizon(TODAY, 3),
        ForecastHorizon(YESTERDAY, 1),
    ]
    assert any(job["deadline_met"] is False for job in report["jobs"])


def test_dated_scope_handles_replacement_and_leaves_other_dates_committed(tmp_path, monkeypatch):
    _, backend, pool, schedule, _ = setup(tmp_path, monkeypatch, "15:22:00")
    replaced = ForecastHorizon(YESTERDAY, 1)
    backend.replace = replaced
    backend.missing.add(ForecastHorizon(YESTERDAY, 2))
    status, report = schedule.run(pool, pool, pool, issue_date=YESTERDAY)
    assert status == 1
    assert len(report["jobs"]) == 3
    assert [row["status"] for row in report["jobs"]] == ["published", "unavailable", "published"]
    assert [
        stamp.strftime("%H:%M") for horizon, stamp in backend.checks if horizon == replaced
    ] == [
        "15:22",
        "15:22",
    ]


def test_disk_blocks_only_the_horizon_without_space_and_completed_pairs_skip_work(
    tmp_path, monkeypatch
):
    _, backend, pool, schedule, _ = setup(tmp_path, monkeypatch, "20:15:00", free=5, max_workers=1)
    blocked, complete = ForecastHorizon(TODAY, 1), ForecastHorizon(TODAY, 2)
    backend.disk_by_horizon[blocked] = 6
    old = Publication(42, "2026-06-02T15:00:00Z", True)
    backend.preexisting[complete] = Admission(run_key(complete), complete, publication=old)
    status, report = schedule.run(pool, pool, pool, issue_date=TODAY)
    assert status == 1
    assert report["jobs"][0]["reason"] == "insufficient_disk_space"
    assert report["jobs"][1]["publication"] == {
        "id": 42,
        "created_at_utc": old.created_at_utc,
        "reused": True,
    }
    assert report["jobs"][2]["status"] == "published"
    assert all(key != run_key(complete) for _, key in backend.calls)
    assert backend.live_calls == 2


class Metadata(HttpTransport):
    def __init__(self, horizon, *, over_seconds=0, body_override=None):
        self.horizon = horizon
        self.over_seconds = over_seconds
        self.body_override = body_override
        self.calls = []

    def request(self, url, *, method="GET", headers=None):
        self.calls.append((url, method))
        cutoff = datetime.fromisoformat(self.horizon.cutoff)
        headers = {"Content-Length": "20", "ETag": '"verified"'}
        headers["Last-Modified"] = format_datetime(cutoff, usegmt=True)
        if method == "HEAD":
            return HttpResponse(200, headers, b"")
        headers["Last-Modified"] = format_datetime(
            cutoff + timedelta(seconds=self.over_seconds), usegmt=True
        )
        lead = int(url.split(".idx")[0].rsplit(".f", 1)[1])
        issue = self.horizon.issue_date
        body = f"1:0:d={issue:%Y%m%d}06:TMP:2 m above ground:{lead} hour fcst:\n".encode()
        return HttpResponse(
            200, headers, body if self.body_override is None else self.body_override
        )


@pytest.mark.parametrize(
    ("issue", "first_hour", "cutoff_hour"), [(date(2026, 1, 5), "08", "14"), (TODAY, "07", "13")]
)
def test_pinned_metadata_cutoff_and_exact_hours_across_dst(
    tmp_path, monkeypatch, issue, first_hour, cutoff_hour
):
    horizon = ForecastHorizon(issue, 1)
    now = datetime.combine(issue, orchestration.time(19), SOFIA)
    preflight = WeatherPreflight("fake", "a" * 64, "b" * 64, "gfs-compact-grid/1")
    checks = Checkpoints(tmp_path / "checkpoints")
    monkeypatch.setattr(WeatherJobs, "_connection", lambda _: FakeDatabase())
    monkeypatch.setattr(weather_jobs, "candidate_weather_runs", lambda *_: ())
    monkeypatch.setattr(
        weather_jobs,
        "GfsPlanner",
        lambda transport: GfsPlanner(
            transport, selectors=(GfsSelector("tmp_2m", "TMP", "2 m above ground"),)
        ),
    )
    transport = Metadata(horizon)
    weather = WeatherJobs(
        tmp_path, preflight, None, checks, MODEL, 2048 * 2**20, transport, None, lambda: now
    )
    admission = weather.probe(horizon)
    assert horizon.cutoff[11:13] == cutoff_hour
    assert horizon.hours[0][11:13] == first_hour
    assert len(transport.calls) == 22
    weather.admit(admission)
    assert weather.probe(horizon).run_key == admission.run_key
    weather.metadata = Metadata(horizon, over_seconds=1)
    with pytest.raises(ForecastJobError) as failure:
        weather.probe(horizon)
    assert failure.value.kind == "late_source"
    weather.metadata = Metadata(horizon, body_override=b"broken index")
    with pytest.raises(GfsPlanningError) as failure:
        weather.probe(horizon)
    assert failure.value.kind == "source_contract_mismatch"


class FakeDatabase:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_recover_completed_predictor_after_crash_before_checkpoint(tmp_path, monkeypatch):
    key = run_key(ForecastHorizon(TODAY, 1))
    artifact_id = "d" * 64
    directory = tmp_path / "data/processed/xc-probability/prediction" / artifact_id
    directory.mkdir(parents=True)
    (directory / "prediction.json").write_text(json.dumps({"run_keys": [key], "model_id": MODEL}))
    checkpoints = Checkpoints(tmp_path / "checkpoint")
    verified = []
    monkeypatch.setattr(predictors, "_verify", lambda *args: verified.append(args))
    monkeypatch.setattr(
        predictors, "predict_runs", lambda **_: pytest.fail("Recomputed retained predictor")
    )
    assert predictors.run_predictor("xc", key, MODEL, tmp_path, "fake", checkpoints) == (
        artifact_id,
        True,
    )
    assert verified == [("xc", artifact_id, key, MODEL, tmp_path)]
    assert checkpoints.load_prediction(key, MODEL, "xc") == artifact_id
