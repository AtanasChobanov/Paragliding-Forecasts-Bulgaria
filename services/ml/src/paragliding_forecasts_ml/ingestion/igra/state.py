"""Append-only hash-linked state for IGRA fresh and offline-resume execution."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from ..atmosphere.contracts import ArtifactReference
from ..weather.serialization import sha256_bytes
from .artifacts import IgraArtifactError, IgraArtifactStore
from .models import IgraRunStateEvent


class IgraStateError(RuntimeError):
    """A transition, ledger sequence, predecessor hash, or boundary is invalid."""


RunStage = Literal["planned", "source_snapshot_complete", "parsed", "normalized", "validated"]
RunDisposition = Literal["ready", "complete", "quarantined", "failed"]
_STAGES: tuple[RunStage, ...] = (
    "planned",
    "source_snapshot_complete",
    "parsed",
    "normalized",
    "validated",
)


class IgraRunStateLedger:
    """Use one exclusive append lock per sequence and never rewrite history."""

    def __init__(self, store: IgraArtifactStore) -> None:
        self.store = store

    def initialize(self, occurred_at_utc: str) -> IgraRunStateEvent:
        if self._paths():
            raise IgraStateError("An IGRA state ledger already exists.")
        event = IgraRunStateEvent(
            run_key=self.store.run_key,
            sequence=1,
            invocation_mode="fresh",
            stage="planned",
            disposition="ready",
            occurred_at_utc=occurred_at_utc,
        )
        self._write(event)
        return event

    def load(self) -> tuple[IgraRunStateEvent, ...]:
        events: list[IgraRunStateEvent] = []
        predecessor: str | None = None
        for expected_sequence, path in enumerate(self._paths(), start=1):
            try:
                content = path.read_bytes()
                event = IgraRunStateEvent.model_validate_json(content, strict=True)
            except Exception as error:
                raise IgraStateError(f"State event is not a valid contract: {path}") from error
            if event.run_key != self.store.run_key or event.sequence != expected_sequence:
                raise IgraStateError("State event sequence or run key is inconsistent.")
            if event.previous_event_sha256 != predecessor or path.name != self._filename(event):
                raise IgraStateError("State event predecessor or filename is inconsistent.")
            if events:
                self._validate_next(
                    tuple(events),
                    event.stage,
                    event.disposition,
                    event.evidence,
                    event.supersedes_sequence,
                )
            elif (
                event.invocation_mode != "fresh"
                or event.stage != "planned"
                or event.disposition != "ready"
            ):
                raise IgraStateError("The first IGRA event must be fresh/planned/ready.")
            events.append(event)
            predecessor = sha256_bytes(content)
        return tuple(events)

    def append(
        self,
        *,
        stage: RunStage,
        disposition: RunDisposition,
        occurred_at_utc: str,
        evidence: ArtifactReference | None = None,
        supersedes_sequence: int | None = None,
        detail: str | None = None,
    ) -> IgraRunStateEvent:
        events = self.load()
        if not events:
            raise IgraStateError("Initialize the run before appending IGRA state.")
        self._validate_next(events, stage, disposition, evidence, supersedes_sequence)
        sequence = len(events) + 1
        self.store.state_events_directory.mkdir(parents=True, exist_ok=True)
        lock = self.store.state_events_directory / f".{sequence:04d}.append.lock"
        try:
            with lock.open("xb"):
                pass
        except FileExistsError as error:
            raise IgraStateError("Another IGRA writer owns this state sequence.") from error
        try:
            if self.load() != events:
                raise IgraStateError("IGRA state changed while preparing an append.")
            predecessor = sha256_bytes(self._paths()[-1].read_bytes())
            event = IgraRunStateEvent(
                run_key=self.store.run_key,
                sequence=sequence,
                invocation_mode="resume",
                stage=stage,
                disposition=disposition,
                occurred_at_utc=occurred_at_utc,
                previous_event_sha256=predecessor,
                evidence=evidence,
                supersedes_sequence=supersedes_sequence,
                detail=detail,
            )
            self._write(event)
            return event
        finally:
            lock.unlink(missing_ok=True)

    def _validate_next(self, events, stage, disposition, evidence, supersedes_sequence) -> None:
        if disposition == "quarantined" and stage != "validated":
            raise IgraStateError("Only validation may quarantine an IGRA run.")
        if disposition == "failed":
            return
        if evidence is None:
            raise IgraStateError("A completed stage requires immutable boundary evidence.")
        if supersedes_sequence is not None:
            if stage in {"planned", "source_snapshot_complete"} or supersedes_sequence > len(
                events
            ):
                raise IgraStateError("Only derived stages may supersede a valid prior boundary.")
            previous = events[supersedes_sequence - 1]
            if previous.stage != stage or previous.disposition not in {"complete", "quarantined"}:
                raise IgraStateError(
                    "Supersession must target a completed boundary of the same stage."
                )
            return
        completed = [
            event.stage
            for event in events
            if event.disposition in {"ready", "complete", "quarantined"}
        ]
        current = completed[-1]
        expected = _STAGES[_STAGES.index(current) + 1] if current != "validated" else None
        if stage != expected:
            raise IgraStateError(f"Expected next IGRA stage {expected}, received {stage}.")

    def _write(self, event: IgraRunStateEvent) -> None:
        try:
            self.store.write_state_event(
                event.sequence, f"{event.stage.replace('_', '-')}-{event.disposition}", event
            )
        except IgraArtifactError as error:
            raise IgraStateError(str(error)) from error

    def _paths(self) -> tuple[Path, ...]:
        if not self.store.state_events_directory.is_dir():
            return ()
        return tuple(sorted(self.store.state_events_directory.glob("*.json")))

    @staticmethod
    def _filename(event: IgraRunStateEvent) -> str:
        return f"{event.sequence:04d}-{event.stage.replace('_', '-')}-{event.disposition}.json"
