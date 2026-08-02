import type { Site, SiteId, SiteSlug } from "@paragliding-forecasts/contracts";

import type { SiteRepository } from "./site.repository.js";

export const initialSiteCatalog = [
  {
    id: 1,
    slug: "sofia-vitosha-kominite",
    name: "Sofia - Vitosha (Kominite)",
    latitude: 42.6013,
    longitude: 23.2844,
  },
  { id: 2, slug: "zlatitsa", name: "Zlatitsa", latitude: 42.7302, longitude: 24.0923 },
  { id: 3, slug: "sopot", name: "Sopot", latitude: 42.68733, longitude: 24.749962 },
  { id: 4, slug: "nevsha", name: "Nevsha", latitude: 43.2622, longitude: 27.2846 },
  { id: 5, slug: "shumen", name: "Shumen", latitude: 43.2575, longitude: 26.9258 },
  { id: 6, slug: "pastrina", name: "Pastrina", latitude: 43.4282, longitude: 23.3032 },
  {
    id: 7,
    slug: "dobrich-region",
    name: "Dobrich region",
    latitude: 43.56667,
    longitude: 27.83333,
  },
] as const satisfies readonly Site[];

export class InMemorySiteRepository implements SiteRepository {
  readonly #sitesBySlug: ReadonlyMap<SiteSlug, Site>;

  constructor(sites: readonly Site[] = initialSiteCatalog) {
    const siteIds = new Set<SiteId>();
    const sitesBySlug = new Map<SiteSlug, Site>();

    for (const site of sites) {
      if (siteIds.has(site.id)) {
        throw new Error(`Duplicate site ID: ${String(site.id)}`);
      }

      if (sitesBySlug.has(site.slug)) {
        throw new Error(`Duplicate site slug: ${site.slug}`);
      }

      siteIds.add(site.id);
      sitesBySlug.set(site.slug, { ...site });
    }

    this.#sitesBySlug = sitesBySlug;
  }

  list(): Promise<readonly Site[]> {
    return Promise.resolve(
      [...this.#sitesBySlug.values()]
        .sort((left, right) => left.id - right.id)
        .map((site) => ({ ...site })),
    );
  }

  findBySlug(siteSlug: SiteSlug): Promise<Site | undefined> {
    const site = this.#sitesBySlug.get(siteSlug);
    return Promise.resolve(site === undefined ? undefined : { ...site });
  }
}
