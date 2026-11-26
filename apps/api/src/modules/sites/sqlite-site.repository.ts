import { siteSchema, type Site, type SiteSlug } from "@paragliding-forecasts/contracts";
import type { DatabaseSync, StatementSync } from "node:sqlite";

import type { SiteRepository } from "./site.repository.js";

export class SqliteSiteRepository implements SiteRepository {
  readonly #list: StatementSync;
  readonly #find: StatementSync;

  constructor(database: DatabaseSync) {
    const activeSites = `
      SELECT id, slug, name, latitude_deg AS latitude, longitude_deg AS longitude
      FROM sites
      WHERE is_active = 1`;
    this.#list = database.prepare(`${activeSites} ORDER BY id`);
    this.#find = database.prepare(`${activeSites} AND slug = ?`);
  }

  list(): Promise<readonly Site[]> {
    return Promise.resolve(this.#list.all().map((row) => siteSchema.parse(row)));
  }

  findBySlug(siteSlug: SiteSlug): Promise<Site | undefined> {
    const row = this.#find.get(siteSlug);
    return Promise.resolve(row === undefined ? undefined : siteSchema.parse(row));
  }
}
