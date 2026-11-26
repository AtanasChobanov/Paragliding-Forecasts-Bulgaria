import { existsSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { basename, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { openDatabase, resolveDatabaseFilePath } from "../src/connection.js";

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

describe("read-only SQLite connection", () => {
  it("reads an existing database without creating missing paths or allowing writes", () => {
    const dataLocal = fileURLToPath(new URL("../../../data/local/", import.meta.url));
    mkdirSync(dataLocal, { recursive: true });
    const directory = mkdtempSync(join(dataLocal, "readonly-connection-test-"));
    const relativePath = `file:./data/local/${basename(directory)}`;
    const databaseUrl = `${relativePath}/forecast.db`;
    try {
      expect(() =>
        openDatabase(`${relativePath}/missing/forecast.db`, { readOnly: true }),
      ).toThrow();
      expect(existsSync(join(directory, "missing"))).toBe(false);

      const writer = openDatabase(databaseUrl);
      try {
        writer.sqlite.exec(
          "CREATE TABLE forecast (p100 REAL); INSERT INTO forecast VALUES (0.0157)",
        );
      } finally {
        writer.close();
      }

      const reader = openDatabase(databaseUrl, { readOnly: true });
      try {
        expect(reader.sqlite.prepare("SELECT p100 FROM forecast").get()).toEqual({ p100: 0.0157 });
        expect(() => {
          reader.sqlite.exec("DELETE FROM forecast");
        }).toThrow(/readonly/i);
      } finally {
        reader.close();
      }
      expect(() => reader.sqlite.prepare("SELECT 1")).toThrow();
    } finally {
      rmSync(directory, { force: true, recursive: true });
    }
  });
});
