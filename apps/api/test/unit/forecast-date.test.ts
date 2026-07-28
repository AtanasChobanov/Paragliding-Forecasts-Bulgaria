import { describe, expect, it } from "vitest";

import {
  addForecastDays,
  createForecastDateWindow,
  toForecastDate,
} from "../../src/modules/forecasts/forecast-date.js";

describe("forecast calendar dates", () => {
  it("derives today in Europe/Sofia rather than UTC", () => {
    expect(toForecastDate(new Date("2026-12-31T22:30:00.000Z"))).toBe("2027-01-01");
  });

  it("adds calendar days across leap-day and year boundaries", () => {
    expect(addForecastDays("2028-02-28", 1)).toBe("2028-02-29");
    expect(addForecastDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addForecastDays("2027-01-01", -1)).toBe("2026-12-31");
  });

  it("creates an inclusive date window around a center date", () => {
    expect(createForecastDateWindow("2026-07-17", 2, 2)).toEqual([
      "2026-07-15",
      "2026-07-16",
      "2026-07-17",
      "2026-07-18",
      "2026-07-19",
    ]);
  });
});
