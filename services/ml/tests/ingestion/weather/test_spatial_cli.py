from __future__ import annotations

from types import SimpleNamespace

from paragliding_forecasts_ml.ingestion.atmosphere.contracts import ArtifactReference
from paragliding_forecasts_ml.ingestion.weather.spatial_cli import build_parser, main


def _reference(key: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_key="stage_manifest",
        relative_path=f"data/interim/weather/test/{key}.json",
        sha256="a" * 64,
        byte_count=1,
        media_type="application/json",
    )


def test_gfs_sample_cli_has_no_network_option() -> None:
    parser = build_parser()
    option_strings = {option for action in parser._actions for option in action.option_strings}
    assert "--allow-live-network" not in option_strings
    assert "--run-key" in option_strings


def test_successful_cli_uses_normalized_evidence_and_appends_spatial_state(
    tmp_path, monkeypatch, capsys
) -> None:
    normalized = _reference("normalized")
    spatial = _reference("spatial")
    appended: list[dict[str, object]] = []

    class FakeLedger:
        def __init__(self, _store) -> None:
            pass

        def load_events(self):
            return (
                SimpleNamespace(
                    stage="normalized",
                    disposition="complete",
                    evidence=normalized,
                ),
            )

        def append(self, **values):
            appended.append(values)

        @staticmethod
        def latest_stage_event(_events, _stage):
            return None

    monkeypatch.setattr(
        "paragliding_forecasts_ml.ingestion.weather.spatial_cli.WeatherArtifactStore",
        lambda _run_key, project_root: SimpleNamespace(project_root=project_root),
    )
    monkeypatch.setattr(
        "paragliding_forecasts_ml.ingestion.weather.spatial_cli.RunStateLedger", FakeLedger
    )
    monkeypatch.setattr(
        "paragliding_forecasts_ml.ingestion.weather.spatial_cli.sample_canonical_sites",
        lambda _store, input_reference, **_kwargs: (
            spatial if input_reference == normalized else None
        ),
    )

    result = main(
        [
            "--run-key",
            "99999999-9999-4999-8999-999999999999",
            "--project-root",
            str(tmp_path),
            "--database-url",
            "file:./data/local/weather.db",
        ]
    )

    assert result == 0
    assert appended[0]["stage"] == "spatially_aligned"
    assert appended[0]["evidence"] == spatial
    output = capsys.readouterr().out
    assert '"network_access": false' in output
    assert '"database_access": "read_only"' in output
