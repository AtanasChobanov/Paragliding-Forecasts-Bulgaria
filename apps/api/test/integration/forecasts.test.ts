import { forecastResponseSchema, problemDetailsSchema } from "@paragliding-forecasts/contracts";
import request from "supertest";
import { describe, expect, it } from "vitest";

import { FIXED_NOW, createTestApp } from "../support/create-test-app.js";

describe("GET /api/v1/forecasts", () => {
  it("returns an available deterministic detailed forecast", async () => {
    const response = await request(createTestApp())
      .get("/api/v1/forecasts")
      .query({ siteSlug: "sopot", date: "2026-07-18" })
      .expect(200);
    const forecast = forecastResponseSchema.parse(response.body);

    expect(forecast).toMatchObject({ siteId: 3, siteSlug: "sopot" });
    expect(forecast.generatedAt).toBe(FIXED_NOW.toISOString());
    expect(forecast.provenance).toEqual({
      source: "t-003-t-005-mock-provider",
      version: "mock-v2",
    });
    expect(forecast.outputs).toMatchObject({
      cloudbaseMslM: { value: 2_500, dataStatus: "mock" },
      chance100KmPct: { value: 73, dataStatus: "mock" },
      chance200KmPct: { value: 39, dataStatus: "mock" },
      chance300KmPct: { value: 13, dataStatus: "mock" },
      overdevelopmentRisk: { value: "medium", dataStatus: "mock" },
    });
    expect(forecast.forecastInputs).toMatchObject({
      provenance: {
        source: "t-006-t-007-mock-weather-provider",
        version: "mock-weather-v1",
      },
      surfaceTemperatureC: { value: 28.2, dataStatus: "mock" },
      capeJPerKg: { value: 685, dataStatus: "mock" },
    });
    expect(forecast.topDrivers.length).toBeGreaterThan(0);
    expect(forecast).not.toHaveProperty("qualityNotes");
  });

  it("returns FORECAST_NOT_FOUND outside the finite fixture window", async () => {
    const response = await request(createTestApp())
      .get("/api/v1/forecasts")
      .query({ siteSlug: "sopot", date: "2026-07-20" })
      .expect(404);
    const problem = problemDetailsSchema.parse(response.body);

    expect(problem).toMatchObject({
      status: 404,
      code: "FORECAST_NOT_FOUND",
      detail: "No forecast exists for site 'sopot' on 2026-07-20.",
    });
  });

  it.each([
    { query: { date: "2026-07-18" }, issuePath: "siteSlug" },
    { query: { siteSlug: "sopot" }, issuePath: "date" },
    { query: { siteSlug: "Sopot", date: "2026-07-18" }, issuePath: "siteSlug" },
    { query: { siteSlug: "sopot", date: "2026-02-30" }, issuePath: "date" },
    {
      query: { siteSlug: "sopot", date: "2026-07-18", unsupported: "value" },
      issuePath: "$",
    },
  ])("returns validation details for $query", async ({ query, issuePath }) => {
    const response = await request(createTestApp())
      .get("/api/v1/forecasts")
      .query(query)
      .expect(400);
    const problem = problemDetailsSchema.parse(response.body);

    expect(problem.code).toBe("VALIDATION_ERROR");
    expect(problem.issues?.some((issue) => issue.path === issuePath)).toBe(true);
  });

  it("distinguishes a valid unknown site slug from an invalid slug", async () => {
    const response = await request(createTestApp())
      .get("/api/v1/forecasts")
      .query({ siteSlug: "unknown-site", date: "2026-07-18" })
      .expect(404);
    const problem = problemDetailsSchema.parse(response.body);

    expect(problem).toMatchObject({
      status: 404,
      code: "SITE_NOT_FOUND",
      detail: "No forecast site exists for slug 'unknown-site'.",
    });
  });
});
