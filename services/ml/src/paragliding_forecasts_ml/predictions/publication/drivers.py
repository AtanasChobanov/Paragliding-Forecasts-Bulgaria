"""Project model explanations and resolve exact SQLite provenance locators."""

from dataclasses import dataclass
from sqlite3 import Connection

from ..cloudbase.models import DailyResult, HourlyInput, HourlyResult
from ..overdevelopment.retained import SELECTORS
from ..xc_probability.models import ConversionSupport
from ..xc_probability.policy import LAYER_BOUNDS, XcPolicy
from ..xc_probability.prediction import PredictionRow

OD_FIELDS = {
    key: (
        code,
        grain,
        {"2m_above_ground": "2m", "10m_above_ground": "10m"}.get(
            dimension, dimension or "canonical"
        ),
    )
    for (code, grain, dimension), (key, _) in SELECTORS.items()
}

CLOUD_REASONS = {
    "near_saturated_surface": (
        "The model surface is nearly saturated.",
        ("surface_pressure_pa", "temperature_2m_k", "specific_humidity_2m_kg_kg"),
    ),
    "widespread_low_cloud": ("The model indicates widespread low cloud.", ("low_cloud_percent",)),
    "low_cloud_input_missing_or_invalid": (
        "Low-cloud cover is unavailable.",
        ("low_cloud_percent",),
    ),
    "potential_base_outside_profile": (
        "The estimated LCL is above the retained model profile.",
        ("profile",),
    ),
    "ccl_not_found_in_profile": (
        "No convective condensation level was found in the model profile.",
        ("profile",),
    ),
    "multiple_ccl_intersections": (
        "The model profile gives multiple convective condensation levels.",
        ("profile",),
    ),
    "formation_input_missing": (
        "Inputs needed to assess cumulus formation are missing.",
        ("pbl_model_agl_m", "profile"),
    ),
    "heating_and_condensation_supported": (
        "The model supports heating and local cumulus condensation.",
        ("pbl_model_agl_m", "profile", "sensible_heat_flux_w_m2", "latent_heat_flux_w_m2"),
    ),
    "positive_heating_not_established": (
        "The model does not establish positive surface heating.",
        ("sensible_heat_flux_w_m2", "latent_heat_flux_w_m2"),
    ),
    "local_cumulus_formation_not_supported": (
        "The model does not support local cumulus formation.",
        ("pbl_model_agl_m", "profile", "low_cloud_percent"),
    ),
    "transition_or_conflicting_evidence": (
        "The model gives mixed signals for local cumulus formation.",
        ("pbl_model_agl_m", "profile"),
    ),
    "cloud_type_unknown": ("Cloud type is uncertain.", ("low_cloud_percent",)),
    "required_source_input_unavailable": ("Required source inputs are unavailable.", ("profile",)),
    "surface_or_model_terrain_missing": (
        "Surface or model terrain inputs are missing.",
        ("surface_pressure_pa", "model_elevation_msl_m"),
    ),
    "model_profile_order_invalid": (
        "The retained model profile has inconsistent vertical ordering.",
        ("profile",),
    ),
    "model_profile_missing": ("The retained model profile is incomplete.", ("profile",)),
}
CLOUD_FORMATION = {
    "near_saturated_surface",
    "widespread_low_cloud",
    "low_cloud_input_missing_or_invalid",
    "potential_base_outside_profile",
    "ccl_not_found_in_profile",
    "multiple_ccl_intersections",
    "formation_input_missing",
    "heating_and_condensation_supported",
    "positive_heating_not_established",
    "local_cumulus_formation_not_supported",
    "transition_or_conflicting_evidence",
}
CLOUD_DAILY = {
    "blue": "All eleven hours lack model support for local cumulus formation.",
    "other_cloud": "Other cloud is forecast throughout the flying window.",
    "indeterminate": "The available hours do not establish a cloudbase maximum.",
    "missing": "Cloudbase inputs are unavailable throughout the flying window.",
}
CLOUD_FIELDS = {
    "surface_pressure_pa": ("air_pressure_pa", "surface"),
    "temperature_2m_k": ("air_temperature_k", "2m"),
    "specific_humidity_2m_kg_kg": ("specific_humidity_kg_per_kg", "2m"),
    "pbl_model_agl_m": ("provider_boundary_layer_height_agl_m", "canonical"),
    "low_cloud_percent": ("cloud_cover_percent", "low"),
    "sensible_heat_flux_w_m2": ("surface_sensible_heat_flux_upward_w_m2", "canonical"),
    "latent_heat_flux_w_m2": ("surface_latent_heat_flux_upward_w_m2", "canonical"),
}


@dataclass(frozen=True)
class DriverInput:
    key: str
    valid: str | None = None
    end: str | None = None
    provenance_id: int | None = None


@dataclass(frozen=True)
class Driver:
    metric: str
    kind: str
    code: str
    message: str
    inputs: tuple[DriverInput, ...] = ()
    stage: str | None = None
    direction: str | None = None
    contribution: float | None = None
    points: float | None = None
    successes: int | None = None
    total: int | None = None


@dataclass(frozen=True)
class Provenance:
    connection: Connection
    snapshot_id: int

    def _unique(self, query: str, parameters: tuple) -> int | None:
        rows = self.connection.execute(query, parameters).fetchmany(2)
        return rows[0][0] if len(rows) == 1 else None

    def xc(self, policy: XcPolicy, key: str) -> DriverInput:
        spec = next(item for item in policy.required_features if item.feature_id == key)
        field = (spec.field_code, spec.variant or "canonical", spec.statistic)
        if spec.scope == "daily":
            provenance_id = self._unique(
                """SELECT id FROM weather_field_provenance WHERE daily_feature_snapshot_id = ?
                   AND field_code = ? AND field_variant = ? AND statistic_type = ?""",
                (self.snapshot_id, *field),
            )
        else:
            provenance_id = self._unique(
                """SELECT p.id FROM weather_field_provenance AS p
                   JOIN weather_daily_feature_profile_layers AS l
                     ON l.id = p.daily_feature_profile_layer_id
                   WHERE l.daily_feature_snapshot_id = ?
                     AND l.layer_base_agl_m = ? AND l.layer_top_agl_m = ?
                     AND p.field_code = ? AND p.field_variant = ? AND p.statistic_type = ?""",
                (self.snapshot_id, *LAYER_BOUNDS[spec.scope], *field),
            )
        return DriverInput(key, provenance_id=provenance_id)

    def hour(self, code: str, variant: str, valid: str, end: str | None, grain: str) -> int | None:
        # Owner paths for the three supported hourly grains. The snapshot input join
        # fixes both the persisted ingestion run and the exact point footprint.
        owner, owner_query = {
            "surface": ("weather_point_sample_id", ""),
            "convection": (
                "point_convection_measurement_id",
                "JOIN weather_point_convection_measurements AS m ON m.weather_point_sample_id = s.id",
            ),
            "interval": (
                "point_interval_measurement_id",
                "JOIN weather_point_interval_measurements AS m ON m.weather_point_sample_id = s.id",
            ),
        }[grain]
        identity = "m.id" if owner_query else "s.id"
        time_clause = "AND m.interval_start_utc = ? AND m.interval_end_utc = ?" if end else ""
        return self._unique(
            f"""SELECT p.id FROM weather_daily_feature_snapshot_inputs AS i
                JOIN weather_point_samples AS s ON s.id = i.weather_point_sample_id
                JOIN weather_product_valid_times AS v ON v.id = s.product_valid_time_id
                {owner_query}
                JOIN weather_field_provenance AS p ON p.{owner} = {identity}
                WHERE i.daily_feature_snapshot_id = ? AND p.field_code = ?
                  AND p.field_variant = ? AND v.valid_at_utc = ? {time_clause}""",
            (self.snapshot_id, code, variant, end or valid, *((valid, end) if end else ())),
        )


def xc_drivers(
    row: PredictionRow, conversion: ConversionSupport, policy: XcPolicy, evidence: Provenance
) -> list[Driver]:
    drivers = []
    for stage in row.stage_drivers:
        groups = {group.group_id: group for group in stage.groups}
        messages = row.stage_messages[stage.stage]
        if not stage.top_group_ids:
            continue
        for key, message in zip(stage.top_group_ids, messages, strict=True):
            group = groups[key]
            drivers.append(
                Driver(
                    "p100" if stage.stage == "p100" else "p200",
                    "xc_contribution",
                    key,
                    message.text,
                    tuple(evidence.xc(policy, source) for source in group.source_feature_ids),
                    stage=stage.stage,
                    direction=group.direction,
                    contribution=group.contribution_logit,
                )
            )
    message = row.threshold_explanations["p300"].message
    if (
        message is not None
        and conversion.n > 0
        and (
            row.probabilities.p300.value is not None
            or row.probabilities.p300.missing_reason == "insufficient_300_support"
        )
    ):
        drivers.append(
            Driver(
                "p300",
                "pooled_conversion",
                conversion.method,
                message.text,
                successes=conversion.k,
                total=conversion.n,
            )
        )
    return drivers


def od_drivers(row: dict, evidence: Provenance) -> list[Driver]:
    drivers = []
    override_codes = {item["code"] for item in row["overrides"]}
    for reason in row["reasons"][:3]:
        inputs = []
        records = reason.get("evidence", [])
        for source in records if isinstance(records, list) else [records]:
            valid = source["valid_at_utc"]
            end = source.get("interval_end_utc")
            keys = (
                [source["key"]]
                if "key" in source
                else [
                    key
                    for key in ("mean_low_cloud_percent", "mean_humidity_percent")
                    if key in source
                ]
            )
            for key in keys:
                provenance_id = None
                if key in OD_FIELDS:
                    field, grain, variant = OD_FIELDS[key]
                    provenance_id = evidence.hour(field, variant, valid, end, grain)
                inputs.append(DriverInput(key, valid, end, provenance_id))
        drivers.append(
            Driver(
                "overdevelopment",
                "od_override" if reason["code"] in override_codes else "od_score_component",
                reason["code"],
                reason["message"],
                tuple(inputs),
                points=reason.get("points"),
            )
        )
    return drivers


def primary_cloud_reason(hour: HourlyResult) -> str:
    if not hour.reason_codes:
        raise ValueError("Cloudbase hour requires its primary reason.")
    if hour.regime == "missing":
        return hour.reason_codes[0]
    return next(
        (code for code in hour.reason_codes if code in CLOUD_FORMATION), hour.reason_codes[0]
    )


def _cloud_reason(code: str, source: HourlyInput, evidence: Provenance) -> Driver:
    message, keys = CLOUD_REASONS.get(code, (code.replace("_", " ").capitalize() + ".", ()))
    inputs = []
    for key in keys:
        interval = {
            "sensible_heat_flux_w_m2": source.sensible_interval,
            "latent_heat_flux_w_m2": source.latent_interval,
        }.get(key)
        valid, end = interval if interval else (source.valid_at_utc, None)
        provenance_id = None
        if key in CLOUD_FIELDS and (
            interval is not None or key not in {"sensible_heat_flux_w_m2", "latent_heat_flux_w_m2"}
        ):
            field, variant = CLOUD_FIELDS[key]
            provenance_id = evidence.hour(
                field, variant, valid, end, "interval" if end else "surface"
            )
        inputs.append(DriverInput(key, valid, end, provenance_id))
    return Driver("cloudbase", "cloudbase_reason", code, message, tuple(inputs))


def cloud_drivers(
    day: DailyResult,
    hours: list[HourlyResult],
    inputs: dict[str, HourlyInput],
    evidence: Provenance,
) -> list[Driver]:
    at = day.max_at_utc or day.potential_max_at_utc
    if at:
        hour = next(item for item in hours if item.valid_at_utc == at)
        codes = dict.fromkeys(
            (primary_cloud_reason(hour), "cloud_type_unknown", *hour.reason_codes)
        )
        return [
            _cloud_reason(code, inputs[at], evidence)
            for code in [code for code in codes if code in hour.reason_codes][:3]
        ]
    return [
        Driver("cloudbase", "cloudbase_reason", day.summary_state, CLOUD_DAILY[day.summary_state])
    ]
