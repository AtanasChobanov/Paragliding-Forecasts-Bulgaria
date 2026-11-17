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

  it("rejects detail in SQLite mode and serves it in explicitly configured mock mode", async () => {
    const query = { siteSlug: selected, date: "2026-11-17" };
    const unavailable = await request(server.app).get(paths.detail).query(query).expect(404);
    expect(problemDetailsSchema.parse(unavailable.body)).toMatchObject({
      code: "FORECAST_NOT_FOUND",
      detail: "Detailed forecasts are not yet available in SQLite mode.",
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
