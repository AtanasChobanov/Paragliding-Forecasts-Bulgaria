import type { ForecastDate, SiteId } from "@paragliding-forecasts/contracts";

import type { ForecastRecord, OverdevelopmentRisk } from "./forecast-record.js";
import type { ForecastRepository } from "./forecast.repository.js";

interface MockForecastProfile {
  readonly cloudbasePredictionMslM: number;
  readonly probability100KmPct: number;
  readonly probability200KmPct: number;
  readonly probability300KmPct: number;
  readonly overdevelopmentRisk: OverdevelopmentRisk;
  readonly topDrivers: readonly string[];
}

const mockProfiles: Readonly<Record<string, MockForecastProfile>> = {
  "sofia-vitosha-kominite": {
    cloudbasePredictionMslM: 2_300,
    probability100KmPct: 45,
    probability200KmPct: 20,
    probability300KmPct: 5,
    overdevelopmentRisk: "medium",
    topDrivers: ["Synthetic thermal profile", "Synthetic mid-level humidity"],
  },
  zlatitsa: {
    cloudbasePredictionMslM: 2_500,
    probability100KmPct: 60,
    probability200KmPct: 30,
    probability300KmPct: 10,
    overdevelopmentRisk: "medium",
    topDrivers: ["Synthetic cloudbase estimate", "Synthetic route-aligned wind"],
  },
  sopot: {
    cloudbasePredictionMslM: 2_400,
    probability100KmPct: 65,
    probability200KmPct: 35,
    probability300KmPct: 12,
    overdevelopmentRisk: "medium",
    topDrivers: ["Synthetic thermal strength", "Synthetic boundary-layer depth"],
  },
  nevsha: {
    cloudbasePredictionMslM: 2_100,
    probability100KmPct: 40,
    probability200KmPct: 15,
    probability300KmPct: 3,
    overdevelopmentRisk: "low",
    topDrivers: ["Synthetic flatland heating", "Synthetic low-level wind"],
  },
  shumen: {
    cloudbasePredictionMslM: 2_150,
    probability100KmPct: 42,
    probability200KmPct: 18,
    probability300KmPct: 4,
    overdevelopmentRisk: "low",
    topDrivers: ["Synthetic convergence signal", "Synthetic cloud-cover estimate"],
  },
  pastrona: {
    cloudbasePredictionMslM: 2_000,
    probability100KmPct: 35,
    probability200KmPct: 12,
    probability300KmPct: 2,
    overdevelopmentRisk: "medium",
    topDrivers: ["Synthetic instability profile", "Synthetic precipitation signal"],
  },
  "dobrich-region": {
    cloudbasePredictionMslM: 2_200,
    probability100KmPct: 50,
    probability200KmPct: 22,
    probability300KmPct: 6,
    overdevelopmentRisk: "low",
    topDrivers: ["Synthetic flatland thermal profile", "Synthetic regional wind"],
  },
};

export interface MockForecastRepositoryDependencies {
  readonly now: () => Date;
}

export class MockForecastRepository implements ForecastRepository {
  readonly #now: () => Date;

  constructor({ now }: MockForecastRepositoryDependencies) {
    this.#now = now;
  }

  get(siteId: SiteId, date: ForecastDate): Promise<ForecastRecord> {
    const profile = mockProfiles[siteId];

    if (profile === undefined) {
      throw new Error(`The mock forecast catalog has no profile for site: ${siteId}`);
    }

    return Promise.resolve({
      siteId,
      date,
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
      qualityNotes: [
        "Synthetic mock decision-support data; not aviation weather and not a safety guarantee.",
      ],
    });
  }
}
