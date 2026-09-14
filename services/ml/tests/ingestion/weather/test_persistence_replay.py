from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from paragliding_forecasts_ml.ingestion.atmosphere.contracts import ArtifactReference
from paragliding_forecasts_ml.ingestion.weather import persistence
from paragliding_forecasts_ml.ingestion.weather.persistence import _canonical_run_graph

RUN_KEY = "99999999-9999-4999-8999-999999999999"


def test_canonical_run_graph_retains_every_non_surrogate_value() -> None:
    rows = {
        "weather_point_samples": [
            {
                "id": 101,
                "ingestion_run_id": 1,
                "product_valid_time_id": 21,
                "point_footprint_id": 31,
                "coverage_status": "complete",
                "air_temperature_2m_k": 294.5,
            }
        ],
        "weather_point_profile_levels": [
            {
                "id": 201,
                "weather_point_sample_id": 101,
                "pressure_pa": 90000.0,
                "air_temperature_k": 289.0,
            }
        ],
        "weather_point_convection_measurements": [],
        "weather_point_interval_measurements": [],
        "weather_daily_feature_snapshots": [],
        "weather_daily_feature_snapshot_inputs": [],
        "weather_daily_feature_profile_layers": [],
        "weather_field_provenance": [
            {
                "id": 301,
                "weather_point_sample_id": 101,
                "point_profile_level_id": None,
                "point_convection_measurement_id": None,
                "point_interval_measurement_id": None,
                "daily_feature_snapshot_id": None,
                "daily_feature_profile_layer_id": None,
                "field_code": "air_temperature_k",
                "field_variant": "2m",
                "quality_state": "real",
                "missing_reason_code": None,
            }
        ],
    }

    canonical = _canonical_run_graph(rows)
    reordered_ids = deepcopy(rows)
    reordered_ids["weather_point_samples"][0]["id"] = 999
    reordered_ids["weather_point_profile_levels"][0]["weather_point_sample_id"] = 999
    reordered_ids["weather_field_provenance"][0]["weather_point_sample_id"] = 999

    assert _canonical_run_graph(reordered_ids) == canonical

    changed_value = deepcopy(rows)
    changed_value["weather_point_profile_levels"][0]["air_temperature_k"] = 288.5

    assert _canonical_run_graph(changed_value) != canonical


@pytest.mark.parametrize(
    ("existing_rows", "expected_status"),
    [
        ([object()], "revalidated_no_op"),
        ([None, object()], "inserted"),
    ],
)
def test_terminal_persisted_replay_or_restoration_does_not_append_another_event(
    tmp_path, monkeypatch, existing_rows, expected_status
) -> None:
    receipt = ArtifactReference(
        artifact_key="weather_persistence_receipt",
        relative_path=f"data/interim/weather/{RUN_KEY}/persistence/receipt.json",
        sha256="a" * 64,
        byte_count=1,
        media_type="application/json",
    )
    snapshot = SimpleNamespace(
        events=(SimpleNamespace(stage="persisted", disposition="persisted"),)
    )
    ledger = SimpleNamespace(
        append_to=lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("terminal replay must not append")
        )
    )
    store = SimpleNamespace(run_key=RUN_KEY)
    prepared = SimpleNamespace(
        snapshot=snapshot,
        ledger=ledger,
        store=store,
        persistence_input_sha256="b" * 64,
    )

    class FakeConnection:
        in_transaction = True
        row_factory = None

        def execute(self, _sql):
            return None

        def rollback(self):
            self.in_transaction = False

        def commit(self):
            self.in_transaction = False

        def close(self):
            return None

    monkeypatch.setattr(persistence, "prepare_weather_persistence", lambda *_a, **_k: prepared)
    monkeypatch.setattr(persistence, "configured_database_url", lambda value: value)
    monkeypatch.setattr(persistence, "open_writable_database", lambda *_a, **_k: FakeConnection())
    monkeypatch.setattr(persistence, "_require_schema", lambda _connection: None)
    existing = iter(existing_rows)
    monkeypatch.setattr(persistence, "_existing_run", lambda *_a: next(existing))
    monkeypatch.setattr(persistence, "_insert_graph", lambda *_a: None)
    monkeypatch.setattr(persistence, "_verify_source", lambda *_a: None)
    monkeypatch.setattr(
        persistence,
        "_verify_existing_run",
        lambda *_a: ({"weather_ingestion_runs": 1}, "c" * 64),
    )
    monkeypatch.setattr(persistence, "_database_identity", lambda *_a: "restored.db")
    monkeypatch.setattr(persistence, "_publish_receipt", lambda *_a, **_k: receipt)

    report, updated = persistence.persist_weather_run_with_state(
        RUN_KEY,
        None,
        database_url="file:./data/local/restored.db",
        project_root=tmp_path,
        store=store,
        ledger=ledger,
        snapshot=snapshot,
    )

    assert report["status"] == expected_status
    assert updated is snapshot
