import type { ForecastDate, ForecastDay } from "@paragliding-forecasts/contracts";
import type { ChangeEvent } from "react";

import { formatForecastDateLong } from "../../dashboard/forecast-presentation.js";
import styles from "./ForecastDateSelector.module.scss";

export interface ForecastDateSelectorProps {
  readonly days: readonly ForecastDay[];
  readonly onSelectDate: (date: ForecastDate) => void;
  readonly selectedDate: ForecastDate;
}

export const ForecastDateSelector = ({
  days,
  onSelectDate,
  selectedDate,
}: ForecastDateSelectorProps) => {
  const handleChange = (event: ChangeEvent<HTMLSelectElement>) => {
    onSelectDate(event.target.value);
  };

  return (
    <div className={styles.field}>
      <label htmlFor="forecast-detail-date-selector">
        <span aria-hidden="true" className={styles.calendar} />
        <span className="visually-hidden">Forecast date</span>
      </label>
      <select id="forecast-detail-date-selector" value={selectedDate} onChange={handleChange}>
        {days.map((day) => (
          <option key={day.forecastDate} value={day.forecastDate}>
            {formatForecastDateLong(day.forecastDate)}
          </option>
        ))}
      </select>
    </div>
  );
};
