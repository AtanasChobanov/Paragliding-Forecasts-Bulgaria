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
  readonly showInstructions?: boolean;
  readonly showSelector?: boolean;
  readonly sites: readonly Site[];
  readonly viewportMode?: "all-sites" | "selected-site";
}

export const SiteSelectorSection = ({
  onSelectSite,
  selectedSite,
  showInstructions = true,
  showSelector = true,
  sites,
  viewportMode = "all-sites",
}: SiteSelectorSectionProps) => (
  <div className={styles.content}>
    {showSelector ? (
      <div className={styles.controls}>
        <AccessibleSiteSelector
          onSelectSite={onSelectSite}
          selectedSite={selectedSite}
          sites={sites}
        />
      </div>
    ) : null}
    <Suspense
      fallback={
        <div aria-busy="true" className={styles.mapFallback} role="status">
          Loading interactive map…
        </div>
      }
    >
      <LazySiteMap
        onSelectSite={onSelectSite}
        selectedSite={selectedSite}
        showInstructions={showInstructions}
        sites={sites}
        viewportMode={viewportMode}
      />
    </Suspense>
  </div>
);
