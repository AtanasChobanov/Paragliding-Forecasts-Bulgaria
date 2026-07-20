import { forecastResponseSchema } from "@paragliding-forecasts/contracts";
import { describe, expect, it, vi } from "vitest";

import { ForecastService } from "../../src/modules/forecasts/forecast.service.js";
import { MockForecastRepository } from "../../src/modules/forecasts/mock-forecast.repository.js";
import { InMemorySiteRepository } from "../../src/modules/sites/in-memory-site.repository.js";
import { SiteService } from "../../src/modules/sites/site.service.js";
import { FIXED_NOW } from "../support/create-test-app.js";

const createService = (): ForecastService => {
  const siteService = new SiteService(new InMemorySiteRepository());
  const forecastRepository = new MockForecastRepository({ now: () => FIXED_NOW });
  return new ForecastService(forecastRepository, siteService);
};

describe("mock forecasts", () => {
  it("maps a domain prediction to a contract-valid API response", async () => {
    const forecast = await createService().getForecast({
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
        source: "t-002-mock-provider",
        version: "mock-v1",
      },
      outputs: {
        cloudbaseMslM: { value: 2_400, dataStatus: "mock" },
        chance100KmPct: { value: 65, dataStatus: "mock" },
        chance200KmPct: { value: 35, dataStatus: "mock" },
        chance300KmPct: { value: 12, dataStatus: "mock" },
        overdevelopmentRisk: { value: "medium", dataStatus: "mock" },
      },
      topDrivers: ["Synthetic thermal strength", "Synthetic boundary-layer depth"],
    });
  });

  it("is deterministic for the same site, date, and clock", async () => {
    const service = createService();
    const query = { siteSlug: "zlatitsa", date: "2026-07-19" } as const;

    await expect(service.getForecast(query)).resolves.toEqual(await service.getForecast(query));
  });

  it("resolves the public slug before querying forecasts by numeric site ID", async () => {
    const siteService = new SiteService(new InMemorySiteRepository());
    const forecastRepository = new MockForecastRepository({ now: () => FIXED_NOW });
    const getPrediction = vi.spyOn(forecastRepository, "get");
    const service = new ForecastService(forecastRepository, siteService);

    await service.getForecast({ siteSlug: "sopot", date: "2026-07-18" });

    expect(getPrediction).toHaveBeenCalledWith(3, "2026-07-18");
  });

  it("produces valid nested probabilities for every initial site", async () => {
    const service = createService();
    const sites = await new InMemorySiteRepository().list();

    for (const site of sites) {
      const forecast = await service.getForecast({ siteSlug: site.slug, date: "2026-07-20" });
      const parsed = forecastResponseSchema.parse(forecast);
      const chance100 = parsed.outputs.chance100KmPct;
      const chance200 = parsed.outputs.chance200KmPct;
      const chance300 = parsed.outputs.chance300KmPct;

      expect(chance100.dataStatus).not.toBe("missing");
      expect(chance200.dataStatus).not.toBe("missing");
      expect(chance300.dataStatus).not.toBe("missing");
    }
  });

  it("returns a typed site-not-found error before consulting forecast storage", async () => {
    await expect(
      createService().getForecast({ siteSlug: "unknown-site", date: "2026-07-18" }),
    ).rejects.toMatchObject({
      status: 404,
      code: "SITE_NOT_FOUND",
    });
  });
});
