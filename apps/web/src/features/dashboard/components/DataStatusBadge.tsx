import type { DisplayDataStatus } from "../forecast-presentation.js";
import { formatDataStatus } from "../forecast-presentation.js";
import styles from "./DataStatusBadge.module.scss";

export interface DataStatusBadgeProps {
  readonly compact?: boolean;
  readonly status: DisplayDataStatus;
}

const statusClassName = (status: DisplayDataStatus): string => {
  switch (status) {
    case "baseline":
      return styles.baseline ?? "";
    case "manual":
      return styles.manual ?? "";
    case "missing":
      return styles.missing ?? "";
    case "mixed":
      return styles.mixed ?? "";
    case "mock":
      return styles.mock ?? "";
    case "real":
      return styles.real ?? "";
  }
};

export const DataStatusBadge = ({ compact = false, status }: DataStatusBadgeProps) => (
  <span
    className={[styles.badge, statusClassName(status), compact ? styles.compact : undefined]
      .filter((candidate): candidate is string => candidate !== undefined)
      .join(" ")}
  >
    {formatDataStatus(status)}
  </span>
);
