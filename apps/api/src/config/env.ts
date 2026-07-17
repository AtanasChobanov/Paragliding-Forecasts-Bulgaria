import { loadEnvFile } from "node:process";

import { z } from "zod";

const rootEnvUrl = new URL("../../../../.env", import.meta.url);

const corsOriginSchema = z.url().refine((value) => {
  const url = new URL(value);

  return (url.protocol === "http:" || url.protocol === "https:") && url.origin === value;
}, "Expected an exact HTTP(S) origin without a path, query, hash, or trailing slash.");

const environmentSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  LOG_LEVEL: z
    .enum(["fatal", "error", "warn", "info", "debug", "trace", "silent"])
    .default("debug"),
  API_HOST: z.string().trim().min(1).default("127.0.0.1"),
  API_PORT: z.coerce.number().int().min(1).max(65_535).default(3_000),
  CORS_ORIGIN: corsOriginSchema.default("http://localhost:5173"),
  FORECAST_DATA_MODE: z.literal("mock").default("mock"),
});

export interface ApiConfig {
  readonly nodeEnv: "development" | "test" | "production";
  readonly logLevel: "fatal" | "error" | "warn" | "info" | "debug" | "trace" | "silent";
  readonly host: string;
  readonly port: number;
  readonly corsOrigin: string;
  readonly forecastDataMode: "mock";
}

type Environment = Readonly<Record<string, string | undefined>>;

const isNodeError = (error: unknown): error is NodeJS.ErrnoException => error instanceof Error;

export const loadRootEnvFile = (): void => {
  try {
    loadEnvFile(rootEnvUrl);
  } catch (error) {
    if (isNodeError(error) && error.code === "ENOENT") {
      return;
    }

    throw error;
  }
};

export const parseConfig = (environment: Environment): ApiConfig => {
  const parsed = environmentSchema.parse(environment);

  return Object.freeze({
    nodeEnv: parsed.NODE_ENV,
    logLevel: parsed.LOG_LEVEL,
    host: parsed.API_HOST,
    port: parsed.API_PORT,
    corsOrigin: parsed.CORS_ORIGIN,
    forecastDataMode: parsed.FORECAST_DATA_MODE,
  });
};
