from __future__ import annotations

from types import SimpleNamespace

from paragliding_forecasts_ml.ingestion.atmosphere.contracts import ArtifactReference
from paragliding_forecasts_ml.ingestion.weather import feature_cli

RUN_KEY = "99999999-9999-4999-8999-999999999999"


def _reference(key: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_key="stage_manifest",
        relative_path=f"data/interim/weather/{RUN_KEY}/{key}/stage-manifest.json",
        sha256=key * 64,
        byte_count=1,
        media_type="application/json",
    )


def test_feature_cli_supersedes_changed_feature_evidence(tmp_path, monkeypatch) -> None:
    validation = _reference("a")
    feature_v1 = _reference("b")
    feature_v2 = _reference("c")
    events = (
        SimpleNamespace(sequence=6, stage="validated", disposition="complete", evidence=validation),
        SimpleNamespace(
            sequence=7, stage="features_built", disposition="complete", evidence=feature_v1
        ),
    )
    appended: list[dict[str, object]] = []

    class FakeLedger:
        def __init__(self, _store) -> None:
            pass

        def load_events(self):
            return events

        @staticmethod
        def latest_stage_event(_events, stage):
            return events[0] if stage == "validated" else events[1]

        def append(self, **values) -> None:
            appended.append(values)

    monkeypatch.setattr(
        feature_cli,
        "WeatherArtifactStore",
        lambda _run_key, project_root: SimpleNamespace(project_root=project_root),
    )
    monkeypatch.setattr(feature_cli, "RunStateLedger", FakeLedger)
    monkeypatch.setattr(feature_cli, "validation_disposition", lambda *_args: "complete")
    monkeypatch.setattr(feature_cli, "build_weather_features", lambda *_args, **_kwargs: feature_v2)

    result = feature_cli.main(["--run-key", RUN_KEY, "--project-root", str(tmp_path)])

    assert result == 0
    assert appended[0]["evidence"] == feature_v2
    assert appended[0]["supersedes_sequence"] == 7


def test_feature_cli_returns_quarantine_without_building(tmp_path, monkeypatch) -> None:
    validation = _reference("a")

    class FakeLedger:
        def __init__(self, _store) -> None:
            pass

        def load_events(self):
            return (
                SimpleNamespace(
                    sequence=6, stage="validated", disposition="quarantined", evidence=validation
                ),
            )

        @staticmethod
        def latest_stage_event(events, _stage):
            return events[0]

    monkeypatch.setattr(
        feature_cli,
        "WeatherArtifactStore",
        lambda _run_key, project_root: SimpleNamespace(project_root=project_root),
    )
    monkeypatch.setattr(feature_cli, "RunStateLedger", FakeLedger)
    monkeypatch.setattr(feature_cli, "validation_disposition", lambda *_args: "quarantined")
    monkeypatch.setattr(
        feature_cli,
        "build_weather_features",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not build")),
    )

    result = feature_cli.main(["--run-key", RUN_KEY, "--project-root", str(tmp_path)])

    assert result == 2
