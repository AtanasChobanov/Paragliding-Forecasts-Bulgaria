import type { Site, SiteId } from "@paragliding-forecasts/contracts";

import type { SiteRepository } from "./site.repository.js";

export class SiteService {
  readonly #repository: SiteRepository;

  constructor(repository: SiteRepository) {
    this.#repository = repository;
  }

  listSites(): Promise<readonly Site[]> {
    return this.#repository.list();
  }

  findSite(siteId: SiteId): Promise<Site | undefined> {
    return this.#repository.findById(siteId);
  }
}
