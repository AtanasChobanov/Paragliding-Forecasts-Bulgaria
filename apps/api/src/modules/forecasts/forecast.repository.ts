import type {
  AvailableForecastSummary,
  ForecastDate,
  ForecastDay,
  ForecastResponse,
  Site,
  SiteId,
} from "@paragliding-forecasts/contracts";

import type { ForecastPrediction } from "./forecast-prediction.js";

export interface ForecastRepository {
  findDetail?(
    site: Site,
    date: ForecastDate,
    today: ForecastDate,
  ): Promise<ForecastResponse | undefined>;
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
