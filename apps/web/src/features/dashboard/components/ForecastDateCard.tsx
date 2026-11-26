import type { ForecastDate, ForecastDay } from "@paragliding-forecasts/contracts";

import {
  formatChancePercent,
  formatForecastDateDayMonth,
  p100Confidence,
} from "../forecast-presentation.js";
import { ConfidenceIndicator } from "./ConfidenceIndicator.js";
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
  const value = metric.value === null ? "Unavailable" : formatChancePercent(metric.value);
  const description =
    metric.dataStatus === "missing"
      ? `${today ? "Today. " : ""}100 or more kilometre chance unavailable. ${metric.missingReason}`
      : `${today ? "Today. " : ""}${value} chance of 100 or more kilometres. ${metric.dataStatus} data. ${metric.confidence.level} confidence. ${metric.confidence.note ?? ""}`;

  return (
    <button
      aria-current={today ? "date" : undefined}
      aria-describedby={descriptionId}
      aria-label={day.forecastDate}
      aria-pressed={selected}
      className={[styles.card, selected ? styles.selected : undefined].join(" ")}
      disabled={day.availability === "missing"}
      title={metric.dataStatus === "missing" ? metric.missingReason : undefined}
      type="button"
      onClick={() => {
        onSelectDate(day.forecastDate);
      }}
    >
      <time className={styles.context} dateTime={day.forecastDate}>
        {today ? "Today" : formatForecastDateDayMonth(day.forecastDate)}
      </time>
      <strong className={metric.dataStatus === "missing" ? styles.unavailable : styles.value}>
        {value}
      </strong>
      {metric.dataStatus === "missing" ? null : (
        <DataStatusBadge compact status={metric.dataStatus} />
      )}
      <ConfidenceIndicator
        accessibleLabel="100+ km confidence"
        compact
        confidence={p100Confidence(metric)}
        label="Conf."
      />
      <span className="visually-hidden" id={descriptionId}>
        {description}
      </span>
    </button>
  );
};
