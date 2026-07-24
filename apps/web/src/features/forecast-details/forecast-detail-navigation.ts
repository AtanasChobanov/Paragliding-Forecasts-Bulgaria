import type { ForecastDate, SiteSlug } from "@paragliding-forecasts/contracts";

import { createCanonicalDashboardSearch } from "../dashboard/dashboard-search-params.js";

export const createForecastDetailPath = (siteSlug: SiteSlug, forecastDate: ForecastDate): string =>
  `/forecast?${createCanonicalDashboardSearch(siteSlug, forecastDate).toString()}`;

export const createDashboardPath = (siteSlug: SiteSlug, forecastDate: ForecastDate): string =>
  `/?${createCanonicalDashboardSearch(siteSlug, forecastDate).toString()}`;
