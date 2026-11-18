import { seedForecastDetailEvidence } from "../support/forecast-detail-evidence.js";
import { requirePublishedValue } from "../../src/modules/forecasts/require-published-value.js";
import {
  forecastDaysResponseSchema,
  forecastResponseSchema,
  forecastSummariesResponseSchema,
  problemDetailsSchema,
  sitesResponseSchema,
} from "@paragliding-forecasts/contracts";
import pino from "pino";
import request from "supertest";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { createConfiguredApp } from "../../src/bootstrap.js";
import { parseConfig } from "../../src/config/env.js";
import { createForecastDatabase, fixtureNow, seedForecasts } from "../support/forecast-database.js";

const logger = pino({ level: "silent" });
const selected = "sofia-vitosha-kominite";
const allSites = `dobrich-region,pastrina,shumen,nevsha,sopot,zlatitsa,${selected}`;
const paths = {
  days: "/api/v1/forecasts/days",
  summaries: "/api/v1/forecasts/summaries",
  detail: "/api/v1/forecasts",
};

describe("SQLite dashboard HTTP integration", () => {
  let database: ReturnType<typeof createForecastDatabase>;
  let server: ReturnType<typeof createConfiguredApp>;

  const cleanup: (() => void)[] = [];

  beforeEach(() => {
    database = createForecastDatabase();
    cleanup.push(() => {
      database.close();
    });
    server = createConfiguredApp(
      parseConfig({ DATABASE_URL: database.databaseUrl }),
      logger,
      fixtureNow,
    );
    cleanup.push(server.close);
  });

  afterEach(() => {
    for (const close of cleanup.splice(0).reverse()) {
      close();
    }
  });

  it("uses the active SQLite site catalog and represents an empty publication database", async () => {
    database.sqlite.exec(
      "UPDATE sites SET name = 'SQLite Vitosha', latitude_deg = 42.5 WHERE id = 1",
    );
    const sites = await request(server.app).get("/api/v1/sites").expect(200);
    const catalog = sitesResponseSchema.parse(sites.body);
    expect(catalog.sites.map((site) => site.id)).toEqual([1, 2, 3, 4, 5, 6, 7]);
    expect(catalog.sites[0]).toMatchObject({ name: "SQLite Vitosha", latitude: 42.5 });

    const days = await request(server.app)
      .get(paths.days)
      .query({ siteSlug: selected })
      .expect(200);
    expect(forecastDaysResponseSchema.parse(days.body)).toMatchObject({
      todayDate: "2026-11-17",
      days: Array.from({ length: 5 }, () => ({
        availability: "missing",
        chance100KmPct: { value: null, dataStatus: "missing", confidence: null },
      })),
    });

    const summaries = await request(server.app)
      .get(paths.summaries)
      .query({ siteSlugs: allSites, date: "2026-11-17" })
      .expect(200);
    expect(
      forecastSummariesResponseSchema
        .parse(summaries.body)
        .summaries.map(({ availability }) => availability),
    ).toEqual(Array.from({ length: 7 }, () => "missing"));

    database.sqlite.exec("UPDATE sites SET is_active = 0 WHERE id = 7");
    const active = await request(server.app).get("/api/v1/sites").expect(200);
    expect(sitesResponseSchema.parse(active.body).sites).toHaveLength(6);
    await request(server.app).get(paths.days).query({ siteSlug: "dobrich-region" }).expect(404);
  });

  it("returns SQLite provenance, fractional percentages, distinct cloudbase states and OD evidence", async () => {
    seedForecasts(database.sqlite);
    const response = await request(server.app)
      .get(paths.summaries)
      .query({ siteSlugs: allSites, date: "2026-11-17" })
      .expect(200);
    const summaries = forecastSummariesResponseSchema.parse(response.body).summaries;
    expect(summaries.map(({ siteId }) => siteId)).toEqual([1, 2, 3, 4, 5, 6, 7]);
    expect(summaries[0]).toMatchObject({
      availability: "available",
      generatedAt: "2026-11-16T18:00:00Z",
      metadata: {
        mode: "sqlite",
        source: "NOAA GFS",
        cycleAtUtc: "2026-11-16T06:00:00Z",
        horizonDays: 1,
        xcModelId: "today-model",
        cloudbaseMethodVersion: "cloudbase-fixture-v2",
        overdevelopmentPolicyVersion: "od-fixture-v1",
        fromPreviousIssue: false,
      },
      outputs: {
        chance100KmPct: {
          value: 0.015712 * 100,
          dataStatus: "baseline",
          confidence: { level: "low", note: "p100 fixture confidence note" },
          limitationsNote: "p100 fixture limitations",
        },
        chance200KmPct: { confidence: { level: "high" } },
        cloudbase: { kind: "conditional_lcl", valueMslM: 2062.2 },
      },
    });
    expect(summaries[1]).toMatchObject({
      outputs: {
        chance100KmPct: { value: 0 },
        cloudbase: { kind: "estimated", valueMslM: 2200 },
        overdevelopmentRisk: { value: "high", confidence: { level: "low" } },
      },
    });
    const high = summaries[1];
    expect(
      high?.availability === "available" && high.outputs.overdevelopmentRisk,
    ).not.toHaveProperty("score");
    expect(summaries[2]).toMatchObject({
      outputs: {
        chance100KmPct: { value: 0.003 },
        cloudbase: { kind: "other_cloud" },
      },
    });
    expect(summaries[3]).toMatchObject({ outputs: { cloudbase: { kind: "indeterminate" } } });
    expect(summaries[4]).toMatchObject({
      outputs: {
        overdevelopmentRisk: { value: null, confidence: null, dataStatus: "missing" },
        cloudbase: { kind: "missing", missingReason: "No value is available for this metric." },
      },
    });
    expect(summaries[5]).toMatchObject({ outputs: { cloudbase: { kind: "blue" } } });
    expect(summaries[6]).toMatchObject({
      availability: "available",
      outputs: {
        chance100KmPct: {
          value: null,
          dataStatus: "missing",
          confidence: null,
          missingReason: "Required weather inputs are missing.",
          confidenceNote: "p100 fixture confidence note",
          limitationsNote: "p100 fixture limitations",
        },
      },
    });
  });

  it("selects whole publications by exact date and cycle, then publication time and ID", async () => {
    seedForecasts(database.sqlite);
    const response = await request(server.app)
      .get(paths.summaries)
      .query({ siteSlugs: `${selected},zlatitsa,sopot`, date: "2026-11-18" })
      .expect(200);
    expect(forecastSummariesResponseSchema.parse(response.body).summaries).toMatchObject([
      {
        availability: "available",
        metadata: { xcModelId: "newest-model", horizonDays: 1, fromPreviousIssue: false },
        outputs: { chance100KmPct: { value: null, dataStatus: "missing" } },
      },
      {
        availability: "available",
        metadata: { xcModelId: "late-import", horizonDays: 2, fromPreviousIssue: true },
        outputs: { chance100KmPct: { value: 20 } },
      },
      { availability: "missing" },
    ]);

    const days = await request(server.app)
      .get(paths.days)
      .query({ siteSlug: selected })
      .expect(200);
    expect(forecastDaysResponseSchema.parse(days.body).days).toMatchObject([
      { forecastDate: "2026-11-15", availability: "missing" },
      { forecastDate: "2026-11-16", availability: "missing" },
      {
        forecastDate: "2026-11-17",
        availability: "available",
        chance100KmPct: { value: 0.015712 * 100 },
      },
      { forecastDate: "2026-11-18", availability: "available", chance100KmPct: { value: null } },
      { forecastDate: "2026-11-19", availability: "available", chance100KmPct: { value: 5 } },
    ]);
  });

  it("routes a corrupt published maximum to Problem Details without falling back", async () => {
    seedForecasts(database.sqlite);
    database.sqlite.exec("DELETE FROM prediction_cloudbase_hours WHERE regime = 'indeterminate'");
    const response = await request(server.app)
      .get(paths.summaries)
      .query({ siteSlugs: selected, date: "2026-11-17" })
      .expect(500);
    expect(problemDetailsSchema.parse(response.body).code).toBe("INTERNAL_SERVER_ERROR");
  });

  it("returns detail from the same whole publication as summaries, including missing metrics", async () => {
    seedForecasts(database.sqlite);
    seedForecastDetailEvidence(database.sqlite);
    for (const date of ["2026-11-17", "2026-11-18", "2026-11-19"]) {
      const batch = await request(server.app)
        .get(paths.summaries)
        .query({ siteSlugs: allSites, date })
        .expect(200);
      for (const summary of forecastSummariesResponseSchema.parse(batch.body).summaries) {
        const response = await request(server.app)
          .get(paths.detail)
          .query({ siteSlug: summary.siteSlug, date });
        if (summary.availability === "missing") {
          expect(response.status).toBe(404);
          continue;
        }
        expect(response.status).toBe(200);
        const detail = forecastResponseSchema.parse(response.body);
        expect(detail.outputs).toEqual(summary.outputs);
        expect(detail.metadata).toEqual(summary.metadata);
        expect(detail.generatedAt).toBe(summary.generatedAt);
        expect(detail.forecastInputs.xcFeatures).toHaveLength(67);
        expect(detail.cloudbaseHours).toHaveLength(11);
        expect(detail.explanations.map((g) => g.metricCode)).toEqual([
          "p100",
          "p200",
          "p300",
          "overdevelopment",
          "cloudbase",
        ]);
      }
    }
  });

  it("preserves exact weather units, OD start-hour convection and end-sample rain intervals", async () => {
    seedForecasts(database.sqlite);
    const snapshot = requirePublishedValue(
      database.sqlite
        .prepare("SELECT daily_feature_snapshot_id id FROM predictions WHERE id = 1")
        .get(),
    );
    const sample = requirePublishedValue(
      database.sqlite
        .prepare(
          `SELECT s.id FROM weather_point_samples s JOIN weather_daily_feature_snapshot_inputs i ON i.weather_point_sample_id=s.id JOIN weather_product_valid_times v ON v.id=s.product_valid_time_id WHERE i.daily_feature_snapshot_id=? AND v.valid_at_utc='2026-11-17T08:00:00Z'`,
        )
        .get(requirePublishedValue(snapshot.id)),
    );
    const endSample = requirePublishedValue(
      database.sqlite
        .prepare(
          `SELECT s.id FROM weather_point_samples s JOIN weather_daily_feature_snapshot_inputs i ON i.weather_point_sample_id=s.id JOIN weather_product_valid_times v ON v.id=s.product_valid_time_id WHERE i.daily_feature_snapshot_id=? AND v.valid_at_utc='2026-11-17T09:00:00Z'`,
        )
        .get(requirePublishedValue(snapshot.id)),
    );
    database.sqlite
      .prepare(
        "UPDATE weather_daily_feature_snapshots SET air_temperature_2m_mean_k=293.123456 WHERE id=?",
      )
      .run(requirePublishedValue(snapshot.id));
    const provenance = database.sqlite
      .prepare(
        "INSERT INTO weather_field_provenance (daily_feature_snapshot_id,field_code,field_variant,statistic_type,quality_state) VALUES (?,'air_temperature_k','2m','mean','derived')",
      )
      .run(requirePublishedValue(snapshot.id)).lastInsertRowid;
    const cape = database.sqlite
      .prepare(
        "INSERT INTO weather_point_convection_measurements (weather_point_sample_id,parcel_method,calculation_method,calculation_method_version,cape_j_per_kg,cin_magnitude_j_per_kg) VALUES (?,'surface','project_profile','fixture-v1',500,20)",
      )
      .run(requirePublishedValue(sample.id)).lastInsertRowid;
    database.sqlite
      .prepare(
        "INSERT INTO weather_field_provenance (point_convection_measurement_id,field_code,field_variant,quality_state) VALUES (?,'convective_available_potential_energy_j_per_kg','surface','real')",
      )
      .run(cape);
    database.sqlite
      .prepare(
        "INSERT INTO weather_field_provenance (point_convection_measurement_id,field_code,field_variant,quality_state) VALUES (?,'convective_inhibition_magnitude_j_per_kg','surface','real')",
      )
      .run(cape);
    database.sqlite
      .prepare(
        "INSERT INTO weather_point_convection_measurements (weather_point_sample_id,parcel_method,calculation_method,cape_j_per_kg) VALUES (?,'most_unstable','provider',9999)",
      )
      .run(requirePublishedValue(sample.id));
    const rain = database.sqlite
      .prepare(
        "INSERT INTO weather_point_interval_measurements (weather_point_sample_id,field_code,component,interval_start_utc,interval_end_utc,statistic_type,canonical_value) VALUES (?,'precipitation_amount_mm','total','2026-11-17T08:00:00Z','2026-11-17T09:00:00Z','accumulation',1.23456)",
      )
      .run(requirePublishedValue(endSample.id)).lastInsertRowid;
    database.sqlite
      .prepare(
        "INSERT INTO weather_field_provenance (point_interval_measurement_id,field_code,statistic_type,quality_state) VALUES (?,'precipitation_amount_mm','accumulation','real')",
      )
      .run(rain);
    const driver = database.sqlite
      .prepare(
        "INSERT INTO prediction_drivers (prediction_id,metric_code,rank,kind,code,message,xc_stage,direction,contribution_logit) VALUES (1,'p100',1,'xc_contribution','temperature','Published contribution','p100','lowers',-0.25)",
      )
      .run().lastInsertRowid;
    database.sqlite
      .prepare(
        "INSERT INTO prediction_driver_inputs VALUES (?,1,'daily.air_temperature_2m_mean_k',NULL,NULL,?)",
      )
      .run(driver, provenance);
    database.sqlite
      .prepare("INSERT INTO prediction_driver_inputs VALUES (?,2,'unretained',NULL,NULL,NULL)")
      .run(driver);
    const response = await request(server.app)
      .get(paths.detail)
      .query({ siteSlug: selected, date: "2026-11-17" })
      .expect(200);
    const f = forecastResponseSchema.parse(response.body);
    expect(f.forecastInputs.xcFeatures[0]).toMatchObject({
      value: 293.123456,
      unit: "K",
      dataStatus: "real",
      qualityState: "derived",
      provenanceId: Number(provenance),
    });
    expect(f.forecastInputs.hourlyContext[0]?.odInputs).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          key: "rain",
          value: 1.23456,
          intervalStartUtc: "2026-11-17T08:00:00Z",
          intervalEndUtc: "2026-11-17T09:00:00Z",
        }),
        expect.objectContaining({ key: "cape", value: 500 }),
        expect.objectContaining({ key: "cin", value: 20 }),
      ]),
    );
    expect(
      f.forecastInputs.hourlyContext[10]?.odInputs
        .filter((r) => ["rain", "cape", "cin"].includes(r.key))
        .every((r) => r.missingReason === "Outside OD interval inputs"),
    ).toBe(true);
    expect(f.explanations[0]?.drivers[0]).toMatchObject({
      rank: 1,
      direction: "lowers",
      contributionLogit: -0.25,
      inputs: [
        { field: { value: 293.123456, unit: "K" } },
        { unavailableReason: "Exact input is retained in the ML artifact" },
      ],
    });
    database.sqlite
      .prepare(
        "UPDATE prediction_driver_inputs SET input_key='daily.relative_humidity_2m_mean_percent' WHERE prediction_driver_id=? AND input_ordinal=1",
      )
      .run(driver);
    await request(server.app)
      .get(paths.detail)
      .query({ siteSlug: selected, date: "2026-11-17" })
      .expect(500);
  });

  it("shows ambiguous heating as missing and resolves exact FK intervals independently", async () => {
    seedForecasts(database.sqlite);
    const sample = requirePublishedValue(
      database.sqlite
        .prepare(
          "SELECT weather_point_sample_id id FROM weather_daily_feature_snapshot_inputs WHERE daily_feature_snapshot_id=1 LIMIT 1",
        )
        .get(),
    );
    const add = database.sqlite.prepare(
      "INSERT INTO weather_point_interval_measurements (weather_point_sample_id,field_code,component,interval_start_utc,interval_end_utc,statistic_type,canonical_value) VALUES (?,'surface_sensible_heat_flux_upward_w_m2','not_applicable',?,'2026-11-17T08:00:00Z','interval_average',40)",
    );
    for (const start of ["2026-11-17T07:00:00Z", "2026-11-17T06:00:00Z"]) {
      const interval = add.run(requirePublishedValue(sample.id), start).lastInsertRowid;
      database.sqlite
        .prepare(
          "INSERT INTO weather_field_provenance (point_interval_measurement_id,field_code,statistic_type,quality_state) VALUES (?,'surface_sensible_heat_flux_upward_w_m2','interval_average','real')",
        )
        .run(interval);
    }
    const provenance = requirePublishedValue(
      database.sqlite
        .prepare(
          "SELECT id FROM weather_field_provenance WHERE field_code='surface_sensible_heat_flux_upward_w_m2' ORDER BY id LIMIT 1",
        )
        .get(),
    ).id;
    const driver = database.sqlite
      .prepare(
        "INSERT INTO prediction_drivers (prediction_id,metric_code,rank,kind,code,message) VALUES (1,'cloudbase',1,'cloudbase_reason','heating','Published heating input')",
      )
      .run().lastInsertRowid;
    database.sqlite
      .prepare(
        "INSERT INTO prediction_driver_inputs VALUES (?,1,'sensible_heat_flux_w_m2','2026-11-17T07:00:00Z','2026-11-17T08:00:00Z',?)",
      )
      .run(driver, requirePublishedValue(provenance));
    const response = await request(server.app)
      .get(paths.detail)
      .query({ siteSlug: selected, date: "2026-11-17" })
      .expect(200);
    expect(
      forecastResponseSchema.parse(response.body).forecastInputs.hourlyContext[0]?.cloudbaseContext,
    ).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          key: "sensible_heat_flux_w_m2",
          value: null,
          missingReason: "Ambiguous retained interval inputs",
        }),
      ]),
    );
    expect(
      forecastResponseSchema.parse(response.body).explanations[4]?.drivers[0]?.inputs[0]?.field,
    ).toMatchObject({
      value: 40,
      unit: "W/m2",
      intervalStartUtc: "2026-11-17T07:00:00Z",
      intervalEndUtc: "2026-11-17T08:00:00Z",
    });
  });

  it.each(["contradictory quality", "duplicated provenance"])(
    "rejects %s for published weather values",
    async (broken) => {
      seedForecasts(database.sqlite);
      seedForecastDetailEvidence(database.sqlite);
      if (broken === "contradictory quality")
        database.sqlite.exec(
          "UPDATE weather_field_provenance SET quality_state='missing',missing_reason_code='fixture' WHERE daily_feature_snapshot_id=1 AND field_code='air_temperature_k' AND statistic_type='mean'",
        );
      else {
        database.sqlite.exec("DROP INDEX weather_field_provenance_feature_field_unique");
        database.sqlite.exec(
          "INSERT INTO weather_field_provenance (daily_feature_snapshot_id,field_code,field_variant,statistic_type,quality_state) VALUES (1,'air_temperature_k','2m','mean','derived')",
        );
      }
      await request(server.app)
        .get(paths.detail)
        .query({ siteSlug: selected, date: "2026-11-17" })
        .expect(500);
    },
  );

  it.each(["hours", "snapshot inputs", "layers", "foreign driver", "maximum"])(
    "returns 5xx for a broken %s graph without fallback",
    async (broken) => {
      seedForecasts(database.sqlite);
      if (broken === "maximum")
        database.sqlite.exec(
          "UPDATE predictions SET conditional_lcl_max_at_utc='2026-11-17T08:00:00Z' WHERE id=1",
        );
      if (broken === "hours")
        database.sqlite.exec(
          "DELETE FROM prediction_cloudbase_hours WHERE prediction_id=1 AND valid_at_utc='2026-11-17T08:00:00Z'",
        );
      if (broken === "snapshot inputs")
        database.sqlite.exec(
          "DELETE FROM weather_daily_feature_snapshot_inputs WHERE daily_feature_snapshot_id=1",
        );
      if (broken === "layers")
        database.sqlite.exec(
          "DELETE FROM weather_daily_feature_profile_layers WHERE daily_feature_snapshot_id=1",
        );
      if (broken === "foreign driver") {
        const provenance = database.sqlite
          .prepare(
            "INSERT INTO weather_field_provenance (daily_feature_snapshot_id,field_code,field_variant,statistic_type,quality_state,missing_reason_code) VALUES (2,'air_temperature_k','2m','mean','missing','fixture')",
          )
          .run().lastInsertRowid;
        const driver = database.sqlite
          .prepare(
            "INSERT INTO prediction_drivers (prediction_id,metric_code,rank,kind,code,message,xc_stage,direction,contribution_logit) VALUES (1,'p100',1,'xc_contribution','temperature','Published','p100','zero',0)",
          )
          .run().lastInsertRowid;
        database.sqlite
          .prepare(
            "INSERT INTO prediction_driver_inputs VALUES (?,1,'daily.air_temperature_2m_mean_k',NULL,NULL,?)",
          )
          .run(driver, provenance);
      }
      await request(server.app)
        .get(paths.detail)
        .query({ siteSlug: selected, date: "2026-11-17" })
        .expect(500);
    },
  );

  it("reports missing publications in SQLite mode and serves detail in explicitly configured mock mode", async () => {
    const query = { siteSlug: selected, date: "2026-11-17" };
    const unavailable = await request(server.app).get(paths.detail).query(query).expect(404);
    expect(problemDetailsSchema.parse(unavailable.body)).toMatchObject({
      code: "FORECAST_NOT_FOUND",
      detail: `No forecast exists for site '${selected}' on 2026-11-17.`,
    });
    const mock = createConfiguredApp(
      parseConfig({
        FORECAST_DATA_MODE: "mock",
        DATABASE_URL: "file:./data/unused.db",
      }),
      logger,
      fixtureNow,
    );
    try {
      const demo = await request(mock.app).get(paths.detail).query(query).expect(200);
      expect(forecastResponseSchema.parse(demo.body).outputs.chance100KmPct.dataStatus).toBe(
        "mock",
      );
    } finally {
      mock.close();
    }
  });

  it("fails startup for a missing or unmigrated database", () => {
    const unmigrated = createForecastDatabase(false);
    try {
      expect(() =>
        createConfiguredApp(parseConfig({ DATABASE_URL: unmigrated.databaseUrl }), logger),
      ).toThrow("forecast database schema is unavailable");
      expect(() =>
        createConfiguredApp(
          parseConfig({
            DATABASE_URL: unmigrated.databaseUrl.replace("forecast.db", "nonexistent.db"),
          }),
          logger,
        ),
      ).toThrow("Unable to open the forecast database read-only");
      expect(() =>
        createConfiguredApp(parseConfig({ DATABASE_URL: "file:./outside.db" }), logger),
      ).toThrow("Check DATABASE_URL");
    } finally {
      unmigrated.close();
    }
  });
});
