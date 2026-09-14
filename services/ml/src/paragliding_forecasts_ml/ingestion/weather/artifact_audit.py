"""Explicit offline verification of effective or all historical weather evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from .artifacts import WeatherArtifactStore
from .state import RunStateLedger

AuditScope = Literal["effective", "all"]


def audit_weather_artifacts(
    run_key: str,
    *,
    scope: AuditScope,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Verify only the requested ledger evidence scope and return a safe report."""

    store = WeatherArtifactStore(run_key, project_root=project_root)
    snapshot = RunStateLedger(store).load_state()
    events = snapshot.evidence_events(scope=scope)
    verified: list[dict[str, Any]] = []
    for event in events:
        if event.evidence is None:  # narrowed by evidence_events
            continue
        store.verify_boundary(event.evidence)
        verified.append(
            {
                "sequence": event.sequence,
                "stage": event.stage,
                "disposition": event.disposition,
                "artifact_key": event.evidence.artifact_key,
                "relative_path": event.evidence.relative_path,
                "sha256": event.evidence.sha256,
            }
        )
    return {
        "run_key": run_key,
        "scope": scope,
        "ledger_event_count": snapshot.final_sequence,
        "verified_boundary_count": len(verified),
        "verified_boundaries": verified,
        "verification_summary": store.verification.verification_summary(),
    }
