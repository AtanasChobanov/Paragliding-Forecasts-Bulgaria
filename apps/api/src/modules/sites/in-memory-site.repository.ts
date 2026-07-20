import type { Site, SiteId, SiteSlug } from "@paragliding-forecasts/contracts";

import type { SiteRepository } from "./site.repository.js";

export const initialSiteCatalog = [
  { id: 1, slug: "sofia-vitosha-kominite", name: "Sofia - Vitosha (Kominite)" },
  { id: 2, slug: "zlatitsa", name: "Zlatitsa" },
  { id: 3, slug: "sopot", name: "Sopot" },
  { id: 4, slug: "nevsha", name: "Nevsha" },
  { id: 5, slug: "shumen", name: "Shumen" },
  { id: 6, slug: "pastrona", name: "Pastrona" },
  { id: 7, slug: "dobrich-region", name: "Dobrich region" },
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
    return Promise.resolve([...this.#sitesBySlug.values()].map((site) => ({ ...site })));
  }

  findBySlug(siteSlug: SiteSlug): Promise<Site | undefined> {
    const site = this.#sitesBySlug.get(siteSlug);
    return Promise.resolve(site === undefined ? undefined : { ...site });
  }
}
