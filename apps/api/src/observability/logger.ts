import pino, { type DestinationStream, type Logger, type LoggerOptions } from "pino";

import type { ApiConfig } from "../config/env.js";

export const API_SERVICE_NAME = "paragliding-forecasts-api";
export const API_VERSION = "0.1.0";

const redactedPaths = [
  "req.headers.authorization",
  "req.headers.cookie",
  "res.headers['set-cookie']",
];

export const createBootstrapLogger = (): Logger =>
  pino({
    base: { service: API_SERVICE_NAME },
    level: "error",
    redact: { paths: redactedPaths, censor: "[Redacted]" },
  });

export const createLogger = (config: ApiConfig, destination?: DestinationStream): Logger => {
  const options: LoggerOptions = {
    base: {
      environment: config.nodeEnv,
      service: API_SERVICE_NAME,
      version: API_VERSION,
    },
    level: config.logLevel,
    redact: { paths: redactedPaths, censor: "[Redacted]" },
    ...(config.nodeEnv === "development"
      ? {
          transport: {
            target: "pino-pretty",
            options: {
              colorize: true,
              singleLine: true,
              translateTime: "SYS:standard",
            },
          },
        }
      : {}),
  };

  return destination === undefined ? pino(options) : pino(options, destination);
};
