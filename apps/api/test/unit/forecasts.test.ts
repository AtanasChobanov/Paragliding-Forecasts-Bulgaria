import { forecastResponseSchema } from "@paragliding-forecasts/contracts";
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

describe("detailed forecast service", () => {
  it("maps an available finite fixture to the detailed forecast contract", async () => {
    const { forecastService } = createDependencies();
    const forecast = await forecastService.getForecast({
      siteSlug: "sopot",
      date: "2026-07-18",
    });

    expect(forecastResponseSchema.safeParse(forecast).success).toBe(true);
    expect(forecast).toMatchObject({
      siteId: 3,
      siteSlug: "sopot",
      forecastDate: "2026-07-18",
      generatedAt: FIXED_NOW.toISOString(),
      provenance: {
        source: "t-003-t-005-mock-provider",
        version: "mock-v2",
      },
      outputs: {
        cloudbaseMslM: { value: 2_500, dataStatus: "mock" },
        chance100KmPct: { value: 73, dataStatus: "mock" },
        chance200KmPct: { value: 39, dataStatus: "mock" },
        chance300KmPct: { value: 13, dataStatus: "mock" },
        overdevelopmentRisk: { value: "medium", dataStatus: "mock" },
      },
      topDrivers: ["Synthetic thermal strength", "Synthetic boundary-layer depth"],
    });
  });

  it("resolves the public slug before querying by numeric site ID and date", async () => {
    const { forecastRepository, forecastService } = createDependencies();
    const findPrediction = vi.spyOn(forecastRepository, "find");

    await forecastService.getForecast({ siteSlug: "sopot", date: "2026-07-18" });

    expect(findPrediction).toHaveBeenCalledWith(3, "2026-07-18");
  });

  it("keeps probability bands nested for every initial site", async () => {
    const { forecastService } = createDependencies();
    const sites = await new InMemorySiteRepository().list();

    for (const site of sites) {
      const forecast = forecastResponseSchema.parse(
        await forecastService.getForecast({ siteSlug: site.slug, date: "2026-07-17" }),
      );
      const chance100 = forecast.outputs.chance100KmPct;
      const chance200 = forecast.outputs.chance200KmPct;
      const chance300 = forecast.outputs.chance300KmPct;

      expect(chance100.dataStatus).not.toBe("missing");
      expect(chance200.dataStatus).not.toBe("missing");
      expect(chance300.dataStatus).not.toBe("missing");
      if (
        chance100.dataStatus !== "missing" &&
        chance200.dataStatus !== "missing" &&
        chance300.dataStatus !== "missing"
      ) {
        expect(chance100.value).toBeGreaterThanOrEqual(chance200.value);
        expect(chance200.value).toBeGreaterThanOrEqual(chance300.value);
      }
    }
  });

  it("returns FORECAST_NOT_FOUND outside the finite fixture window", async () => {
    const { forecastService } = createDependencies();

    await expect(
      forecastService.getForecast({ siteSlug: "sopot", date: "2026-07-20" }),
    ).rejects.toMatchObject({
      status: 404,
      code: "FORECAST_NOT_FOUND",
      detail: "No forecast exists for site 'sopot' on 2026-07-20.",
    });
  });

  it("returns SITE_NOT_FOUND before consulting forecast storage", async () => {
    const { forecastRepository, forecastService } = createDependencies();
    const findPrediction = vi.spyOn(forecastRepository, "find");

    await expect(
      forecastService.getForecast({ siteSlug: "unknown-site", date: "2026-07-18" }),
    ).rejects.toMatchObject({ status: 404, code: "SITE_NOT_FOUND" });
    expect(findPrediction).not.toHaveBeenCalled();
  });
});
