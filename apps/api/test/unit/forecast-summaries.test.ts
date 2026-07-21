import { forecastSummariesResponseSchema } from "@paragliding-forecasts/contracts";
import { describe, expect, it, vi } from "vitest";

import { ForecastService } from "../../src/modules/forecasts/forecast.service.js";
import { MockForecastRepository } from "../../src/modules/forecasts/mock-forecast.repository.js";
import { InMemorySiteRepository } from "../../src/modules/sites/in-memory-site.repository.js";
import { SiteService } from "../../src/modules/sites/site.service.js";
import { FIXED_NOW } from "../support/create-test-app.js";

const createDependencies = () => {
  const siteService = new SiteService(new InMemorySiteRepository());
  const forecastRepository = new MockForecastRepository({ now: () => FIXED_NOW });
  const forecastService = new ForecastService(forecastRepository, siteService);

  return { forecastRepository, forecastService };
};

describe("forecast summary service", () => {
  it("sorts requested sites by ID and preserves a missing item", async () => {
    const { forecastRepository, forecastService } = createDependencies();
    const sopotPrediction = await forecastRepository.find(3, "2026-07-18");

    expect(sopotPrediction).toBeDefined();
    vi.spyOn(forecastRepository, "listBySiteIdsAndDate").mockResolvedValue([sopotPrediction!]);

    const summaries = await forecastService.getForecastSummaries({
      date: "2026-07-18",
      siteSlugs: ["sopot", "sofia-vitosha-kominite"],
    });

    expect(forecastSummariesResponseSchema.safeParse(summaries).success).toBe(true);
    expect(summaries.summaries).toEqual([
      {
        availability: "missing",
        siteId: 1,
        siteSlug: "sofia-vitosha-kominite",
        forecastDate: "2026-07-18",
        missingReason: "No forecast exists for site 'sofia-vitosha-kominite' on 2026-07-18.",
      },
      expect.objectContaining({
        availability: "available",
        siteId: 3,
        siteSlug: "sopot",
        forecastDate: "2026-07-18",
      }),
    ]);
    expect(forecastRepository.listBySiteIdsAndDate).toHaveBeenCalledWith([1, 3], "2026-07-18");
  });

  it("does not depend on repository result order", async () => {
    const { forecastRepository, forecastService } = createDependencies();
    const sofia = await forecastRepository.find(1, "2026-07-18");
    const sopot = await forecastRepository.find(3, "2026-07-18");

    expect(sofia).toBeDefined();
    expect(sopot).toBeDefined();
    vi.spyOn(forecastRepository, "listBySiteIdsAndDate").mockResolvedValue([sopot!, sofia!]);

    const response = await forecastService.getForecastSummaries({
      date: "2026-07-18",
      siteSlugs: ["sopot", "sofia-vitosha-kominite"],
    });

    expect(response.summaries.map((summary) => summary.siteId)).toEqual([1, 3]);
    expect(response.summaries.map((summary) => summary.siteSlug)).toEqual([
      "sofia-vitosha-kominite",
      "sopot",
    ]);
  });

  it("resolves every site before consulting forecast storage", async () => {
    const { forecastRepository, forecastService } = createDependencies();
    const listPredictions = vi.spyOn(forecastRepository, "listBySiteIdsAndDate");

    await expect(
      forecastService.getForecastSummaries({
        date: "2026-07-18",
        siteSlugs: ["sopot", "unknown-site"],
      }),
    ).rejects.toMatchObject({ status: 404, code: "SITE_NOT_FOUND" });
    expect(listPredictions).not.toHaveBeenCalled();
  });
});
