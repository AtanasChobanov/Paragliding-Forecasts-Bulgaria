import type { Site, SiteSlug } from "@paragliding-forecasts/contracts";
import { lazy, Suspense } from "react";

import { AccessibleSiteSelector } from "./AccessibleSiteSelector.js";
import styles from "./SiteSelectorSection.module.scss";

const LazySiteMap = lazy(async () => {
  const module = await import("./SiteMap.js");
  return { default: module.SiteMap };
});

export interface SiteSelectorSectionProps {
  readonly onSelectSite: (siteSlug: SiteSlug) => void;
  readonly selectedSite: Site;
  readonly sites: readonly Site[];
}

export const SiteSelectorSection = ({
  onSelectSite,
  selectedSite,
  sites,
}: SiteSelectorSectionProps) => (
  <div className={styles.content}>
    <div className={styles.controls}>
      <AccessibleSiteSelector
        onSelectSite={onSelectSite}
        selectedSite={selectedSite}
        sites={sites}
      />
    </div>
    <Suspense
      fallback={
        <div aria-busy="true" className={styles.mapFallback} role="status">
          Loading interactive map…
        </div>
      }
    >
      <LazySiteMap onSelectSite={onSelectSite} selectedSite={selectedSite} sites={sites} />
    </Suspense>
  </div>
);
