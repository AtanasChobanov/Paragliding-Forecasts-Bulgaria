"""Append-only weather run state ledger for fresh and offline-resume execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ..atmosphere.contracts import (
    SHA256_PATTERN,
    UUID_V4_PATTERN,
    ArtifactReference,
    AtmosphericContract,
    validate_utc_timestamp,
)
from .artifacts import ArtifactError, WeatherArtifactStore
from .serialization import sha256_bytes

RunMode = Literal["fresh", "resume"]
RunStage = Literal[
    "planned",
    "raw_complete",
    "parsed",
    "normalized",
    "spatially_aligned",
    "validated",
    "features_built",
    "persisted",
]
RunDisposition = Literal["ready", "complete", "failed", "partial", "quarantined", "persisted"]

STAGE_ORDER: tuple[RunStage, ...] = (
    "planned",
    "raw_complete",
    "parsed",
    "normalized",
    "spatially_aligned",
    "validated",
    "features_built",
    "persisted",
)

_EFFECTIVE_DISPOSITIONS = frozenset({"ready", "complete", "partial", "quarantined", "persisted"})


class StateError(RuntimeError):
    """The event ledger is corrupt or attempts an illegal state transition."""


class RunStateEvent(AtmosphericContract):
    """One immutable, hash-linked transition in the weather-run lifecycle."""

    # Version 1 events remain readable. Version 2 adds an explicit link when
    # an immutable derived boundary replaces an earlier boundary for the same
    # run/stage. Version 3 permits a retryable persistence failure event.
    state_event_schema_version: Literal[1, 2, 3] = 3
    run_key: str
    sequence: int = Field(ge=1)
    invocation_mode: RunMode
    stage: RunStage
    disposition: RunDisposition
    occurred_at_utc: str
    previous_event_sha256: str | None = None
    evidence: ArtifactReference | None = None
    supersedes_sequence: int | None = Field(default=None, ge=1)
    detail: str | None = None

    @field_validator("run_key")
    @classmethod
    def run_key_must_be_uuid_v4(cls, value: str) -> str:
        if UUID_V4_PATTERN.fullmatch(value) is None:
            raise ValueError("run_key must be a lowercase UUID v4.")
        return value

    @field_validator("occurred_at_utc")
    @classmethod
    def occurred_at_must_be_utc(cls, value: str) -> str:
        return validate_utc_timestamp(value)

    @field_validator("previous_event_sha256")
    @classmethod
    def previous_hash_must_be_sha256(cls, value: str | None) -> str | None:
        if value is not None and SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("previous_event_sha256 must be a SHA-256 when present.")
        return value

    @model_validator(mode="after")
    def terminal_and_evidence_shape_must_match(self) -> RunStateEvent:
        if self.stage == "planned" and self.disposition != "ready":
            raise ValueError("The planned state must use the ready disposition.")
        if self.stage == "persisted" and self.disposition not in {"persisted", "failed"}:
            raise ValueError("The persisted stage must use persisted or failed disposition.")
        if self.disposition == "quarantined" and self.stage != "validated":
            raise ValueError("Only validation can produce a quarantined run state.")
        if self.disposition == "partial" and self.stage != "raw_complete":
            raise ValueError("Only incomplete raw coverage can produce a partial run state.")
        if self.state_event_schema_version == 1 and self.supersedes_sequence is not None:
            raise ValueError("State-event schema version 1 cannot supersede another event.")
        return self


@dataclass(frozen=True, slots=True)
class RunStateSnapshot:
    """One metadata-only, hash-chain-validated view of a weather run ledger."""

    events: tuple[RunStateEvent, ...]
    event_sha256s: tuple[str, ...]
    effective_stage_events: tuple[tuple[RunStage, RunStateEvent], ...]

    @classmethod
    def build(
        cls,
        events: tuple[RunStateEvent, ...],
        event_sha256s: tuple[str, ...],
    ) -> RunStateSnapshot:
        if len(events) != len(event_sha256s):
            raise StateError("State snapshot event and digest counts do not match.")
        effective: dict[RunStage, RunStateEvent] = {}
        for event in events:
            if event.disposition in _EFFECTIVE_DISPOSITIONS:
                effective[event.stage] = event
        return cls(
            events=events,
            event_sha256s=event_sha256s,
            effective_stage_events=tuple(
                (stage, effective[stage]) for stage in STAGE_ORDER if stage in effective
            ),
        )

    @property
    def final_sequence(self) -> int:
        return len(self.events)

    @property
    def final_event_sha256(self) -> str | None:
        return self.event_sha256s[-1] if self.event_sha256s else None

    def effective_event(self, stage: RunStage) -> RunStateEvent | None:
        for candidate_stage, event in self.effective_stage_events:
            if candidate_stage == stage:
                return event
        return None

    def evidence_events(self, *, scope: Literal["effective", "all"]) -> tuple[RunStateEvent, ...]:
        """Return evidence-bearing events selected for an explicit audit scope."""

        if scope == "all":
            candidates = self.events
        elif scope == "effective":
            candidates = tuple(event for _, event in self.effective_stage_events)
        else:
            raise ValueError(f"Unsupported weather artifact audit scope: {scope}")
        return tuple(event for event in candidates if event.evidence is not None)


class RunStateLedger:
    """Validates ledger metadata and appends only legal transitions for one run."""

    def __init__(self, store: WeatherArtifactStore) -> None:
        self.store = store

    @property
    def events_directory(self) -> Path:
        return self.store.interim_dir / "state" / "events"

    def initialize(self, *, occurred_at_utc: str) -> RunStateEvent:
        """Create the first event for a newly reserved fresh run."""

        if self.events_directory.exists() and any(self.events_directory.glob("*.json")):
            raise StateError("A weather run state ledger already exists.")
        event = RunStateEvent(
            run_key=self.store.run_key,
            sequence=1,
            invocation_mode="fresh",
            stage="planned",
            disposition="ready",
            occurred_at_utc=occurred_at_utc,
        )
        self._write(event)
        return event

    def append(
        self,
        *,
        invocation_mode: RunMode,
        stage: RunStage,
        disposition: RunDisposition,
        occurred_at_utc: str,
        evidence: ArtifactReference | None = None,
        supersedes_sequence: int | None = None,
        detail: str | None = None,
    ) -> RunStateEvent:
        """Compatibility wrapper around metadata-only snapshot-aware append."""

        event, _ = self.append_to(
            self.load_state(),
            invocation_mode=invocation_mode,
            stage=stage,
            disposition=disposition,
            occurred_at_utc=occurred_at_utc,
            evidence=evidence,
            supersedes_sequence=supersedes_sequence,
            detail=detail,
        )
        return event

    def append_to(
        self,
        snapshot: RunStateSnapshot,
        *,
        invocation_mode: RunMode,
        stage: RunStage,
        disposition: RunDisposition,
        occurred_at_utc: str,
        evidence: ArtifactReference | None = None,
        supersedes_sequence: int | None = None,
        detail: str | None = None,
    ) -> tuple[RunStateEvent, RunStateSnapshot]:
        """Append against one current snapshot and return the updated in-memory state."""

        events = snapshot.events
        if not events:
            raise StateError("A weather run must be initialized before appending transitions.")
        next_sequence = snapshot.final_sequence + 1
        lock_path = self.events_directory / f".{next_sequence:04d}.append.lock"
        try:
            with lock_path.open("xb"):
                pass
        except FileExistsError as error:
            raise StateError("Another writer is appending this state ledger sequence.") from error
        try:
            self._assert_snapshot_is_current(snapshot)
            self._validate_next(
                events,
                invocation_mode=invocation_mode,
                stage=stage,
                disposition=disposition,
                evidence=evidence,
                supersedes_sequence=supersedes_sequence,
            )
            if evidence is not None:
                self._validate_evidence_reference(evidence, stage=stage)
            event = RunStateEvent(
                run_key=self.store.run_key,
                sequence=next_sequence,
                invocation_mode=invocation_mode,
                stage=stage,
                disposition=disposition,
                occurred_at_utc=occurred_at_utc,
                previous_event_sha256=snapshot.final_event_sha256,
                evidence=evidence,
                supersedes_sequence=supersedes_sequence,
                detail=detail,
            )
            reference = self._write(event)
        finally:
            lock_path.unlink(missing_ok=True)
        updated = RunStateSnapshot.build(
            (*events, event),
            (*snapshot.event_sha256s, reference.sha256),
        )
        return event, updated

    def load_state(self) -> RunStateSnapshot:
        """Load ledger metadata once without opening referenced artifact evidence."""

        if not self.events_directory.is_dir():
            return RunStateSnapshot.build((), ())
        paths = sorted(self.events_directory.glob("*.json"))
        events: list[RunStateEvent] = []
        digests: list[str] = []
        for expected_sequence, path in enumerate(paths, start=1):
            try:
                content = path.read_bytes()
                event = RunStateEvent.model_validate_json(content, strict=True)
            except Exception as error:
                raise StateError(f"State event is invalid JSON contract: {path}") from error
            if event.run_key != self.store.run_key or event.sequence != expected_sequence:
                raise StateError("State event sequence or run key is inconsistent.")
            if path.name != self._event_filename(event):
                raise StateError("State event filename does not match its sequence and transition.")
            digest = sha256_bytes(content)
            if not digests:
                if event.previous_event_sha256 is not None:
                    raise StateError("First state event cannot have a predecessor hash.")
            elif event.previous_event_sha256 != digests[-1]:
                raise StateError("State event predecessor hash does not match prior evidence.")
            if event.evidence is not None:
                self._validate_evidence_reference(event.evidence, stage=event.stage)
            if events:
                self._validate_next(
                    tuple(events),
                    invocation_mode=event.invocation_mode,
                    stage=event.stage,
                    disposition=event.disposition,
                    evidence=event.evidence,
                    supersedes_sequence=event.supersedes_sequence,
                )
            elif not (
                event.invocation_mode == "fresh"
                and event.stage == "planned"
                and event.disposition == "ready"
            ):
                raise StateError("The first state event must be fresh/planned/ready.")
            events.append(event)
            digests.append(digest)
        return RunStateSnapshot.build(tuple(events), tuple(digests))

    def load_events(self) -> tuple[RunStateEvent, ...]:
        """Compatibility wrapper; validates ledger metadata but not artifact contents."""

        return self.load_state().events

    def _write(self, event: RunStateEvent) -> ArtifactReference:
        try:
            return self.store.write_state_event(
                event.sequence,
                f"{event.stage}-{event.disposition}",
                event,
            )
        except ArtifactError as error:
            raise StateError(str(error)) from error

    def _event_path(self, event: RunStateEvent) -> Path:
        path = self.events_directory / self._event_filename(event)
        if not path.is_file():
            raise StateError("Expected state event file does not exist.")
        return path

    @staticmethod
    def _event_filename(event: RunStateEvent) -> str:
        return f"{event.sequence:04d}-{event.stage.replace('_', '-')}-{event.disposition}.json"

    def _assert_snapshot_is_current(self, snapshot: RunStateSnapshot) -> None:
        if any(event.run_key != self.store.run_key for event in snapshot.events):
            raise StateError("State snapshot belongs to another weather run.")
        expected_names = tuple(self._event_filename(event) for event in snapshot.events)
        actual_names = tuple(path.name for path in sorted(self.events_directory.glob("*.json")))
        if actual_names != expected_names:
            raise StateError("State ledger changed after the supplied snapshot was loaded.")

    def _validate_evidence_reference(
        self, reference: ArtifactReference, *, stage: RunStage
    ) -> None:
        parts = PurePosixPath(reference.relative_path).parts
        raw_manifest = ("data", "raw", "weather", self.store.run_key, "manifest.json")
        interim_prefix = ("data", "interim", "weather", self.store.run_key)
        if stage == "raw_complete" and reference.artifact_key == "raw_manifest":
            valid = parts == raw_manifest
        elif stage != "raw_complete" and reference.artifact_key == "stage_manifest":
            valid = (
                len(parts) > len(interim_prefix)
                and parts[: len(interim_prefix)] == interim_prefix
                and parts[-1] == "stage-manifest.json"
            )
        else:
            valid = False
        if not valid:
            raise StateError("State event evidence is not a structural run boundary reference.")

    @staticmethod
    def _last_successful_stage(events: tuple[RunStateEvent, ...]) -> RunStage:
        for event in reversed(events):
            if event.disposition in {"ready", "complete", "persisted"}:
                return event.stage
        raise StateError("State ledger does not contain a successful stage.")

    @staticmethod
    def latest_stage_event(
        events: tuple[RunStateEvent, ...], stage: RunStage
    ) -> RunStateEvent | None:
        """Return the current completed/quarantined boundary for one stage."""

        allowed = {"complete"}
        if stage == "validated":
            allowed.add("quarantined")
        for event in reversed(events):
            if event.stage == stage and event.disposition in allowed:
                return event
        return None

    def _validate_next(
        self,
        events: tuple[RunStateEvent, ...],
        *,
        invocation_mode: RunMode,
        stage: RunStage,
        disposition: RunDisposition,
        evidence: ArtifactReference | None = None,
        supersedes_sequence: int | None = None,
    ) -> None:
        latest = events[-1]
        if latest.disposition in {"partial", "persisted"}:
            raise StateError(f"A {latest.disposition} weather run is terminal and cannot resume.")
        if invocation_mode != "resume":
            raise StateError(
                "Only a fresh initialization may use fresh mode; subsequent events use resume."
            )
        if supersedes_sequence is not None:
            self._validate_supersession(
                events,
                stage=stage,
                disposition=disposition,
                evidence=evidence,
                supersedes_sequence=supersedes_sequence,
            )
        else:
            successful = self._last_successful_stage(events)
            successful_index = STAGE_ORDER.index(successful)
            expected = (
                STAGE_ORDER[successful_index + 1] if successful != "persisted" else "persisted"
            )
            if stage != expected:
                raise StateError(f"Illegal transition: expected {expected}, received {stage}.")
        if disposition == "ready":
            raise StateError("Only the initial planned state may use ready disposition.")
        if disposition == "persisted" and stage != "persisted":
            raise StateError("Persisted disposition requires the persisted stage.")
        if stage == "persisted" and disposition not in {"persisted", "failed"}:
            raise StateError("The persisted stage requires persisted or failed disposition.")
        if stage == "persisted" and disposition == "failed" and evidence is None:
            raise StateError("A retryable persistence failure requires immutable evidence.")
        if disposition == "quarantined" and stage != "validated":
            raise StateError("Only validation can quarantine a weather run.")
        if disposition == "partial" and stage != "raw_complete":
            raise StateError("Only raw collection coverage can be partial.")

    def _validate_supersession(
        self,
        events: tuple[RunStateEvent, ...],
        *,
        stage: RunStage,
        disposition: RunDisposition,
        evidence: ArtifactReference | None,
        supersedes_sequence: int,
    ) -> None:
        """Validate a deliberate rerun of a versioned derived stage.

        A supersession never rewrites history. It publishes a distinct,
        hash-verified boundary and points to the previous effective boundary
        for the same stage, so downstream commands can select the latest
        lineage without scanning artifact directories.
        """

        if stage in {"planned", "raw_complete", "persisted"}:
            raise StateError("Only derived weather stages can supersede prior evidence.")
        if disposition not in {"complete", "quarantined"}:
            raise StateError("A superseding event must publish a complete or quarantined boundary.")
        if disposition == "quarantined" and stage != "validated":
            raise StateError("Only validation can publish a quarantined boundary.")
        if evidence is None:
            raise StateError("A superseding event requires immutable boundary evidence.")
        if supersedes_sequence > len(events):
            raise StateError("A superseding event must reference an earlier state event.")
        superseded = events[supersedes_sequence - 1]
        if superseded.stage != stage or superseded.disposition not in {"complete", "quarantined"}:
            raise StateError(
                "A superseding event must reference a completed boundary of the same stage."
            )
        current = self.latest_stage_event(events, stage)
        if current is None or current.sequence != supersedes_sequence:
            raise StateError(
                "A superseding event must reference the current boundary for its stage."
            )
        if superseded.evidence == evidence:
            raise StateError("A superseding event must publish distinct boundary evidence.")
