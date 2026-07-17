import { sitesResponseSchema } from "@paragliding-forecasts/contracts";
import request from "supertest";
import { describe, expect, it } from "vitest";

import { createTestApp } from "../support/create-test-app.js";

describe("GET /api/v1/sites", () => {
  it("returns the contract-valid initial site catalog", async () => {
    const response = await request(createTestApp()).get("/api/v1/sites").expect(200);
    const body = sitesResponseSchema.parse(response.body);

    expect(body.sites).toHaveLength(7);
    expect(body.sites.map((site) => site.id)).toEqual([
      "sofia-vitosha-kominite",
      "zlatitsa",
      "sopot",
      "nevsha",
      "shumen",
      "pastrona",
      "dobrich-region",
    ]);
    expect(body.sites.every((site) => Object.keys(site).length === 2)).toBe(true);
  });
});
