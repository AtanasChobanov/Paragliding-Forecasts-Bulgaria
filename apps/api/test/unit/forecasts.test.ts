import { forecastResponseSchema } from "@paragliding-forecasts/contracts";
import { describe, expect, it } from "vitest";

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
  it("maps a storage-shaped record to a contract-valid API response", async () => {
    const forecast = await createService().getForecast({
      siteId: "sopot",
      date: "2026-07-18",
    });

    expect(forecastResponseSchema.safeParse(forecast).success).toBe(true);
    expect(forecast).toMatchObject({
      siteId: "sopot",
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
    });
    expect(forecast.qualityNotes.join(" ")).toContain("not a safety guarantee");
  });

  it("is deterministic for the same site, date, and clock", async () => {
    const service = createService();
    const query = { siteId: "zlatitsa", date: "2026-07-19" } as const;

    await expect(service.getForecast(query)).resolves.toEqual(await service.getForecast(query));
  });

  it("produces valid nested probabilities for every initial site", async () => {
    const service = createService();
    const sites = await new InMemorySiteRepository().list();

    for (const site of sites) {
      const forecast = await service.getForecast({ siteId: site.id, date: "2026-07-20" });
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
      createService().getForecast({ siteId: "unknown-site", date: "2026-07-18" }),
    ).rejects.toMatchObject({
      status: 404,
      code: "SITE_NOT_FOUND",
    });
  });
});
