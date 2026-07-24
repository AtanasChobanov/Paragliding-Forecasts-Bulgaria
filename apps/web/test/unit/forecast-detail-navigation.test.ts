import { describe, expect, it } from "vitest";

import {
  createDashboardPath,
  createForecastDetailPath,
} from "../../src/features/forecast-details/forecast-detail-navigation.js";

describe("forecast detail navigation", () => {
  it("creates canonical detail and dashboard paths from a site/date selection", () => {
    expect(createForecastDetailPath("sopot", "2026-07-18")).toBe(
      "/forecast?site=sopot&date=2026-07-18",
    );
    expect(createDashboardPath("sopot", "2026-07-18")).toBe("/?site=sopot&date=2026-07-18");
  });
});
