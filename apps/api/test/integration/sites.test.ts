import { sitesResponseSchema } from "@paragliding-forecasts/contracts";
import request from "supertest";
import { describe, expect, it } from "vitest";

import { createTestApp } from "../support/create-test-app.js";

describe("GET /api/v1/sites", () => {
  it("returns the contract-valid initial site catalog", async () => {
    const response = await request(createTestApp()).get("/api/v1/sites").expect(200);
    const body = sitesResponseSchema.parse(response.body);

    expect(body.sites).toHaveLength(7);
    expect(body.sites.map((site) => site.id)).toEqual([1, 2, 3, 4, 5, 6, 7]);
    expect(body.sites.map((site) => site.slug)).toEqual([
      "sofia-vitosha-kominite",
      "zlatitsa",
      "sopot",
      "nevsha",
      "shumen",
      "pastrina",
      "dobrich-region",
    ]);
    expect(body.sites.map((site) => site.name)).toEqual([
      "Sofia - Vitosha (Kominite)",
      "Zlatitsa",
      "Sopot",
      "Nevsha",
      "Shumen",
      "Pastrina",
      "Dobrich region",
    ]);
    expect(body.sites.map(({ latitude, longitude }) => ({ latitude, longitude }))).toEqual([
      { latitude: 42.6013, longitude: 23.2844 },
      { latitude: 42.7302, longitude: 24.0923 },
      { latitude: 42.68733, longitude: 24.749962 },
      { latitude: 43.2622, longitude: 27.2846 },
      { latitude: 43.2575, longitude: 26.9258 },
      { latitude: 43.4282, longitude: 23.3032 },
      { latitude: 43.56667, longitude: 27.83333 },
    ]);
    expect(body.sites.every((site) => Object.keys(site).length === 5)).toBe(true);
  });
});
