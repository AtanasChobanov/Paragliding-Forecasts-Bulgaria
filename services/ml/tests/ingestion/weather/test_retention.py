"""Cold copy verification and reversible raw eviction on disposable files."""

from __future__ import annotations

from uuid import uuid4

import pytest

from paragliding_forecasts_ml.ingestion.weather import retention


def test_archive_eviction_and_restore_require_verified_cold_bytes(tmp_path, monkeypatch) -> None:
    root = tmp_path / "working"
    volume = tmp_path / "cold"
    volume.mkdir()
    run_key = str(uuid4())
    raw = root / "data/raw/weather" / run_key
    interim = root / "data/interim/weather" / run_key
    (raw / "payloads").mkdir(parents=True)
    interim.mkdir(parents=True)
    (raw / "payloads" / "a.grib2").write_bytes(b"selected global GRIB bytes")
    (raw / "manifest.json").write_bytes(b"raw-manifest")
    (interim / "features.json").write_bytes(b"compact-features")
    monkeypatch.setattr(retention, "_volume", lambda _root, dest: (dest.resolve(), "volume-test"))
    monkeypatch.setattr(retention, "audit_weather_artifacts", lambda *_a, **_k: {"ok": True})
    monkeypatch.setattr(
        retention,
        "_database_graph",
        lambda *_a, **_k: {"graph_sha256": "a" * 64, "raw_manifest_sha256": "b" * 64},
    )

    archived = retention.archive_run(run_key, destination=volume, project_root=root)
    assert archived["state"] == "archived_verified"
    cold_payload = volume / "weather-archives" / run_key / "raw/payloads/a.grib2"
    cold_payload.write_bytes(b"damaged")
    with pytest.raises(retention.RetentionError, match="hash differs"):
        retention.evict_local(run_key, destination=volume, project_root=root)
    assert (raw / "payloads/a.grib2").exists()
    cold_payload.write_bytes(b"selected global GRIB bytes")
    evicted = retention.evict_local(run_key, destination=volume, project_root=root)
    assert evicted["evicted_bytes"] == len(b"selected global GRIB bytes")
    assert not (raw / "payloads/a.grib2").exists()
    assert retention.audit_compact(run_key, project_root=root)["state"] == "archived_verified"
    restored = retention.restore_run(run_key, destination=volume, project_root=root)
    assert restored["state"] == "restored_full"
    assert (raw / "payloads/a.grib2").read_bytes() == cold_payload.read_bytes()
    assert retention.audit_compact(run_key, project_root=root)["state"] == "restored_full"
