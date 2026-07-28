import type {
  ForecastDaysQuery,
  ForecastDaysResponse,
  ForecastQuery,
  ForecastResponse,
  ForecastSummariesQuery,
  ForecastSummariesResponse,
  Site,
  SiteSlug,
} from "@paragliding-forecasts/contracts";

import { AppError } from "../../http/errors/app-error.js";
import { createForecastDateWindow, FORECAST_TIME_ZONE, toForecastDate } from "./forecast-date.js";
import {
  createMissingChance100KmMetric,
  createMissingForecastSummary,
  mapPredictionToChance100KmMetric,
  mapPredictionToForecastResponse,
  mapPredictionToForecastSummary,
} from "./forecast-response.mapper.js";
import type { ForecastRepository } from "./forecast.repository.js";

export interface SiteLookup {
  findSiteBySlug(siteSlug: SiteSlug): Promise<Site | undefined>;
}

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

    return mapPredictionToForecastResponse(prediction, site.slug);
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
    const summaries = sites.map((site) => {
      const prediction = predictionsBySiteId.get(site.id);

      if (prediction === undefined) {
        return createMissingForecastSummary(site, query.date);
      }

      return mapPredictionToForecastSummary(prediction, site.slug);
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
              ? createMissingChance100KmMetric(site.slug, forecastDate)
              : mapPredictionToChance100KmMetric(prediction),
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
