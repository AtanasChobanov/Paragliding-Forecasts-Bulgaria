import { describe, expect, it } from "vitest";

import {
  forecastDateSchema,
  forecastResponseSchema,
  healthResponseSchema,
  problemDetailsSchema,
  siteIdSchema,
  sitesResponseSchema,
  type ForecastResponse,
} from "../src/index.js";

const confidence = {
  level: "low" as const,
  note: "Synthetic demonstration value.",
};

const availableMetric = <Value>(value: Value) => ({
  value,
  dataStatus: "mock" as const,
  confidence,
});

const createForecast = (): ForecastResponse => ({
  siteId: "sopot",
  forecastDate: "2026-07-18",
  generatedAt: "2026-07-17T12:00:00.000Z",
  provenance: {
    source: "t-002-mock-provider",
    version: "mock-v1",
  },
  outputs: {
    cloudbaseMslM: availableMetric(2_200),
    chance100KmPct: availableMetric(60),
    chance200KmPct: availableMetric(30),
    chance300KmPct: availableMetric(10),
    overdevelopmentRisk: availableMetric("medium" as const),
  },
  topDrivers: ["Synthetic mock driver"],
  qualityNotes: ["Mock decision-support data; not aviation weather."],
});

describe("shared HTTP contracts", () => {
  it("accepts the canonical response payloads", () => {
    expect(
      healthResponseSchema.parse({
        status: "ok",
        service: "paragliding-forecasts-api",
        version: "0.1.0",
        timestamp: "2026-07-17T12:00:00.000Z",
      }),
    ).toBeDefined();

    expect(
      sitesResponseSchema.parse({
        sites: [{ id: "sofia-vitosha-kominite", name: "Sofia - Vitosha (Kominite)" }],
      }),
    ).toBeDefined();

    expect(forecastResponseSchema.parse(createForecast())).toBeDefined();

    expect(
      problemDetailsSchema.parse({
        type: "urn:paragliding-forecasts:problem:validation-error",
        title: "Invalid request",
        status: 400,
        detail: "The forecast query is invalid.",
        code: "VALIDATION_ERROR",
        requestId: "0f52f44f-c261-4c23-8673-abddf2cdd2ae",
        issues: [{ path: "date", message: "Expected a real calendar date." }],
      }),
    ).toBeDefined();
  });

  it("distinguishes invalid site identifiers from valid unknown slugs", () => {
    expect(siteIdSchema.safeParse("new-site").success).toBe(true);
    expect(siteIdSchema.safeParse("New Site").success).toBe(false);
  });

  it("rejects dates that match the shape but are not real calendar dates", () => {
    expect(forecastDateSchema.safeParse("2026-02-28").success).toBe(true);
    expect(forecastDateSchema.safeParse("2026-02-30").success).toBe(false);
  });

  it("requires missing metrics to use null and an explicit reason", () => {
    const forecast = createForecast();
    forecast.outputs.cloudbaseMslM = {
      value: null,
      dataStatus: "missing",
      confidence: null,
      missingReason: "No cloudbase estimate is available.",
    };

    expect(forecastResponseSchema.safeParse(forecast).success).toBe(true);
    expect(
      forecastResponseSchema.safeParse({
        ...forecast,
        outputs: {
          ...forecast.outputs,
          cloudbaseMslM: {
            value: 0,
            dataStatus: "missing",
            confidence: null,
            missingReason: "No cloudbase estimate is available.",
          },
        },
      }).success,
    ).toBe(false);
  });

  it("rejects invalid probability ranges and nesting", () => {
    const outOfRange = createForecast();
    outOfRange.outputs.chance100KmPct = availableMetric(101);
    expect(forecastResponseSchema.safeParse(outOfRange).success).toBe(false);

    const inconsistent = createForecast();
    inconsistent.outputs.chance200KmPct = availableMetric(70);
    expect(forecastResponseSchema.safeParse(inconsistent).success).toBe(false);
  });

  it("rejects unknown response fields", () => {
    expect(
      healthResponseSchema.safeParse({
        status: "ok",
        service: "paragliding-forecasts-api",
        version: "0.1.0",
        timestamp: "2026-07-17T12:00:00.000Z",
        database: "not-checked",
      }).success,
    ).toBe(false);
  });
});
