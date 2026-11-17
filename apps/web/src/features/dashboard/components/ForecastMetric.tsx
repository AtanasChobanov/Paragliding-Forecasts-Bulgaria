import type { ReactNode } from "react";

import styles from "./ForecastMetric.module.scss";

export interface ForecastMetricProps {
  readonly icon: ReactNode;
  readonly label: string;
  readonly primary?: boolean;
  readonly unit?: string;
  readonly value: string;
  readonly missingReason?: string | undefined;
}

export const ForecastMetric = ({
  icon,
  label,
  primary = false,
  unit,
  value,
  missingReason,
}: ForecastMetricProps) => (
  <li className={[styles.metric, primary ? styles.primary : undefined].join(" ")}>
    <span aria-hidden="true" className={styles.icon}>
      {icon}
    </span>
    <div className={styles.valueRow}>
      <strong
        className={missingReason === undefined ? styles.value : styles.unavailable}
        title={missingReason}
      >
        {value}
      </strong>
      {unit === undefined ? null : <span className={styles.unit}>{unit}</span>}
    </div>
    <span className={styles.label}>{label}</span>
  </li>
);
