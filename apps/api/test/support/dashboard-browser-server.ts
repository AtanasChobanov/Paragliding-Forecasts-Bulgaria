import { seedForecastDetailEvidence } from "./forecast-detail-evidence.js";
import pino from "pino";

import { createConfiguredApp } from "../../src/bootstrap.js";
import { parseConfig } from "../../src/config/env.js";
import { startServer } from "../../src/server.js";
import { createForecastDatabase, fixtureNow, seedForecasts } from "./forecast-database.js";

const mode = process.env.FORECAST_DATA_MODE;
if (mode !== "mock" && mode !== "sqlite") {
  throw new Error("Specify the browser fixture forecast mode.");
}

const database = mode === "sqlite" ? createForecastDatabase() : undefined;
let closeApp: (() => void) | undefined;
const close = () => {
  try {
    closeApp?.();
  } finally {
    database?.close();
  }
};

try {
  if (database !== undefined) {
    seedForecasts(database.sqlite);
    seedForecastDetailEvidence(database.sqlite);
  }

  const config = parseConfig({ ...process.env, DATABASE_URL: database?.databaseUrl });
  const api = createConfiguredApp(config, pino({ level: "silent" }), fixtureNow);
  closeApp = api.close;
  const server = await startServer({ app: api.app, host: config.host, port: config.port });
  process.once("SIGTERM", () => {
    void server
      .close()
      .finally(close)
      .catch((error: unknown) => {
        process.stderr.write(`${String(error)}\n`);
        process.exitCode = 1;
      });
  });
} catch (error) {
  close();
  throw error;
}
