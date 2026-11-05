"""Shared synthetic inputs; never loads the user's local forecast data."""

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from paragliding_forecasts_ml.ingestion.gfs.models import sofia_window_instants
from paragliding_forecasts_ml.ingestion.weather.serialization import (
    canonical_json_bytes,
    sha256_bytes,
)
from paragliding_forecasts_ml.predictions.cloudbase.models import HourlyInput, ProfileLevel
from paragliding_forecasts_ml.predictions.xc_probability.inputs import ForecastInput, Observation
from paragliding_forecasts_ml.predictions.xc_probability.policy import load_policy
from paragliding_forecasts_ml.predictions.xc_probability.study import StudyRow, compile_study


@pytest.fixture
def synthetic_study():
    policy, _ = load_policy()
    rows = []
    for season, first in ((2022, "2021-10-01"), (2023, "2022-10-01"), (2024, "2023-10-05")):
        for index in range(14):
            target = date.fromisoformat(first) + timedelta(days=index // 7)
            labels = (int(index < 7), int(index < 3), int(season > 2022 and index < 1))
            denominator = 1 if labels[1] else 2
            for horizon in (1, 2, 3):
                issue = target - timedelta(days=horizon)
                key = {"season": season, "index": index, "horizon": horizon}
                inputs = ForecastInput(
                    run_key=str(UUID(int=target.toordinal() * 3 + horizon, version=4)),
                    site_id=index % 7 + 1,
                    site_slug=f"site-{index % 7 + 1}",
                    target_local_date=str(target),
                    issue_local_date=str(issue),
                    horizon_days=horizon,
                    cycle_reference_utc=f"{issue}T06:00:00Z",
                    source_ready_at_utc=f"{issue}T10:00:00Z",
                    issue_cutoff_utc=datetime.combine(
                        issue, time(16), tzinfo=ZoneInfo("Europe/Sofia")
                    )
                    .astimezone(UTC)
                    .strftime("%Y-%m-%dT%H:%M:%SZ"),
                    valid_times_utc=sofia_window_instants(str(target)),
                    observations=tuple(
                        Observation(
                            feature_id=spec.feature_id,
                            value=float(position + index + horizon + 1),
                            canonical_unit=spec.canonical_unit,
                            quality_state="derived",
                            missing_reason=None,
                            provenance={"fixture": "synthetic"},
                        )
                        for position, spec in enumerate(policy.required_features)
                    ),
                    source_lineage={"fixture": "synthetic"},
                )
                rows.append(
                    StudyRow(
                        row_id=sha256_bytes(canonical_json_bytes(key)),
                        inputs=inputs,
                        source_season=season,
                        labels=labels,
                        sampling_weight=float(denominator),
                        inclusion_numerator=1,
                        inclusion_denominator=denominator,
                        label_row_sha256="a" * 64,
                        cohort_row_sha256=sha256_bytes(
                            canonical_json_bytes({"season": season, "index": index})
                        ),
                    )
                )
    source_lineage = {
        key: letter * 64
        for key, letter in zip(
            (
                "dataset_id",
                "parent_dataset_id",
                "correction_id",
                "cohort_plan_id",
                "source_audit_id",
                "dataset_manifest_sha256",
                "cohort_manifest_sha256",
            ),
            "abcdefa",
            strict=True,
        )
    }
    return compile_study(tuple(rows), lineage=source_lineage, policy=policy)


@pytest.fixture
def cloudbase_column():
    return HourlyInput(
        run_key="11111111-1111-4111-8111-111111111111",
        site_id=1,
        site_slug="mountain",
        target_local_date="2024-06-29",
        valid_at_utc="2024-06-29T12:00:00Z",
        reference_at_utc="2024-06-28T06:00:00Z",
        issue_cutoff_utc="2024-06-28T13:00:00Z",
        source_ready_at_utc="2024-06-28T10:00:00Z",
        horizon_days=1,
        site_elevation_msl_m=1500,
        model_elevation_msl_m=500,
        surface_pressure_pa=95000,
        temperature_2m_k=300,
        specific_humidity_2m_kg_kg=0.010,
        pbl_model_agl_m=2500,
        low_cloud_percent=5,
        total_cloud_percent=10,
        sensible_heat_flux_w_m2=150,
        latent_heat_flux_w_m2=80,
        sensible_interval=("2024-06-29T11:00:00Z", "2024-06-29T12:00:00Z"),
        latent_interval=("2024-06-29T11:00:00Z", "2024-06-29T12:00:00Z"),
        profile=tuple(
            ProfileLevel(pressure_pa=p, height_msl_m=z, temperature_k=t, specific_humidity_kg_kg=q)
            for p, z, t, q in [
                (92500, 750, 297, 0.010),
                (90000, 1000, 294, 0.009),
                (85000, 1500, 289, 0.008),
                (80000, 2000, 285, 0.006),
                (70000, 3100, 275, 0.004),
                (60000, 4300, 267, 0.003),
                (50000, 5600, 255, 0.001),
            ]
        ),
    )
