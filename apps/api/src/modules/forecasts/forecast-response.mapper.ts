import type {
  AvailableForecastSummary,
  ForecastDate,
  ForecastDay,
  ForecastResponse,
  ForecastSummary,
  DashboardForecastOutputs,
  Site,
  SiteSlug,
} from "@paragliding-forecasts/contracts";

import { mockForecastDetail } from "./mock-forecast-detail.js";
import type { ForecastPrediction } from "./forecast-prediction.js";

const mapPredictionMetric = <Value>(prediction: ForecastPrediction, value: Value) => ({
  value,
  dataStatus: prediction.dataStatus,
  confidence: { ...prediction.confidence },
});

const mapPredictionChancesAndRisk = (prediction: ForecastPrediction) => ({
  chance100KmPct: mapPredictionMetric(prediction, prediction.probability100KmPct),
  chance200KmPct: mapPredictionMetric(prediction, prediction.probability200KmPct),
  chance300KmPct: mapPredictionMetric(prediction, prediction.probability300KmPct),
  overdevelopmentRisk: mapPredictionMetric(prediction, prediction.overdevelopmentRisk),
});

export const mapPredictionToForecastResponse = (
  prediction: ForecastPrediction,
  siteSlug: SiteSlug,
): ForecastResponse =>
  mockForecastDetail(mapPredictionToForecastSummary(prediction, siteSlug), prediction.topDrivers);

export const mapPredictionToForecastSummary = (
  prediction: ForecastPrediction,
  siteSlug: SiteSlug,
): AvailableForecastSummary => {
  const outputs: DashboardForecastOutputs = {
    ...mapPredictionChancesAndRisk(prediction),
    cloudbase: {
      kind: "estimated",
      dataStatus: "mock",
      valueMslM: prediction.cloudbasePredictionMslM,
      confidence: { ...prediction.confidence },
    },
  };

  return {
    availability: "available",
    siteId: prediction.siteId,
    siteSlug,
    forecastDate: prediction.forecastDate,
    generatedAt: prediction.generatedAt,
    metadata: { mode: "mock", ...prediction.provenance },
    outputs,
  };
};

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

export const mapPredictionToForecastDay = (
  prediction: ForecastPrediction,
): Extract<ForecastDay, { availability: "available" }> => ({
  availability: "available",
  forecastDate: prediction.forecastDate,
  chance100KmPct: mapPredictionMetric(prediction, prediction.probability100KmPct),
});

export const createMissingForecastDay = (
  siteSlug: SiteSlug,
  forecastDate: ForecastDate,
): ForecastDay => ({
  availability: "missing",
  forecastDate,
  missingReason: `No forecast exists for site '${siteSlug}' on ${forecastDate}.`,
  chance100KmPct: {
    value: null,
    dataStatus: "missing",
    confidence: null,
    missingReason: `No 100+ km forecast is available for site '${siteSlug}' on ${forecastDate}.`,
  },
});
