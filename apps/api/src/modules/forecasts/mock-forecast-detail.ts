import { requirePublishedValue } from "./require-published-value.js";
import {
  metricCodes,
  sofiaFlyingHours,
  xcInputInventory,
  type AvailableForecastSummary,
  type ForecastInputRow,
  type ForecastResponse,
} from "@paragliding-forecasts/contracts";

// Explicit synthetic detail data, never used by the SQLite adapter.
export const mockForecastDetail = (
  summary: AvailableForecastSummary,
  messages: readonly string[],
): ForecastResponse => {
  const hours = sofiaFlyingHours(summary.forecastDate);
  const cloud = summary.outputs.cloudbase;
  const height = "valueMslM" in cloud ? cloud.valueMslM : 2400;
  const xcFeatures: ForecastInputRow[] = xcInputInventory.map((spec) => ({
    key: spec.key,
    label: spec.label,
    group: spec.group,
    scope: spec.scope,
    unit: spec.unit,
    statistic: spec.statistic,
    dataStatus: "mock",
    qualityState: "synthetic",
    value:
      spec.unit === "K"
        ? 299.4
        : spec.unit === "Pa"
          ? 100800
          : spec.unit === "kg/kg"
            ? 0.007
            : spec.unit === "%"
              ? 52
              : 2.4,
    ...("layerBaseAglM" in spec
      ? { layerBaseAglM: spec.layerBaseAglM, layerTopAglM: spec.layerTopAglM }
      : {}),
  }));
  const keys = [
    "chance100KmPct",
    "chance200KmPct",
    "chance300KmPct",
    "overdevelopmentRisk",
    "cloudbase",
  ] as const;
  return {
    siteId: summary.siteId,
    siteSlug: summary.siteSlug,
    forecastDate: summary.forecastDate,
    generatedAt: summary.generatedAt,
    metadata: summary.metadata,
    outputs: summary.outputs,
    forecastInputs: {
      windowStartUtc: requirePublishedValue(hours[0]),
      windowEndUtc: requirePublishedValue(hours[10]),
      featureContractVersion: "synthetic-detail/1",
      xcFeatures,
      hourlyContext: hours.map((validAtUtc) => ({
        validAtUtc,
        odInputs: [],
        cloudbaseContext: [],
      })),
    },
    cloudbaseHours: hours.map((validAtUtc, i) => ({
      validAtUtc,
      regime: "cumulus",
      heightMslM: height - Math.abs(i - 3) * 75,
      heightModelAglM: height - Math.abs(i - 3) * 75 - 500,
      heightSiteAglM: height - Math.abs(i - 3) * 75 - 900,
      confidenceLevel: "low",
      reasonCode: "synthetic_demo",
      reasonText: "Synthetic demonstration cloudbase.",
    })),
    explanations: metricCodes.map((metricCode, i) => {
      const metric = summary.outputs[requirePublishedValue(keys[i])];
      return {
        metricCode,
        dataStatus: metric.dataStatus,
        confidenceLevel: metric.confidence?.level ?? null,
        drivers:
          metricCode === "p100"
            ? messages.slice(0, 3).map((message, rank) => ({
                kind: "xc_contribution",
                code: `synthetic_${String(rank)}`,
                message,
                rank: rank + 1,
                xcStage: "p100",
                direction: "raises",
                contributionLogit: 0.2,
                inputs: [
                  {
                    inputKey: requirePublishedValue(xcFeatures[0]).key,
                    field: requirePublishedValue(xcFeatures[0]),
                  },
                ],
              }))
            : [],
      };
    }),
  };
};
