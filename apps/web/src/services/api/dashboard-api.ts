import {
  forecastDaysResponseSchema,
  forecastSummariesResponseSchema,
  sitesResponseSchema,
  type ForecastDate,
  type ForecastDaysResponse,
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

export interface DashboardApi {
  listSites(signal: AbortSignal): Promise<SitesResponse>;
  getForecastSummaries(request: ForecastSummariesRequest): Promise<ForecastSummariesResponse>;
  getForecastDays(request: ForecastDaysRequest): Promise<ForecastDaysResponse>;
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
});
