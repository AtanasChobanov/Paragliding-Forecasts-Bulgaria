import { Writable } from "node:stream";

import { Router } from "express";
import request from "supertest";
import { describe, expect, it } from "vitest";

import { createApp } from "../../src/app.js";
import { parseConfig } from "../../src/config/env.js";
import { createLogger } from "../../src/observability/logger.js";

describe("HTTP log redaction", () => {
  it("redacts credential headers from the real pino-http request and response record", async () => {
    const chunks: string[] = [];
    const destination = new Writable({
      write(chunk, _encoding, callback) {
        chunks.push(String(chunk));
        callback();
      },
    });
    const logger = createLogger(
      parseConfig({ NODE_ENV: "production", LOG_LEVEL: "info" }),
      destination,
    );
    const router = Router();

    router.get("/redaction-probe", (_request, response) => {
      response.setHeader("Set-Cookie", "session=response-secret; HttpOnly");
      response.status(200).json({ status: "ok" });
    });

    const app = createApp({
      corsOrigin: "http://localhost:5173",
      logger,
      router,
    });

    await request(app)
      .get("/redaction-probe")
      .set("Authorization", "Bearer authorization-secret")
      .set("Cookie", "session=request-cookie-secret")
      .expect(200);
    await new Promise<void>((resolve) => {
      setImmediate(resolve);
    });

    const output = chunks.join("");
    expect(output).not.toContain("authorization-secret");
    expect(output).not.toContain("request-cookie-secret");
    expect(output).not.toContain("response-secret");
    expect(output.match(/\[Redacted\]/g)).toHaveLength(3);
  });
});
