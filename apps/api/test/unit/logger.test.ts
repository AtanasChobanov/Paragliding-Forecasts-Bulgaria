import { Writable } from "node:stream";

import { describe, expect, it } from "vitest";

import { parseConfig } from "../../src/config/env.js";
import { createLogger } from "../../src/observability/logger.js";

describe("structured logger", () => {
  it("redacts sensitive HTTP headers", () => {
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

    logger.info({
      req: {
        headers: {
          authorization: "Bearer secret-token",
          cookie: "session=secret-cookie",
        },
      },
      res: { headers: { "set-cookie": "session=secret-response-cookie" } },
    });

    const output = chunks.join("");
    expect(output).not.toContain("secret-token");
    expect(output).not.toContain("secret-cookie");
    expect(output).not.toContain("secret-response-cookie");
    expect(output.match(/\[Redacted\]/g)).toHaveLength(3);
  });
});
