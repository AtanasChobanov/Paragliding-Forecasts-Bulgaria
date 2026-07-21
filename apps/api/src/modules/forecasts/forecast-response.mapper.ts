import type {
  ForecastDate,
  ForecastDay,
  ForecastOutputs,
  ForecastResponse,
  ForecastSummary,
  Site,
  SiteSlug,
} from "@paragliding-forecasts/contracts";

import type { ForecastPrediction } from "./forecast-prediction.js";

const mapPredictionMetric = <Value>(prediction: ForecastPrediction, value: Value) => ({
  value,
  dataStatus: prediction.dataStatus,
  confidence: { ...prediction.confidence },
});

const mapPredictionOutputs = (prediction: ForecastPrediction): ForecastOutputs => ({
  cloudbaseMslM: mapPredictionMetric(prediction, prediction.cloudbasePredictionMslM),
  chance100KmPct: mapPredictionMetric(prediction, prediction.probability100KmPct),
  chance200KmPct: mapPredictionMetric(prediction, prediction.probability200KmPct),
  chance300KmPct: mapPredictionMetric(prediction, prediction.probability300KmPct),
  overdevelopmentRisk: mapPredictionMetric(prediction, prediction.overdevelopmentRisk),
});

export const mapPredictionToForecastResponse = (
  prediction: ForecastPrediction,
  siteSlug: SiteSlug,
): ForecastResponse => ({
  siteId: prediction.siteId,
  siteSlug,
  forecastDate: prediction.forecastDate,
  generatedAt: prediction.generatedAt,
  provenance: { ...prediction.provenance },
  outputs: mapPredictionOutputs(prediction),
  topDrivers: [...prediction.topDrivers],
});

export const mapPredictionToForecastSummary = (
  prediction: ForecastPrediction,
  siteSlug: SiteSlug,
): ForecastSummary => ({
  availability: "available",
  siteId: prediction.siteId,
  siteSlug,
  forecastDate: prediction.forecastDate,
  generatedAt: prediction.generatedAt,
  provenance: { ...prediction.provenance },
  outputs: mapPredictionOutputs(prediction),
});

export const createMissingForecastSummary = (
  site: Site,
  forecastDate: ForecastDate,
): ForecastSummary => ({
  availability: "missing",
  siteId: site.id,
  siteSlug: site.slug,
  forecastDate,
  missingReason: `No forecast exists for site '${site.slug}' on ${forecastDate}.`,
});

export const mapPredictionToChance100KmMetric = (
  prediction: ForecastPrediction,
): ForecastDay["chance100KmPct"] => mapPredictionMetric(prediction, prediction.probability100KmPct);

export const createMissingChance100KmMetric = (
  siteSlug: SiteSlug,
  forecastDate: ForecastDate,
): ForecastDay["chance100KmPct"] => ({
  value: null,
  dataStatus: "missing",
  confidence: null,
  missingReason: `No 100+ km forecast is available for site '${siteSlug}' on ${forecastDate}.`,
});
