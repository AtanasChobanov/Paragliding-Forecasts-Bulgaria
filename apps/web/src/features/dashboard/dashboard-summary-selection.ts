import type {
  ForecastSummariesResponse,
  ForecastSummary,
  Site,
  SiteSlug,
} from "@paragliding-forecasts/contracts";

const OTHER_LOCATION_COUNT = 3;

const compareSitesById = (left: Site, right: Site): number =>
  left.id - right.id || left.slug.localeCompare(right.slug);

export const selectOtherLocationSites = (sites: readonly Site[]): readonly Site[] =>
  sites
    .slice()
    .sort(compareSitesById)
    .slice(1, OTHER_LOCATION_COUNT + 1);

export const createCanonicalSummarySiteSlugs = (
  sites: readonly Site[],
  selectedSite: Site,
): readonly SiteSlug[] => {
  const seenSiteIds = new Set<number>();
  const requestedSites = [selectedSite, ...selectOtherLocationSites(sites)].filter((site) => {
    if (seenSiteIds.has(site.id)) {
      return false;
    }

    seenSiteIds.add(site.id);
    return true;
  });

  return requestedSites.sort(compareSitesById).map((site) => site.slug);
};

export const indexForecastSummariesBySlug = (
  response: ForecastSummariesResponse,
): ReadonlyMap<SiteSlug, ForecastSummary> =>
  new Map(response.summaries.map((summary) => [summary.siteSlug, summary]));
