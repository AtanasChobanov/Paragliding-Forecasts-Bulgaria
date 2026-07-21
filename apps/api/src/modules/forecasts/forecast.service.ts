import type {
  ForecastOutputs,
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

const metric = <Value>(prediction: ForecastPrediction, value: Value) => ({
  value,
  dataStatus: prediction.dataStatus,
  confidence: { ...prediction.confidence },
});

const mapPredictionOutputs = (prediction: ForecastPrediction): ForecastOutputs => ({
  cloudbaseMslM: metric(prediction, prediction.cloudbasePredictionMslM),
  chance100KmPct: metric(prediction, prediction.probability100KmPct),
  chance200KmPct: metric(prediction, prediction.probability200KmPct),
  chance300KmPct: metric(prediction, prediction.probability300KmPct),
  overdevelopmentRisk: metric(prediction, prediction.overdevelopmentRisk),
});

const mapPredictionToResponse = (
  prediction: ForecastPrediction,
  siteSlug: SiteSlug,
): ForecastResponse => ({
  siteId: prediction.siteId,
  siteSlug,
  forecastDate: prediction.forecastDate,
  generatedAt: prediction.generatedAt,
  provenance: { ...prediction.provenance },
  outputs: mapPredictionOutputs(prediction),
  topDrivers: [...prediction.topDrivers],
});

export class ForecastService {
  readonly #forecastRepository: ForecastRepository;
  readonly #siteLookup: SiteLookup;

  constructor(forecastRepository: ForecastRepository, siteLookup: SiteLookup) {
    this.#forecastRepository = forecastRepository;
    this.#siteLookup = siteLookup;
  }

  async getForecast(query: ForecastQuery): Promise<ForecastResponse> {
    const site = await this.#getSite(query.siteSlug);
    const prediction = await this.#forecastRepository.find(site.id, query.date);

    if (prediction === undefined) {
      throw new AppError({
        code: "FORECAST_NOT_FOUND",
        detail: `No forecast exists for site '${site.slug}' on ${query.date}.`,
      });
    }

    return mapPredictionToResponse(prediction, site.slug);
  }

  async #getSite(siteSlug: SiteSlug): Promise<Site> {
    const site = await this.#siteLookup.findSiteBySlug(siteSlug);

    if (site === undefined) {
      throw new AppError({
        code: "SITE_NOT_FOUND",
        detail: `No forecast site exists for slug '${siteSlug}'.`,
      });
    }

    return site;
  }
}
