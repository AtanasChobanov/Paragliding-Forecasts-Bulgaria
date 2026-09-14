from __future__ import annotations

from types import SimpleNamespace

from paragliding_forecasts_ml.ingestion.atmosphere.contracts import ArtifactReference
from paragliding_forecasts_ml.ingestion.weather import services

RUN_KEY = "99999999-9999-4999-8999-999999999999"


def _reference(key: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_key=f"{key}_manifest",
        relative_path=f"data/interim/weather/{RUN_KEY}/{key}/stage-manifest.json",
        sha256={"raw": "a", "parsed": "b", "normalized": "c"}[key] * 64,
        byte_count=1,
        media_type="application/json",
    )


class _Snapshot:
    def __init__(self, events: dict[str, object], generation: int = 0) -> None:
        self.events = events
        self.generation = generation

    def effective_event(self, stage: str):
        return self.events.get(stage)


def test_context_open_creates_one_session_and_loads_ledger_once(tmp_path, monkeypatch) -> None:
    verification = object()
    store = object()
    snapshot = object()
    loads: list[None] = []

    class FakeLedger:
        def __init__(self, actual_store) -> None:
            assert actual_store is store

        def load_state(self):
            loads.append(None)
            return snapshot

    monkeypatch.setattr(
        services,
        "ArtifactVerificationSession",
        lambda *, project_root, run_key: verification,
    )

    def open_store(run_key, *, project_root, verification_session):
        assert run_key == RUN_KEY
        assert project_root == tmp_path.resolve()
        assert verification_session is verification
        return store

    monkeypatch.setattr(services, "WeatherArtifactStore", open_store)
    monkeypatch.setattr(services, "RunStateLedger", FakeLedger)

    context = services.WeatherRunContext.open(
        RUN_KEY,
        project_root=tmp_path,
        database_url="file:./data/local/weather.db",
    )

    assert context.verification is verification
    assert context.store is store
    assert context.snapshot is snapshot
    assert len(loads) == 1


def test_parse_and_normalize_carries_each_appended_snapshot(monkeypatch, tmp_path) -> None:
    raw = _reference("raw")
    parsed = _reference("parsed")
    normalized = _reference("normalized")
    raw_event = SimpleNamespace(sequence=2, disposition="complete", evidence=raw)
    initial = _Snapshot({"raw_complete": raw_event})
    appended_from: list[_Snapshot] = []

    class FakeLedger:
        def append_to(self, snapshot, **values):
            appended_from.append(snapshot)
            stage = values["stage"]
            updated_events = dict(snapshot.events)
            event = SimpleNamespace(
                sequence=len(updated_events) + 2,
                disposition=values["disposition"],
                evidence=values["evidence"],
            )
            updated_events[stage] = event
            return event, _Snapshot(updated_events, snapshot.generation + 1)

    store = SimpleNamespace(verify_raw_manifest=lambda reference: reference)
    context = SimpleNamespace(
        snapshot=initial,
        store=store,
        ledger=FakeLedger(),
        project_root=tmp_path,
        require_database_url=lambda: "file:./data/local/weather.db",
    )
    monkeypatch.setattr(services, "raw_manifest_reference", lambda actual: raw)
    monkeypatch.setattr(services, "parse", lambda *_a, **_k: parsed)
    monkeypatch.setattr(services, "normalize", lambda *_a, **_k: normalized)

    result, final = services.parse_and_normalize(context)

    assert result.parser_disposition == "created"
    assert result.normalizer_disposition == "created"
    assert [snapshot.generation for snapshot in appended_from] == [0, 1]
    assert final.generation == 2
    assert final.effective_event("normalized").evidence == normalized


def test_parse_and_normalize_reuses_effective_current_boundaries(monkeypatch, tmp_path) -> None:
    raw = _reference("raw")
    parsed = _reference("parsed")
    normalized = _reference("normalized")
    snapshot = _Snapshot(
        {
            "raw_complete": SimpleNamespace(sequence=2, disposition="complete", evidence=raw),
            "parsed": SimpleNamespace(sequence=3, disposition="complete", evidence=parsed),
            "normalized": SimpleNamespace(sequence=4, disposition="complete", evidence=normalized),
        }
    )

    def manifest(reference):
        if reference == parsed:
            return SimpleNamespace(
                stage="parser", producer_version=services.GFS_PARSER_VERSION, inputs=(raw,)
            )
        return SimpleNamespace(
            stage="normalizer",
            producer_version=services.GFS_NORMALIZER_VERSION,
            inputs=(parsed,),
        )

    context = SimpleNamespace(
        snapshot=snapshot,
        store=SimpleNamespace(
            verify_raw_manifest=lambda reference: reference,
            read_stage_manifest=manifest,
        ),
        ledger=SimpleNamespace(
            append_to=lambda *_a, **_k: (_ for _ in ()).throw(
                AssertionError("matching boundaries must not append")
            )
        ),
        project_root=tmp_path,
        require_database_url=lambda: "file:./data/local/weather.db",
    )
    monkeypatch.setattr(services, "raw_manifest_reference", lambda actual: raw)
    monkeypatch.setattr(
        services,
        "parse",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("parser must be reused")),
    )
    monkeypatch.setattr(
        services,
        "normalize",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("normalizer must be reused")),
    )

    result, final = services.parse_and_normalize(context)

    assert result.parser_disposition == "reused"
    assert result.normalizer_disposition == "reused"
    assert final is snapshot
