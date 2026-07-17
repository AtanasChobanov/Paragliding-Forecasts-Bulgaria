import type { Logger } from "pino";

import { createApp } from "./app.js";
import { loadRootEnvFile, parseConfig } from "./config/env.js";
import { createRootRouter } from "./http/router.js";
import { createForecastRouter } from "./modules/forecasts/forecast.routes.js";
import { ForecastService } from "./modules/forecasts/forecast.service.js";
import { MockForecastRepository } from "./modules/forecasts/mock-forecast.repository.js";
import { createHealthRouter } from "./modules/health/health.routes.js";
import { InMemorySiteRepository } from "./modules/sites/in-memory-site.repository.js";
import { createSiteRouter } from "./modules/sites/site.routes.js";
import { SiteService } from "./modules/sites/site.service.js";
import { API_VERSION, createBootstrapLogger, createLogger } from "./observability/logger.js";
import { startServer } from "./server.js";

let activeLogger: Logger = createBootstrapLogger();

process.on("uncaughtExceptionMonitor", (error, origin) => {
  activeLogger.fatal({ err: error, origin }, "Uncaught exception; the process will terminate.");
});

const run = async (): Promise<void> => {
  loadRootEnvFile();
  const config = parseConfig(process.env);
  const logger = createLogger(config);
  activeLogger = logger;

  const healthRouter = createHealthRouter({
    now: () => new Date(),
    version: API_VERSION,
  });
  const siteRepository = new InMemorySiteRepository();
  const siteService = new SiteService(siteRepository);
  const siteRouter = createSiteRouter({ siteService });
  const forecastRepository = new MockForecastRepository({ now: () => new Date() });
  const forecastService = new ForecastService(forecastRepository, siteService);
  const forecastRouter = createForecastRouter({ forecastService });
  const router = createRootRouter([healthRouter, siteRouter, forecastRouter]);
  const app = createApp({
    corsOrigin: config.corsOrigin,
    logger,
    router,
  });
  const runningServer = await startServer({
    app,
    host: config.host,
    port: config.port,
  });

  logger.info(
    { host: runningServer.address.address, port: runningServer.address.port },
    "API server started.",
  );

  let shutdownRequested = false;
  const shutdown = async (signal: NodeJS.Signals): Promise<void> => {
    if (shutdownRequested) {
      return;
    }

    shutdownRequested = true;
    logger.info({ signal }, "API server shutdown started.");

    try {
      await runningServer.close();
      logger.info({ signal }, "API server shutdown completed.");
      process.exitCode = 0;
    } catch (error) {
      logger.error({ err: error, signal }, "API server shutdown failed.");
      process.exitCode = 1;
    }
  };

  process.once("SIGINT", () => {
    void shutdown("SIGINT");
  });
  process.once("SIGTERM", () => {
    void shutdown("SIGTERM");
  });
};

void run().catch((error: unknown) => {
  activeLogger.fatal({ err: error }, "API server startup failed.");
  process.exitCode = 1;
});
