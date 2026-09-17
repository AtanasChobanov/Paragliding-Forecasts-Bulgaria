"""Immutable content-addressed snapshots and per-run IGRA artifacts."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from ..atmosphere.contracts import ArtifactReference
from ..weather.serialization import canonical_json_bytes, pretty_json_bytes, sha256_bytes, sha256_file
from .models import IgraSourceSnapshotManifest


class IgraArtifactError(RuntimeError):
    """An artifact attempts an unsafe path, overwrite, or invalid immutable reuse."""


def repository_root() -> Path:
    """Resolve the checkout root from this source-tree package layout."""

    return Path(__file__).resolve().parents[6]


def stage_directory_name(stage: str, producer_version: str) -> str:
    """Return the planned stage directory name without a filesystem-derived identity."""

    return f"{stage}-v{producer_version.rsplit('/', 1)[-1]}"


def stage_input_fingerprint(
    *,
    stage: str,
    producer_version: str,
    inputs: tuple[ArtifactReference, ...],
    configuration: dict[str, object],
) -> str:
    """Hash exact inputs/configuration, deliberately excluding clocks and absolute paths."""

    return sha256_bytes(
        canonical_json_bytes(
            {
                "stage": stage,
                "producer_version": producer_version,
                "inputs": [reference.model_dump(mode="json") for reference in inputs],
                "configuration": configuration,
            }
        )
    )


class IgraArtifactStore:
    """Own a UUID run root and safely publish shared raw provider snapshots."""

    def __init__(self, run_key: str, *, project_root: Path | None = None, create: bool = False) -> None:
        self.run_key = run_key
        self.project_root = (project_root or repository_root()).resolve()
        self.interim_dir = self.project_root / "data" / "interim" / "soundings" / run_key
        self.raw_root = self.project_root / "data" / "raw" / "soundings" / "igra"
        if create:
            self.interim_dir.mkdir(parents=True, exist_ok=False)
        elif not self.interim_dir.is_dir():
            raise IgraArtifactError(f"IGRA run root does not exist: {run_key}")

    @classmethod
    def create_fresh(cls, run_key: str, *, project_root: Path | None = None) -> IgraArtifactStore:
        return cls(run_key, project_root=project_root, create=True)

    @property
    def state_events_directory(self) -> Path:
        return self.interim_dir / "state" / "events"

    def stage_directory(self, stage: str, producer_version: str, fingerprint: str) -> Path:
        return self.interim_dir / stage_directory_name(stage, producer_version) / fingerprint

    def snapshot_directory(self, station_id: str, snapshot_id: str) -> Path:
        return self.raw_root / station_id / snapshot_id

    def create_work_directory(self) -> Path:
        path = self.interim_dir / "work" / str(uuid4())
        path.mkdir(parents=True, exist_ok=False)
        return path

    def write_request_plan(self, model: BaseModel) -> ArtifactReference:
        return self.write_model(self.interim_dir / "request-plan.json", "request_plan", model)

    def write_state_event(self, sequence: int, label: str, model: BaseModel) -> ArtifactReference:
        if sequence < 1 or not label.replace("-", "").isalnum():
            raise IgraArtifactError("State-event filename label is unsafe.")
        return self.write_model(
            self.state_events_directory / f"{sequence:04d}-{label}.json",
            f"state_event_{sequence}",
            model,
        )

    def write_model(
        self, path: Path, artifact_key: str, model: BaseModel, *, record_count: int | None = None
    ) -> ArtifactReference:
        return self.write_bytes(
            path,
            artifact_key,
            pretty_json_bytes(model),
            media_type="application/json",
            record_count=record_count,
        )

    def write_jsonl(
        self, path: Path, artifact_key: str, records: tuple[BaseModel, ...]
    ) -> ArtifactReference:
        return self.write_bytes(
            path,
            artifact_key,
            b"".join(canonical_json_bytes(record) for record in records),
            media_type="application/x-ndjson",
            record_count=len(records),
        )

    def write_bytes(
        self,
        path: Path,
        artifact_key: str,
        content: bytes,
        *,
        media_type: str,
        record_count: int | None = None,
    ) -> ArtifactReference:
        self._assert_allowed(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            if temporary.stat().st_size != len(content):
                raise IgraArtifactError("Temporary artifact has an inconsistent byte count.")
            os.link(temporary, path)
        except FileExistsError as error:
            raise IgraArtifactError(f"Refusing to overwrite immutable artifact: {path}") from error
        finally:
            temporary.unlink(missing_ok=True)
        return self.reference_for(path, artifact_key, media_type=media_type, record_count=record_count)

    def publish_directory(self, work_directory: Path, destination: Path) -> Path:
        """Publish a complete work directory once, otherwise verify/reuse the winner."""

        self._assert_allowed(work_directory)
        self._assert_allowed(destination)
        if not work_directory.is_dir():
            raise IgraArtifactError("Only a complete work directory can be published.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.rename(work_directory, destination)
        except FileExistsError:
            self.verify_directory(destination)
            shutil.rmtree(work_directory)
        return destination

    def write_snapshot_manifest(
        self, station_id: str, snapshot_id: str, manifest: IgraSourceSnapshotManifest
    ) -> ArtifactReference:
        if manifest.station_id != station_id or manifest.source_snapshot_id != snapshot_id:
            raise IgraArtifactError("Snapshot manifest does not match its destination identity.")
        destination = self.snapshot_directory(station_id, snapshot_id)
        for reference in manifest.artifacts:
            self.verify_reference(reference, expected_root=destination)
        return self.write_model(destination / "manifest.json", "source_snapshot_manifest", manifest)

    def reference_for(
        self,
        path: Path,
        artifact_key: str,
        *,
        media_type: str,
        record_count: int | None = None,
    ) -> ArtifactReference:
        self._assert_allowed(path)
        if not path.is_file():
            raise IgraArtifactError(f"Artifact does not exist: {path}")
        return ArtifactReference(
            artifact_key=artifact_key,
            relative_path=path.resolve().relative_to(self.project_root).as_posix(),
            sha256=sha256_file(path),
            byte_count=path.stat().st_size,
            media_type=media_type,
            record_count=record_count,
        )

    def verify_reference(self, reference: ArtifactReference, *, expected_root: Path | None = None) -> Path:
        path = (self.project_root / reference.relative_path).resolve()
        self._assert_allowed(path)
        if expected_root is not None and not _contained_by(path, expected_root.resolve()):
            raise IgraArtifactError("Artifact reference escapes the expected immutable boundary.")
        if not path.is_file() or path.stat().st_size != reference.byte_count:
            raise IgraArtifactError("Artifact is absent or its byte count changed.")
        if sha256_file(path) != reference.sha256:
            raise IgraArtifactError("Artifact SHA-256 does not match its reference.")
        return path

    def verify_directory(self, directory: Path) -> None:
        self._assert_allowed(directory)
        if not directory.is_dir() or not any(path.is_file() for path in directory.rglob("*")):
            raise IgraArtifactError("Published boundary is absent or has no files.")

    def _assert_allowed(self, path: Path) -> None:
        resolved = path.resolve()
        if not (_contained_by(resolved, self.interim_dir.resolve()) or _contained_by(resolved, self.raw_root.resolve())):
            raise IgraArtifactError("IGRA artifacts must remain below raw soundings or this run's interim root.")


def _contained_by(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True