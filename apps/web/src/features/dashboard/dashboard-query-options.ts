import { queryOptions } from "@tanstack/react-query";
import type { ForecastDate, SiteSlug } from "@paragliding-forecasts/contracts";

import type { DashboardApi } from "../../services/api/dashboard-api.js";
import {
  assertForecastDaysCorrelation,
  assertForecastSummariesCorrelation,
} from "./dashboard-compatibility-error.js";

export const dashboardQueryKeys = {
  sites: () => ["sites"] as const,
  forecastDays: (siteSlug: SiteSlug) => ["forecastDays", siteSlug] as const,
  forecastSummaries: (date: ForecastDate, canonicalSiteSlugs: readonly SiteSlug[]) =>
    ["forecastSummaries", date, Object.freeze([...canonicalSiteSlugs])] as const,
};

export const createDashboardQueryOptions = (dashboardApi: DashboardApi) => ({
  sites: () =>
    queryOptions({
      queryKey: dashboardQueryKeys.sites(),
      queryFn: ({ signal }) => dashboardApi.listSites(signal),
      staleTime: Infinity,
    }),
  forecastDays: (siteSlug: SiteSlug) =>
    queryOptions({
      queryKey: dashboardQueryKeys.forecastDays(siteSlug),
      queryFn: async ({ signal }) =>
        assertForecastDaysCorrelation(
          await dashboardApi.getForecastDays({ siteSlug, signal }),
          siteSlug,
        ),
    }),
  forecastSummaries: (date: ForecastDate, canonicalSiteSlugs: readonly SiteSlug[]) => {
    const queryKey = dashboardQueryKeys.forecastSummaries(date, canonicalSiteSlugs);

    return queryOptions({
      queryKey,
      queryFn: async ({ signal }) =>
        assertForecastSummariesCorrelation(
          await dashboardApi.getForecastSummaries({
            date: queryKey[1],
            siteSlugs: queryKey[2],
            signal,
          }),
          queryKey[1],
          queryKey[2],
        ),
    });
  },
});
