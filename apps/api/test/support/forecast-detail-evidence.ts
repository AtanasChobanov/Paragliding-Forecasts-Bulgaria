import { xcInputInventory } from "@paragliding-forecasts/contracts";
import type { DatabaseSync } from "node:sqlite";
import { surfaceInputs } from "../../src/modules/forecasts/forecast-input-catalogue.js";
import { requirePublishedValue } from "../../src/modules/forecasts/require-published-value.js";

// Deterministic synthetic evidence for the real SQL adapter, never the local database.
export const seedForecastDetailEvidence = (database: DatabaseSync) => {
  for (const predictionId of [1, 2]) {
    database.prepare("UPDATE predictions SET p_300km=p_200km*3.0/42 WHERE id=?").run(predictionId);
    const snapshotId = Number(
      requirePublishedValue(
        database
          .prepare("SELECT daily_feature_snapshot_id id FROM predictions WHERE id=?")
          .get(predictionId),
      ).id,
    );
    const layers = database
      .prepare(
        "SELECT * FROM weather_daily_feature_profile_layers WHERE daily_feature_snapshot_id=?",
      )
      .all(snapshotId);
    for (const spec of xcInputInventory) {
      const daily = spec.scope === "daily";
      const owner = daily
        ? snapshotId
        : Number(layers.find((l) => l.layer_base_agl_m === spec.layerBaseAglM)?.id);
      const table = daily
        ? "weather_daily_feature_snapshots"
        : "weather_daily_feature_profile_layers";
      const key = daily ? "daily_feature_snapshot_id" : "daily_feature_profile_layer_id";
      const value =
        spec.unit === "K"
          ? 293.123456
          : spec.unit === "Pa"
            ? 100123.456
            : spec.unit === "kg/kg"
              ? 0.006
              : spec.unit === "%"
                ? 55
                : spec.unit === "degree"
                  ? 180
                  : spec.unit === "m"
                    ? 1000
                    : 1.23456;
      database.prepare(`UPDATE ${table} SET ${spec.column}=? WHERE id=?`).run(value, owner);
      database
        .prepare(
          `INSERT INTO weather_field_provenance (${key},field_code,field_variant,statistic_type,quality_state) VALUES (?,?,?,?,'derived')`,
        )
        .run(owner, spec.fieldCode, spec.variant, spec.statistic);
    }
    const samples = database
      .prepare(
        "SELECT s.*,v.valid_at_utc FROM weather_point_samples s JOIN weather_daily_feature_snapshot_inputs i ON i.weather_point_sample_id=s.id JOIN weather_product_valid_times v ON v.id=s.product_valid_time_id WHERE i.daily_feature_snapshot_id=? ORDER BY v.valid_at_utc",
      )
      .all(snapshotId);
    for (const sample of samples) {
      for (const [key, , column, code, variant, unit] of surfaceInputs) {
        const value =
          unit === "K"
            ? 293.5
            : unit === "Pa"
              ? 98000
              : unit === "kg/kg"
                ? 0.007
                : unit === "%"
                  ? 20
                  : unit === "m"
                    ? 1500
                    : 3.5;
        // PBL's method and height must change together under its CHECK constraint.
        if (key === "pbl_model_agl_m")
          database
            .prepare(
              "UPDATE weather_point_samples SET provider_boundary_layer_height_agl_m=?,provider_boundary_layer_method='fixture' WHERE id=?",
            )
            .run(value, requirePublishedValue(sample.id));
        else
          database
            .prepare(`UPDATE weather_point_samples SET ${column}=? WHERE id=?`)
            .run(value, requirePublishedValue(sample.id));
        database
          .prepare(
            "INSERT INTO weather_field_provenance (weather_point_sample_id,field_code,field_variant,statistic_type,quality_state) VALUES (?,?,?,?, 'real')",
          )
          .run(
            requirePublishedValue(sample.id),
            code,
            variant,
            key === "stored_weather_lcl" ? "instantaneous" : null,
          );
      }
    }
    for (const [metric, stage] of [
      ["p100", "p100"],
      ["p200", "q200"],
    ] as const) {
      for (const [i, direction] of ["raises", "lowers", "zero"].entries()) {
        const spec = requirePublishedValue(xcInputInventory[i]);
        const provenance = requirePublishedValue(
          database
            .prepare(
              "SELECT id FROM weather_field_provenance WHERE daily_feature_snapshot_id=? AND field_code=? AND field_variant=? AND statistic_type=?",
            )
            .get(snapshotId, spec.fieldCode, spec.variant, spec.statistic),
        );
        const driver = database
          .prepare(
            "INSERT INTO prediction_drivers (prediction_id,metric_code,rank,kind,code,message,xc_stage,direction,contribution_logit) VALUES (?,?,?,'xc_contribution',?,?,?, ?,?)",
          )
          .run(
            predictionId,
            metric,
            i + 1,
            `fixture_${direction}`,
            `Published ${direction} temperature contribution`,
            stage,
            direction,
            i === 0 ? 0.3 : i === 1 ? -0.2 : 0,
          ).lastInsertRowid;
        database
          .prepare("INSERT INTO prediction_driver_inputs VALUES (?,1,?,NULL,NULL,?)")
          .run(driver, spec.key, requirePublishedValue(provenance.id));
      }
    }
    database
      .prepare(
        "INSERT INTO prediction_drivers (prediction_id,metric_code,rank,kind,code,message,support_successes,support_total) VALUES (?,'p300',1,'pooled_conversion','pooled','P300 = P200 × 3/42; sparse pooled support',3,42)",
      )
      .run(predictionId);
    database
      .prepare(
        "INSERT INTO prediction_drivers (prediction_id,metric_code,rank,kind,code,message,score_points) VALUES (?,'overdevelopment',1,?,?,?,?)",
      )
      .run(
        predictionId,
        predictionId === 2 ? "od_override" : "od_score_component",
        predictionId === 2 ? "critical_rain" : "low_cloud",
        predictionId === 2 ? "Critical rainfall override" : "Low cloud risk component",
        predictionId === 2 ? null : 8,
      );
    const driver = database
      .prepare(
        "INSERT INTO prediction_drivers (prediction_id,metric_code,rank,kind,code,message) VALUES (?,'cloudbase',1,'cloudbase_reason','transition_or_conflicting_evidence','Mixed evidence for local cumulus formation')",
      )
      .run(predictionId).lastInsertRowid;
    database
      .prepare(
        "INSERT INTO prediction_driver_inputs VALUES (?,1,'profile','2026-11-17T12:00:00Z',NULL,NULL)",
      )
      .run(driver);
  }
  // Mixed numeric and nonnumeric regimes, with separate estimated/conditional maxima.
  database.exec(
    "UPDATE prediction_cloudbase_hours SET regime='cumulus',estimated_cloudbase_msl_m=2100,estimated_cloudbase_model_agl_m=1400,estimated_cloudbase_site_agl_m=-100 WHERE prediction_id=2 AND valid_at_utc='2026-11-17T10:00:00Z'",
  );
  database.exec(
    "UPDATE prediction_cloudbase_hours SET regime='indeterminate',estimated_cloudbase_msl_m=2000,estimated_cloudbase_model_agl_m=1300,estimated_cloudbase_site_agl_m=-200 WHERE prediction_id=2 AND valid_at_utc='2026-11-17T13:00:00Z'",
  );
  database.exec(
    "UPDATE prediction_cloudbase_hours SET regime='other_cloud' WHERE prediction_id=2 AND valid_at_utc='2026-11-17T09:00:00Z'",
  );
  database.exec(
    "UPDATE prediction_cloudbase_hours SET regime='missing',confidence_level=NULL WHERE prediction_id=2 AND valid_at_utc='2026-11-17T14:00:00Z'",
  );
  database.exec(
    "UPDATE prediction_cloudbase_hours SET regime='indeterminate' WHERE prediction_id=2 AND valid_at_utc='2026-11-17T15:00:00Z'",
  );
};
