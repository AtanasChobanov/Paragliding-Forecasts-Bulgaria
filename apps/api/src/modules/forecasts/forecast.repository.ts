import type {
  AvailableForecastSummary,
  ForecastDate,
  ForecastDay,
  Site,
  SiteId,
} from "@paragliding-forecasts/contracts";

import type { ForecastPrediction } from "./forecast-prediction.js";

export interface ForecastRepository {
  find?(siteId: SiteId, date: ForecastDate): Promise<ForecastPrediction | undefined>;
  listSummaries(
    sites: readonly Site[],
    date: ForecastDate,
    todayDate: ForecastDate,
  ): Promise<readonly AvailableForecastSummary[]>;
  listDays(
    siteId: SiteId,
    fromDate: ForecastDate,
    throughDate: ForecastDate,
  ): Promise<readonly Extract<ForecastDay, { availability: "available" }>[]>;
}
