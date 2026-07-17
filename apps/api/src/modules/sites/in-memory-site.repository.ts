import type { Site, SiteId } from "@paragliding-forecasts/contracts";

import type { SiteRepository } from "./site.repository.js";

export const initialSiteCatalog = [
  { id: "sofia-vitosha-kominite", name: "Sofia - Vitosha (Kominite)" },
  { id: "zlatitsa", name: "Zlatitsa" },
  { id: "sopot", name: "Sopot" },
  { id: "nevsha", name: "Nevsha" },
  { id: "shumen", name: "Shumen" },
  { id: "pastrona", name: "Pastrona" },
  { id: "dobrich-region", name: "Dobrich region" },
] as const satisfies readonly Site[];

export class InMemorySiteRepository implements SiteRepository {
  readonly #sitesById: ReadonlyMap<SiteId, Site>;

  constructor(sites: readonly Site[] = initialSiteCatalog) {
    const sitesById = new Map<SiteId, Site>();

    for (const site of sites) {
      if (sitesById.has(site.id)) {
        throw new Error(`Duplicate site ID: ${site.id}`);
      }

      sitesById.set(site.id, { ...site });
    }

    this.#sitesById = sitesById;
  }

  list(): Promise<readonly Site[]> {
    return Promise.resolve([...this.#sitesById.values()].map((site) => ({ ...site })));
  }

  findById(siteId: SiteId): Promise<Site | undefined> {
    const site = this.#sitesById.get(siteId);
    return Promise.resolve(site === undefined ? undefined : { ...site });
  }
}
