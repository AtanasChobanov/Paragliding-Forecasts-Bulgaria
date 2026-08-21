"""Source-specific adapter interfaces around the shared atmospheric contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from ..weather.artifacts import WeatherArtifactStore
from .contracts import (
    CanonicalSample,
    FeatureSnapshot,
    NativeBatch,
    ProfileLevel,
    RawManifest,
    RequestPlan,
    ValidationReport,
)


class SourceAdapter(Protocol):
    """Provider code owns source selection, auth, transport, and raw collection."""

    source_id: str
    collector_version: str

    def plan(self, request: Mapping[str, Any]) -> RequestPlan:
        """Create a deterministic source-owned request plan before collection."""

    def fetch(self, plan: RequestPlan, artifacts: WeatherArtifactStore) -> RawManifest:
        """Collect immutable raw artifacts and return their verified manifest."""


class SourceParser(Protocol):
    """A parser decodes a source-native artifact without canonical normalization."""

    parser_version: str

    def parse(self, manifest: RawManifest) -> NativeBatch:
        """Parse native source records with units, levels, steps, and missing metadata."""


class Normalizer(Protocol):
    """Convert parser output into catalogue-defined canonical values."""

    normalizer_version: str

    def normalize(
        self, batch: NativeBatch
    ) -> tuple[tuple[CanonicalSample, ...], tuple[ProfileLevel, ...]]:
        """Return canonical point samples and profile levels with explicit provenance."""


class SpatialAligner(Protocol):
    """Apply approved site/grid footprints without changing atmospheric semantics."""

    spatial_version: str

    def align(
        self, samples: tuple[CanonicalSample, ...], profiles: tuple[ProfileLevel, ...]
    ) -> tuple[tuple[CanonicalSample, ...], tuple[ProfileLevel, ...]]:
        """Return deterministically aligned point/neighbourhood records."""


class AtmosphericValidator(Protocol):
    """Validate source-aware units, times, coverage, ranges, and quarantine policy."""

    validator_version: str

    def validate(
        self, samples: tuple[CanonicalSample, ...], profiles: tuple[ProfileLevel, ...]
    ) -> ValidationReport:
        """Write no persistence; describe accepted and quarantined evidence only."""


class FeatureBuilder(Protocol):
    """Build versioned derived meteorological feature snapshots."""

    feature_builder_version: str

    def build(
        self, samples: tuple[CanonicalSample, ...], profiles: tuple[ProfileLevel, ...]
    ) -> tuple[FeatureSnapshot, ...]:
        """Produce immutable feature snapshots from validated canonical evidence."""


class WeatherPersistence(Protocol):
    """S08 non-migrating persistence boundary; declared here but not implemented in S02."""

    persistence_version: str
