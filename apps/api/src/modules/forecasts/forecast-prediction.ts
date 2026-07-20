import type {
  AvailableDataStatus,
  Confidence,
  ForecastDate,
  Provenance,
  SiteId,
} from "@paragliding-forecasts/contracts";

export type OverdevelopmentRisk = "low" | "medium" | "high";

export interface ForecastPrediction {
  readonly siteId: SiteId;
  readonly forecastDate: ForecastDate;
  readonly generatedAt: string;
  readonly provenance: Provenance;
  readonly dataStatus: AvailableDataStatus;
  readonly confidence: Confidence;
  readonly cloudbasePredictionMslM: number;
  readonly probability100KmPct: number;
  readonly probability200KmPct: number;
  readonly probability300KmPct: number;
  readonly overdevelopmentRisk: OverdevelopmentRisk;
  readonly topDrivers: readonly string[];
}
