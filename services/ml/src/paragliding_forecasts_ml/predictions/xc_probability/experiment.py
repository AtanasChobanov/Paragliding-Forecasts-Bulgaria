"""Versioned C searches, independent of the reusable feature/study policy.

Version 1 is the original grid embedded in policy.json. Version 2 overrides
only that grid and freezes its exact configuration as experiment.json in
trial, selection and model bundles. Legacy bytes and identities stay intact.
"""

from importlib.resources import files
from typing import Annotated, Literal

from pydantic import Field, FiniteFloat, model_validator

from ...ingestion.atmosphere.contracts import AtmosphericContract
from .policy import load_policy

ExperimentVersion = Literal[1, 2]
CValue = Annotated[FiniteFloat, Field(gt=0)]
CURRENT_EXPERIMENT_VERSION: ExperimentVersion = 2
SUPPORTED_EXPERIMENT_VERSIONS = (1, 2)
EXPERIMENT_RESOURCE = "xc-regularization-experiment-v2.json"


class RegularizationExperiment(AtmosphericContract):
    schema_version: Literal["xc-regularization-experiment/1"]
    experiment_version: Literal[2]
    regularization_grid: tuple[CValue, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def ordered_unique_grid(self) -> "RegularizationExperiment":
        if self.regularization_grid != tuple(sorted(set(self.regularization_grid))):
            raise ValueError("Experiment C values must be distinct and increasing.")
        return self


def experiment_payloads(experiment_version: ExperimentVersion) -> dict[str, bytes]:
    if experiment_version == 1:
        return {}
    if experiment_version != CURRENT_EXPERIMENT_VERSION:
        raise ValueError("Unsupported XC regularization experiment version.")
    raw = files(__package__).joinpath("resources", EXPERIMENT_RESOURCE).read_bytes()
    RegularizationExperiment.model_validate_json(raw)
    return {"experiment.json": raw}


def regularization_values(experiment_version: ExperimentVersion) -> tuple[float, ...]:
    if experiment_version == 1:
        return load_policy()[0].regularization_grid
    return RegularizationExperiment.model_validate_json(
        experiment_payloads(experiment_version)["experiment.json"]
    ).regularization_grid


def validate_experiment_payload(payloads: dict[str, bytes], experiment_version: ExperimentVersion):
    actual = {name: raw for name, raw in payloads.items() if name == "experiment.json"}
    if actual != experiment_payloads(experiment_version):
        raise ValueError("Bundle experiment.json differs from its declared experiment version.")
