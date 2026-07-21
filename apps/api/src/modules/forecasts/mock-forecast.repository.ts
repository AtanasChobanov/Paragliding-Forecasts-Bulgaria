import type { ForecastDate, SiteId } from "@paragliding-forecasts/contracts";

import { addForecastDays, toForecastDate } from "./forecast-date.js";
import type { ForecastPrediction, OverdevelopmentRisk } from "./forecast-prediction.js";
import type { ForecastRepository } from "./forecast.repository.js";

interface MockForecastProfile {
  readonly cloudbasePredictionMslM: number;
  readonly probability100KmPct: number;
  readonly probability200KmPct: number;
  readonly probability300KmPct: number;
  readonly overdevelopmentRisk: OverdevelopmentRisk;
  readonly topDrivers: readonly string[];
}

interface DayAdjustment {
  readonly cloudbaseMslM: number;
  readonly probability100KmPct: number;
  readonly probability200KmPct: number;
  readonly probability300KmPct: number;
}

const mockProfiles = new Map<SiteId, MockForecastProfile>([
  [
    1,
    {
      cloudbasePredictionMslM: 2_300,
      probability100KmPct: 45,
      probability200KmPct: 20,
      probability300KmPct: 5,
      overdevelopmentRisk: "medium",
      topDrivers: ["Synthetic thermal profile", "Synthetic mid-level humidity"],
    },
  ],
  [
    2,
    {
      cloudbasePredictionMslM: 2_500,
      probability100KmPct: 60,
      probability200KmPct: 30,
      probability300KmPct: 10,
      overdevelopmentRisk: "medium",
      topDrivers: ["Synthetic cloudbase estimate", "Synthetic route-aligned wind"],
    },
  ],
  [
    3,
    {
      cloudbasePredictionMslM: 2_400,
      probability100KmPct: 65,
      probability200KmPct: 35,
      probability300KmPct: 12,
      overdevelopmentRisk: "medium",
      topDrivers: ["Synthetic thermal strength", "Synthetic boundary-layer depth"],
    },
  ],
  [
    4,
    {
      cloudbasePredictionMslM: 2_100,
      probability100KmPct: 40,
      probability200KmPct: 15,
      probability300KmPct: 3,
      overdevelopmentRisk: "low",
      topDrivers: ["Synthetic flatland heating", "Synthetic low-level wind"],
    },
  ],
  [
    5,
    {
      cloudbasePredictionMslM: 2_150,
      probability100KmPct: 42,
      probability200KmPct: 18,
      probability300KmPct: 4,
      overdevelopmentRisk: "low",
      topDrivers: ["Synthetic convergence signal", "Synthetic cloud-cover estimate"],
    },
  ],
  [
    6,
    {
      cloudbasePredictionMslM: 2_000,
      probability100KmPct: 35,
      probability200KmPct: 12,
      probability300KmPct: 2,
      overdevelopmentRisk: "medium",
      topDrivers: ["Synthetic instability profile", "Synthetic precipitation signal"],
    },
  ],
  [
    7,
    {
      cloudbasePredictionMslM: 2_200,
      probability100KmPct: 50,
      probability200KmPct: 22,
      probability300KmPct: 6,
      overdevelopmentRisk: "low",
      topDrivers: ["Synthetic flatland thermal profile", "Synthetic regional wind"],
    },
  ],
]);

const dayAdjustments = new Map<number, DayAdjustment>([
  [
    -2,
    {
      cloudbaseMslM: -150,
      probability100KmPct: -10,
      probability200KmPct: -5,
      probability300KmPct: -2,
    },
  ],
  [
    -1,
    {
      cloudbaseMslM: -75,
      probability100KmPct: -5,
      probability200KmPct: -2,
      probability300KmPct: -1,
    },
  ],
  [
    0,
    {
      cloudbaseMslM: 0,
      probability100KmPct: 0,
      probability200KmPct: 0,
      probability300KmPct: 0,
    },
  ],
  [
    1,
    {
      cloudbaseMslM: 100,
      probability100KmPct: 8,
      probability200KmPct: 4,
      probability300KmPct: 1,
    },
  ],
  [
    2,
    {
      cloudbaseMslM: 50,
      probability100KmPct: -3,
      probability200KmPct: -1,
      probability300KmPct: 0,
    },
  ],
]);

const metric = (value: number, delta: number): number => Math.max(0, Math.min(100, value + delta));

const clonePrediction = (prediction: ForecastPrediction): ForecastPrediction => ({
  ...prediction,
  confidence: { ...prediction.confidence },
  provenance: { ...prediction.provenance },
  topDrivers: [...prediction.topDrivers],
});

const predictionKey = (siteId: SiteId, date: ForecastDate): string => `${String(siteId)}:${date}`;

export interface MockForecastRepositoryDependencies {
  readonly now: () => Date;
}

export class MockForecastRepository implements ForecastRepository {
  readonly #predictions: ReadonlyMap<string, ForecastPrediction>;

  constructor({ now }: MockForecastRepositoryDependencies) {
    const generatedAt = now().toISOString();
    const today = toForecastDate(new Date(generatedAt));
    const predictions = new Map<string, ForecastPrediction>();

    for (const [siteId, profile] of mockProfiles) {
      for (const [dayOffset, adjustment] of dayAdjustments) {
        const forecastDate = addForecastDays(today, dayOffset);
        const prediction: ForecastPrediction = {
          siteId,
          forecastDate,
          generatedAt,
          provenance: {
            source: "t-003-t-005-mock-provider",
            version: "mock-v2",
          },
          dataStatus: "mock",
          confidence: {
            level: "low",
            note: "Synthetic demonstration value; not a model output.",
          },
          cloudbasePredictionMslM:
            profile.cloudbasePredictionMslM + adjustment.cloudbaseMslM,
          probability100KmPct: metric(
            profile.probability100KmPct,
            adjustment.probability100KmPct,
          ),
          probability200KmPct: metric(
            profile.probability200KmPct,
            adjustment.probability200KmPct,
          ),
          probability300KmPct: metric(
            profile.probability300KmPct,
            adjustment.probability300KmPct,
          ),
          overdevelopmentRisk: profile.overdevelopmentRisk,
          topDrivers: [...profile.topDrivers],
        };

        predictions.set(predictionKey(siteId, forecastDate), prediction);
      }
    }

    this.#predictions = predictions;
  }

  find(siteId: SiteId, date: ForecastDate): Promise<ForecastPrediction | undefined> {
    const prediction = this.#predictions.get(predictionKey(siteId, date));
    return Promise.resolve(prediction === undefined ? undefined : clonePrediction(prediction));
  }

  listBySiteIdsAndDate(
    siteIds: readonly SiteId[],
    date: ForecastDate,
  ): Promise<readonly ForecastPrediction[]> {
    const predictions = siteIds
      .map((siteId) => this.#predictions.get(predictionKey(siteId, date)))
      .filter((prediction): prediction is ForecastPrediction => prediction !== undefined)
      .map(clonePrediction);

    return Promise.resolve(predictions);
  }

  listBySiteAndDateRange(
    siteId: SiteId,
    fromDate: ForecastDate,
    throughDate: ForecastDate,
  ): Promise<readonly ForecastPrediction[]> {
    const predictions = [...this.#predictions.values()]
      .filter(
        (prediction) =>
          prediction.siteId === siteId &&
          prediction.forecastDate >= fromDate &&
          prediction.forecastDate <= throughDate,
      )
      .sort((left, right) => left.forecastDate.localeCompare(right.forecastDate))
      .map(clonePrediction);

    return Promise.resolve(predictions);
  }
}
