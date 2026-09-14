"""Independent version identifiers for durable weather ingestion stages."""

from __future__ import annotations

from pydantic import model_validator

from ..atmosphere.contracts import AtmosphericContract, validate_component_version

COMPONENT_ORDER = (
    "collector",
    "parser",
    "normalizer",
    "spatial",
    "validator",
    "feature_builder",
    "persistence",
)


class PipelineVersions(AtmosphericContract):
    """The complete ordered version tuple persisted by S08."""

    collector: str
    parser: str
    normalizer: str
    spatial: str
    validator: str
    feature_builder: str
    persistence: str

    @model_validator(mode="after")
    def versions_must_be_independent_component_versions(self) -> PipelineVersions:
        for component in COMPONENT_ORDER:
            validate_component_version(getattr(self, component))
        return self

    @property
    def pipe_delimited(self) -> str:
        return "|".join(getattr(self, component) for component in COMPONENT_ORDER)

    def for_stage(self, stage: str) -> str:
        if stage not in COMPONENT_ORDER:
            raise ValueError(f"Unknown weather pipeline component: {stage}")
        return getattr(self, stage)


def output_directory_name(component_version: str) -> str:
    """Return a stable, source-independent stage directory name such as parser-v1."""

    validate_component_version(component_version)
    _name, revision = component_version.rsplit("/", maxsplit=1)
    return f"v{revision}"
