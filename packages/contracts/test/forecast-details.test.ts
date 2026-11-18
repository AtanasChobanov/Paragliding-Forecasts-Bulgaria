import { requirePublishedValue } from "../../../apps/api/src/modules/forecasts/require-published-value.js";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  cloudbaseHourSchema,
  forecastResponseSchema,
  sofiaFlyingHours,
  xcInputInventory,
} from "../src/index.js";
import { createForecast } from "./forecast-fixture.js";

describe("published detail contract", () => {
  it("matches all 67 ML policy fields, owners, units, statistics and order", () => {
    const policy = JSON.parse(
      readFileSync(
        new URL(
          "../../../services/ml/src/paragliding_forecasts_ml/predictions/xc_probability/resources/xc-probability-policy-v1.json",
          import.meta.url,
        ),
        "utf8",
      ),
    ) as { required_features: Record<string, unknown>[] };
    expect(xcInputInventory).toHaveLength(67);
    expect(
      xcInputInventory.map((s) => [
        s.key,
        s.column,
        s.scope,
        s.unit,
        s.fieldCode,
        s.variant,
        s.statistic,
      ]),
    ).toEqual(
      policy.required_features.map((s) => [
        s.feature_id,
        s.feature_key,
        s.scope,
        s.canonical_unit,
        s.field_code,
        s.variant ?? "canonical",
        s.statistic,
      ]),
    );
  });
  it.each(["2026-03-29", "2026-10-25", "2026-07-18", "2026-11-18"])(
    "uses the correct actual Sofia hours on %s",
    (date) => {
      const forecast = createForecast(date);
      expect(forecastResponseSchema.safeParse(forecast).success).toBe(true);
      const clock = new Intl.DateTimeFormat("en-GB", {
        timeZone: "Europe/Sofia",
        hour: "2-digit",
        hourCycle: "h23",
      });
      expect(sofiaFlyingHours(date).map((at) => clock.format(new Date(at)))).toEqual(
        Array.from({ length: 11 }, (_, i) => String(i + 10)),
      );
      requirePublishedValue(forecast.cloudbaseHours[1]).validAtUtc = requirePublishedValue(
        forecast.cloudbaseHours[0],
      ).validAtUtc;
      expect(forecastResponseSchema.safeParse(forecast).success).toBe(false);
    },
  );
  it.each(["blue", "other_cloud", "indeterminate", "missing"] as const)(
    "accepts %s without fabricated heights",
    (regime) => {
      const f = createForecast();
      f.cloudbaseHours = f.cloudbaseHours.map((h) => ({
        ...h,
        regime,
        heightMslM: null,
        heightModelAglM: null,
        heightSiteAglM: null,
        confidenceLevel: regime === "missing" ? null : "low",
      }));
      f.outputs.cloudbase =
        regime === "missing"
          ? {
              kind: regime,
              dataStatus: "missing",
              confidence: null,
              missingReason: "Missing profile",
            }
          : { kind: regime, dataStatus: "baseline", confidence: { level: "low" } };
      f.explanations[4] = {
        metricCode: "cloudbase",
        dataStatus: f.outputs.cloudbase.dataStatus,
        confidenceLevel: regime === "missing" ? null : "low",
        ...(regime === "missing" ? { missingReason: "Missing profile" } : {}),
        drivers: [],
      };
      expect(forecastResponseSchema.safeParse(f).success).toBe(true);
      expect(
        cloudbaseHourSchema.safeParse({ ...f.cloudbaseHours[0], heightMslM: 2000 }).success,
      ).toBe(false);
    },
  );
  it("keeps estimated maxima ahead of higher conditional hours, and rejects a foreign maximum", () => {
    const f = createForecast();
    f.cloudbaseHours[1] = {
      ...requirePublishedValue(f.cloudbaseHours[1]),
      regime: "indeterminate",
      heightMslM: 3000,
    };
    expect(forecastResponseSchema.safeParse(f).success).toBe(true);
    f.outputs.cloudbase = { ...f.outputs.cloudbase, kind: "conditional_lcl", valueMslM: 3000 };
    expect(forecastResponseSchema.safeParse(f).success).toBe(false);
  });
  it("allows conditional-only LCL and signed site AGL but requires confidence and complete height triples", () => {
    const f = createForecast();
    f.cloudbaseHours = f.cloudbaseHours.map((h) => ({ ...h, regime: "indeterminate" }));
    f.outputs.cloudbase = {
      kind: "conditional_lcl",
      valueMslM: 2200,
      dataStatus: "mock",
      confidence: { level: "low" },
    };
    expect(forecastResponseSchema.safeParse(f).success).toBe(true);
    expect(
      cloudbaseHourSchema.safeParse({ ...f.cloudbaseHours[0], confidenceLevel: null }).success,
    ).toBe(false);
    expect(
      cloudbaseHourSchema.safeParse({ ...f.cloudbaseHours[0], heightModelAglM: null }).success,
    ).toBe(false);
  });
});
