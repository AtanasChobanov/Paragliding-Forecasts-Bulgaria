import type { ForecastDate, SiteId } from "@paragliding-forecasts/contracts";

import type { ForecastPrediction } from "./forecast-prediction.js";

export interface ForecastRepository {
  find(siteId: SiteId, date: ForecastDate): Promise<ForecastPrediction | undefined>;
  listBySiteIdsAndDate(
    siteIds: readonly SiteId[],
    date: ForecastDate,
  ): Promise<readonly ForecastPrediction[]>;
  listBySiteAndDateRange(
    siteId: SiteId,
    fromDate: ForecastDate,
    throughDate: ForecastDate,
  ): Promise<readonly ForecastPrediction[]>;
}
