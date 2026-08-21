from __future__ import annotations

import pytest
from pydantic import ValidationError

from paragliding_forecasts_ml.ingestion.atmosphere.catalogue import load_catalogue
from paragliding_forecasts_ml.ingestion.atmosphere.contracts import (
    CanonicalFieldValue,
    FieldProvenance,
    RequestPlan,
)

RUN_KEY = "123e4567-e89b-42d3-a456-426614174000"
UTC = "2026-08-21T12:00:00Z"


def request_plan() -> RequestPlan:
    catalogue = load_catalogue()
    return RequestPlan(
        run_key=RUN_KEY,
        source_id="noaa_gfs_0p25_aws_grib2",
        source_kind="forecast",
        ingestion_method="public_object_archive",
        request_purpose="historical_forecast",
        catalogue_version=catalogue.version,
        catalogue_sha256=catalogue.sha256,
        adapter_request_schema_version=1,
        adapter_request={"cycle": "00", "lead_hours": [24, 48]},
        expected_artifact_keys=("surface", "profile"),
        created_at_utc=UTC,
    )


def test_request_plan_round_trips_strict_json() -> None:
    plan = request_plan()

    restored = RequestPlan.model_validate_json(plan.model_dump_json(), strict=True)

    assert restored == plan


def test_request_plan_rejects_stale_catalogue_identity() -> None:
    payload = request_plan().model_dump()
    payload["catalogue_sha256"] = "0" * 64

    with pytest.raises(ValidationError, match="exact packaged T-017 catalogue"):
        RequestPlan.model_validate(payload, strict=True)


def test_canonical_field_uses_catalogue_unit_and_explicit_missingness() -> None:
    missing = CanonicalFieldValue(
        field_code="provider_cloud_base_agl_m",
        canonical_unit="m",
        canonical_value=None,
        provenance=FieldProvenance(quality_state="missing"),
    )
    assert missing.canonical_value is None

    with pytest.raises(ValidationError, match="Canonical unit"):
        CanonicalFieldValue(
            field_code="air_temperature_k",
            canonical_unit="C",
            canonical_value=293.15,
            provenance=FieldProvenance(quality_state="real"),
        )
    with pytest.raises(ValidationError, match="Missing canonical values"):
        CanonicalFieldValue(
            field_code="provider_cloud_base_agl_m",
            canonical_unit="m",
            canonical_value=900.0,
            provenance=FieldProvenance(quality_state="missing"),
        )
    with pytest.raises(ValidationError, match="Unknown canonical field"):
        CanonicalFieldValue(
            field_code="not_in_t017",
            canonical_unit="m",
            canonical_value=1.0,
            provenance=FieldProvenance(quality_state="real"),
        )
