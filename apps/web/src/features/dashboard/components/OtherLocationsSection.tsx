import type { ForecastSummary, Site, SiteSlug } from "@paragliding-forecasts/contracts";

import { LocationSummaryCard } from "./LocationSummaryCard.js";
import styles from "./OtherLocationsSection.module.scss";

export interface OtherLocationsSectionProps {
  readonly sites: readonly Site[];
  readonly summariesBySlug: ReadonlyMap<SiteSlug, ForecastSummary> | undefined;
}

export const OtherLocationsSection = ({ sites, summariesBySlug }: OtherLocationsSectionProps) => (
  <ul aria-label="Other location summaries" className={styles.list}>
    {sites.map((site) => (
      <li data-site-slug={site.slug} key={site.id}>
        <LocationSummaryCard site={site} summary={summariesBySlug?.get(site.slug)} />
      </li>
    ))}
  </ul>
);
