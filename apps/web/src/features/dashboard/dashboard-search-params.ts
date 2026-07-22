import {
  forecastDateSchema,
  type ForecastDate,
  type ForecastDaysResponse,
  type Site,
  type SiteSlug,
} from "@paragliding-forecasts/contracts";

export const DASHBOARD_SITE_PARAMETER = "site";
export const DASHBOARD_DATE_PARAMETER = "date";

export type DashboardSiteParameter =
  | { readonly kind: "missing" }
  | { readonly kind: "repeated" }
  | { readonly kind: "single"; readonly value: string };

export type DashboardDateParameter =
  | { readonly kind: "missing" }
  | { readonly kind: "repeated" }
  | { readonly kind: "invalid"; readonly value: string }
  | { readonly kind: "valid"; readonly value: ForecastDate };

export interface DashboardSearchSelection {
  readonly site: DashboardSiteParameter;
  readonly date: DashboardDateParameter;
}

const readSingleParameter = (
  searchParameters: URLSearchParams,
  name: string,
):
  | { readonly kind: "missing" | "repeated" }
  | { readonly kind: "single"; readonly value: string } => {
  const values = searchParameters.getAll(name);

  if (values.length === 0) {
    return { kind: "missing" };
  }

  if (values.length !== 1) {
    return { kind: "repeated" };
  }

  return { kind: "single", value: values[0] ?? "" };
};

export const parseDashboardSearch = (
  searchParameters: URLSearchParams,
): DashboardSearchSelection => {
  const site = readSingleParameter(searchParameters, DASHBOARD_SITE_PARAMETER);
  const rawDate = readSingleParameter(searchParameters, DASHBOARD_DATE_PARAMETER);

  if (rawDate.kind !== "single") {
    return { site, date: rawDate };
  }

  const dateResult = forecastDateSchema.safeParse(rawDate.value);

  return {
    site,
    date: dateResult.success
      ? { kind: "valid", value: dateResult.data }
      : { kind: "invalid", value: rawDate.value },
  };
};

export const findDefaultSite = (sites: readonly Site[]): Site | undefined =>
  sites.reduce<Site | undefined>(
    (minimum, site) => (minimum === undefined || site.id < minimum.id ? site : minimum),
    undefined,
  );

export const resolveSelectedSite = (
  selection: DashboardSearchSelection,
  sites: readonly Site[],
): Site | undefined => {
  if (selection.site.kind === "single") {
    const requestedSiteSlug = selection.site.value;
    const requestedSite = sites.find((site) => site.slug === requestedSiteSlug);

    if (requestedSite !== undefined) {
      return requestedSite;
    }
  }

  return findDefaultSite(sites);
};

export const resolveSelectedDate = (
  selection: DashboardSearchSelection,
  forecastDays: ForecastDaysResponse | undefined,
): ForecastDate | undefined => {
  if (selection.date.kind === "valid") {
    const requestedDate = selection.date.value;

    if (
      forecastDays === undefined ||
      forecastDays.days.some((day) => day.forecastDate === requestedDate)
    ) {
      return requestedDate;
    }

    return forecastDays.todayDate;
  }

  return forecastDays?.todayDate;
};

export const createCanonicalDashboardSearch = (
  siteSlug: SiteSlug,
  forecastDate: ForecastDate | undefined,
): URLSearchParams => {
  const canonicalSearch = new URLSearchParams();
  canonicalSearch.set(DASHBOARD_SITE_PARAMETER, siteSlug);

  if (forecastDate !== undefined) {
    canonicalSearch.set(DASHBOARD_DATE_PARAMETER, forecastDate);
  }

  return canonicalSearch;
};

export const dashboardSearchesMatch = (
  currentSearch: URLSearchParams,
  nextSearch: URLSearchParams,
): boolean => currentSearch.toString() === nextSearch.toString();
