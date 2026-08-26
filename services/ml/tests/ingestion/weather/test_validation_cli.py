from __future__ import annotations

from types import SimpleNamespace

from paragliding_forecasts_ml.ingestion.atmosphere.contracts import ArtifactReference
from paragliding_forecasts_ml.ingestion.weather import validation_cli

RUN_KEY = "99999999-9999-4999-8999-999999999999"


def _reference(key: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_key="stage_manifest",
        relative_path=f"data/interim/weather/{RUN_KEY}/{key}/stage-manifest.json",
        sha256=key * 64,
        byte_count=1,
        media_type="application/json",
    )


def test_validation_rebuilds_for_a_superseding_spatial_boundary(tmp_path, monkeypatch) -> None:
    spatial_v1 = _reference("a")
    validation_v1 = _reference("b")
    spatial_v2 = _reference("c")
    validation_v2 = _reference("d")
    events = (
        SimpleNamespace(
            sequence=5,
            stage="spatially_aligned",
            disposition="complete",
            evidence=spatial_v1,
        ),
        SimpleNamespace(
            sequence=6,
            stage="validated",
            disposition="complete",
            evidence=validation_v1,
        ),
        SimpleNamespace(
            sequence=7,
            stage="spatially_aligned",
            disposition="complete",
            evidence=spatial_v2,
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
            return events[1] if stage == "validated" else None

        def append(self, **values) -> None:
            appended.append(values)

    monkeypatch.setattr(
        validation_cli,
        "WeatherArtifactStore",
        lambda _run_key, project_root: SimpleNamespace(project_root=project_root),
    )
    monkeypatch.setattr(validation_cli, "RunStateLedger", FakeLedger)
    monkeypatch.setattr(validation_cli, "configured_database_url", lambda value: value)
    monkeypatch.setattr(
        validation_cli,
        "validation_version",
        lambda _store, _reference: "source-aware-weather-validator/2",
    )
    monkeypatch.setattr(
        validation_cli,
        "validation_upstream_boundary",
        lambda _store, _reference: spatial_v1,
    )
    monkeypatch.setattr(
        validation_cli,
        "validate_weather_run",
        lambda _store, upstream, **_kwargs: validation_v2 if upstream == spatial_v2 else None,
    )
    monkeypatch.setattr(validation_cli, "validation_disposition", lambda *_args: "complete")

    result = validation_cli.main(
        [
            "--run-key",
            RUN_KEY,
            "--project-root",
            str(tmp_path),
            "--database-url",
            "file:./data/local/weather.db",
        ]
    )

    assert result == 0
    assert appended[0]["evidence"] == validation_v2
    assert appended[0]["supersedes_sequence"] == 6
