import type { ForecastDate, ForecastDay } from "@paragliding-forecasts/contracts";

import {
  formatForecastDateDayMonth,
  formatForecastDateWeekday,
  formatInteger,
} from "../forecast-presentation.js";
import { DataStatusBadge } from "./DataStatusBadge.js";
import styles from "./ForecastDateCard.module.scss";

export interface ForecastDateCardProps {
  readonly day: ForecastDay;
  readonly onSelectDate: (date: ForecastDate) => void;
  readonly selected: boolean;
  readonly today: boolean;
}

export const ForecastDateCard = ({ day, onSelectDate, selected, today }: ForecastDateCardProps) => {
  const metric = day.chance100KmPct;
  const descriptionId = `forecast-date-description-${day.forecastDate}`;
  const description =
    metric.dataStatus === "missing"
      ? `${today ? "Today. " : ""}100 or more kilometre chance unavailable. ${metric.missingReason}`
      : `${today ? "Today. " : ""}${String(metric.value)} percent chance of 100 or more kilometres. ${metric.dataStatus} data. ${metric.confidence.level} confidence. ${metric.confidence.note}`;

  return (
    <button
      aria-current={today ? "date" : undefined}
      aria-describedby={descriptionId}
      aria-label={day.forecastDate}
      aria-pressed={selected}
      className={[styles.card, selected ? styles.selected : undefined]
        .filter((candidate): candidate is string => candidate !== undefined)
        .join(" ")}
      type="button"
      onClick={() => {
        onSelectDate(day.forecastDate);
      }}
    >
      <span className={styles.context}>
        {today ? "Today" : formatForecastDateWeekday(day.forecastDate)}
      </span>
      <time className={styles.date} dateTime={day.forecastDate}>
        {formatForecastDateDayMonth(day.forecastDate)}
      </time>
      {metric.dataStatus === "missing" ? (
        <>
          <strong className={styles.unavailable}>Unavailable</strong>
          <span className={styles.metricLabel}>100+ km chance</span>
          <DataStatusBadge compact status="missing" />
          <span className={styles.reason}>{metric.missingReason}</span>
        </>
      ) : (
        <>
          <strong className={styles.value}>{formatInteger(metric.value)}%</strong>
          <span className={styles.metricLabel}>100+ km chance</span>
          <DataStatusBadge compact status={metric.dataStatus} />
          <span className={styles.confidence} title={metric.confidence.note}>
            {metric.confidence.level} confidence
          </span>
        </>
      )}
      <span className="visually-hidden" id={descriptionId}>
        {description}
      </span>
    </button>
  );
};
