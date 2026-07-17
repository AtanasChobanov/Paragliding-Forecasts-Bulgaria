import type {
  Confidence,
  ForecastDate,
  Provenance,
  SiteId,
} from "@paragliding-forecasts/contracts";

export type OverdevelopmentRisk = "low" | "medium" | "high";

export interface ForecastRecord {
  readonly siteId: SiteId;
  readonly date: ForecastDate;
  readonly generatedAt: string;
  readonly provenance: Provenance;
  readonly dataStatus: "mock";
  readonly confidence: Confidence;
  readonly cloudbasePredictionMslM: number;
  readonly probability100KmPct: number;
  readonly probability200KmPct: number;
  readonly probability300KmPct: number;
  readonly overdevelopmentRisk: OverdevelopmentRisk;
  readonly topDrivers: readonly string[];
  readonly qualityNotes: readonly string[];
}
