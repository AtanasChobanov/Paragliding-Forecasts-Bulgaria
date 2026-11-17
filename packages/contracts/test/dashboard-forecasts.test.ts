import { describe, expect, it } from "vitest";

import {
  forecastDaySchema,
  forecastDaysQuerySchema,
  forecastDaysResponseSchema,
  forecastSummariesQuerySchema,
  forecastSummariesResponseSchema,
  forecastSummarySchema,
  problemDetailsSchema,
  type ForecastDaysResponse,
  type DashboardForecastOutputs,
  type ForecastSummariesResponse,
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

const missingMetric = {
  value: null,
  dataStatus: "missing" as const,
  confidence: null,
  missingReason: "No forecast run is available for this site and date.",
};

const requireItem = <Value>(values: readonly Value[], index: number): Value => {
  const value = values[index];

  if (value === undefined) {
    throw new Error(`Expected an item at index ${String(index)}.`);
  }

  return value;
};

const createOutputs = (): DashboardForecastOutputs => ({
  cloudbase: { dataStatus: "mock", confidence, kind: "estimated", valueMslM: 2_400 },
  chance100KmPct: availableMetric(65),
  chance200KmPct: availableMetric(35),
  chance300KmPct: availableMetric(12),
  overdevelopmentRisk: availableMetric("medium" as const),
});

const createSummariesResponse = (): ForecastSummariesResponse => ({
  forecastDate: "2026-07-21",
  summaries: [
    {
      availability: "available",
      siteId: 1,
      siteSlug: "sofia-vitosha-kominite",
      forecastDate: "2026-07-21",
      generatedAt: "2026-07-20T20:00:00.000Z",
      metadata: {
        mode: "mock",
        source: "t-003-t-005-mock-provider",
        version: "mock-v2",
      },
      outputs: createOutputs(),
    },
    {
      availability: "missing",
      siteId: 2,
      siteSlug: "zlatitsa",
      forecastDate: "2026-07-21",
      missingReason: "No forecast run is available for this site and date.",
    },
  ],
});

const createDaysResponse = (): ForecastDaysResponse => ({
  siteId: 3,
  siteSlug: "sopot",
  timeZone: "Europe/Sofia",
  todayDate: "2026-07-21",
  days: [
    { availability: "available", forecastDate: "2026-07-19", chance100KmPct: availableMetric(45) },
    { availability: "available", forecastDate: "2026-07-20", chance100KmPct: availableMetric(55) },
    { availability: "available", forecastDate: "2026-07-21", chance100KmPct: availableMetric(65) },
    { availability: "available", forecastDate: "2026-07-22", chance100KmPct: availableMetric(73) },
    {
      availability: "missing",
      forecastDate: "2026-07-23",
      chance100KmPct: missingMetric,
      missingReason: missingMetric.missingReason,
    },
  ],
});

describe("dashboard forecast contracts", () => {
  it("parses one CSV query value into one to seven unique site slugs", () => {
    expect(
      forecastSummariesQuerySchema.parse({
        date: "2026-07-21",
        siteSlugs: "sopot, zlatitsa",
      }),
    ).toEqual({
      date: "2026-07-21",
      siteSlugs: ["sopot", "zlatitsa"],
    });

    expect(
      forecastSummariesQuerySchema.safeParse({
        date: "2026-07-21",
        siteSlugs: "sopot,sopot",
      }).success,
    ).toBe(false);
    expect(
      forecastSummariesQuerySchema.safeParse({
        date: "2026-07-21",
        siteSlugs: "one,two,three,four,five,six,seven,eight",
      }).success,
    ).toBe(false);
    expect(
      forecastSummariesQuerySchema.safeParse({
        date: "2026-07-21",
        siteSlugs: ["sopot", "zlatitsa"],
      }).success,
    ).toBe(false);
    expect(
      forecastSummariesQuerySchema.safeParse({
        date: "2026-07-21",
        siteSlugs: "sopot,",
      }).success,
    ).toBe(false);
  });

  it("accepts ordered available and explicitly missing summary items", () => {
    expect(forecastSummariesResponseSchema.parse(createSummariesResponse())).toBeDefined();
  });

  it("requires summaries to match the envelope date and ascending unique sites", () => {
    const mismatchedDate = createSummariesResponse();
    requireItem(mismatchedDate.summaries, 0).forecastDate = "2026-07-20";
    expect(forecastSummariesResponseSchema.safeParse(mismatchedDate).success).toBe(false);

    const descending = createSummariesResponse();
    descending.summaries.reverse();
    expect(forecastSummariesResponseSchema.safeParse(descending).success).toBe(false);

    const duplicateSlug = createSummariesResponse();
    requireItem(duplicateSlug.summaries, 1).siteSlug = "sofia-vitosha-kominite";
    expect(forecastSummariesResponseSchema.safeParse(duplicateSlug).success).toBe(false);

    const duplicateId = createSummariesResponse();
    requireItem(duplicateId.summaries, 1).siteId = 1;
    expect(forecastSummariesResponseSchema.safeParse(duplicateId).success).toBe(false);
  });

  it("rejects malformed summary branches and unknown fields", () => {
    const response = createSummariesResponse();

    expect(
      forecastSummariesResponseSchema.safeParse({
        ...response,
        summaries: [
          {
            ...response.summaries[1],
            generatedAt: "2026-07-20T20:00:00.000Z",
          },
        ],
      }).success,
    ).toBe(false);
    expect(
      forecastSummariesResponseSchema.safeParse({
        ...response,
        summaries: [],
      }).success,
    ).toBe(false);
  });

  it("requires cloudbase heights only for numeric regimes and separates dates from P100", () => {
    const available = requireItem(createSummariesResponse().summaries, 0);
    if (available.availability !== "available") {
      throw new Error("Expected an available fixture.");
    }
    const summary = (cloudbase: unknown) => ({
      ...available,
      outputs: { ...available.outputs, cloudbase },
    });
    const blue = { kind: "blue", dataStatus: "baseline", confidence: { level: "low" } };
    expect(forecastSummarySchema.safeParse(summary(blue)).success).toBe(true);
    expect(forecastSummarySchema.safeParse(summary({ ...blue, valueMslM: 2000 })).success).toBe(
      false,
    );
    expect(
      forecastSummarySchema.safeParse(summary({ ...blue, kind: "conditional_lcl" })).success,
    ).toBe(false);

    const publishedDay = {
      availability: "available",
      forecastDate: "2026-07-23",
      chance100KmPct: missingMetric,
    };
    expect(forecastDaySchema.safeParse(publishedDay).success).toBe(true);
    expect(
      forecastDaySchema.safeParse({
        ...publishedDay,
        availability: "missing",
        chance100KmPct: availableMetric(0),
        missingReason: "No publication",
      }).success,
    ).toBe(false);
  });

  it("accepts exactly today minus two through today plus two across year boundaries", () => {
    const response = createDaysResponse();
    response.todayDate = "2026-01-01";
    response.days = [
      {
        availability: "available",
        forecastDate: "2025-12-30",
        chance100KmPct: availableMetric(45),
      },
      {
        availability: "available",
        forecastDate: "2025-12-31",
        chance100KmPct: availableMetric(55),
      },
      {
        availability: "available",
        forecastDate: "2026-01-01",
        chance100KmPct: availableMetric(65),
      },
      {
        availability: "available",
        forecastDate: "2026-01-02",
        chance100KmPct: availableMetric(73),
      },
      {
        availability: "missing",
        forecastDate: "2026-01-03",
        chance100KmPct: missingMetric,
        missingReason: missingMetric.missingReason,
      },
    ];

    expect(forecastDaysResponseSchema.parse(response)).toBeDefined();
    expect(forecastDaysQuerySchema.parse({ siteSlug: "sopot" })).toEqual({ siteSlug: "sopot" });
  });

  it("rejects incomplete, shifted, and over-specified five-day responses", () => {
    const incomplete = createDaysResponse();
    incomplete.days.pop();
    expect(forecastDaysResponseSchema.safeParse(incomplete).success).toBe(false);

    const shifted = createDaysResponse();
    requireItem(shifted.days, 0).forecastDate = "2026-07-18";
    expect(forecastDaysResponseSchema.safeParse(shifted).success).toBe(false);

    expect(forecastDaysQuerySchema.safeParse({ siteSlug: "sopot", limit: "5" }).success).toBe(
      false,
    );
  });

  it("accepts forecast-not-found Problem Details and enforces its definition", () => {
    expect(
      problemDetailsSchema.parse({
        type: "urn:paragliding-forecasts:problem:forecast-not-found",
        title: "Forecast not found",
        status: 404,
        detail: "No forecast exists for Sopot on 2026-07-18.",
        code: "FORECAST_NOT_FOUND",
        requestId: "request-forecast-not-found",
      }),
    ).toBeDefined();
  });
});
