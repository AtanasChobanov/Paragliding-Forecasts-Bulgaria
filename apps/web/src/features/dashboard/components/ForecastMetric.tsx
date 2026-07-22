import type { ForecastOutputs } from "@paragliding-forecasts/contracts";

import { DataStatusBadge } from "./DataStatusBadge.js";
import styles from "./ForecastMetric.module.scss";

export type ForecastMetricState = ForecastOutputs[keyof ForecastOutputs];

export interface ForecastMetricProps {
  readonly label: string;
  readonly metric: ForecastMetricState;
  readonly primary?: boolean;
  readonly showStatus: boolean;
  readonly unit?: string;
  readonly value: string | null;
}

export const ForecastMetric = ({
  label,
  metric,
  primary = false,
  showStatus,
  unit,
  value,
}: ForecastMetricProps) => {
  const missing = metric.dataStatus === "missing" || value === null;

  return (
    <li
      className={[styles.metric, primary ? styles.primary : undefined]
        .filter((candidate): candidate is string => candidate !== undefined)
        .join(" ")}
    >
      <div className={styles.valueRow}>
        {missing ? (
          <strong className={styles.unavailable}>Unavailable</strong>
        ) : (
          <strong className={styles.value}>{value}</strong>
        )}
        {missing || unit === undefined ? null : <span className={styles.unit}>{unit}</span>}
      </div>
      <span className={styles.label}>{label}</span>
      {showStatus || missing ? (
        <DataStatusBadge compact status={missing ? "missing" : metric.dataStatus} />
      ) : null}
      {metric.dataStatus === "missing" ? (
        <span className={styles.reason}>{metric.missingReason}</span>
      ) : null}
      {metric.dataStatus !== "missing" && value !== null && showStatus ? (
        <span className={styles.metricConfidence} title={metric.confidence.note}>
          {metric.confidence.level} confidence
        </span>
      ) : null}
    </li>
  );
};
