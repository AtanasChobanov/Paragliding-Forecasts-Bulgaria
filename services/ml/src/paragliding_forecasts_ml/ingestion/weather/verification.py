"""Command-scoped, conservative verification caches for immutable weather artifacts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter_ns
from typing import Any

import numpy as np
from pydantic import BaseModel

from ..atmosphere.contracts import ArtifactReference

ArtifactIdentity = tuple[str, str, str, int, str, int | None]


@dataclass(frozen=True, slots=True)
class FileStatSnapshot:
    size: int
    mtime_ns: int
    ctime_ns: int
    device: int | None
    inode: int | None


@dataclass(frozen=True, slots=True)
class _VerifiedFile:
    path: Path
    stat: FileStatSnapshot
    digest_source: str


@dataclass(frozen=True, slots=True)
class _VerifiedBoundary:
    path: Path
    dependencies: tuple[tuple[ArtifactReference, Path], ...]


class ArtifactVerificationSession:
    """Cache trusted files and parsed boundaries for exactly one command/run."""

    def __init__(self, *, project_root: Path, run_key: str) -> None:
        self.project_root = project_root.resolve()
        self.run_key = run_key
        self._files: dict[ArtifactIdentity, _VerifiedFile] = {}
        self._models: dict[ArtifactIdentity, BaseModel] = {}
        self._matrices: dict[ArtifactIdentity, np.ndarray] = {}
        self._boundaries: dict[ArtifactIdentity, _VerifiedBoundary] = {}
        self.files_hashed = 0
        self.bytes_hashed = 0
        self.cache_hits = 0
        self.manifests_parsed = 0
        self.boundaries_verified = 0
        self.files_registered = 0
        self.matrices_loaded = 0
        self.hash_elapsed_ns = 0

    def assert_compatible(self, *, project_root: Path, run_key: str) -> None:
        if self.project_root != project_root.resolve() or self.run_key != run_key:
            raise ValueError("Artifact verification session belongs to another project or run.")

    def identity(self, reference: ArtifactReference, path: Path) -> ArtifactIdentity:
        return (
            str(path.resolve()),
            reference.artifact_key,
            reference.sha256,
            reference.byte_count,
            reference.media_type,
            reference.record_count,
        )

    def verify_file(
        self,
        reference: ArtifactReference,
        path: Path,
        *,
        require_disk_hash: bool = False,
    ) -> Path:
        identity = self.identity(reference, path)
        current = self._stat(path)
        cached = self._files.get(identity)
        if (
            cached is not None
            and cached.stat == current
            and (not require_disk_hash or cached.digest_source == "disk")
        ):
            self.cache_hits += 1
            return cached.path
        if cached is not None:
            self._invalidate(identity)
        if current.size != reference.byte_count:
            raise ValueError(f"Artifact byte count does not match: {reference.relative_path}")
        started = perf_counter_ns()
        digest = self._sha256_file(path)
        self.hash_elapsed_ns += perf_counter_ns() - started
        after = self._stat(path)
        if after != current:
            self._invalidate(identity)
            raise ValueError(f"Artifact changed during verification: {reference.relative_path}")
        self.files_hashed += 1
        self.bytes_hashed += current.size
        if digest != reference.sha256:
            raise ValueError(f"Artifact SHA-256 does not match: {reference.relative_path}")
        self._files[identity] = _VerifiedFile(
            path=path,
            stat=current,
            digest_source="disk",
        )
        return path

    def reference_for_existing(
        self,
        path: Path,
        *,
        artifact_key: str,
        relative_path: str,
        media_type: str,
        record_count: int | None = None,
    ) -> ArtifactReference:
        """Hash an unreferenced existing file once and register its exact identity."""

        current = self._stat(path)
        started = perf_counter_ns()
        digest = self._sha256_file(path)
        self.hash_elapsed_ns += perf_counter_ns() - started
        after = self._stat(path)
        if after != current:
            raise ValueError(f"Artifact changed during verification: {relative_path}")
        reference = ArtifactReference(
            artifact_key=artifact_key,
            relative_path=relative_path,
            sha256=digest,
            byte_count=current.size,
            media_type=media_type,
            record_count=record_count,
        )
        identity = self.identity(reference, path)
        self.files_hashed += 1
        self.bytes_hashed += current.size
        self._files[identity] = _VerifiedFile(
            path=path,
            stat=current,
            digest_source="disk",
        )
        return reference

    def register_written(
        self,
        reference: ArtifactReference,
        path: Path,
        *,
        model: BaseModel | None = None,
    ) -> None:
        current = self._stat(path)
        if current.size != reference.byte_count:
            raise ValueError(
                f"Written artifact byte count does not match: {reference.relative_path}"
            )
        identity = self.identity(reference, path)
        self._files[identity] = _VerifiedFile(
            path=path,
            stat=current,
            digest_source="write",
        )
        if model is not None:
            self._models[identity] = model
        self.files_registered += 1

    def cached_model(
        self,
        reference: ArtifactReference,
        path: Path,
        model_type: type[BaseModel],
    ) -> BaseModel | None:
        model = self._models.get(self.identity(reference, path))
        if model is not None and isinstance(model, model_type):
            self.cache_hits += 1
            return model
        return None

    def register_parsed_model(
        self,
        reference: ArtifactReference,
        path: Path,
        model: BaseModel,
        *,
        manifest: bool,
    ) -> None:
        self._models[self.identity(reference, path)] = model
        if manifest:
            self.manifests_parsed += 1

    def cached_matrix(self, reference: ArtifactReference, path: Path) -> np.ndarray | None:
        matrix = self._matrices.get(self.identity(reference, path))
        if matrix is not None:
            self.cache_hits += 1
        return matrix

    def register_matrix(self, reference: ArtifactReference, path: Path, matrix: np.ndarray) -> None:
        matrix.setflags(write=False)
        self._matrices[self.identity(reference, path)] = matrix
        self.matrices_loaded += 1

    def cached_boundary(
        self, reference: ArtifactReference, path: Path
    ) -> tuple[Path, tuple[tuple[ArtifactReference, Path], ...]] | None:
        identity = self.identity(reference, path)
        boundary = self._boundaries.get(identity)
        if boundary is None:
            return None
        for dependency, dependency_path in boundary.dependencies:
            dependency_identity = self.identity(dependency, dependency_path)
            verified = self._files.get(dependency_identity)
            if verified is None:
                self._boundaries.pop(identity, None)
                return None
            try:
                current = self._stat(verified.path)
            except OSError:
                self._invalidate(dependency_identity)
                return None
            if current != verified.stat:
                self._invalidate(dependency_identity)
                return None
        self.cache_hits += 1
        return boundary.path, boundary.dependencies

    def register_boundary(
        self,
        reference: ArtifactReference,
        path: Path,
        dependencies: tuple[tuple[ArtifactReference, Path], ...],
    ) -> None:
        identity = self.identity(reference, path)
        ordered: dict[ArtifactIdentity, tuple[ArtifactReference, Path]] = {}
        for dependency, dependency_path in dependencies:
            dependency_identity = self.identity(dependency, dependency_path)
            if dependency_identity not in self._files:
                raise ValueError("A boundary dependency was not fully verified.")
            ordered[dependency_identity] = (dependency, dependency_path)
        if identity not in self._boundaries:
            self.boundaries_verified += 1
        self._boundaries[identity] = _VerifiedBoundary(
            path=path,
            dependencies=tuple(ordered.values()),
        )

    def verification_summary(self) -> dict[str, Any]:
        return {
            "files_hashed": self.files_hashed,
            "bytes_hashed": self.bytes_hashed,
            "cache_hits": self.cache_hits,
            "manifests_parsed": self.manifests_parsed,
            "boundaries_verified": self.boundaries_verified,
            "files_registered": self.files_registered,
            "matrices_loaded": self.matrices_loaded,
            "hash_elapsed_ms": round(self.hash_elapsed_ns / 1_000_000, 3),
        }

    def _invalidate(self, identity: ArtifactIdentity) -> None:
        self._files.pop(identity, None)
        self._models.pop(identity, None)
        self._matrices.pop(identity, None)
        for boundary_identity, boundary in tuple(self._boundaries.items()):
            if any(
                self.identity(reference, path) == identity
                for reference, path in boundary.dependencies
            ):
                self._boundaries.pop(boundary_identity, None)

    @staticmethod
    def _stat(path: Path) -> FileStatSnapshot:
        stat = path.stat()
        return FileStatSnapshot(
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            ctime_ns=stat.st_ctime_ns,
            device=getattr(stat, "st_dev", None),
            inode=getattr(stat, "st_ino", None),
        )

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
