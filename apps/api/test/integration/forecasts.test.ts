import { forecastResponseSchema, problemDetailsSchema } from "@paragliding-forecasts/contracts";
import request from "supertest";
import { describe, expect, it } from "vitest";

import { FIXED_NOW, createTestApp } from "../support/create-test-app.js";

describe("GET /api/v1/forecasts", () => {
  it("returns a deterministic contract-valid mock forecast", async () => {
    const response = await request(createTestApp())
      .get("/api/v1/forecasts")
      .query({ siteId: "sopot", date: "2026-07-18" })
      .expect(200);
    const forecast = forecastResponseSchema.parse(response.body);

    expect(forecast.generatedAt).toBe(FIXED_NOW.toISOString());
    expect(forecast.provenance).toEqual({
      source: "t-002-mock-provider",
      version: "mock-v1",
    });
    expect(forecast.outputs).toMatchObject({
      cloudbaseMslM: { value: 2_400, dataStatus: "mock" },
      chance100KmPct: { value: 65, dataStatus: "mock" },
      chance200KmPct: { value: 35, dataStatus: "mock" },
      chance300KmPct: { value: 12, dataStatus: "mock" },
      overdevelopmentRisk: { value: "medium", dataStatus: "mock" },
    });
    expect(forecast.topDrivers.length).toBeGreaterThan(0);
    expect(forecast.qualityNotes.join(" ")).toContain("not aviation weather");
  });

  it.each([
    { query: { date: "2026-07-18" }, issuePath: "siteId" },
    { query: { siteId: "sopot" }, issuePath: "date" },
    { query: { siteId: "Sopot", date: "2026-07-18" }, issuePath: "siteId" },
    { query: { siteId: "sopot", date: "2026-02-30" }, issuePath: "date" },
    {
      query: { siteId: "sopot", date: "2026-07-18", unsupported: "value" },
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

  it("distinguishes a valid unknown site from an invalid site ID", async () => {
    const response = await request(createTestApp())
      .get("/api/v1/forecasts")
      .query({ siteId: "unknown-site", date: "2026-07-18" })
      .expect(404);
    const problem = problemDetailsSchema.parse(response.body);

    expect(problem).toMatchObject({
      status: 404,
      code: "SITE_NOT_FOUND",
      detail: "No forecast site exists for siteId 'unknown-site'.",
    });
  });
});
