import type { ForecastDate, SiteId } from "@paragliding-forecasts/contracts";

import type { ForecastRecord } from "./forecast-record.js";

export interface ForecastRepository {
  get(siteId: SiteId, date: ForecastDate): Promise<ForecastRecord>;
}
