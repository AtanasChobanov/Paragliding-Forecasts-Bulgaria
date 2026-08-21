"""Runtime access to the single T-017 atmospheric field catalogue."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

CATALOGUE_RESOURCE_NAME = "weather-field-catalogue.json"


class CatalogueError(ValueError):
    """The packaged T-017 catalogue cannot safely define runtime contracts."""


class CatalogueField(BaseModel):
    """One canonical weather field with its source-of-truth unit."""

    model_config = ConfigDict(extra="allow", frozen=True, strict=True)

    name: str = Field(min_length=1)
    unit: str = Field(min_length=1)


class CatalogueSourceMapping(BaseModel):
    """A source mapping retains its T-017 source-specific metadata verbatim."""

    model_config = ConfigDict(extra="allow", frozen=True, strict=True)

    sourceId: str = Field(min_length=1)
    sourceKind: str = Field(min_length=1)


class CatalogueDocument(BaseModel):
    """The validated shape needed at the runtime boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    catalogueVersion: str = Field(min_length=1)
    generatedAt: str = Field(min_length=1)
    status: str = Field(min_length=1)
    notForSafetyCriticalUse: bool
    sourceKinds: tuple[str, ...] = Field(min_length=1)
    requiredProvenance: tuple[str, ...] = Field(min_length=1)
    qualityStates: tuple[str, ...] = Field(min_length=1)
    canonicalFields: tuple[CatalogueField, ...] = Field(min_length=1)
    sourceMappings: tuple[CatalogueSourceMapping, ...] = Field(min_length=1)
    sourceRoleDecision: dict[str, str] = Field(min_length=1)

    @field_validator("sourceKinds", "qualityStates")
    @classmethod
    def values_must_be_unique(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)) or any(not value.strip() for value in values):
            raise ValueError("Catalogue values must be non-empty and unique.")
        return values

    @model_validator(mode="after")
    def mappings_and_fields_must_be_unique(self) -> CatalogueDocument:
        names = [field.name for field in self.canonicalFields]
        source_ids = [mapping.sourceId for mapping in self.sourceMappings]
        if len(names) != len(set(names)):
            raise ValueError("Canonical field names must be unique.")
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Source mapping IDs must be unique.")
        if any(mapping.sourceKind not in self.sourceKinds for mapping in self.sourceMappings):
            raise ValueError("Every source mapping must use a declared source kind.")
        return self


@dataclass(frozen=True)
class AtmosphericCatalogue:
    """Immutable indexed access to the packaged catalogue bytes and definitions."""

    document: CatalogueDocument
    sha256: str
    resource_path: str

    @property
    def version(self) -> str:
        return self.document.catalogueVersion

    @property
    def field_codes(self) -> frozenset[str]:
        return frozenset(field.name for field in self.document.canonicalFields)

    @property
    def quality_states(self) -> frozenset[str]:
        return frozenset(self.document.qualityStates)

    @property
    def source_ids(self) -> frozenset[str]:
        return frozenset(mapping.sourceId for mapping in self.document.sourceMappings)

    def field_unit(self, field_code: str) -> str:
        for field in self.document.canonicalFields:
            if field.name == field_code:
                return field.unit
        raise CatalogueError(f"Unknown canonical field: {field_code}")

    def validate_field_code(self, field_code: str) -> str:
        self.field_unit(field_code)
        return field_code

    def validate_quality_state(self, quality_state: str) -> str:
        if quality_state not in self.quality_states:
            raise CatalogueError(f"Unknown catalogue quality state: {quality_state}")
        return quality_state

    def validate_source_id(self, source_id: str) -> str:
        if source_id not in self.source_ids:
            raise CatalogueError(f"Unknown T-017 source ID: {source_id}")
        return source_id


@lru_cache(maxsize=1)
def load_catalogue() -> AtmosphericCatalogue:
    """Load and validate the one packaged catalogue resource exactly once."""

    resource = resources.files("paragliding_forecasts_ml.ingestion.atmosphere").joinpath(
        "resources", CATALOGUE_RESOURCE_NAME
    )
    raw = resource.read_bytes()
    try:
        document = CatalogueDocument.model_validate_json(raw, strict=True)
    except ValidationError as error:
        raise CatalogueError("The packaged T-017 weather catalogue is invalid.") from error
    return AtmosphericCatalogue(
        document=document,
        sha256=hashlib.sha256(raw).hexdigest(),
        resource_path=(
            "paragliding_forecasts_ml.ingestion.atmosphere.resources/" + CATALOGUE_RESOURCE_NAME
        ),
    )
