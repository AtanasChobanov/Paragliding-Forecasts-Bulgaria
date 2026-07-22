import { queryOptions } from "@tanstack/react-query";
import type { ForecastDate, SiteSlug } from "@paragliding-forecasts/contracts";

import type { DashboardApi } from "../../services/api/dashboard-api.js";

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
      queryFn: ({ signal }) => dashboardApi.getForecastDays({ siteSlug, signal }),
    }),
  forecastSummaries: (date: ForecastDate, canonicalSiteSlugs: readonly SiteSlug[]) => {
    const queryKey = dashboardQueryKeys.forecastSummaries(date, canonicalSiteSlugs);

    return queryOptions({
      queryKey,
      queryFn: ({ signal }) =>
        dashboardApi.getForecastSummaries({
          date: queryKey[1],
          siteSlugs: queryKey[2],
          signal,
        }),
    });
  },
});
