import { queryOptions } from "@tanstack/react-query";
import type { ForecastDate, ForecastResponse, SiteSlug } from "@paragliding-forecasts/contracts";

import { DashboardCompatibilityError } from "../dashboard/dashboard-compatibility-error.js";
import type { DashboardApi } from "../../services/api/dashboard-api.js";

const assertForecastDetailCorrelation = (
  response: ForecastResponse,
  siteSlug: SiteSlug,
  forecastDate: ForecastDate,
): ForecastResponse => {
  if (response.siteSlug !== siteSlug || response.forecastDate !== forecastDate) {
    throw new DashboardCompatibilityError(
      "forecast-detail",
      "The forecast service returned a detailed forecast for a different location or date.",
    );
  }

  return response;
};

export const forecastDetailQueryKey = (siteSlug: SiteSlug, forecastDate: ForecastDate) =>
  ["forecastDetail", siteSlug, forecastDate] as const;

export const createForecastDetailQueryOptions = (
  dashboardApi: DashboardApi,
  siteSlug: SiteSlug,
  forecastDate: ForecastDate,
) =>
  queryOptions({
    queryKey: forecastDetailQueryKey(siteSlug, forecastDate),
    queryFn: async ({ signal }) =>
      assertForecastDetailCorrelation(
        await dashboardApi.getForecastDetail({ date: forecastDate, signal, siteSlug }),
        siteSlug,
        forecastDate,
      ),
  });
