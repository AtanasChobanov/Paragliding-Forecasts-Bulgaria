import type {
  ForecastDate,
  ForecastDaysResponse,
  ForecastSummariesResponse,
  SiteSlug,
} from "@paragliding-forecasts/contracts";

export type DashboardCompatibilityResource = "forecast-days" | "forecast-summaries";

export class DashboardCompatibilityError extends Error {
  readonly kind = "api-compatibility" as const;
  readonly resource: DashboardCompatibilityResource;

  constructor(resource: DashboardCompatibilityResource, message: string) {
    super(message);
    this.name = "DashboardCompatibilityError";
    this.resource = resource;
  }
}

export const assertForecastDaysCorrelation = (
  response: ForecastDaysResponse,
  requestedSiteSlug: SiteSlug,
): ForecastDaysResponse => {
  if (response.siteSlug !== requestedSiteSlug) {
    throw new DashboardCompatibilityError(
      "forecast-days",
      "The forecast service returned days for a different location.",
    );
  }

  return response;
};

export const assertForecastSummariesCorrelation = (
  response: ForecastSummariesResponse,
  requestedDate: ForecastDate,
  requestedSiteSlugs: readonly SiteSlug[],
): ForecastSummariesResponse => {
  if (response.forecastDate !== requestedDate) {
    throw new DashboardCompatibilityError(
      "forecast-summaries",
      "The forecast service returned summaries for a different date.",
    );
  }

  const requestedSlugSet = new Set(requestedSiteSlugs);
  const unexpectedSummary = response.summaries.find(
    (summary) => !requestedSlugSet.has(summary.siteSlug),
  );

  if (unexpectedSummary !== undefined) {
    throw new DashboardCompatibilityError(
      "forecast-summaries",
      "The forecast service returned a summary for an unrequested location.",
    );
  }

  return response;
};
