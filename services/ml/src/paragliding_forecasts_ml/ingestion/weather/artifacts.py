"""Immutable raw/interim weather artifact storage and hash-chain verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ..atmosphere.contracts import ArtifactReference, RawManifest, RequestPlan, StageManifest
from .serialization import canonical_json_bytes, pretty_json_bytes, sha256_bytes, sha256_file
from .versions import output_directory_name


class ArtifactError(RuntimeError):
    """A weather artifact cannot safely participate in the durable protocol."""


def repository_root() -> Path:
    """Locate the repository from the installed source-tree package layout."""

    return Path(__file__).resolve().parents[6]


class WeatherArtifactStore:
    """Owns a single weather run's immutable raw and interim filesystem evidence."""

    def __init__(
        self, run_key: str, *, project_root: Path | None = None, create: bool = False
    ) -> None:
        self.project_root = (project_root or repository_root()).resolve()
        self.run_key = run_key
        self.raw_dir = self.project_root / "data" / "raw" / "weather" / run_key
        self.interim_dir = self.project_root / "data" / "interim" / "weather" / run_key
        if create:
            self._create_run_directories()
        else:
            self._require_existing_run_directories()

    @classmethod
    def create_fresh(
        cls, run_key: str, *, project_root: Path | None = None
    ) -> WeatherArtifactStore:
        """Create both run roots exactly once for a fresh UUID."""

        return cls(run_key, project_root=project_root, create=True)

    def _create_run_directories(self) -> None:
        if self.raw_dir.exists() or self.interim_dir.exists():
            raise FileExistsError(
                f"Weather run already exists and cannot be overwritten: {self.run_key}"
            )
        self.raw_dir.mkdir(parents=True, exist_ok=False)
        self.interim_dir.mkdir(parents=True, exist_ok=False)

    def _require_existing_run_directories(self) -> None:
        if not self.raw_dir.is_dir() or not self.interim_dir.is_dir():
            raise ArtifactError(f"Weather run directories do not exist: {self.run_key}")

    def write_request_plan(self, plan: RequestPlan) -> ArtifactReference:
        """Write the one immutable request plan before source collection begins."""

        if plan.run_key != self.run_key:
            raise ArtifactError("Request plan run_key does not match the artifact store.")
        return self._write_model(self.raw_dir / "request-plan.json", "request_plan", plan)

    def write_raw_bytes(
        self,
        artifact_key: str,
        filename: str,
        content: bytes,
        *,
        media_type: str,
    ) -> ArtifactReference:
        """Write one immutable raw payload beneath this run's payload directory."""

        if not filename or Path(filename).name != filename:
            raise ArtifactError("Raw payload filename must be one safe filename.")
        return self._write_bytes(
            self.raw_dir / "payloads" / filename,
            artifact_key,
            content,
            media_type=media_type,
        )

    def write_raw_model(
        self,
        artifact_key: str,
        filename: str,
        model: BaseModel,
        *,
        record_count: int | None = None,
    ) -> ArtifactReference:
        """Write one source-specific immutable JSON record beneath raw payloads."""

        if not filename or Path(filename).name != filename:
            raise ArtifactError("Raw payload filename must be one safe filename.")
        return self._write_model(
            self.raw_dir / "payloads" / filename,
            artifact_key,
            model,
            record_count=record_count,
        )

    def write_raw_manifest(self, manifest: RawManifest) -> ArtifactReference:
        """Finalize the raw evidence manifest once, without overwriting a partial attempt."""

        if manifest.run_key != self.run_key:
            raise ArtifactError("Raw manifest run_key does not match the artifact store.")
        self.verify_reference(manifest.request_plan, expected_root=self.raw_dir)
        for reference in manifest.artifacts:
            self.verify_reference(reference, expected_root=self.raw_dir)
        return self._write_model(self.raw_dir / "manifest.json", "raw_manifest", manifest)

    def write_state_event(self, sequence: int, label: str, event: BaseModel) -> ArtifactReference:
        """Append one immutable state-ledger event outside any processing-stage directory."""

        if sequence < 1:
            raise ArtifactError("State event sequence must be positive.")
        safe_label = label.replace("_", "-")
        if not safe_label or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in safe_label
        ):
            raise ArtifactError("State event label must be lowercase and filesystem-safe.")
        directory = self.interim_dir / "state" / "events"
        return self._write_model(
            directory / f"{sequence:04d}-{safe_label}.json",
            f"state_event_{sequence}",
            event,
        )

    def verify_raw_manifest(self, reference: ArtifactReference) -> RawManifest:
        """Load a raw manifest and verify its request plan and every raw payload hash."""

        path = self.verify_reference(reference, expected_root=self.raw_dir)
        try:
            manifest = RawManifest.model_validate_json(path.read_bytes(), strict=True)
        except Exception as error:
            raise ArtifactError("Raw manifest does not satisfy its versioned contract.") from error
        if manifest.run_key != self.run_key:
            raise ArtifactError("Raw manifest belongs to another weather run.")
        self.verify_reference(manifest.request_plan, expected_root=self.raw_dir)
        for artifact in manifest.artifacts:
            self.verify_reference(artifact, expected_root=self.raw_dir)
        return manifest

    def _stage_directory(
        self, stage: str, component_version: str, input_fingerprint_sha256: str
    ) -> Path:
        return (
            self.interim_dir
            / f"{stage}-{output_directory_name(component_version)}"
            / input_fingerprint_sha256
        )

    def existing_stage_manifest(
        self, stage: str, component_version: str, input_fingerprint_sha256: str
    ) -> ArtifactReference | None:
        """Return a fully verified completed boundary for exact stage inputs, if present."""

        manifest_path = (
            self._stage_directory(stage, component_version, input_fingerprint_sha256)
            / "stage-manifest.json"
        )
        if not manifest_path.is_file():
            return None
        reference = ArtifactReference(
            artifact_key="stage_manifest",
            relative_path=manifest_path.relative_to(self.project_root).as_posix(),
            sha256=sha256_file(manifest_path),
            byte_count=manifest_path.stat().st_size,
            media_type="application/json",
        )
        manifest = self.read_stage_manifest(reference)
        if (
            manifest.stage != stage
            or manifest.producer_version != component_version
            or manifest.input_fingerprint_sha256 != input_fingerprint_sha256
            or manifest.disposition
            not in ({"complete", "quarantined"} if stage == "validator" else {"complete"})
        ):
            raise ArtifactError("Existing stage manifest does not match the requested boundary.")
        return reference

    def begin_stage(
        self, stage: str, component_version: str, input_fingerprint_sha256: str
    ) -> Path:
        """Reserve an immutable version/fingerprint directory for one successful stage output."""

        directory = self._stage_directory(stage, component_version, input_fingerprint_sha256)
        directory.mkdir(parents=True, exist_ok=False)
        return directory

    def write_stage_model(
        self,
        stage_directory: Path,
        filename: str,
        artifact_key: str,
        model: BaseModel,
        *,
        record_count: int | None = None,
    ) -> ArtifactReference:
        """Write an immutable JSON output only under a reserved stage directory."""

        self._assert_stage_directory(stage_directory)
        if not filename or Path(filename).name != filename:
            raise ArtifactError("Stage filename must be one safe filename.")
        return self._write_model(
            stage_directory / filename,
            artifact_key,
            model,
            record_count=record_count,
        )

    def write_stage_bytes(
        self,
        stage_directory: Path,
        filename: str,
        artifact_key: str,
        content: bytes,
        *,
        media_type: str,
        record_count: int | None = None,
    ) -> ArtifactReference:
        """Write one immutable non-JSON stage payload such as a NumPy array."""

        self._assert_stage_directory(stage_directory)
        if not filename or Path(filename).name != filename:
            raise ArtifactError("Stage filename must be one safe filename.")
        return self._write_bytes(
            stage_directory / filename,
            artifact_key,
            content,
            media_type=media_type,
            record_count=record_count,
        )

    def write_stage_manifest(
        self, stage_directory: Path, manifest: StageManifest
    ) -> ArtifactReference:
        """Write a stage manifest after verifying every input and output hash."""

        self._assert_stage_directory(stage_directory)
        if manifest.run_key != self.run_key:
            raise ArtifactError("Stage manifest run_key does not match the artifact store.")
        for reference in (*manifest.inputs, *manifest.outputs):
            self.verify_reference(reference)
        return self._write_model(
            stage_directory / "stage-manifest.json", "stage_manifest", manifest
        )

    def verify_boundary(self, reference: ArtifactReference) -> Path:
        """Recursively verify a raw or stage manifest boundary and all of its inputs."""

        return self._verify_boundary(reference, visited=set())

    def read_stage_manifest(self, reference: ArtifactReference) -> StageManifest:
        """Return one hash-verified non-raw stage manifest."""

        if reference.artifact_key != "stage_manifest":
            raise ArtifactError("Expected a stage-manifest boundary reference.")
        path = self.verify_boundary(reference)
        try:
            return StageManifest.model_validate_json(path.read_bytes(), strict=True)
        except Exception as error:
            raise ArtifactError(
                "Stage manifest does not satisfy its versioned contract."
            ) from error

    def _verify_boundary(self, reference: ArtifactReference, *, visited: set[str]) -> Path:
        if reference.sha256 in visited:
            return self.verify_reference(reference)
        visited.add(reference.sha256)
        if reference.artifact_key == "raw_manifest":
            return self.verify_raw_manifest(reference)
        if reference.artifact_key != "stage_manifest":
            return self.verify_reference(reference)
        path = self.verify_reference(reference, expected_root=self.interim_dir)
        try:
            manifest = StageManifest.model_validate_json(path.read_bytes(), strict=True)
        except Exception as error:
            raise ArtifactError(
                "Stage manifest does not satisfy its versioned contract."
            ) from error
        if manifest.run_key != self.run_key:
            raise ArtifactError("Stage manifest belongs to another weather run.")
        expected_fingerprint = stage_input_fingerprint(
            stage=manifest.stage,
            producer_version=manifest.producer_version,
            inputs=manifest.inputs,
            configuration=manifest.configuration,
        )
        if expected_fingerprint != manifest.input_fingerprint_sha256:
            raise ArtifactError(
                "Stage manifest input fingerprint does not match its declared inputs."
            )
        for item in (*manifest.inputs, *manifest.outputs):
            self._verify_boundary(item, visited=visited)
        return path

    def verify_reference(
        self, reference: ArtifactReference, *, expected_root: Path | None = None
    ) -> Path:
        """Verify path containment, byte length, and SHA-256 for a referenced artifact."""

        path = self._resolve_relative(reference.relative_path)
        if expected_root is not None:
            try:
                path.relative_to(expected_root.resolve())
            except ValueError as error:
                raise ArtifactError(
                    "Artifact reference escapes the required weather run root."
                ) from error
        if not path.is_file():
            raise ArtifactError(f"Referenced artifact does not exist: {reference.relative_path}")
        if path.stat().st_size != reference.byte_count:
            raise ArtifactError(f"Artifact byte count does not match: {reference.relative_path}")
        if sha256_file(path) != reference.sha256:
            raise ArtifactError(f"Artifact SHA-256 does not match: {reference.relative_path}")
        return path

    def _write_model(
        self,
        path: Path,
        artifact_key: str,
        model: BaseModel,
        *,
        record_count: int | None = None,
    ) -> ArtifactReference:
        return self._write_bytes(
            path,
            artifact_key,
            pretty_json_bytes(model),
            media_type="application/json",
            record_count=record_count,
        )

    def _write_bytes(
        self,
        path: Path,
        artifact_key: str,
        content: bytes,
        *,
        media_type: str,
        record_count: int | None = None,
    ) -> ArtifactReference:
        self._assert_under_run(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as handle:
                handle.write(content)
        except FileExistsError as error:
            raise FileExistsError(f"Refusing to overwrite immutable artifact: {path}") from error
        return ArtifactReference(
            artifact_key=artifact_key,
            relative_path=path.relative_to(self.project_root).as_posix(),
            sha256=sha256_bytes(content),
            byte_count=len(content),
            media_type=media_type,
            record_count=record_count,
        )

    def _resolve_relative(self, relative_path: str) -> Path:
        candidate = (self.project_root / relative_path).resolve()
        try:
            candidate.relative_to(self.project_root)
        except ValueError as error:
            raise ArtifactError("Artifact path escapes the repository root.") from error
        return candidate

    def _assert_under_run(self, path: Path) -> None:
        resolved = path.resolve()
        for allowed in (self.raw_dir.resolve(), self.interim_dir.resolve()):
            try:
                resolved.relative_to(allowed)
                return
            except ValueError:
                continue
        raise ArtifactError(
            "Weather artifacts must remain below this run's raw or interim directory."
        )

    def _assert_stage_directory(self, directory: Path) -> None:
        resolved = directory.resolve()
        try:
            resolved.relative_to(self.interim_dir.resolve())
        except ValueError as error:
            raise ArtifactError(
                "Stage output directory escapes the interim weather run directory."
            ) from error
        if not resolved.is_dir():
            raise ArtifactError("Stage output directory does not exist.")


def stage_input_fingerprint(
    *,
    stage: str,
    producer_version: str,
    inputs: tuple[ArtifactReference, ...],
    configuration: dict[str, Any] | None = None,
) -> str:
    """Hash the complete immutable input/configuration boundary for one stage."""

    payload = {
        "stage": stage,
        "producer_version": producer_version,
        "inputs": [item.model_dump(mode="json") for item in inputs],
        "configuration": configuration or {},
    }
    return sha256_bytes(canonical_json_bytes(payload))
