import type { ForecastDate } from "@paragliding-forecasts/contracts";

export const FORECAST_TIME_ZONE = "Europe/Sofia";

const dateFormatter = new Intl.DateTimeFormat("en-CA", {
  day: "2-digit",
  month: "2-digit",
  timeZone: FORECAST_TIME_ZONE,
  year: "numeric",
});

export const toForecastDate = (instant: Date): ForecastDate => {
  const parts = new Map(
    dateFormatter
      .formatToParts(instant)
      .filter((part) => part.type === "year" || part.type === "month" || part.type === "day")
      .map((part) => [part.type, part.value]),
  );
  const year = parts.get("year");
  const month = parts.get("month");
  const day = parts.get("day");

  if (year === undefined || month === undefined || day === undefined) {
    throw new Error("Could not derive the Europe/Sofia calendar date.");
  }

  return `${year}-${month}-${day}`;
};

export const addForecastDays = (date: ForecastDate, days: number): ForecastDate => {
  const [yearText, monthText, dayText] = date.split("-");
  const shifted = new Date(
    Date.UTC(Number(yearText), Number(monthText) - 1, Number(dayText) + days),
  );

  return shifted.toISOString().slice(0, 10);
};

export const createForecastDateWindow = (
  centerDate: ForecastDate,
  daysBefore: number,
  daysAfter: number,
): readonly ForecastDate[] =>
  Array.from({ length: daysBefore + daysAfter + 1 }, (_, index) =>
    addForecastDays(centerDate, index - daysBefore),
  );
