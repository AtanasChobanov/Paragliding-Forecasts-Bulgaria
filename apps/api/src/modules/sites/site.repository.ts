import type { Site, SiteId } from "@paragliding-forecasts/contracts";

export interface SiteRepository {
  list(): Promise<readonly Site[]>;
  findById(siteId: SiteId): Promise<Site | undefined>;
}
