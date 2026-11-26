import { openDatabase } from "@paragliding-forecasts/database";
import type { Logger } from "pino";

import { createApp } from "./app.js";
import { API_VERSION } from "./app-metadata.js";
import type { ApiConfig } from "./config/env.js";
import { createRootRouter } from "./http/router.js";
import type { ForecastRepository } from "./modules/forecasts/forecast.repository.js";
import { createForecastRouter } from "./modules/forecasts/forecast.routes.js";
import { ForecastService } from "./modules/forecasts/forecast.service.js";
import { MockForecastRepository } from "./modules/forecasts/mock-forecast.repository.js";
import { SqliteForecastRepository } from "./modules/forecasts/sqlite-forecast.repository.js";
import { createHealthRouter } from "./modules/health/health.routes.js";
import { InMemorySiteRepository } from "./modules/sites/in-memory-site.repository.js";
import type { SiteRepository } from "./modules/sites/site.repository.js";
import { createSiteRouter } from "./modules/sites/site.routes.js";
import { SiteService } from "./modules/sites/site.service.js";
import { SqliteSiteRepository } from "./modules/sites/sqlite-site.repository.js";

interface ForecastDataSource {
  readonly sites: SiteRepository;
  readonly forecasts: ForecastRepository;
  readonly close: () => void;
}

const openForecastData = (config: ApiConfig, now: () => Date): ForecastDataSource => {
  if (config.forecastDataMode === "mock") {
    return {
      sites: new InMemorySiteRepository(),
      forecasts: new MockForecastRepository({ now }),
      close: () => undefined,
    };
  }

  let connection: ReturnType<typeof openDatabase>;
  try {
    connection = openDatabase(config.databaseUrl, { readOnly: true });
  } catch (error) {
    throw new Error(
      "Unable to open the forecast database read-only. Check DATABASE_URL and that the file exists.",
      {
        cause: error,
      },
    );
  }

  try {
    // Preparing the adapters' statements verifies the columns and tables needed by the API.
    return {
      sites: new SqliteSiteRepository(connection.sqlite),
      forecasts: new SqliteForecastRepository(connection.sqlite),
      close: connection.close,
    };
  } catch (error) {
    connection.close();
    throw new Error(
      "The forecast database schema is unavailable. Apply the repository's database migrations.",
      {
        cause: error,
      },
    );
  }
};

export const createConfiguredApp = (config: ApiConfig, logger: Logger, now = () => new Date()) => {
  const data = openForecastData(config, now);

  try {
    const siteService = new SiteService(data.sites);
    const forecastService = new ForecastService(data.forecasts, siteService, now);
    const router = createRootRouter([
      createHealthRouter({ now, version: API_VERSION }),
      createSiteRouter({ siteService }),
      createForecastRouter({ forecastService }),
    ]);
    return {
      app: createApp({ corsOrigin: config.corsOrigin, logger, router }),
      close: data.close,
    };
  } catch (error) {
    data.close();
    throw error;
  }
};
