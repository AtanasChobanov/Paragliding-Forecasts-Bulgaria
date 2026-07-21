import type {
  ForecastDate,
  ForecastDaysQuery,
  ForecastDaysResponse,
  ForecastOutputs,
  ForecastQuery,
  ForecastResponse,
  ForecastSummariesQuery,
  ForecastSummariesResponse,
  ForecastSummary,
  Site,
  SiteSlug,
} from "@paragliding-forecasts/contracts";

import { AppError } from "../../http/errors/app-error.js";
import { createForecastDateWindow, FORECAST_TIME_ZONE, toForecastDate } from "./forecast-date.js";
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

const missingChance = (siteSlug: SiteSlug, forecastDate: ForecastDate) => ({
  value: null,
  dataStatus: "missing" as const,
  confidence: null,
  missingReason: `No 100+ km forecast is available for site '${siteSlug}' on ${forecastDate}.`,
});

export class ForecastService {
  readonly #forecastRepository: ForecastRepository;
  readonly #now: () => Date;
  readonly #siteLookup: SiteLookup;

  constructor(forecastRepository: ForecastRepository, siteLookup: SiteLookup, now: () => Date) {
    this.#forecastRepository = forecastRepository;
    this.#siteLookup = siteLookup;
    this.#now = now;
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

  async getForecastSummaries(query: ForecastSummariesQuery): Promise<ForecastSummariesResponse> {
    const sites = await Promise.all(query.siteSlugs.map((siteSlug) => this.#getSite(siteSlug)));
    sites.sort((left, right) => left.id - right.id);

    const predictions = await this.#forecastRepository.listBySiteIdsAndDate(
      sites.map((site) => site.id),
      query.date,
    );
    const predictionsBySiteId = new Map(
      predictions.map((prediction) => [prediction.siteId, prediction]),
    );
    const summaries: ForecastSummary[] = sites.map((site) => {
      const prediction = predictionsBySiteId.get(site.id);

      if (prediction === undefined) {
        return {
          availability: "missing",
          siteId: site.id,
          siteSlug: site.slug,
          forecastDate: query.date,
          missingReason: `No forecast exists for site '${site.slug}' on ${query.date}.`,
        };
      }

      return {
        availability: "available",
        siteId: site.id,
        siteSlug: site.slug,
        forecastDate: prediction.forecastDate,
        generatedAt: prediction.generatedAt,
        provenance: { ...prediction.provenance },
        outputs: mapPredictionOutputs(prediction),
      };
    });

    return { forecastDate: query.date, summaries };
  }

  async getForecastDays(query: ForecastDaysQuery): Promise<ForecastDaysResponse> {
    const referenceInstant = this.#now();
    const site = await this.#getSite(query.siteSlug);
    const todayDate = toForecastDate(referenceInstant);
    const dates = createForecastDateWindow(todayDate, 2, 2);
    const fromDate = dates[0];
    const throughDate = dates.at(-1);

    if (fromDate === undefined || throughDate === undefined) {
      throw new Error("Forecast date window cannot be empty.");
    }

    const predictions = await this.#forecastRepository.listBySiteAndDateRange(
      site.id,
      fromDate,
      throughDate,
    );
    const predictionsByDate = new Map(
      predictions.map((prediction) => [prediction.forecastDate, prediction]),
    );

    return {
      siteId: site.id,
      siteSlug: site.slug,
      timeZone: FORECAST_TIME_ZONE,
      todayDate,
      days: dates.map((forecastDate) => {
        const prediction = predictionsByDate.get(forecastDate);

        return {
          forecastDate,
          chance100KmPct:
            prediction === undefined
              ? missingChance(site.slug, forecastDate)
              : metric(prediction, prediction.probability100KmPct),
        };
      }),
    };
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
