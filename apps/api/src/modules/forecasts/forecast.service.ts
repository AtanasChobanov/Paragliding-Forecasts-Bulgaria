import type {
  ForecastQuery,
  ForecastResponse,
  Site,
  SiteId,
} from "@paragliding-forecasts/contracts";

import { AppError } from "../../http/errors/app-error.js";
import type { ForecastRecord } from "./forecast-record.js";
import type { ForecastRepository } from "./forecast.repository.js";

export interface SiteLookup {
  findSite(siteId: SiteId): Promise<Site | undefined>;
}

const mapRecordToResponse = (record: ForecastRecord): ForecastResponse => {
  const metric = <Value>(value: Value) => ({
    value,
    dataStatus: record.dataStatus,
    confidence: { ...record.confidence },
  });

  return {
    siteId: record.siteId,
    forecastDate: record.date,
    generatedAt: record.generatedAt,
    provenance: { ...record.provenance },
    outputs: {
      cloudbaseMslM: metric(record.cloudbasePredictionMslM),
      chance100KmPct: metric(record.probability100KmPct),
      chance200KmPct: metric(record.probability200KmPct),
      chance300KmPct: metric(record.probability300KmPct),
      overdevelopmentRisk: metric(record.overdevelopmentRisk),
    },
    topDrivers: [...record.topDrivers],
    qualityNotes: [...record.qualityNotes],
  };
};

export class ForecastService {
  readonly #forecastRepository: ForecastRepository;
  readonly #siteLookup: SiteLookup;

  constructor(forecastRepository: ForecastRepository, siteLookup: SiteLookup) {
    this.#forecastRepository = forecastRepository;
    this.#siteLookup = siteLookup;
  }

  async getForecast(query: ForecastQuery): Promise<ForecastResponse> {
    const site = await this.#siteLookup.findSite(query.siteId);

    if (site === undefined) {
      throw new AppError({
        code: "SITE_NOT_FOUND",
        detail: `No forecast site exists for siteId '${query.siteId}'.`,
      });
    }

    const record = await this.#forecastRepository.get(query.siteId, query.date);
    return mapRecordToResponse(record);
  }
}
