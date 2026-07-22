import {
  forecastSummariesResponseSchema,
  problemDetailsSchema,
} from "@paragliding-forecasts/contracts";
import request from "supertest";
import { describe, expect, it, vi } from "vitest";

import { MockForecastRepository } from "../../src/modules/forecasts/mock-forecast.repository.js";
import { FIXED_NOW, createTestApp } from "../support/create-test-app.js";

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
    expect(body.summaries.map((summary) => summary.siteSlug)).toEqual([
      "sofia-vitosha-kominite",
      "sopot",
      "dobrich-region",
    ]);
    expect(body.summaries.every((summary) => summary.availability === "available")).toBe(true);
  });

  it("supports the successful upper bound of all seven unique sites", async () => {
    const response = await request(createTestApp())
      .get("/api/v1/forecasts/summaries")
      .query({
        date: "2026-07-18",
        siteSlugs: "dobrich-region,pastrina,shumen,nevsha,sopot,zlatitsa,sofia-vitosha-kominite",
      })
      .expect(200);
    const body = forecastSummariesResponseSchema.parse(response.body);

    expect(body.summaries.map((summary) => summary.siteSlug)).toEqual([
      "sofia-vitosha-kominite",
      "zlatitsa",
      "sopot",
      "nevsha",
      "shumen",
      "pastrina",
      "dobrich-region",
    ]);
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

  it("returns available and missing items together without failing the batch", async () => {
    const forecastRepository = new MockForecastRepository({ now: () => FIXED_NOW });
    const sopotPrediction = await forecastRepository.find(3, "2026-07-18");

    if (sopotPrediction === undefined) {
      throw new Error("Expected the Sopot fixture prediction to exist.");
    }

    vi.spyOn(forecastRepository, "listBySiteIdsAndDate").mockResolvedValue([sopotPrediction]);

    const response = await request(createTestApp({ forecastRepository }))
      .get("/api/v1/forecasts/summaries")
      .query({ date: "2026-07-18", siteSlugs: "sopot,zlatitsa" })
      .expect(200);
    const body = forecastSummariesResponseSchema.parse(response.body);

    expect(body.summaries).toEqual([
      {
        availability: "missing",
        siteId: 2,
        siteSlug: "zlatitsa",
        forecastDate: "2026-07-18",
        missingReason: "No forecast exists for site 'zlatitsa' on 2026-07-18.",
      },
      expect.objectContaining({
        availability: "available",
        siteId: 3,
        siteSlug: "sopot",
        forecastDate: "2026-07-18",
      }),
    ]);
  });

  it.each([
    { query: { siteSlugs: "sopot" }, issuePath: "date" },
    { query: { date: "2026-07-18" }, issuePath: "siteSlugs" },
    {
      query: { date: ["2026-07-18", "2026-07-19"], siteSlugs: "sopot" },
      issuePath: "date",
    },
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

    expect(response.headers["content-type"]).toMatch(/^application\/problem\+json/);
    expect(response.headers["x-request-id"]).toBe(problem.requestId);
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
