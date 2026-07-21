import { forecastDaysResponseSchema } from "@paragliding-forecasts/contracts";
import { describe, expect, it, vi } from "vitest";

import { ForecastService } from "../../src/modules/forecasts/forecast.service.js";
import { MockForecastRepository } from "../../src/modules/forecasts/mock-forecast.repository.js";
import { InMemorySiteRepository } from "../../src/modules/sites/in-memory-site.repository.js";
import { SiteService } from "../../src/modules/sites/site.service.js";
import { FIXED_NOW } from "../support/create-test-app.js";

const createDependencies = () => {
  const siteService = new SiteService(new InMemorySiteRepository());
  const forecastRepository = new MockForecastRepository({ now: () => FIXED_NOW });
  const now = vi.fn(() => FIXED_NOW);
  const forecastService = new ForecastService(forecastRepository, siteService, now);

  return { forecastRepository, forecastService, now };
};

const requirePrediction = <Value>(value: Value | undefined): Value => {
  if (value === undefined) {
    throw new Error("Expected the mock forecast prediction to exist.");
  }

  return value;
};

describe("forecast day preview service", () => {
  it("returns exactly Sofia today minus two through today plus two with p100 metrics", async () => {
    const { forecastService, now } = createDependencies();
    const response = await forecastService.getForecastDays({ siteSlug: "sopot" });
    const days = forecastDaysResponseSchema.parse(response);

    expect(days).toMatchObject({
      siteId: 3,
      siteSlug: "sopot",
      timeZone: "Europe/Sofia",
      todayDate: "2026-07-17",
    });
    expect(days.days.map((day) => day.forecastDate)).toEqual([
      "2026-07-15",
      "2026-07-16",
      "2026-07-17",
      "2026-07-18",
      "2026-07-19",
    ]);
    expect(days.days.map((day) => day.chance100KmPct.value)).toEqual([55, 60, 65, 73, 62]);
    expect(days.days.every((day) => Object.keys(day).length === 2)).toBe(true);
    expect(now).toHaveBeenCalledOnce();
  });

  it("keeps missing slots instead of shifting or shortening the date window", async () => {
    const { forecastRepository, forecastService } = createDependencies();
    const todayPrediction = await forecastRepository.find(3, "2026-07-17");

    vi.spyOn(forecastRepository, "listBySiteAndDateRange").mockResolvedValue([
      requirePrediction(todayPrediction),
    ]);

    const response = await forecastService.getForecastDays({ siteSlug: "sopot" });

    expect(forecastDaysResponseSchema.safeParse(response).success).toBe(true);
    expect(response.days).toHaveLength(5);
    expect(response.days[0]?.chance100KmPct).toMatchObject({
      value: null,
      dataStatus: "missing",
      confidence: null,
      missingReason: "No 100+ km forecast is available for site 'sopot' on 2026-07-15.",
    });
    expect(response.days[2]?.chance100KmPct).toMatchObject({
      value: 65,
      dataStatus: "mock",
    });
  });

  it("does not depend on range result order", async () => {
    const { forecastRepository, forecastService } = createDependencies();
    const earlier = await forecastRepository.find(3, "2026-07-16");
    const later = await forecastRepository.find(3, "2026-07-18");

    vi.spyOn(forecastRepository, "listBySiteAndDateRange").mockResolvedValue([
      requirePrediction(later),
      requirePrediction(earlier),
    ]);

    const response = await forecastService.getForecastDays({ siteSlug: "sopot" });

    expect(response.days[1]?.chance100KmPct.value).toBe(60);
    expect(response.days[3]?.chance100KmPct.value).toBe(73);
  });

  it("returns SITE_NOT_FOUND before consulting the date range", async () => {
    const { forecastRepository, forecastService } = createDependencies();
    const listPredictions = vi.spyOn(forecastRepository, "listBySiteAndDateRange");

    await expect(
      forecastService.getForecastDays({ siteSlug: "unknown-site" }),
    ).rejects.toMatchObject({ status: 404, code: "SITE_NOT_FOUND" });
    expect(listPredictions).not.toHaveBeenCalled();
  });
});
