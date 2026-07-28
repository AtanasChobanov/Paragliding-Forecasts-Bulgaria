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
      { latitude: 42.60222, longitude: 23.28927 },
      { latitude: 42.71506, longitude: 24.13749 },
      { latitude: 42.68776, longitude: 24.74996 },
      { latitude: 43.27155, longitude: 27.29945 },
      { latitude: 43.27667, longitude: 26.92917 },
      { latitude: 43.42481, longitude: 23.30355 },
      { latitude: 43.56667, longitude: 27.83333 },
    ]);
    expect(body.sites.every((site) => Object.keys(site).length === 5)).toBe(true);
  });
});
