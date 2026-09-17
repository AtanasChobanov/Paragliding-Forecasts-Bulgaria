"""Fresh and offline-resume execution for the IGRA artifact pipeline."""

from __future__ import annotations

import json
import zipfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ..atmosphere.contracts import ArtifactReference
from ..weather.serialization import canonical_json_bytes, pretty_json_bytes, sha256_bytes
from .artifacts import IgraArtifactStore, stage_input_fingerprint
from .collector import collect_snapshot
from .inventory import inventory
from .models import IgraRequestPlan, IgraSourceSnapshotManifest, IgraStageManifest
from .normalizer import normalize
from .parser import parse_members
from .state import IgraRunStateLedger
from .station import parse_station_list
from .transport import IgraTransport, RetryingIgraTransport, UrllibIgraTransport
from .validation import validate
from .versions import (
    COLLECTOR_VERSION,
    NORMALIZER_VERSION,
    PARSER_VERSION,
    SOURCE_POLICY_VERSION,
    VALIDATOR_VERSION,
)


class IgraPipelineError(RuntimeError):
    """Artifact state cannot be safely continued."""


def fresh(
    *,
    station_id: str,
    dates_utc: tuple[str, ...],
    nominal_hours: tuple[int, ...],
    archive: str,
    maximum_total_mib: int,
    project_root: Path | None = None,
    transport: IgraTransport | None = None,
) -> dict[str, object]:
    """Create a new run after a fresh bounded inventory; only this mode creates a transport."""
    source = transport or RetryingIgraTransport(UrllibIgraTransport())
    inventory_result, policy_sha = inventory(
        source,
        station_id=station_id,
        dates_utc=dates_utc,
        nominal_hours=nominal_hours,
        requested_archive_mode=archive,
    )
    store = IgraArtifactStore.create_fresh(str(uuid4()), project_root=project_root)
    plan = IgraRequestPlan(
        run_key=store.run_key,
        dates_utc=dates_utc,
        nominal_hours=nominal_hours,
        requested_archive_mode=archive,
        resolved_archive_mode=inventory_result.resolved_archive_mode,
        maximum_total_mib=maximum_total_mib,
        source_policy_version=SOURCE_POLICY_VERSION,
        source_policy_sha256=policy_sha,
        component_versions={
            "collector": COLLECTOR_VERSION,
            "parser": PARSER_VERSION,
            "normalizer": NORMALIZER_VERSION,
            "validator": VALIDATOR_VERSION,
        },
        created_at_utc=_now(),
        remote_objects=inventory_result.remote_objects,
    )
    plan_ref = store.write_request_plan(plan)
    ledger = IgraRunStateLedger(store)
    ledger.initialize(_now())
    snapshot, reused = collect_snapshot(
        store,
        source,
        station_id=station_id,
        archive_mode=plan.resolved_archive_mode,
        objects=plan.remote_objects,
        maximum_total_mib=maximum_total_mib,
    )
    snapshot_ref = store.reference_for(
        store.snapshot_directory(station_id, snapshot.source_snapshot_id) / "manifest.json",
        "source_snapshot_manifest",
        media_type="application/json",
    )
    source_ref = _publish(
        store,
        "source_snapshot",
        COLLECTOR_VERSION,
        (plan_ref, snapshot_ref),
        {"snapshot": snapshot_ref.model_dump(mode="json")},
    )
    ledger.append(
        stage="source_snapshot_complete",
        disposition="complete",
        occurred_at_utc=_now(),
        evidence=source_ref,
    )
    return _process(store, plan, snapshot, reused)


def resume(*, run_key: str, project_root: Path | None = None) -> dict[str, object]:
    """Read hash-verified state only; it has no network option and constructs no transport."""
    store = IgraArtifactStore(run_key, project_root=project_root)
    events = IgraRunStateLedger(store).load()
    if not any(
        event.stage == "source_snapshot_complete" and event.disposition == "complete"
        for event in events
    ):
        raise IgraPipelineError("No complete source snapshot exists; start a new fresh run.")
    plan = IgraRequestPlan.model_validate_json(
        (store.interim_dir / "request-plan.json").read_bytes(), strict=True
    )
    source_event = next(
        event
        for event in reversed(events)
        if event.stage == "source_snapshot_complete" and event.disposition == "complete"
    )
    source_stage = _load_stage(store, source_event.evidence)
    payload = json.loads(store.verify_reference(_output(source_stage, "snapshot")).read_bytes())
    snapshot_ref = ArtifactReference.model_validate(payload, strict=True)
    snapshot = IgraSourceSnapshotManifest.model_validate_json(
        store.verify_reference(snapshot_ref).read_bytes(), strict=True
    )
    return _process(store, plan, snapshot, True)


def _process(
    store: IgraArtifactStore,
    plan: IgraRequestPlan,
    snapshot: IgraSourceSnapshotManifest,
    reused: bool,
) -> dict[str, object]:
    ledger = IgraRunStateLedger(store)
    events = ledger.load()
    artifacts = {item.artifact_key: item for item in snapshot.artifacts}
    station = parse_station_list(
        store.verify_reference(artifacts["station_list"]).read_bytes(), plan.station_id
    )
    parsed_event = _latest(events, "parsed")
    if parsed_event is None:
        raw_ref = artifacts.get("recent_zip") or artifacts["period_of_record_zip"]
        with (
            _open_zip_member(
                store.verify_reference(raw_ref), raw_ref.artifact_key, snapshot
            ) as raw_member,
            _open_zip_member(
                store.verify_reference(artifacts["derived_zip"]), "derived_zip", snapshot
            ) as derived_member,
        ):
            parsed = parse_members(
                raw_content=raw_member,
                derived_content=derived_member,
                station_id=plan.station_id,
                dates_utc=plan.dates_utc,
                nominal_hours=plan.nominal_hours,
                raw_artifact_key=raw_ref.artifact_key,
            )
        parsed_ref = _publish(
            store,
            "parser",
            PARSER_VERSION,
            (
                store.reference_for(
                    store.snapshot_directory(plan.station_id, snapshot.source_snapshot_id)
                    / "manifest.json",
                    "source_snapshot_manifest",
                    media_type="application/json",
                ),
            ),
            {
                "native-soundings.jsonl": parsed.raw_soundings,
                "native-derived-soundings.jsonl": parsed.derived_soundings,
                "parse-summary.json": {
                    "raw_scanned": parsed.raw_scanned,
                    "derived_scanned": parsed.derived_scanned,
                    "raw_selected": parsed.raw_selected,
                    "derived_selected": parsed.derived_selected,
                },
            },
        )
        ledger.append(
            stage="parsed", disposition="complete", occurred_at_utc=_now(), evidence=parsed_ref
        )
        parsed_event = ledger.load()[-1]
    normalized_event = _latest(ledger.load(), "normalized")
    if normalized_event is None:
        parsed_stage = _load_stage(store, parsed_event.evidence)
        from .models import NativeIgraDerivedSounding, NativeIgraSounding

        normalized = normalize(
            _read_models(store, _output(parsed_stage, "native_soundings"), NativeIgraSounding),
            _read_models(
                store, _output(parsed_stage, "native_derived_soundings"), NativeIgraDerivedSounding
            ),
            source_snapshot_id=snapshot.source_snapshot_id,
            inventory_latitude_deg=station.latitude_deg,
            inventory_longitude_deg=station.longitude_deg,
        )
        norm_ref = _publish(
            store,
            "normalizer",
            NORMALIZER_VERSION,
            (parsed_event.evidence,),
            {
                "soundings.jsonl": normalized.soundings,
                "levels.jsonl": normalized.levels,
                "provider-derived-parameters.jsonl": normalized.provider_parameters,
                "provider-derived-levels.jsonl": normalized.provider_levels,
                "normalization-report.json": normalized.report,
            },
        )
        ledger.append(
            stage="normalized", disposition="complete", occurred_at_utc=_now(), evidence=norm_ref
        )
        normalized_event = ledger.load()[-1]
    validated_event = _latest(ledger.load(), "validated")
    if validated_event is None:
        normal_stage = _load_stage(store, normalized_event.evidence)
        from .models import (
            CanonicalSounding,
            CanonicalSoundingLevel,
            ProviderDerivedSoundingLevel,
            ProviderDerivedSoundingParameters,
        )

        result = validate(
            _read_models(store, _output(normal_stage, "soundings"), CanonicalSounding),
            _read_models(store, _output(normal_stage, "levels"), CanonicalSoundingLevel),
            _read_models(
                store,
                _output(normal_stage, "provider_derived_parameters"),
                ProviderDerivedSoundingParameters,
            ),
            _read_models(
                store,
                _output(normal_stage, "provider_derived_levels"),
                ProviderDerivedSoundingLevel,
            ),
            requested_dates_utc=plan.dates_utc,
            requested_nominal_hours=plan.nominal_hours,
        )
        disposition = "complete" if not result.quarantined_soundings else "quarantined"
        valid_ref = _publish(
            store,
            "validator",
            VALIDATOR_VERSION,
            (normalized_event.evidence,),
            {
                "accepted-soundings.jsonl": result.accepted_soundings,
                "quarantined-soundings.jsonl": result.quarantined_soundings,
                "accepted-levels.jsonl": result.accepted_levels,
                "excluded-levels.jsonl": result.excluded_levels,
                "invalid-values.jsonl": result.invalid_values,
                "accepted-provider-derived-parameters.jsonl": result.accepted_provider_parameters,
                "accepted-provider-derived-levels.jsonl": result.accepted_provider_levels,
                "rejected-derived-associations.jsonl": result.rejected_derived_associations,
                "missing-evidence.jsonl": result.missing_evidence,
                "validation-report.json": result.report,
            },
            disposition=disposition,
        )
        ledger.append(
            stage="validated", disposition=disposition, occurred_at_utc=_now(), evidence=valid_ref
        )
        validated_event = ledger.load()[-1]
    report = json.loads(
        store.verify_reference(
            _output(_load_stage(store, validated_event.evidence), "validation_report")
        ).read_bytes()
    )
    accepted, quarantined = int(report["soundings_accepted"]), int(report["soundings_quarantined"])
    return {
        "run_key": plan.run_key,
        "source_snapshot_id": snapshot.source_snapshot_id,
        "archive_mode": plan.resolved_archive_mode,
        "dates_utc": list(plan.dates_utc),
        "nominal_hours": list(plan.nominal_hours),
        "accepted_soundings": accepted,
        "quarantined_soundings": quarantined,
        "missing_evidence": int(report["missing_evidence"]),
        "network_mode": "cache_reuse" if reused else "fresh_bounded",
        "validated_manifest": validated_event.evidence.model_dump(mode="json")
        if validated_event.evidence
        else None,
        "next_step": "T-039 may read the effective validated manifest; T-020 must not use IGRA predictors.",
        "exit_code": 0 if accepted and not quarantined else 2,
    }


def _publish(
    store: IgraArtifactStore,
    stage: str,
    version: str,
    inputs: tuple[ArtifactReference, ...],
    outputs: dict[str, object],
    disposition: str = "complete",
) -> ArtifactReference:
    fingerprint = stage_input_fingerprint(
        stage=stage, producer_version=version, inputs=inputs, configuration={}
    )
    destination = store.stage_directory(stage, version, fingerprint)
    existing = destination / "stage-manifest.json"
    if existing.is_file():
        return store.reference_for(existing, "stage_manifest", media_type="application/json")
    work = store.create_work_directory() / "boundary"
    work.mkdir()
    refs = []
    for filename, value in outputs.items():
        is_jsonl = filename.endswith(".jsonl")
        records = tuple(value) if is_jsonl else ()
        content = (
            b"".join(canonical_json_bytes(record) for record in records)
            if is_jsonl
            else pretty_json_bytes(value)
        )
        (work / filename).write_bytes(content)
        refs.append(
            ArtifactReference(
                artifact_key=filename.rsplit(".", 1)[0].replace("-", "_"),
                relative_path=(destination / filename).relative_to(store.project_root).as_posix(),
                sha256=sha256_bytes(content),
                byte_count=len(content),
                media_type="application/x-ndjson" if is_jsonl else "application/json",
                record_count=len(records) if is_jsonl else None,
            )
        )
    manifest = IgraStageManifest(
        run_key=store.run_key,
        stage=stage,
        producer_version=version,
        input_fingerprint_sha256=fingerprint,
        inputs=inputs,
        outputs=tuple(refs),
        disposition=disposition,
        completed_at_utc=_now(),
    )
    (work / "stage-manifest.json").write_bytes(pretty_json_bytes(manifest))
    store.publish_directory(work, destination)
    return store.reference_for(
        destination / "stage-manifest.json", "stage_manifest", media_type="application/json"
    )


def _load_stage(store: IgraArtifactStore, reference: ArtifactReference | None) -> IgraStageManifest:
    if reference is None:
        raise IgraPipelineError("Required stage evidence is missing.")
    manifest = IgraStageManifest.model_validate_json(
        store.verify_reference(reference).read_bytes(), strict=True
    )
    for output in manifest.outputs:
        store.verify_reference(output)
    return manifest


def _output(manifest: IgraStageManifest, key: str) -> ArtifactReference:
    for output in manifest.outputs:
        if output.artifact_key == key:
            return output
    raise IgraPipelineError(f"Stage output is missing: {key}")


def _read_jsonl(store: IgraArtifactStore, ref: ArtifactReference) -> tuple[dict[str, object], ...]:
    return tuple(
        json.loads(line)
        for line in store.verify_reference(ref).read_text(encoding="utf-8").splitlines()
        if line
    )


def _read_models(store: IgraArtifactStore, ref: ArtifactReference, model):
    return tuple(
        model.model_validate_json(line, strict=True)
        for line in store.verify_reference(ref).read_text(encoding="utf-8").splitlines()
        if line
    )


@contextmanager
def _open_zip_member(path: Path, key: str, snapshot: IgraSourceSnapshotManifest):
    remote = next(item for item in snapshot.remote_objects if item.artifact_key == key)
    if remote.expected_member_name is None:
        raise IgraPipelineError(f"ZIP source object {key} has no expected member name.")
    with zipfile.ZipFile(path) as archive, archive.open(remote.expected_member_name) as member:
        yield member


def _latest(events, stage: str):
    return next(
        (
            event
            for event in reversed(events)
            if event.stage == stage and event.disposition in {"complete", "quarantined"}
        ),
        None,
    )


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
