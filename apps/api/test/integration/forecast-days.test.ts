import { forecastDaysResponseSchema, problemDetailsSchema } from "@paragliding-forecasts/contracts";
import request from "supertest";
import { describe, expect, it } from "vitest";

import { createTestApp } from "../support/create-test-app.js";

describe("GET /api/v1/forecasts/days", () => {
  it("returns five Sofia-local p100 previews centered on today", async () => {
    const response = await request(createTestApp())
      .get("/api/v1/forecasts/days")
      .query({ siteSlug: "sopot" })
      .expect(200);
    const body = forecastDaysResponseSchema.parse(response.body);

    expect(body).toMatchObject({
      siteId: 3,
      siteSlug: "sopot",
      timeZone: "Europe/Sofia",
      todayDate: "2026-07-17",
    });
    expect(body.days.map((day) => day.forecastDate)).toEqual([
      "2026-07-15",
      "2026-07-16",
      "2026-07-17",
      "2026-07-18",
      "2026-07-19",
    ]);
    expect(body.days.map((day) => day.chance100KmPct.value)).toEqual([55, 60, 65, 73, 62]);
    expect(body.days.every((day) => Object.keys(day).length === 2)).toBe(true);
  });

  it.each([
    { query: {}, issuePath: "siteSlug" },
    { query: { siteSlug: "Sopot" }, issuePath: "siteSlug" },
    { query: { siteSlug: "sopot", limit: "5" }, issuePath: "$" },
    { query: { siteSlug: "sopot", date: "2026-07-18" }, issuePath: "$" },
  ])("rejects unsupported navigation parameters for $query", async ({ query, issuePath }) => {
    const response = await request(createTestApp())
      .get("/api/v1/forecasts/days")
      .query(query)
      .expect(400);
    const problem = problemDetailsSchema.parse(response.body);

    expect(problem.code).toBe("VALIDATION_ERROR");
    expect(problem.issues?.some((issue) => issue.path === issuePath)).toBe(true);
  });

  it("returns SITE_NOT_FOUND for an unknown site", async () => {
    const response = await request(createTestApp())
      .get("/api/v1/forecasts/days")
      .query({ siteSlug: "unknown-site" })
      .expect(404);
    const problem = problemDetailsSchema.parse(response.body);

    expect(problem).toMatchObject({ status: 404, code: "SITE_NOT_FOUND" });
  });
});
