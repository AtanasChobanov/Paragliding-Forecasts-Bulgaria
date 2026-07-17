import type { Logger } from "pino";

import { createApp } from "./app.js";
import { loadRootEnvFile, parseConfig } from "./config/env.js";
import { createRootRouter } from "./http/router.js";
import { createHealthRouter } from "./modules/health/health.routes.js";
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
  const router = createRootRouter([healthRouter]);
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
