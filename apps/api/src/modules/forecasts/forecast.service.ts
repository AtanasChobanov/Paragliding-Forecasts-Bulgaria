import type {
  ForecastQuery,
  ForecastResponse,
  Site,
  SiteSlug,
} from "@paragliding-forecasts/contracts";

import { AppError } from "../../http/errors/app-error.js";
import type { ForecastPrediction } from "./forecast-prediction.js";
import type { ForecastRepository } from "./forecast.repository.js";

export interface SiteLookup {
  findSiteBySlug(siteSlug: SiteSlug): Promise<Site | undefined>;
}

const mapPredictionToResponse = (
  prediction: ForecastPrediction,
  siteSlug: SiteSlug,
): ForecastResponse => {
  const metric = <Value>(value: Value) => ({
    value,
    dataStatus: prediction.dataStatus,
    confidence: { ...prediction.confidence },
  });

  return {
    siteId: prediction.siteId,
    siteSlug,
    forecastDate: prediction.forecastDate,
    generatedAt: prediction.generatedAt,
    provenance: { ...prediction.provenance },
    outputs: {
      cloudbaseMslM: metric(prediction.cloudbasePredictionMslM),
      chance100KmPct: metric(prediction.probability100KmPct),
      chance200KmPct: metric(prediction.probability200KmPct),
      chance300KmPct: metric(prediction.probability300KmPct),
      overdevelopmentRisk: metric(prediction.overdevelopmentRisk),
    },
    topDrivers: [...prediction.topDrivers],
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
    const site = await this.#siteLookup.findSiteBySlug(query.siteSlug);

    if (site === undefined) {
      throw new AppError({
        code: "SITE_NOT_FOUND",
        detail: `No forecast site exists for slug '${query.siteSlug}'.`,
      });
    }

    const prediction = await this.#forecastRepository.get(site.id, query.date);
    return mapPredictionToResponse(prediction, site.slug);
  }
}
