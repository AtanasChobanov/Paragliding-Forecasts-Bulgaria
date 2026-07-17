import { Router } from "express";
import request from "supertest";
import { describe, expect, it } from "vitest";

import { problemDetailsSchema } from "@paragliding-forecasts/contracts";

import { createTestApp, createThrowingRouter, FIXED_NOW } from "../support/create-test-app.js";

describe("API HTTP foundation", () => {
  it("returns a contract-valid health response", async () => {
    const response = await request(createTestApp()).get("/health").expect(200);

    expect(response.headers["content-type"]).toMatch(/^application\/json/);
    expect(response.headers["x-request-id"]).toMatch(/^[0-9a-f-]{36}$/);
    expect(response.body).toEqual({
      status: "ok",
      service: "paragliding-forecasts-api",
      version: "0.1.0",
      timestamp: FIXED_NOW.toISOString(),
    });
  });

  it("preserves a valid client request ID", async () => {
    const response = await request(createTestApp())
      .get("/health")
      .set("X-Request-Id", "client.request-1")
      .expect(200);

    expect(response.headers["x-request-id"]).toBe("client.request-1");
  });

  it("replaces an invalid client request ID", async () => {
    const response = await request(createTestApp())
      .get("/health")
      .set("X-Request-Id", "invalid request id")
      .expect(200);

    expect(response.headers["x-request-id"]).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("adds CORS headers only for the configured browser origin", async () => {
    const app = createTestApp();
    const allowed = await request(app)
      .get("/health")
      .set("Origin", "http://localhost:5173")
      .expect(200);
    const disallowed = await request(app)
      .get("/health")
      .set("Origin", "https://untrusted.example.test")
      .expect(200);

    expect(allowed.headers["access-control-allow-origin"]).toBe("http://localhost:5173");
    expect(allowed.headers["access-control-expose-headers"]).toBe("X-Request-Id");
    expect(disallowed.headers["access-control-allow-origin"]).toBeUndefined();
  });

  it("handles an allowed CORS preflight", async () => {
    const response = await request(createTestApp())
      .options("/health")
      .set("Origin", "http://localhost:5173")
      .set("Access-Control-Request-Method", "GET")
      .expect(204);

    expect(response.headers["access-control-allow-origin"]).toBe("http://localhost:5173");
  });

  it("returns RFC 9457 details for an unknown route", async () => {
    const response = await request(createTestApp()).get("/does-not-exist").expect(404);

    expect(response.headers["content-type"]).toMatch(/^application\/problem\+json/);
    expect(problemDetailsSchema.safeParse(response.body).success).toBe(true);
    expect(response.body).toMatchObject({
      status: 404,
      code: "ROUTE_NOT_FOUND",
      detail: "GET /does-not-exist does not exist.",
    });
  });

  it("does not expose an unexpected error", async () => {
    const response = await request(createTestApp({ additionalRouters: [createThrowingRouter()] }))
      .get("/boom")
      .expect(500);

    expect(response.headers["content-type"]).toMatch(/^application\/problem\+json/);
    expect(problemDetailsSchema.safeParse(response.body).success).toBe(true);
    expect(JSON.stringify(response.body)).not.toContain("Internal secret failure");
    expect(response.body).toMatchObject({
      status: 500,
      code: "INTERNAL_SERVER_ERROR",
      detail: "An unexpected error occurred.",
    });
  });

  it("turns an invalid response payload into a safe contract error", async () => {
    const response = await request(createTestApp({ version: "" }))
      .get("/health")
      .expect(500);

    expect(problemDetailsSchema.safeParse(response.body).success).toBe(true);
    expect(response.body).toMatchObject({
      status: 500,
      code: "RESPONSE_CONTRACT_ERROR",
      detail: "The server could not produce a valid response.",
    });
  });

  it("forwards rejected Express 5 handlers to the global error handler", async () => {
    const router = Router();
    router.get("/async-boom", async () => {
      await Promise.resolve();
      throw new Error("Async internal secret failure");
    });

    const response = await request(createTestApp({ additionalRouters: [router] }))
      .get("/async-boom")
      .expect(500);
    const problem = problemDetailsSchema.parse(response.body);

    expect(problem.code).toBe("INTERNAL_SERVER_ERROR");
    expect(JSON.stringify(response.body)).not.toContain("Async internal secret failure");
  });
});
