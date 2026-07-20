import type { Site, SiteSlug } from "@paragliding-forecasts/contracts";

import type { SiteRepository } from "./site.repository.js";

export class SiteService {
  readonly #repository: SiteRepository;

  constructor(repository: SiteRepository) {
    this.#repository = repository;
  }

  listSites(): Promise<readonly Site[]> {
    return this.#repository.list();
  }

  findSiteBySlug(siteSlug: SiteSlug): Promise<Site | undefined> {
    return this.#repository.findBySlug(siteSlug);
  }
}
