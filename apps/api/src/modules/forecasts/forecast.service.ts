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
  createMissingForecastDay,
  createMissingForecastSummary,
  mapPredictionToForecastResponse,
} from "./forecast-response.mapper.js";
import type { ForecastRepository } from "./forecast.repository.js";

export interface SiteLookup {
  findSiteBySlug(siteSlug: SiteSlug): Promise<Site | undefined>;
  listSites(): Promise<readonly Site[]>;
}

const requireSite = (site: Site | undefined, siteSlug: SiteSlug): Site => {
  if (site === undefined) {
    throw new AppError({
      code: "SITE_NOT_FOUND",
      detail: `No forecast site exists for slug '${siteSlug}'.`,
    });
  }
  return site;
};

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
    const site = requireSite(await this.#siteLookup.findSiteBySlug(query.siteSlug), query.siteSlug);
    if (this.#forecastRepository.find === undefined) {
      throw new AppError({
        code: "FORECAST_NOT_FOUND",
        detail: "Detailed forecasts are not yet available in SQLite mode.",
      });
    }
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
    const todayDate = toForecastDate(this.#now());
    const catalog = await this.#siteLookup.listSites();
    const sitesBySlug = new Map(catalog.map((site) => [site.slug, site]));
    const sites = query.siteSlugs.map((slug) => requireSite(sitesBySlug.get(slug), slug));
    sites.sort((left, right) => left.id - right.id);

    const predictions = await this.#forecastRepository.listSummaries(sites, query.date, todayDate);
    const predictionsBySiteId = new Map(
      predictions.map((prediction) => [prediction.siteId, prediction]),
    );
    const summaries = sites.map(
      (site) => predictionsBySiteId.get(site.id) ?? createMissingForecastSummary(site, query.date),
    );

    return { forecastDate: query.date, summaries };
  }

  async getForecastDays(query: ForecastDaysQuery): Promise<ForecastDaysResponse> {
    const referenceInstant = this.#now();
    const site = requireSite(await this.#siteLookup.findSiteBySlug(query.siteSlug), query.siteSlug);
    const todayDate = toForecastDate(referenceInstant);
    const dates = createForecastDateWindow(todayDate, 2, 2);
    const fromDate = dates[0];
    const throughDate = dates.at(-1);

    if (fromDate === undefined || throughDate === undefined) {
      throw new Error("Forecast date window cannot be empty.");
    }

    const days = await this.#forecastRepository.listDays(site.id, fromDate, throughDate);
    const daysByDate = new Map(days.map((day) => [day.forecastDate, day]));

    return {
      siteId: site.id,
      siteSlug: site.slug,
      timeZone: FORECAST_TIME_ZONE,
      todayDate,
      days: dates.map((date) => daysByDate.get(date) ?? createMissingForecastDay(site.slug, date)),
    };
  }
}
