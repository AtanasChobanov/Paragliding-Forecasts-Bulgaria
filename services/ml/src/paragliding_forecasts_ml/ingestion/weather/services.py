"""Typed, command-scoped services for offline weather stage orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..atmosphere.contracts import ArtifactReference
from ..gfs.normalizer import GFS_NORMALIZER_VERSION, normalize
from ..gfs.parser import GFS_PARSER_VERSION, parse, raw_manifest_reference
from .artifacts import WeatherArtifactStore
from .feature_stage import WeatherFeatureBuildError, build_weather_features
from .persistence import persist_weather_run_with_state
from .spatial import WEATHER_SPATIAL_VERSION, sample_canonical_sites
from .state import RunStateEvent, RunStateLedger, RunStateSnapshot
from .validation import (
    WEATHER_VALIDATOR_VERSION,
    validate_weather_run,
    validation_disposition,
    validation_upstream_boundary,
    validation_version,
)
from .verification import ArtifactVerificationSession


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(slots=True)
class WeatherRunContext:
    """One store, verifier, ledger, and current snapshot for one top-level command."""

    run_key: str
    project_root: Path
    database_url: str | None
    source_family: str
    verification: ArtifactVerificationSession
    store: WeatherArtifactStore
    ledger: RunStateLedger
    snapshot: RunStateSnapshot

    @classmethod
    def open(
        cls,
        run_key: str,
        *,
        project_root: Path | None = None,
        database_url: str | None = None,
        source_family: str = "gfs",
    ) -> WeatherRunContext:
        root = (project_root or Path.cwd()).resolve()
        verification = ArtifactVerificationSession(project_root=root, run_key=run_key)
        store = WeatherArtifactStore(
            run_key,
            project_root=root,
            verification_session=verification,
        )
        ledger = RunStateLedger(store)
        return cls(
            run_key=run_key,
            project_root=root,
            database_url=database_url,
            source_family=source_family,
            verification=verification,
            store=store,
            ledger=ledger,
            snapshot=ledger.load_state(),
        )

    def require_database_url(self) -> str:
        if self.database_url is None:
            raise ValueError("This weather stage requires a resolved DATABASE_URL.")
        return self.database_url

    def verification_summary(self) -> dict[str, Any]:
        return self.verification.verification_summary()


@dataclass(frozen=True, slots=True)
class ParseNormalizeResult:
    parser_manifest: ArtifactReference
    normalizer_manifest: ArtifactReference
    parser_disposition: str
    normalizer_disposition: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "parser_manifest": self.parser_manifest.relative_path,
            "normalizer_manifest": self.normalizer_manifest.relative_path,
            "parser_disposition": self.parser_disposition,
            "normalizer_disposition": self.normalizer_disposition,
            "network_access": False,
            "database_access": "read_only",
        }


@dataclass(frozen=True, slots=True)
class SpatialResult:
    spatial_manifest: ArtifactReference
    disposition: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "spatial_manifest": self.spatial_manifest.relative_path,
            "disposition": self.disposition,
            "network_access": False,
            "database_access": "read_only",
        }


@dataclass(frozen=True, slots=True)
class ValidationResult:
    validation_manifest: ArtifactReference
    disposition: str
    boundary_disposition: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "validation_manifest": self.validation_manifest.relative_path,
            "disposition": self.disposition,
            "boundary_disposition": self.boundary_disposition,
            "network_access": False,
            "database_access": "read_only",
        }


@dataclass(frozen=True, slots=True)
class FeatureResult:
    validation_manifest: ArtifactReference
    feature_manifest: ArtifactReference | None
    disposition: str
    boundary_disposition: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "validation_manifest": self.validation_manifest.relative_path,
            "feature_manifest": (
                self.feature_manifest.relative_path if self.feature_manifest is not None else None
            ),
            "disposition": self.disposition,
            "boundary_disposition": self.boundary_disposition,
            "network_access": False,
        }


@dataclass(frozen=True, slots=True)
class PersistenceResult:
    report: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return dict(self.report)


def _effective(context: WeatherRunContext, stage: str) -> RunStateEvent | None:
    return context.snapshot.effective_event(stage)  # type: ignore[arg-type]


def _complete_evidence(context: WeatherRunContext, stage: str) -> ArtifactReference:
    event = _effective(context, stage)
    if event is None or event.disposition != "complete" or event.evidence is None:
        raise ValueError(f"Weather stage {stage!r} requires complete effective evidence.")
    return event.evidence


def _manifest_matches(
    context: WeatherRunContext,
    reference: ArtifactReference | None,
    *,
    stage: str,
    producer_version: str,
    upstream: ArtifactReference,
) -> bool:
    if reference is None:
        return False
    manifest = context.store.read_stage_manifest(reference)
    return (
        manifest.stage == stage
        and manifest.producer_version == producer_version
        and manifest.inputs == (upstream,)
    )


def _append_complete(
    context: WeatherRunContext,
    snapshot: RunStateSnapshot,
    *,
    stage: str,
    evidence: ArtifactReference,
    occurred_at_utc: str,
    detail: str,
    previous: RunStateEvent | None,
    disposition: str = "complete",
) -> RunStateSnapshot:
    _, updated = context.ledger.append_to(
        snapshot,
        invocation_mode="resume",
        stage=stage,  # type: ignore[arg-type]
        disposition=disposition,  # type: ignore[arg-type]
        occurred_at_utc=occurred_at_utc,
        evidence=evidence,
        supersedes_sequence=previous.sequence if previous is not None else None,
        detail=detail,
    )
    return updated


def parse_and_normalize(
    context: WeatherRunContext,
) -> tuple[ParseNormalizeResult, RunStateSnapshot]:
    """Reuse or build the current compact parser and normalizer boundaries."""

    snapshot = context.snapshot
    raw_event = snapshot.effective_event("raw_complete")
    if (
        raw_event is None
        or raw_event.disposition != "complete"
        or raw_event.evidence is None
        or raw_event.evidence != raw_manifest_reference(context.store)
    ):
        raise ValueError("GFS parse requires the current complete raw manifest state event.")
    context.store.verify_raw_manifest(raw_event.evidence)

    parser_event = snapshot.effective_event("parsed")
    parser_reference = parser_event.evidence if parser_event is not None else None
    if _manifest_matches(
        context,
        parser_reference,
        stage="parser",
        producer_version=GFS_PARSER_VERSION,
        upstream=raw_event.evidence,
    ):
        parser_disposition = "reused"
        assert parser_reference is not None
    else:
        occurred_at_utc = _utc_now()
        parser_reference = parse(
            context.store,
            database_url=context.require_database_url(),
            occurred_at_utc=occurred_at_utc,
            project_root=context.project_root,
        )
        snapshot = _append_complete(
            context,
            snapshot,
            stage="parsed",
            evidence=parser_reference,
            occurred_at_utc=occurred_at_utc,
            detail="offline ecCodes compact native-grid parse",
            previous=parser_event,
        )
        parser_disposition = "created"

    normalizer_event = snapshot.effective_event("normalized")
    normalizer_reference = normalizer_event.evidence if normalizer_event is not None else None
    if _manifest_matches(
        context,
        normalizer_reference,
        stage="normalizer",
        producer_version=GFS_NORMALIZER_VERSION,
        upstream=parser_reference,
    ):
        normalizer_disposition = "reused"
        assert normalizer_reference is not None
    else:
        occurred_at_utc = _utc_now()
        normalizer_reference = normalize(
            context.store,
            parser_reference,
            occurred_at_utc=occurred_at_utc,
        )
        snapshot = _append_complete(
            context,
            snapshot,
            stage="normalized",
            evidence=normalizer_reference,
            occurred_at_utc=occurred_at_utc,
            detail="canonical compact GFS grid normalization",
            previous=normalizer_event,
        )
        normalizer_disposition = "created"
    return (
        ParseNormalizeResult(
            parser_manifest=parser_reference,
            normalizer_manifest=normalizer_reference,
            parser_disposition=parser_disposition,
            normalizer_disposition=normalizer_disposition,
        ),
        snapshot,
    )


def sample_sites(context: WeatherRunContext) -> tuple[SpatialResult, RunStateSnapshot]:
    """Reuse or build the current spatial alignment boundary."""

    snapshot = context.snapshot
    upstream = _complete_evidence(context, "normalized")
    previous = snapshot.effective_event("spatially_aligned")
    reference = previous.evidence if previous is not None else None
    if _manifest_matches(
        context,
        reference,
        stage="spatial",
        producer_version=WEATHER_SPATIAL_VERSION,
        upstream=upstream,
    ):
        disposition = "reused"
        assert reference is not None
    else:
        occurred_at_utc = _utc_now()
        reference = sample_canonical_sites(
            context.store,
            upstream,
            database_url=context.require_database_url(),
            occurred_at_utc=occurred_at_utc,
            project_root=context.project_root,
        )
        snapshot = _append_complete(
            context,
            snapshot,
            stage="spatially_aligned",
            evidence=reference,
            occurred_at_utc=occurred_at_utc,
            detail="bilinear point samples and 50 km physical-radius node evidence",
            previous=previous,
        )
        disposition = "created"
    return SpatialResult(reference, disposition), snapshot


def validate_run(context: WeatherRunContext) -> tuple[ValidationResult, RunStateSnapshot]:
    """Reuse or build the current source-aware validation boundary."""

    snapshot = context.snapshot
    upstream = _complete_evidence(context, "spatially_aligned")
    previous = snapshot.effective_event("validated")
    reference = previous.evidence if previous is not None else None
    matches = reference is not None
    if reference is not None:
        matches = (
            validation_version(context.store, reference) == WEATHER_VALIDATOR_VERSION
            and validation_upstream_boundary(context.store, reference) == upstream
        )
    if matches:
        boundary_disposition = "reused"
        assert reference is not None
        disposition = validation_disposition(context.store, reference)
    else:
        occurred_at_utc = _utc_now()
        reference = validate_weather_run(
            context.store,
            upstream,
            database_url=context.require_database_url(),
            occurred_at_utc=occurred_at_utc,
            project_root=context.project_root,
        )
        disposition = validation_disposition(context.store, reference)
        snapshot = _append_complete(
            context,
            snapshot,
            stage="validated",
            evidence=reference,
            occurred_at_utc=occurred_at_utc,
            detail="source-aware offline validation and quarantine evidence",
            previous=previous,
            disposition=disposition,
        )
        boundary_disposition = "created"
    return ValidationResult(reference, disposition, boundary_disposition), snapshot


def build_features(context: WeatherRunContext) -> tuple[FeatureResult, RunStateSnapshot]:
    """Reuse or build features after a complete validator boundary."""

    snapshot = context.snapshot
    validation_event = snapshot.effective_event("validated")
    if validation_event is None or validation_event.evidence is None:
        raise ValueError("Feature building requires effective validation evidence.")
    validation_reference = validation_event.evidence
    disposition = validation_disposition(context.store, validation_reference)
    if disposition == "quarantined":
        return FeatureResult(validation_reference, None, disposition, "not_run"), snapshot
    if disposition != "complete":
        raise WeatherFeatureBuildError("Validation disposition is not complete.")
    occurred_at_utc = _utc_now()
    reference = build_weather_features(
        context.store,
        validation_reference,
        occurred_at_utc=occurred_at_utc,
    )
    previous = snapshot.effective_event("features_built")
    if previous is not None and previous.evidence == reference:
        boundary_disposition = "reused"
    else:
        snapshot = _append_complete(
            context,
            snapshot,
            stage="features_built",
            evidence=reference,
            occurred_at_utc=occurred_at_utc,
            detail="strict daily weather feature snapshots and quality evidence",
            previous=previous,
        )
        boundary_disposition = "created"
    return FeatureResult(
        validation_reference, reference, "complete", boundary_disposition
    ), snapshot


def persist_run(
    context: WeatherRunContext,
    usage_policy_path: Path | None,
) -> tuple[PersistenceResult, RunStateSnapshot]:
    """Persist or revalidate through the context's existing store and snapshot."""

    report, snapshot = persist_weather_run_with_state(
        context.run_key,
        usage_policy_path,
        database_url=context.require_database_url(),
        project_root=context.project_root,
        store=context.store,
        ledger=context.ledger,
        snapshot=context.snapshot,
    )
    return PersistenceResult(report), snapshot
