import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { resolveDatabaseFilePath } from "../src/connection.js";

const repositoryRoot = resolve("database-connection-test-workspace");

describe("resolveDatabaseFilePath", () => {
  it("resolves a relative file URL below the repository data directory", () => {
    expect(resolveDatabaseFilePath("file:./data/local/test.db", repositoryRoot)).toBe(
      resolve(repositoryRoot, "data/local/test.db"),
    );
  });

  it.each([
    "https://example.test/paragliding.db",
    "file:",
    "file:./data/local/test.db?mode=ro",
    "file:./data/local/test.db#fragment",
    "file:../outside-data.db",
    "file:./data/../outside-data.db",
    "file:C:\\outside-data.db",
  ])("rejects an invalid database URL: %s", (databaseUrl) => {
    expect(() => resolveDatabaseFilePath(databaseUrl, repositoryRoot)).toThrow(/DATABASE_URL/);
  });
});
