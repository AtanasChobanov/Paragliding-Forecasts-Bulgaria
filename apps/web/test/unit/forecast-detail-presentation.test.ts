import { describe, expect, it } from "vitest";
import {
  defaultCloudbaseHour,
  formatInputValue,
  presentDriver,
} from "../../src/features/forecast-details/forecast-detail-presentation.js";
import { createForecastResponse } from "../support/dashboard-fixtures.js";

describe("detail evidence presentation", () => {
  it("converts display units while retaining canonical inputs and small scientific values", () => {
    const row = createForecastResponse().forecastInputs.xcFeatures[0];
    if (!row) throw new Error("Fixture input missing");
    expect(formatInputValue({ ...row, unit: "K", value: 293.15 })).toBe("20 °C");
    expect(formatInputValue({ ...row, unit: "Pa", value: 100123.456 })).toBe("1,001.23 hPa");
    expect(formatInputValue({ ...row, unit: "kg/kg", value: 0.0045 })).toBe("4.5 g/kg");
    expect(formatInputValue({ ...row, unit: "1/s", value: -0.0000123 })).toBe("-1.23e-5 1/s");
    expect(row.unit).toBe("K");
  });
  it("uses published direction only for XC, and metric-specific meanings for other drivers", () => {
    const base = { code: "future_code", message: "Positive text", rank: 1, inputs: [] };
    expect(
      presentDriver({
        ...base,
        kind: "xc_contribution",
        direction: "raises",
        xcStage: "p100",
        contributionLogit: 1,
      }),
    ).toMatchObject({ symbol: "+", tone: "primary" });
    expect(
      presentDriver({
        ...base,
        kind: "xc_contribution",
        direction: "lowers",
        xcStage: "q200",
        contributionLogit: -1,
      }),
    ).toMatchObject({ symbol: "−", tone: "danger" });
    expect(
      presentDriver({
        ...base,
        kind: "xc_contribution",
        direction: "zero",
        xcStage: "p100",
        contributionLogit: 0,
      }),
    ).toMatchObject({ symbol: "=" });
    expect(
      presentDriver({ ...base, kind: "pooled_conversion", supportSuccesses: 3, supportTotal: 42 }),
    ).toMatchObject({ symbol: "ƒ" });
    expect(presentDriver({ ...base, kind: "od_override" })).toMatchObject({
      tone: "danger",
      meaning: "Critical risk rule",
    });
    expect(presentDriver({ ...base, kind: "od_score_component", scorePoints: 10 })).toMatchObject({
      tone: "warning",
    });
    expect(presentDriver({ ...base, kind: "od_score_component", scorePoints: 0 })).toMatchObject({
      tone: "secondary",
    });
    expect(presentDriver({ ...base, kind: "cloudbase_reason" })).toMatchObject({
      symbol: "ⓘ",
      tone: "sky",
    });
    expect(
      presentDriver({ ...base, kind: "cloudbase_reason", code: "cloud_type_unknown" }),
    ).toMatchObject({ symbol: "△" });
  });
  it("defaults to the daily estimated maximum even with a higher conditional hour", () => {
    const f = createForecastResponse();
    const first = f.cloudbaseHours[0];
    if (!first) throw new Error("Fixture hour missing");
    f.cloudbaseHours[0] = { ...first, regime: "indeterminate", heightMslM: 9000 };
    expect(defaultCloudbaseHour(f)).toBe(f.cloudbaseHours[3]?.validAtUtc);
  });
});
