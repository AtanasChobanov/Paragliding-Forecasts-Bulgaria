import { describe, expect, it } from "vitest";

import { sanitizeRequestId } from "../../src/observability/http-logger.js";

describe("request ID sanitization", () => {
  it("accepts a bounded safe correlation ID", () => {
    expect(sanitizeRequestId("client.request-1:abc")).toBe("client.request-1:abc");
  });

  it.each([
    undefined,
    "",
    "contains spaces",
    "contains/newline\n",
    "a".repeat(129),
    ["multiple", "values"],
  ])("rejects an unsafe request ID", (value) => {
    expect(sanitizeRequestId(value)).toBeUndefined();
  });
});
