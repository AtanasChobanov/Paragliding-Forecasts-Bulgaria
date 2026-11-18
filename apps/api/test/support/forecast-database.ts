import { requirePublishedValue } from "../../src/modules/forecasts/require-published-value.js";
import { sofiaFlyingHours } from "@paragliding-forecasts/contracts";
import { randomUUID } from "node:crypto";
import { mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { basename, join } from "node:path";
import type { DatabaseSync } from "node:sqlite";
import { fileURLToPath } from "node:url";

import { openDatabase } from "@paragliding-forecasts/database";

import { runMigrations } from "../../../../packages/database/src/migrate.js";

export const fixtureNow = () => new Date("2026-11-17T08:00:00Z");

const dataLocalDirectory = fileURLToPath(new URL("../../../../data/local/", import.meta.url));

export const createForecastDatabase = (migrate = true) => {
  mkdirSync(dataLocalDirectory, { recursive: true });
  const directory = mkdtempSync(join(dataLocalDirectory, "t025-forecast-test-"));
  const databaseUrl = `file:./data/local/${basename(directory)}/forecast.db`;
  const remove = () => {
    rmSync(directory, { force: true, recursive: true });
  };

  try {
    if (migrate) {
      runMigrations(databaseUrl);
    }
    const connection = openDatabase(databaseUrl);
    return {
      databaseUrl,
      sqlite: connection.sqlite,
      close() {
        try {
          connection.close();
        } finally {
          remove();
        }
      },
    };
  } catch (error) {
    remove();
    throw error;
  }
};

type CloudbaseState =
  | "cloudbase_available"
  | "potential_base_available"
  | "blue"
  | "other_cloud"
  | "indeterminate"
  | "missing";

interface FixtureForecast {
  readonly siteId: number;
  readonly p100: number | null;
  readonly cloudbase?: CloudbaseState;
  readonly od?: "low" | "high" | null;
}

export const seedForecasts = (sqlite: DatabaseSync) => {
  sqlite.exec(`
    INSERT INTO weather_grids (source_id, grid_key)
    SELECT id, 'gfs_0p25_global' FROM weather_sources WHERE code = 'noaa_gfs_0p25_aws_grib2';

    INSERT INTO weather_sampling_footprints
      (id, site_id, grid_id, purpose, sampling_method, sampling_method_version, radius_km)
    SELECT 2 * site.id, site.id, grid.id, 'point', 'bilinear', 'fixture-v1', NULL
    FROM sites AS site CROSS JOIN weather_grids AS grid WHERE grid.grid_key = 'gfs_0p25_global'
    UNION ALL
    SELECT 2 * site.id + 1, site.id, grid.id, 'neighbourhood', 'radius', 'fixture-v1', 50
    FROM sites AS site CROSS JOIN weather_grids AS grid WHERE grid.grid_key = 'gfs_0p25_global';
  `);

  const addWeather = (
    issueDate: string,
    targetDate: string,
    { cycle = "06", allowed = 1, purpose = "operational_forecast" } = {},
  ) => {
    const cycleAt = `${issueDate}T${cycle}:00:00Z`;
    sqlite
      .prepare(
        `
      INSERT OR IGNORE INTO weather_product_runs (source_id, source_product_key, reference_at_utc)
      SELECT id, ?, ? FROM weather_sources WHERE code = 'noaa_gfs_0p25_aws_grib2'
    `,
      )
      .run(cycleAt, cycleAt);
    return sqlite
      .prepare(
        `
      INSERT INTO weather_ingestion_runs (
        run_key, product_run_id, target_local_date, ingestion_method, request_purpose, status,
        source_url, permission_basis, permission_reference, operational_use_allowed,
        raw_manifest_path, raw_manifest_sha256, feature_manifest_path, feature_manifest_sha256,
        persistence_input_sha256, pipeline_version, started_at_utc, completed_at_utc
      )
      SELECT ?, id, ?, 'public_object_archive', ?, 'succeeded',
             'https://weather.example/test', 'fixture', 'fixture', ?,
             'data/raw/weather/fixture.json', ?, 'data/interim/weather/fixture.json', ?, ?,
             'fixture/1', ?, ?
      FROM weather_product_runs WHERE source_product_key = ?
    `,
      )
      .run(
        randomUUID(),
        targetDate,
        purpose,
        allowed,
        "a".repeat(64),
        "b".repeat(64),
        "c".repeat(64),
        cycleAt,
        cycleAt,
        cycleAt,
      ).lastInsertRowid;
  };

  const publish = (
    weatherId: number | bigint,
    target: string,
    createdAt: string,
    model: string,
    forecasts: readonly FixtureForecast[],
  ) => {
    const run = sqlite
      .prepare(
        `
      INSERT INTO prediction_runs (
        weather_ingestion_run_id, created_at_utc, xc_model_id,
        cloudbase_method_version, overdevelopment_policy_version
      ) VALUES (?, ?, ?, 'cloudbase-fixture-v2', 'od-fixture-v1')
    `,
      )
      .run(weatherId, createdAt, model).lastInsertRowid;

    for (const forecast of forecasts) {
      const { siteId, p100, cloudbase = "blue", od = "low" } = forecast;
      sqlite
        .prepare(
          `
        INSERT OR IGNORE INTO weather_daily_feature_snapshots
          (ingestion_run_id, point_footprint_id, neighbourhood_footprint_id, feature_contract_version)
        VALUES (?, ?, ?, 'fixture-v1')
      `,
        )
        .run(weatherId, 2 * siteId, 2 * siteId + 1);
      const snapshot = requirePublishedValue(
        sqlite
          .prepare(
            "SELECT * FROM weather_daily_feature_snapshots WHERE ingestion_run_id = ? AND point_footprint_id = ?",
          )
          .get(weatherId, 2 * siteId),
      );
      const snapshotId = Number(snapshot.id);
      if (
        !sqlite
          .prepare(
            "SELECT id FROM weather_daily_feature_profile_layers WHERE daily_feature_snapshot_id = ?",
          )
          .get(snapshotId)
      ) {
        for (const base of [0, 1500])
          sqlite
            .prepare(
              "INSERT INTO weather_daily_feature_profile_layers (daily_feature_snapshot_id, layer_base_agl_m, layer_top_agl_m) VALUES (?, ?, ?)",
            )
            .run(snapshotId, base, base + 1500);
        for (const at of sofiaFlyingHours(target)) {
          sqlite
            .prepare(
              "INSERT OR IGNORE INTO weather_product_valid_times (product_run_id, valid_at_utc) SELECT product_run_id, ? FROM weather_ingestion_runs WHERE id = ?",
            )
            .run(at, weatherId);
          const sample = sqlite
            .prepare(
              "INSERT INTO weather_point_samples (ingestion_run_id, product_valid_time_id, point_footprint_id, coverage_status) SELECT ?, v.id, ?, 'complete' FROM weather_product_valid_times v JOIN weather_ingestion_runs w ON w.product_run_id = v.product_run_id WHERE w.id = ? AND v.valid_at_utc = ?",
            )
            .run(weatherId, 2 * siteId, weatherId, at).lastInsertRowid;
          sqlite
            .prepare("INSERT INTO weather_daily_feature_snapshot_inputs VALUES (?, ?)")
            .run(snapshotId, sample);
        }
      }
      const max = cloudbase === "cloudbase_available" ? `${target}T11:00:00Z` : null;
      const lcl =
        max !== null || cloudbase === "potential_base_available" ? `${target}T12:00:00Z` : null;
      const prediction = sqlite
        .prepare(
          `
        INSERT INTO predictions (
          prediction_run_id, daily_feature_snapshot_id, p_100km, p_200km, p_300km,
          overdevelopment_risk, overdevelopment_score,
          cloudbase_summary_state, cloudbase_max_at_utc, conditional_lcl_max_at_utc
        )
        SELECT ?, id, ?, ?, ?, ?, ?, ?, ?, ?
        FROM weather_daily_feature_snapshots WHERE ingestion_run_id = ? AND point_footprint_id = ?
      `,
        )
        .run(
          run,
          p100,
          p100 === null ? null : p100 / 2,
          p100 === null ? null : p100 / 4,
          od,
          od === "low" ? 8 : null,
          cloudbase,
          max,
          lcl,
          weatherId,
          2 * siteId,
        ).lastInsertRowid;

      const addHour = sqlite.prepare(`
        INSERT INTO prediction_cloudbase_hours (
          prediction_id, valid_at_utc, regime, estimated_cloudbase_msl_m,
          estimated_cloudbase_model_agl_m, estimated_cloudbase_site_agl_m, confidence_level, reason_code
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'fixture')
      `);
      if (max !== null) {
        addHour.run(prediction, max, "cumulus", 2200, 1500, 1300, "low");
      }
      if (lcl !== null) {
        addHour.run(prediction, lcl, "indeterminate", 2062.2, 1400, -120, "low");
      }
      for (const at of sofiaFlyingHours(target)) {
        if (at === max || at === lcl) continue;
        const regime =
          cloudbase === "missing"
            ? "missing"
            : cloudbase === "other_cloud"
              ? "other_cloud"
              : cloudbase === "indeterminate"
                ? "indeterminate"
                : "blue";
        addHour.run(prediction, at, regime, null, null, null, regime === "missing" ? null : "low");
      }
      const addMetric = sqlite.prepare(`
        INSERT INTO prediction_metric_details (
          prediction_id, metric_code, data_status, confidence_level,
          confidence_note, missing_reason_code, limitations_note
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
      `);
      for (const code of ["p100", "p200", "p300", "overdevelopment", "cloudbase"]) {
        const missing = code.startsWith("p")
          ? p100 === null
          : code === "cloudbase"
            ? cloudbase === "missing"
            : od === null;
        const reason = code.startsWith("p") ? "required_inputs_missing" : "fixture_unknown";
        addMetric.run(
          prediction,
          code,
          missing ? "missing" : "baseline",
          missing ? null : code === "p200" ? "high" : "low",
          `${code} fixture confidence note`,
          missing ? reason : null,
          `${code} fixture limitations`,
        );
      }
    }
  };

  const today = "2026-11-17";
  const tomorrow = "2026-11-18";
  const later = "2026-11-19";
  publish(addWeather("2026-11-16", today), today, "2026-11-16T18:00:00Z", "today-model", [
    { siteId: 1, p100: 0.015712, cloudbase: "potential_base_available" },
    { siteId: 2, p100: 0, cloudbase: "cloudbase_available", od: "high" },
    { siteId: 3, p100: 0.00003, cloudbase: "other_cloud" },
    { siteId: 4, p100: 0.12, cloudbase: "indeterminate" },
    { siteId: 5, p100: 0.17, cloudbase: "missing", od: null },
    { siteId: 6, p100: 0.03, cloudbase: "blue" },
    { siteId: 7, p100: null },
  ]);

  publish(addWeather("2026-11-16", tomorrow), tomorrow, "2026-11-17T19:00:00Z", "late-import", [
    { siteId: 1, p100: 0.75 },
    { siteId: 2, p100: 0.2 },
  ]);
  const newest = addWeather(today, tomorrow);
  publish(newest, tomorrow, "2026-11-17T17:00:00Z", "first-model", [{ siteId: 1, p100: 0.5 }]);
  publish(newest, tomorrow, "2026-11-17T18:00:00Z", "second-model", [{ siteId: 1, p100: 0.4 }]);
  publish(newest, tomorrow, "2026-11-17T18:00:00Z", "newest-model", [{ siteId: 1, p100: null }]);
  publish(
    addWeather(today, tomorrow, { allowed: 0 }),
    tomorrow,
    "2026-11-17T21:00:00Z",
    "disallowed-model",
    [{ siteId: 1, p100: 0.99 }],
  );
  publish(
    addWeather(today, tomorrow, { cycle: "12" }),
    tomorrow,
    "2026-11-17T21:00:00Z",
    "midday-model",
    [{ siteId: 1, p100: 0.99 }],
  );
  publish(
    addWeather(today, tomorrow, { purpose: "historical_forecast" }),
    tomorrow,
    "2026-11-17T21:00:00Z",
    "historical-model",
    [{ siteId: 1, p100: 0.99 }],
  );
  publish(addWeather(today, later), later, "2026-11-17T18:00:00Z", "newest-model", [
    { siteId: 1, p100: 0.05, cloudbase: "potential_base_available" },
    { siteId: 6, p100: 0.03, cloudbase: "blue" },
  ]);
};
