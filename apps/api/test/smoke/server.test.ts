import { describe, expect, it } from "vitest";

import { startServer } from "../../src/server.js";
import { createTestApp } from "../support/create-test-app.js";

describe("API server startup", () => {
  it("serves health over a real socket and closes idempotently", async () => {
    const runningServer = await startServer({
      app: createTestApp(),
      host: "127.0.0.1",
      port: 0,
      gracePeriodMs: 500,
    });

    try {
      const response = await fetch(`http://127.0.0.1:${String(runningServer.address.port)}/health`);
      expect(response.status).toBe(200);
      await expect(response.json()).resolves.toMatchObject({ status: "ok" });
    } finally {
      const firstClose = runningServer.close();
      const secondClose = runningServer.close();
      expect(secondClose).toBe(firstClose);
      await firstClose;
    }

    expect(runningServer.server.listening).toBe(false);
  });
});
