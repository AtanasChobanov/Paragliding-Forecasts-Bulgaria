import type { ReactNode } from "react";

import { DashboardPanel } from "../../../components/dashboard-panel/DashboardPanel.js";
import styles from "./DashboardShell.module.scss";

export interface DashboardShellProps {
  readonly announcement: string;
  readonly datesBusy?: boolean;
  readonly forecastDates: ReactNode;
  readonly locationBusy?: boolean;
  readonly locationSelector: ReactNode;
  readonly otherBusy?: boolean;
  readonly otherLocations: ReactNode;
  readonly overview: ReactNode;
  readonly overviewBusy?: boolean;
}

export const DashboardShell = ({
  announcement,
  datesBusy = false,
  forecastDates,
  locationBusy = false,
  locationSelector,
  otherBusy = false,
  otherLocations,
  overview,
  overviewBusy = false,
}: DashboardShellProps) => (
  <main aria-label="XC Forecast dashboard" className={styles.main}>
    <DashboardPanel
      busy={overviewBusy}
      className={styles.overview}
      headingLevel={null}
      headingId="forecast-overview-heading"
      title="Forecast overview"
    >
      {overview}
    </DashboardPanel>
    <DashboardPanel
      busy={locationBusy}
      className={styles.location}
      headerClassName={styles.locationHeader}
      headingId="site-selector-heading"
      title="Select a location"
    >
      {locationSelector}
    </DashboardPanel>
    <DashboardPanel
      busy={otherBusy}
      className={styles.other}
      headingId="other-locations-heading"
      title="Other locations for this date"
    >
      {otherLocations}
    </DashboardPanel>
    <DashboardPanel
      busy={datesBusy}
      className={styles.dates}
      headingId="forecast-date-heading"
      title="Select forecast date"
    >
      {forecastDates}
    </DashboardPanel>
    <p aria-live="polite" className="visually-hidden">
      {announcement}
    </p>
  </main>
);
