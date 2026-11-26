import { requirePublishedValue } from "./require-published-value.js";
import { surfaceInputs, heatingInputs } from "./forecast-input-catalogue.js";
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
      hourlyContext: hours.map((validAtUtc, i) => {
        const input = (
          key: string,
          label: string,
          unit: string,
          value: number,
        ): ForecastInputRow => ({
          key,
          label,
          unit,
          value,
          scope: "hourly",
          group: "Synthetic hourly context",
          statistic: "instantaneous",
          dataStatus: "mock",
          qualityState: "synthetic",
        });
        const surface = surfaceInputs.map(([key, label, , , , unit]) =>
          input(
            key,
            label,
            unit,
            unit === "K"
              ? 299.4
              : unit === "Pa"
                ? 100800
                : unit === "kg/kg"
                  ? 0.007
                  : unit === "m"
                    ? 1500
                    : unit === "%"
                      ? 24
                      : 4,
          ),
        );
        const end = hours[i + 1];
        const odInputs = [
          input("rain", "Rain accumulation", "mm", 0),
          input("cape", "Surface parcel CAPE", "J/kg", 600),
          input("cin", "Surface parcel CIN magnitude", "J/kg", 20),
          ...surface
            .filter((row) => ["low_cloud_percent", "humidity", "wind"].includes(row.key))
            .map((row) => (row.key === "low_cloud_percent" ? { ...row, key: "low_cloud" } : row)),
        ].map((row) =>
          !end && ["rain", "cape", "cin"].includes(row.key)
            ? {
                ...row,
                value: null,
                dataStatus: "missing" as const,
                qualityState: "missing",
                missingReason: "Outside OD interval inputs",
              }
            : row.key === "rain" && end
              ? {
                  ...row,
                  statistic: "accumulation",
                  intervalStartUtc: validAtUtc,
                  intervalEndUtc: end,
                }
              : row,
        );
        const previous = new Date(Date.parse(validAtUtc) - 3_600_000).toISOString();
        return {
          validAtUtc,
          odInputs,
          cloudbaseContext: [
            ...surface.filter((row) => !["humidity", "wind"].includes(row.key)),
            ...heatingInputs.map(([key, label]) => ({
              ...input(key, label, "W/m2", 70),
              statistic: "interval_average",
              intervalStartUtc: previous,
              intervalEndUtc: validAtUtc,
            })),
          ],
        };
      }),
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
        ...(metric.confidence?.note ? { confidenceNote: metric.confidence.note } : {}),
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
