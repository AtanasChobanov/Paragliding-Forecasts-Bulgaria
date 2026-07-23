import type { Site, SiteSlug } from "@paragliding-forecasts/contracts";
import type { ChangeEvent } from "react";

import styles from "./AccessibleSiteSelector.module.scss";

export interface AccessibleSiteSelectorProps {
  readonly onSelectSite: (siteSlug: SiteSlug) => void;
  readonly selectedSite: Site;
  readonly sites: readonly Site[];
}

export const AccessibleSiteSelector = ({
  onSelectSite,
  selectedSite,
  sites,
}: AccessibleSiteSelectorProps) => {
  const handleChange = (event: ChangeEvent<HTMLSelectElement>) => {
    onSelectSite(event.target.value);
  };

  return (
    <div className={styles.field}>
      <label htmlFor="dashboard-site-selector">
        <span aria-hidden="true" className={styles.pin} />
        <span className="visually-hidden">Location</span>
      </label>
      <select
        aria-describedby="dashboard-site-selector-help"
        id="dashboard-site-selector"
        value={selectedSite.slug}
        onChange={handleChange}
      >
        {sites
          .slice()
          .sort((left, right) => left.id - right.id)
          .map((site) => (
            <option key={site.id} value={site.slug}>
              {site.name}
            </option>
          ))}
      </select>
      <p className="visually-hidden" id="dashboard-site-selector-help">
        Select any forecast location without using the map.
      </p>
    </div>
  );
};
