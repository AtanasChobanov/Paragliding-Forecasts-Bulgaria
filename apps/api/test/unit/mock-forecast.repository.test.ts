import { describe, expect, it } from "vitest";

import { MockForecastRepository } from "../../src/modules/forecasts/mock-forecast.repository.js";
import { FIXED_NOW } from "../support/create-test-app.js";

const createRepository = (): MockForecastRepository =>
  new MockForecastRepository({ now: () => FIXED_NOW });

describe("mock forecast repository", () => {
  it("creates a bounded date-aware catalog around the Sofia current date", async () => {
    const repository = createRepository();

    await expect(repository.find(3, "2026-07-14")).resolves.toBeUndefined();
    await expect(repository.find(3, "2026-07-20")).resolves.toBeUndefined();
    await expect(repository.find(3, "2026-07-15")).resolves.toMatchObject({
      forecastDate: "2026-07-15",
      probability100KmPct: 55,
      probability200KmPct: 30,
      probability300KmPct: 10,
      cloudbasePredictionMslM: 2_250,
    });
    await expect(repository.find(3, "2026-07-17")).resolves.toMatchObject({
      forecastDate: "2026-07-17",
      probability100KmPct: 65,
      probability200KmPct: 35,
      probability300KmPct: 12,
      cloudbasePredictionMslM: 2_400,
    });
    await expect(repository.find(3, "2026-07-18")).resolves.toMatchObject({
      forecastDate: "2026-07-18",
      probability100KmPct: 73,
      probability200KmPct: 39,
      probability300KmPct: 13,
      cloudbasePredictionMslM: 2_500,
    });
  });

  it("captures generated time once and returns defensive copies", async () => {
    const repository = createRepository();
    const first = await repository.find(3, "2026-07-17");
    const second = await repository.find(3, "2026-07-17");

    expect(first?.generatedAt).toBe(FIXED_NOW.toISOString());
    expect(second).toEqual(first);
    expect(second).not.toBe(first);
    expect(second?.topDrivers).not.toBe(first?.topDrivers);
  });

  it("lists requested sites on one date in requested order", async () => {
    const predictions = await createRepository().listBySiteIdsAndDate(
      [3, 1, 7],
      "2026-07-17",
    );

    expect(predictions.map((prediction) => prediction.siteId)).toEqual([3, 1, 7]);
  });

  it("lists an inclusive site/date range in chronological order", async () => {
    const predictions = await createRepository().listBySiteAndDateRange(
      3,
      "2026-07-16",
      "2026-07-18",
    );

    expect(predictions.map((prediction) => prediction.forecastDate)).toEqual([
      "2026-07-16",
      "2026-07-17",
      "2026-07-18",
    ]);
  });
});
