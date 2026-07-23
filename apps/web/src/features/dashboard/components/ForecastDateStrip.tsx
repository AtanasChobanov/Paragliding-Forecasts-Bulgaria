import type { ForecastDate, ForecastDay } from "@paragliding-forecasts/contracts";

import { formatForecastYear } from "../forecast-presentation.js";
import { ForecastDateCard } from "./ForecastDateCard.js";
import styles from "./ForecastDateStrip.module.scss";

export interface ForecastDateStripProps {
  readonly days: readonly ForecastDay[];
  readonly onSelectDate: (date: ForecastDate) => void;
  readonly selectedDate: ForecastDate;
  readonly todayDate: ForecastDate;
}

export const ForecastDateStrip = ({
  days,
  onSelectDate,
  selectedDate,
  todayDate,
}: ForecastDateStripProps) => (
  <div>
    <p className={styles.year}>{formatForecastYear(todayDate)}</p>
    <ol aria-label="Five-day forecast dates" className={styles.list}>
      {days.map((day) => (
        <li key={day.forecastDate}>
          <ForecastDateCard
            day={day}
            onSelectDate={onSelectDate}
            selected={day.forecastDate === selectedDate}
            today={day.forecastDate === todayDate}
          />
        </li>
      ))}
    </ol>
  </div>
);
