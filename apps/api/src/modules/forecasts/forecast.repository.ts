import type { ForecastDate, SiteId } from "@paragliding-forecasts/contracts";

import type { ForecastPrediction } from "./forecast-prediction.js";

export interface ForecastRepository {
  get(siteId: SiteId, date: ForecastDate): Promise<ForecastPrediction>;
}
