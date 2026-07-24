import type { ForecastDate, ForecastDay } from "@paragliding-forecasts/contracts";

import { formatForecastDateDayMonth, formatInteger } from "../forecast-presentation.js";
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
      <time className={styles.context} dateTime={day.forecastDate}>
        {today ? "Today" : formatForecastDateDayMonth(day.forecastDate)}
      </time>
      {metric.dataStatus === "missing" ? (
        <>
          <strong className={styles.unavailable}>Unavailable</strong>
          <DataStatusBadge compact status="missing" />
          <ConfidenceIndicator
            compact
            confidence={{ level: "unavailable", notes: [metric.missingReason] }}
            label="Conf."
          />
          <span className={styles.reason}>{metric.missingReason}</span>
        </>
      ) : (
        <>
          <strong className={styles.value}>{formatInteger(metric.value)}%</strong>
          <DataStatusBadge compact status={metric.dataStatus} />
          <ConfidenceIndicator
            compact
            confidence={{ level: metric.confidence.level, notes: [metric.confidence.note] }}
            label="Conf."
          />
        </>
      )}
      <span className="visually-hidden" id={descriptionId}>
        {description}
      </span>
    </button>
  );
};
