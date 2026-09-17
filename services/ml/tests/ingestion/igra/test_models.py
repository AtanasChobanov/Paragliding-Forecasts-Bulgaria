from paragliding_forecasts_ml.ingestion.igra.models import IgraRunStateEvent


def test_initial_state_contract_accepts_a_v4_uuid() -> None:
    event = IgraRunStateEvent(
        run_key="00000000-0000-4000-8000-000000000000",
        sequence=1,
        invocation_mode="fresh",
        stage="planned",
        disposition="ready",
        occurred_at_utc="2025-08-02T00:00:00Z",
    )
    assert event.sequence == 1