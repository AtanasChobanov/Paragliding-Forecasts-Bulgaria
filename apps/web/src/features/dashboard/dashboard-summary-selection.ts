import type {
  ForecastSummariesResponse,
  ForecastSummary,
  Site,
  SiteSlug,
} from "@paragliding-forecasts/contracts";

export const OTHER_LOCATION_SLUGS = [
  "zlatitsa",
  "sofia-vitosha-kominite",
  "dobrich-region",
] as const satisfies readonly SiteSlug[];

export const selectOtherLocationSites = (sites: readonly Site[]): readonly Site[] => {
  const sitesBySlug = new Map(sites.map((site) => [site.slug, site]));

  return OTHER_LOCATION_SLUGS.flatMap((slug) => {
    const site = sitesBySlug.get(slug);
    return site === undefined ? [] : [site];
  });
};

export const createCanonicalSummarySiteSlugs = (
  sites: readonly Site[],
  selectedSite: Site,
): readonly SiteSlug[] => {
  const requestedSlugs = new Set<SiteSlug>([selectedSite.slug, ...OTHER_LOCATION_SLUGS]);
  const requestedSites = sites
    .filter((site) => requestedSlugs.has(site.slug))
    .slice()
    .sort((left, right) => left.id - right.id || left.slug.localeCompare(right.slug));
  const seenSiteIds = new Set<number>();

  return requestedSites.flatMap((site) => {
    if (seenSiteIds.has(site.id)) {
      return [];
    }

    seenSiteIds.add(site.id);
    return [site.slug];
  });
};

export const indexForecastSummariesBySlug = (
  response: ForecastSummariesResponse,
): ReadonlyMap<SiteSlug, ForecastSummary> =>
  new Map(response.summaries.map((summary) => [summary.siteSlug, summary]));
