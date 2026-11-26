import {
  metricCodes,
  sofiaFlyingHours,
  xcInputInventory,
  type ForecastResponse,
} from "../src/index.js";

export const createForecast = (date = "2026-07-18"): ForecastResponse => {
  const hours = sofiaFlyingHours(date);
  const metric = <V>(value: V) => ({
    value,
    dataStatus: "mock" as const,
    confidence: { level: "low" as const },
  });
  return {
    siteId: 3,
    siteSlug: "sopot",
    forecastDate: date,
    generatedAt: "2026-07-17T12:00:00Z",
    metadata: { mode: "mock", source: "test", version: "synthetic/1" },
    outputs: {
      chance100KmPct: metric(60),
      chance200KmPct: metric(30),
      chance300KmPct: metric(10),
      overdevelopmentRisk: metric("medium"),
      cloudbase: {
        kind: "estimated",
        valueMslM: 2200,
        dataStatus: "mock",
        confidence: { level: "low" },
      },
    },
    forecastInputs: {
      windowStartUtc: requirePublishedValue(hours[0]),
      windowEndUtc: requirePublishedValue(hours[10]),
      featureContractVersion: "fixture/1",
      xcFeatures: xcInputInventory.map((spec) => ({
        key: spec.key,
        label: spec.label,
        group: spec.group,
        scope: spec.scope,
        unit: spec.unit,
        statistic: spec.statistic,
        dataStatus: "mock",
        qualityState: "synthetic",
        value: 1,
        ...("layerBaseAglM" in spec
          ? { layerBaseAglM: spec.layerBaseAglM, layerTopAglM: spec.layerTopAglM }
          : {}),
      })),
      hourlyContext: hours.map((validAtUtc) => ({
        validAtUtc,
        odInputs: [],
        cloudbaseContext: [],
      })),
    },
    explanations: metricCodes.map((metricCode) => ({
      metricCode,
      dataStatus: "mock",
      confidenceLevel: "low",
      drivers: [],
    })),
    cloudbaseHours: hours.map((validAtUtc) => ({
      validAtUtc,
      regime: "cumulus",
      heightMslM: 2200,
      heightModelAglM: 1200,
      heightSiteAglM: -100,
      confidenceLevel: "low",
      reasonCode: "fixture",
      reasonText: "Synthetic hour.",
    })),
  };
};

export const requirePublishedValue = <T>(value: T | undefined | null): T => {
  if (value === undefined || value === null) throw new Error("Fixture evidence missing");
  return value;
};
