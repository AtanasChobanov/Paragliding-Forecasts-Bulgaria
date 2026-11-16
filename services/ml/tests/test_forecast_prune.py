"""Operational cleanup of disposable forecast evidence."""

from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from sqlite3 import connect
from types import SimpleNamespace
from uuid import uuid4

import pytest

from paragliding_forecasts_ml.ingestion.atmosphere.catalogue import load_catalogue
from paragliding_forecasts_ml.ingestion.atmosphere.contracts import RawManifest, RequestPlan
from paragliding_forecasts_ml.ingestion.gfs.models import GFS_SOURCE_ID
from paragliding_forecasts_ml.ingestion.weather import artifact_audit, operational_retention
from paragliding_forecasts_ml.ingestion.weather.artifacts import ArtifactError, WeatherArtifactStore
from paragliding_forecasts_ml.ingestion.weather.state import RunStateLedger
from paragliding_forecasts_ml.predictions.publication import prune
from paragliding_forecasts_ml.predictions.publication.checkpoints import Checkpoints
from paragliding_forecasts_ml.storage.file_lock import file_lock, weather_run_lock

STAMP = "2026-11-16T23:05:14Z"
URL = "file:./data/local/test.db"


@pytest.fixture
def raw_run(tmp_path):
    store = WeatherArtifactStore.create_fresh(str(uuid4()), project_root=tmp_path)
    ledger = RunStateLedger(store)
    ledger.initialize(occurred_at_utc=STAMP)
    gribs = tuple(
        store.write_raw_bytes(f"grib_{i}", f"{i}.grib2", b"GRIB", media_type="application/x-grib2")
        for i in (1, 2)
    )
    index = store.write_raw_bytes("idx", "gfs.idx", b"index", media_type="text/plain")
    catalogue = load_catalogue()
    plan = store.write_request_plan(
        RequestPlan(
            run_key=store.run_key,
            source_id=GFS_SOURCE_ID,
            source_kind="forecast",
            ingestion_method="public_object_archive",
            request_purpose="operational_forecast",
            catalogue_version=catalogue.version,
            catalogue_sha256=catalogue.sha256,
            adapter_request_schema_version=1,
            adapter_request={"fixture": True},
            expected_artifact_keys=("grib_1", "grib_2", "idx"),
            created_at_utc=STAMP,
        )
    )
    ref = store.write_raw_manifest(
        RawManifest(
            run_key=store.run_key,
            source_id=GFS_SOURCE_ID,
            source_kind="forecast",
            collector_version="gfs-collector/1",
            request_plan=plan,
            source_product_key="test",
            source_url="https://example.test",
            permission_basis="test",
            permission_reference="test",
            retrieved_at_utc=STAMP,
            valid_from_utc=STAMP,
            valid_to_utc=STAMP,
            artifacts=(*gribs, index),
            status="complete",
            completed_at_utc=STAMP,
        )
    )
    ledger.append(
        invocation_mode="resume",
        stage="raw_complete",
        disposition="complete",
        occurred_at_utc=STAMP,
        evidence=ref,
    )
    return store, ref, gribs


def test_prune_recovers_partial_removal_and_retains_compact_audit(raw_run, monkeypatch):
    store, ref, gribs = raw_run
    targets = [store.project_root / item.relative_path for item in gribs]
    expected = (ref.relative_path, ref.sha256)
    unlink = Path.unlink

    def interrupt(path, *args, **kwargs):
        if path == targets[1]:
            raise OSError("simulated interruption after first unlink")
        return unlink(path, *args, **kwargs)

    with monkeypatch.context() as patched:
        patched.setattr(Path, "unlink", interrupt)
        with pytest.raises(OSError, match="interruption"):
            prune._prune_payloads(store, expected)
    assert not targets[0].exists() and targets[1].is_file()
    assert (store.raw_dir / operational_retention.INTENT).is_file()
    with pytest.raises(ArtifactError, match="incomplete"):
        operational_retention.pruned_gribs(store, ref.sha256)

    assert prune._prune_payloads(store, expected) == ("pruned", 4)
    assert prune._prune_payloads(store, expected) == ("already_pruned", 0)
    assert not any(target.exists() for target in targets)
    assert (store.raw_dir / "payloads/gfs.idx").is_file()
    assert (store.raw_dir / "request-plan.json").is_file()
    skipped = operational_retention.pruned_gribs(store, ref.sha256)
    assert (
        artifact_audit.audit_weather_artifacts(
            store.run_key, scope="effective", project_root=store.project_root, pruned_raw=skipped
        )["verified_boundary_count"]
        == 1
    )
    with pytest.raises(ArtifactError):
        artifact_audit.audit_weather_artifacts(
            store.run_key, scope="effective", project_root=store.project_root
        )
    (store.raw_dir / "payloads/gfs.idx").unlink()
    with pytest.raises(ArtifactError):
        artifact_audit.audit_weather_artifacts(
            store.run_key, scope="effective", project_root=store.project_root, pruned_raw=skipped
        )


def test_accidental_missing_or_symlink_aborts_before_intent(raw_run, tmp_path):
    store, ref, gribs = raw_run
    victim = store.project_root / gribs[0].relative_path
    victim.unlink()
    with pytest.raises(FileNotFoundError):
        prune._prune_payloads(store, (ref.relative_path, ref.sha256))
    foreign = tmp_path / "outside.grib2"
    foreign.write_bytes(b"GRIB")
    victim.symlink_to(foreign)
    with pytest.raises(ArtifactError, match="symlink"):
        prune._prune_payloads(store, (ref.relative_path, ref.sha256))
    assert foreign.read_bytes() == b"GRIB"
    assert not (store.raw_dir / operational_retention.INTENT).exists()


def test_prune_boundary_active_and_historical_with_disposable_database(raw_run, monkeypatch):
    store, ref, _ = raw_run
    root = store.project_root
    key = store.run_key
    historical = str(uuid4())
    database = root / "data/local/test.db"
    database.parent.mkdir(parents=True)
    with closing(connect(database)) as db, db:
        db.execute(
            "CREATE TABLE weather_ingestion_runs(run_key TEXT,status TEXT,request_purpose TEXT)"
        )
        db.execute(
            "CREATE TABLE prediction_runs(id INTEGER,weather_ingestion_run_id INTEGER,xc_model_id TEXT,created_at_utc TEXT)"
        )
        db.executemany(
            "INSERT INTO weather_ingestion_runs VALUES(?,'succeeded',?)",
            [(key, "operational_forecast"), (historical, "historical_forecast")],
        )
        db.execute("INSERT INTO prediction_runs VALUES(1,1,'model',?)", (STAMP,))
    checkpoints = Checkpoints.for_database(root, database)
    checkpoints.marker(key).parent.mkdir(parents=True)
    monkeypatch.setattr(prune, "require_schema", lambda _: None)
    monkeypatch.setattr(prune.Checkpoints, "mark_managed", lambda *_: None)
    monkeypatch.setattr(
        prune,
        "read_weather",
        lambda *_: SimpleNamespace(
            id=1, horizon=None, raw_manifest=(ref.relative_path, ref.sha256)
        ),
    )
    monkeypatch.setattr(prune, "existing_publication", lambda *_: object())
    cutoff = datetime.fromisoformat(STAMP).astimezone(UTC) + timedelta(hours=48)
    assert prune.prune(root, URL, cutoff)["pruned_runs"] == []
    for run_key in (key, historical):
        checkpoints.marker(run_key).touch()

    before = prune.prune(root, URL, cutoff - timedelta(seconds=1))
    assert {entry["reason"] for entry in before["skipped_runs"]} == {
        "no_publication_at_least_48_hours_old",
        "non_operational",
    }
    with file_lock(weather_run_lock(root, key)):
        locked = prune.prune(root, URL, cutoff)
    assert {entry["reason"] for entry in locked["skipped_runs"]} == {
        "active_run",
        "non_operational",
    }
    result = prune.prune(root, URL, cutoff)
    assert result["errors"] == [] and result["freed_bytes"] == 8
    assert result["pruned_runs"][0]["run_key"] == key
