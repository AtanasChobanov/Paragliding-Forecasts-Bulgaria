import type { ForecastOutputs } from "@paragliding-forecasts/contracts";
import { describe, expect, it } from "vitest";

import {
  formatConfidence,
  formatDataStatus,
  formatForecastDateDayMonth,
  formatForecastDateLong,
  formatForecastDateWeekday,
  formatForecastYear,
  formatGeneratedAt,
  formatInteger,
  formatRisk,
  summarizeConfidence,
  summarizeDataStatus,
} from "../../src/features/dashboard/forecast-presentation.js";
import { createForecastOutputs, missingMetric } from "../support/dashboard-fixtures.js";

describe("forecast presentation helpers", () => {
  it("formats date-only values without a local-timezone shift", () => {
    expect(formatForecastDateLong("2026-07-20")).toBe("Monday, 20 Jul");
    expect(formatForecastDateLong("2026-01-01")).toBe("Thursday, 01 Jan");
    expect(formatForecastDateDayMonth("2026-12-31")).toBe("31 Dec");
    expect(formatForecastDateWeekday("2026-12-31")).toBe("Thursday");
    expect(formatForecastYear("2026-12-31")).toBe("2026");
  });

  it("formats generated instants in the Europe/Sofia timezone", () => {
    expect(formatGeneratedAt("2026-07-17T20:00:00.000Z")).toBe("23:00 EEST");
    expect(formatGeneratedAt("2026-01-17T20:00:00.000Z")).toBe("22:00 EET");
  });

  it("formats numeric, risk, status, and confidence labels explicitly", () => {
    expect(formatInteger(2_400)).toBe("2,400");
    expect(formatRisk("medium")).toBe("Medium");
    expect(formatDataStatus("mock")).toBe("Mock data");
    expect(formatDataStatus("manual")).toBe("Manual data");
    expect(formatDataStatus("baseline")).toBe("Baseline data");
    expect(formatDataStatus("real")).toBe("Real data");
    expect(formatDataStatus("missing")).toBe("Unavailable");
    expect(formatDataStatus("mixed")).toBe("Mixed data");
    expect(formatConfidence("low")).toBe("Low confidence");
    expect(formatConfidence("medium")).toBe("Medium confidence");
    expect(formatConfidence("high")).toBe("High confidence");
    expect(formatConfidence("mixed")).toBe("Mixed confidence");
    expect(formatConfidence("unavailable")).toBe("Confidence unavailable");
  });

  it("summarizes homogeneous, mixed, and fully unavailable metric states", () => {
    const outputs = createForecastOutputs();
    expect(summarizeDataStatus(outputs)).toBe("mock");
    expect(summarizeConfidence(outputs)).toEqual({
      level: "low",
      notes: ["Synthetic demonstration value."],
    });

    const mixed: ForecastOutputs = {
      ...outputs,
      chance100KmPct: {
        value: 65,
        dataStatus: "manual",
        confidence: { level: "high", note: "Reviewed by a human." },
      },
      chance300KmPct: missingMetric,
    };
    expect(summarizeDataStatus(mixed)).toBe("mixed");
    expect(summarizeConfidence(mixed)).toEqual({
      level: "mixed",
      notes: ["Reviewed by a human.", "Synthetic demonstration value."],
    });

    const unavailable: ForecastOutputs = {
      cloudbaseMslM: missingMetric,
      chance100KmPct: missingMetric,
      chance200KmPct: missingMetric,
      chance300KmPct: missingMetric,
      overdevelopmentRisk: missingMetric,
    };
    expect(summarizeDataStatus(unavailable)).toBe("missing");
    expect(summarizeConfidence(unavailable)).toEqual({ level: "unavailable", notes: [] });
  });
});
