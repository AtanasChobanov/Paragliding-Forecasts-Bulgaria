import {
  forecastDaysResponseSchema,
  forecastSummariesResponseSchema,
  forecastResponseSchema,
  sitesResponseSchema,
  type ForecastDate,
  type ForecastDaysResponse,
  type ForecastResponse,
  type ForecastSummariesResponse,
  type SiteSlug,
  type SitesResponse,
} from "@paragliding-forecasts/contracts";

import type { ApiClient } from "./api-client.js";

export interface ForecastSummariesRequest {
  readonly date: ForecastDate;
  readonly siteSlugs: readonly SiteSlug[];
  readonly signal: AbortSignal;
}

export interface ForecastDaysRequest {
  readonly siteSlug: SiteSlug;
  readonly signal: AbortSignal;
}

export interface ForecastDetailRequest {
  readonly date: ForecastDate;
  readonly signal: AbortSignal;
  readonly siteSlug: SiteSlug;
}

export interface DashboardApi {
  listSites(signal: AbortSignal): Promise<SitesResponse>;
  getForecastSummaries(request: ForecastSummariesRequest): Promise<ForecastSummariesResponse>;
  getForecastDays(request: ForecastDaysRequest): Promise<ForecastDaysResponse>;
  getForecastDetail(request: ForecastDetailRequest): Promise<ForecastResponse>;
}

export const createDashboardApi = (apiClient: ApiClient): DashboardApi => ({
  listSites: (signal) =>
    apiClient.get({
      endpoint: "api/v1/sites",
      schema: sitesResponseSchema,
      signal,
    }),
  getForecastSummaries: ({ date, siteSlugs, signal }) =>
    apiClient.get({
      endpoint: "api/v1/forecasts/summaries",
      schema: forecastSummariesResponseSchema,
      searchParameters: [
        ["date", date],
        ["siteSlugs", siteSlugs.join(",")],
      ],
      signal,
    }),
  getForecastDays: ({ siteSlug, signal }) =>
    apiClient.get({
      endpoint: "api/v1/forecasts/days",
      schema: forecastDaysResponseSchema,
      searchParameters: [["siteSlug", siteSlug]],
      signal,
    }),
  getForecastDetail: ({ date, siteSlug, signal }) =>
    apiClient.get({
      endpoint: "api/v1/forecasts",
      schema: forecastResponseSchema,
      searchParameters: [
        ["siteSlug", siteSlug],
        ["date", date],
      ],
      signal,
    }),
});
