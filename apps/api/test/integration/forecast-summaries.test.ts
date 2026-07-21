import {
  forecastSummariesResponseSchema,
  problemDetailsSchema,
} from "@paragliding-forecasts/contracts";
import request from "supertest";
import { describe, expect, it } from "vitest";

import { createTestApp } from "../support/create-test-app.js";

describe("GET /api/v1/forecasts/summaries", () => {
  it("supports one summary for the selected forecast overview", async () => {
    const response = await request(createTestApp())
      .get("/api/v1/forecasts/summaries")
      .query({ date: "2026-07-18", siteSlugs: "sopot" })
      .expect(200);
    const body = forecastSummariesResponseSchema.parse(response.body);

    expect(body.summaries).toHaveLength(1);
    expect(body.summaries[0]).toMatchObject({
      availability: "available",
      siteId: 3,
      siteSlug: "sopot",
      forecastDate: "2026-07-18",
      outputs: { chance100KmPct: { value: 73, dataStatus: "mock" } },
    });
  });

  it("returns a multi-site request in ascending ID order", async () => {
    const response = await request(createTestApp())
      .get("/api/v1/forecasts/summaries")
      .query({
        date: "2026-07-18",
        siteSlugs: "sopot,sofia-vitosha-kominite,dobrich-region",
      })
      .expect(200);
    const body = forecastSummariesResponseSchema.parse(response.body);

    expect(body.forecastDate).toBe("2026-07-18");
    expect(body.summaries).toHaveLength(3);
    expect(body.summaries.map((summary) => summary.siteId)).toEqual([1, 3, 7]);
    expect(body.summaries.every((summary) => summary.availability === "available")).toBe(true);
  });

  it("returns explicit missing items without failing the batch", async () => {
    const response = await request(createTestApp())
      .get("/api/v1/forecasts/summaries")
      .query({ date: "2026-07-20", siteSlugs: "sopot,zlatitsa" })
      .expect(200);
    const body = forecastSummariesResponseSchema.parse(response.body);

    expect(body.summaries).toEqual([
      {
        availability: "missing",
        siteId: 2,
        siteSlug: "zlatitsa",
        forecastDate: "2026-07-20",
        missingReason: "No forecast exists for site 'zlatitsa' on 2026-07-20.",
      },
      {
        availability: "missing",
        siteId: 3,
        siteSlug: "sopot",
        forecastDate: "2026-07-20",
        missingReason: "No forecast exists for site 'sopot' on 2026-07-20.",
      },
    ]);
  });

  it.each([
    { query: { date: "2026-07-18", siteSlugs: "sopot,sopot" }, issuePath: "siteSlugs" },
    {
      query: { date: "2026-07-18", siteSlugs: ["sopot", "zlatitsa"] },
      issuePath: "siteSlugs",
    },
    { query: { date: "2026-07-18", siteSlugs: "sopot," }, issuePath: "siteSlugs.1" },
    {
      query: {
        date: "2026-07-18",
        siteSlugs: "one,two,three,four,five,six,seven,eight",
      },
      issuePath: "siteSlugs",
    },
    {
      query: { date: "2026-07-18", siteSlugs: "sopot", unsupported: "value" },
      issuePath: "$",
    },
  ])("returns validation details for $query", async ({ query, issuePath }) => {
    const response = await request(createTestApp())
      .get("/api/v1/forecasts/summaries")
      .query(query)
      .expect(400);
    const problem = problemDetailsSchema.parse(response.body);

    expect(problem.code).toBe("VALIDATION_ERROR");
    expect(problem.issues?.some((issue) => issue.path === issuePath)).toBe(true);
  });

  it("rejects an unknown slug before returning any forecast summaries", async () => {
    const response = await request(createTestApp())
      .get("/api/v1/forecasts/summaries")
      .query({ date: "2026-07-18", siteSlugs: "sopot,unknown-site" })
      .expect(404);
    const problem = problemDetailsSchema.parse(response.body);

    expect(problem).toMatchObject({
      status: 404,
      code: "SITE_NOT_FOUND",
      detail: "No forecast site exists for slug 'unknown-site'.",
    });
  });
});
