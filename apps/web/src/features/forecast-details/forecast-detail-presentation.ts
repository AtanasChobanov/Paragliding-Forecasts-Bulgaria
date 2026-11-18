import type {
  ForecastDriver,
  ForecastInputRow,
  ForecastResponse,
} from "@paragliding-forecasts/contracts";

const numeric = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 });
export const formatInputValue = (row: ForecastInputRow): string => {
  if (row.value === null)
    return row.missingReason === "Outside OD interval inputs" ? row.missingReason : "Unavailable";
  let value = row.value,
    unit = row.unit;
  if (unit === "K") {
    value -= 273.15;
    unit = "°C";
  } else if (unit === "Pa") {
    value /= 100;
    unit = "hPa";
  } else if (unit === "kg/kg") {
    value *= 1000;
    unit = "g/kg";
  } else if (unit === "K/km") unit = "°C/km";
  const text =
    value !== 0 && Math.abs(value) < 0.01 ? value.toExponential(2) : numeric.format(value);
  return `${text} ${unit}`;
};

const sofiaClock = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/Sofia",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});
export const formatSofiaHour = (at: string) => sofiaClock.format(new Date(at));
const dateTime = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/Sofia",
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});
const cycleDate = new Intl.DateTimeFormat("en-GB", {
  timeZone: "UTC",
  day: "numeric",
  month: "short",
  year: "numeric",
});
export const sourceLine = (forecast: ForecastResponse) =>
  forecast.metadata.mode === "sqlite"
    ? `GFS ${cycleDate.format(new Date(forecast.metadata.cycleAtUtc))} 06Z`
    : `Synthetic data · ${forecast.metadata.version}`;
export const publicationLine = (forecast: ForecastResponse) =>
  `${sourceLine(forecast)} · Published ${dateTime.format(new Date(forecast.generatedAt))} Sofia`;

const uncertain = new Set([
  "missing",
  "indeterminate",
  "cloud_type_unknown",
  "widespread_low_cloud",
  "buoyancy_input_missing",
  "transition_or_conflicting_evidence",
  "low_cloud_input_missing_or_invalid",
  "formation_input_missing",
  "required_source_input_unavailable",
  "surface_or_model_terrain_missing",
  "model_profile_order_invalid",
  "model_profile_missing",
  "potential_base_outside_profile",
]);
export const presentDriver = (
  driver: ForecastDriver,
): {
  symbol: string;
  meaning: string;
  tone: "primary" | "danger" | "secondary" | "sky" | "warning";
} => {
  if (driver.kind === "xc_contribution") {
    return driver.direction === "raises"
      ? { symbol: "+", meaning: "Raises the model estimate", tone: "primary" }
      : driver.direction === "lowers"
        ? { symbol: "−", meaning: "Lowers the model estimate", tone: "danger" }
        : { symbol: "=", meaning: "No directional contribution", tone: "secondary" };
  }
  if (driver.kind === "pooled_conversion")
    return { symbol: "ƒ", meaning: "Pooled conversion", tone: "sky" };
  if (driver.kind === "od_override")
    return { symbol: "△", meaning: "Critical risk rule", tone: "danger" };
  if (driver.kind === "od_score_component")
    return {
      symbol: "◴",
      meaning: "Risk score component",
      tone: driver.scorePoints === 0 ? "secondary" : "warning",
    };
  return uncertain.has(driver.code) || /(?:missing|invalid|insufficient)/.test(driver.code)
    ? { symbol: "△", meaning: "Uncertain cloudbase evidence", tone: "warning" }
    : { symbol: "ⓘ", meaning: "Cloudbase explanation", tone: "sky" };
};

export const defaultCloudbaseHour = (forecast: ForecastResponse): string => {
  const cloud = forecast.outputs.cloudbase;
  if (cloud.kind === "estimated" || cloud.kind === "conditional_lcl") {
    const regime = cloud.kind === "estimated" ? "cumulus" : "indeterminate";
    const maximum = forecast.cloudbaseHours.find(
      (h) => h.regime === regime && h.heightMslM === cloud.valueMslM,
    );
    if (maximum) return maximum.validAtUtc;
  }
  return forecast.cloudbaseHours[0]?.validAtUtc ?? forecast.forecastInputs.windowStartUtc;
};
