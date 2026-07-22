import { describe, expect, it } from "vitest";

import { parseRuntimeConfig } from "../../src/config/runtime-config.js";

describe("web runtime configuration", () => {
  it.each([
    ["http://127.0.0.1:3000/", "http://127.0.0.1:3000"],
    ["https://forecast.example.test/api/", "https://forecast.example.test/api"],
  ])("accepts and normalizes the API base URL %s", (value, expected) => {
    expect(parseRuntimeConfig({ VITE_API_BASE_URL: value })).toEqual({ apiBaseUrl: expected });
  });

  it.each([
    ["a missing value", {}],
    ["a blank value", { VITE_API_BASE_URL: " " }],
    ["a relative URL", { VITE_API_BASE_URL: "/api" }],
    ["a non-HTTP URL", { VITE_API_BASE_URL: "file:///tmp/forecast" }],
  ])("rejects %s before the application starts", (_description, environment) => {
    expect(() => parseRuntimeConfig(environment)).toThrow(
      "VITE_API_BASE_URL must be an absolute HTTP(S) URL.",
    );
  });
});
