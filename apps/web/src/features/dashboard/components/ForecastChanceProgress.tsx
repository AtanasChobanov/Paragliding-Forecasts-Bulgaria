import styles from "./ForecastChanceProgress.module.scss";

export interface ForecastChanceProgressProps {
  readonly label: string;
  readonly value: number;
}

export const ForecastChanceProgress = ({ label, value }: ForecastChanceProgressProps) => (
  <div
    aria-label={`${String(value)} percent ${label}`}
    aria-valuemax={100}
    aria-valuemin={0}
    aria-valuenow={value}
    className={styles.progress}
    role="progressbar"
  >
    <span style={{ width: `${String(value)}%` }} />
  </div>
);
