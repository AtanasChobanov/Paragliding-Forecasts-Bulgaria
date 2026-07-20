import { describe, expect, it } from "vitest";

import { parseConfig } from "../../src/config/env.js";

describe("API configuration", () => {
  it("uses safe local defaults", () => {
    expect(parseConfig({})).toEqual({
      nodeEnv: "development",
      logLevel: "info",
      host: "127.0.0.1",
      port: 3_000,
      corsOrigin: "http://localhost:5173",
      forecastDataMode: "mock",
    });
  });

  it("parses supported explicit values", () => {
    expect(
      parseConfig({
        NODE_ENV: "production",
        LOG_LEVEL: "warn",
        API_HOST: "localhost",
        API_PORT: "3100",
        CORS_ORIGIN: "https://dashboard.example.test",
        FORECAST_DATA_MODE: "mock",
      }),
    ).toMatchObject({
      nodeEnv: "production",
      logLevel: "warn",
      host: "localhost",
      port: 3_100,
      corsOrigin: "https://dashboard.example.test",
      forecastDataMode: "mock",
    });
  });

  it.each([
    { environment: { API_PORT: "0" }, description: "port zero" },
    { environment: { API_PORT: "65536" }, description: "an out-of-range port" },
    { environment: { API_PORT: "not-a-port" }, description: "a non-numeric port" },
    {
      environment: { CORS_ORIGIN: "http://localhost:5173/" },
      description: "an origin with a trailing slash",
    },
    {
      environment: { CORS_ORIGIN: "file:///tmp/dashboard" },
      description: "a non-HTTP origin",
    },
    { environment: { FORECAST_DATA_MODE: "real" }, description: "an unsupported data mode" },
  ])("rejects $description", ({ environment }) => {
    expect(() => parseConfig(environment)).toThrow();
  });
});
