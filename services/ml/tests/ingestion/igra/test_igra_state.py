from pathlib import Path

from paragliding_forecasts_ml.ingestion.igra.artifacts import IgraArtifactStore
from paragliding_forecasts_ml.ingestion.igra.state import IgraRunStateLedger


def test_ledger_starts_with_a_fresh_planned_event(tmp_path: Path) -> None:
    store = IgraArtifactStore.create_fresh(
        "00000000-0000-4000-8000-000000000000", project_root=tmp_path
    )
    ledger = IgraRunStateLedger(store)
    ledger.initialize("2025-08-02T00:00:00Z")
    assert ledger.load()[0].stage == "planned"
