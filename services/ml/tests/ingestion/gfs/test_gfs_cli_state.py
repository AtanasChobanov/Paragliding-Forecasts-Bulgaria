from __future__ import annotations

from types import SimpleNamespace

from paragliding_forecasts_ml.ingestion.atmosphere.contracts import ArtifactReference
from paragliding_forecasts_ml.ingestion.gfs import cli, parser_cli

RUN_KEY = "99999999-9999-4999-8999-999999999999"


def _reference(key: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_key=f"{key}_manifest",
        relative_path=f"data/{key}/manifest.json",
        sha256="a" * 64,
        byte_count=1,
        media_type="application/json",
    )


def test_collect_initializes_ledger_and_records_verified_raw_boundary(
    tmp_path, monkeypatch
) -> None:
    raw = _reference("raw")
    initialized: list[str] = []
    appended: list[dict[str, object]] = []
    store = SimpleNamespace(
        verify_raw_manifest=lambda reference: SimpleNamespace(status="complete")
    )

    class FakeLedger:
        def __init__(self, actual_store) -> None:
            assert actual_store is store

        def initialize(self, *, occurred_at_utc: str) -> None:
            initialized.append(occurred_at_utc)

        def append(self, **values) -> None:
            appended.append(values)

    monkeypatch.setattr(cli, "uuid4", lambda: RUN_KEY)
    monkeypatch.setattr(cli, "UrllibTransport", lambda: object())
    monkeypatch.setattr(cli, "RetryingTransport", lambda transport: transport)
    monkeypatch.setattr(
        cli, "GfsPlanner", lambda _transport: SimpleNamespace(plan=lambda *_a, **_k: object())
    )
    monkeypatch.setattr(cli.WeatherArtifactStore, "create_fresh", lambda *_a, **_k: store)
    monkeypatch.setattr(
        cli, "GfsCollector", lambda _transport: SimpleNamespace(fetch=lambda *_a: raw)
    )
    monkeypatch.setattr(cli, "RunStateLedger", FakeLedger)

    result = cli.main(
        [
            "--valid-at",
            "2026-08-21T07:00:00Z",
            "--explicit-run-at",
            "2026-08-21T00:00:00Z",
            "--purpose",
            "historical_forecast",
            "--project-root",
            str(tmp_path),
            "--allow-live-network",
        ]
    )

    assert result == 0
    assert len(initialized) == 1
    assert appended[0]["stage"] == "raw_complete"
    assert appended[0]["disposition"] == "complete"
    assert appended[0]["evidence"] == raw


def test_parse_records_parsed_and_normalized_boundaries(tmp_path, monkeypatch) -> None:
    raw = _reference("raw")
    parsed = _reference("parsed")
    normalized = _reference("normalized")
    events = [SimpleNamespace(stage="raw_complete", disposition="complete", evidence=raw)]
    appended: list[dict[str, object]] = []
    store = object()

    class FakeLedger:
        def __init__(self, actual_store) -> None:
            assert actual_store is store

        def load_events(self):
            return tuple(events)

        def append(self, **values) -> None:
            appended.append(values)
            events.append(
                SimpleNamespace(
                    stage=values["stage"],
                    disposition=values["disposition"],
                    evidence=values["evidence"],
                )
            )

    monkeypatch.setattr(parser_cli, "WeatherArtifactStore", lambda *_a, **_k: store)
    monkeypatch.setattr(parser_cli, "RunStateLedger", FakeLedger)
    monkeypatch.setattr(parser_cli, "raw_manifest_reference", lambda _store: raw)
    monkeypatch.setattr(parser_cli, "parse", lambda *_a, **_k: parsed)
    monkeypatch.setattr(parser_cli, "normalize", lambda *_a, **_k: normalized)

    result = parser_cli.main(["--run-key", RUN_KEY, "--project-root", str(tmp_path)])

    assert result == 0
    assert [item["stage"] for item in appended] == ["parsed", "normalized"]
    assert appended[0]["evidence"] == parsed
    assert appended[1]["evidence"] == normalized


def test_parse_resume_reuses_existing_parsed_evidence(tmp_path, monkeypatch) -> None:
    raw = _reference("raw")
    parsed = _reference("parsed")
    normalized = _reference("normalized")
    events = (
        SimpleNamespace(stage="raw_complete", disposition="complete", evidence=raw),
        SimpleNamespace(stage="parsed", disposition="complete", evidence=parsed),
    )
    appended: list[dict[str, object]] = []

    class FakeLedger:
        def __init__(self, _store) -> None:
            pass

        def load_events(self):
            return events

        def append(self, **values) -> None:
            appended.append(values)

    monkeypatch.setattr(parser_cli, "WeatherArtifactStore", lambda *_a, **_k: object())
    monkeypatch.setattr(parser_cli, "RunStateLedger", FakeLedger)
    monkeypatch.setattr(parser_cli, "raw_manifest_reference", lambda _store: raw)
    monkeypatch.setattr(
        parser_cli,
        "parse",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("parse must not rerun")),
    )
    monkeypatch.setattr(
        parser_cli,
        "normalize",
        lambda _store, evidence, **_k: normalized if evidence == parsed else None,
    )

    result = parser_cli.main(["--run-key", RUN_KEY, "--project-root", str(tmp_path)])

    assert result == 0
    assert [item["stage"] for item in appended] == ["normalized"]
