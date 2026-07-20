import type { Site, SiteSlug } from "@paragliding-forecasts/contracts";

export interface SiteRepository {
  list(): Promise<readonly Site[]>;
  findBySlug(siteSlug: SiteSlug): Promise<Site | undefined>;
}
