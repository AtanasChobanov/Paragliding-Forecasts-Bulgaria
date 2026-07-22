import type {
  Confidence,
  DataStatus,
  ForecastDate,
  ForecastOutputs,
} from "@paragliding-forecasts/contracts";

export type DisplayDataStatus = DataStatus | "mixed";
export type DisplayConfidenceLevel = Confidence["level"] | "mixed" | "unavailable";

export interface DisplayConfidence {
  readonly level: DisplayConfidenceLevel;
  readonly notes: readonly string[];
}

const DATA_STATUS_LABELS: Readonly<Record<DisplayDataStatus, string>> = {
  baseline: "Baseline data",
  manual: "Manual data",
  missing: "Unavailable",
  mixed: "Mixed data",
  mock: "Mock data",
  real: "Real data",
};

const CONFIDENCE_LABELS: Readonly<Record<DisplayConfidenceLevel, string>> = {
  high: "High confidence",
  low: "Low confidence",
  medium: "Medium confidence",
  mixed: "Mixed confidence",
  unavailable: "Confidence unavailable",
};

const outputMetrics = (outputs: ForecastOutputs) => [
  outputs.chance100KmPct,
  outputs.cloudbaseMslM,
  outputs.chance200KmPct,
  outputs.chance300KmPct,
  outputs.overdevelopmentRisk,
];

export const formatDataStatus = (status: DisplayDataStatus): string => DATA_STATUS_LABELS[status];

export const formatConfidence = (level: DisplayConfidenceLevel): string => CONFIDENCE_LABELS[level];

export const summarizeDataStatus = (outputs: ForecastOutputs): DisplayDataStatus => {
  const statuses = new Set(outputMetrics(outputs).map((metric) => metric.dataStatus));

  return statuses.size === 1 ? ([...statuses][0] ?? "missing") : "mixed";
};

export const summarizeConfidence = (outputs: ForecastOutputs): DisplayConfidence => {
  const availableMetrics = outputMetrics(outputs).filter(
    (metric): metric is typeof metric & { readonly confidence: Confidence } =>
      metric.dataStatus !== "missing",
  );

  if (availableMetrics.length === 0) {
    return { level: "unavailable", notes: [] };
  }

  const levels = new Set(availableMetrics.map((metric) => metric.confidence.level));
  const notes = [...new Set(availableMetrics.map((metric) => metric.confidence.note))];

  return {
    level: levels.size === 1 ? ([...levels][0] ?? "unavailable") : "mixed",
    notes,
  };
};

const parseForecastDate = (date: ForecastDate): Date => {
  const [year, month, day] = date.split("-").map(Number) as [number, number, number];
  return new Date(Date.UTC(year, month - 1, day));
};

export const formatForecastDateLong = (date: ForecastDate): string => {
  const parts = new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    timeZone: "UTC",
    weekday: "long",
  }).formatToParts(parseForecastDate(date));
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((candidate) => candidate.type === type)?.value ?? "";

  return `${part("weekday")}, ${part("day")} ${part("month")}`;
};

export const formatGeneratedAt = (generatedAt: string): string => {
  const parts = new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    hourCycle: "h23",
    minute: "2-digit",
    timeZone: "Europe/Sofia",
    timeZoneName: "short",
  }).formatToParts(new Date(generatedAt));
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((candidate) => candidate.type === type)?.value ?? "";

  return `${part("hour")}:${part("minute")} ${part("timeZoneName")}`.trim();
};

export const formatInteger = (value: number): string =>
  new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 }).format(value);

export const formatRisk = (value: "low" | "medium" | "high"): string =>
  `${value.charAt(0).toUpperCase()}${value.slice(1)}`;
