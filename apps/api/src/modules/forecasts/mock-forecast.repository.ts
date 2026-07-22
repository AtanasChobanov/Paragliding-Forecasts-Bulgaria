import type { ForecastDate, SiteId } from "@paragliding-forecasts/contracts";

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

export interface MockForecastRepositoryDependencies {
  readonly now: () => Date;
}

export class MockForecastRepository implements ForecastRepository {
  readonly #now: () => Date;

  constructor({ now }: MockForecastRepositoryDependencies) {
    this.#now = now;
  }

  get(siteId: SiteId, date: ForecastDate): Promise<ForecastPrediction> {
    const profile = mockProfiles.get(siteId);

    if (profile === undefined) {
      throw new Error(`The mock forecast catalog has no profile for site: ${String(siteId)}`);
    }

    return Promise.resolve({
      siteId,
      forecastDate: date,
      generatedAt: this.#now().toISOString(),
      provenance: {
        source: "t-002-mock-provider",
        version: "mock-v1",
      },
      dataStatus: "mock",
      confidence: {
        level: "low",
        note: "Synthetic demonstration value; not a model output.",
      },
      cloudbasePredictionMslM: profile.cloudbasePredictionMslM,
      probability100KmPct: profile.probability100KmPct,
      probability200KmPct: profile.probability200KmPct,
      probability300KmPct: profile.probability300KmPct,
      overdevelopmentRisk: profile.overdevelopmentRisk,
      topDrivers: [...profile.topDrivers],
    });
  }
}
