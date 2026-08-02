import { fileURLToPath } from "node:url";

import { describe, expect, it, vi } from "vitest";

import { isMigrationEntrypoint, loadRootEnvironmentIfNeeded } from "../src/migrate.js";

describe("migration command helpers", () => {
  it("loads the root environment only when no database URL is configured", () => {
    const loadEnvironmentFile = vi.fn();

    loadRootEnvironmentIfNeeded(undefined, undefined, true, loadEnvironmentFile);
    loadRootEnvironmentIfNeeded("file:./data/local/test.db", undefined, true, loadEnvironmentFile);
    loadRootEnvironmentIfNeeded(undefined, "file:./data/local/test.db", true, loadEnvironmentFile);
    loadRootEnvironmentIfNeeded(undefined, undefined, false, loadEnvironmentFile);

    expect(loadEnvironmentFile).toHaveBeenCalledTimes(1);
    expect(loadEnvironmentFile).toHaveBeenCalledWith(
      fileURLToPath(new URL("../../../.env", import.meta.url)),
    );
  });

  it("identifies the migration module entrypoint", () => {
    expect(isMigrationEntrypoint(undefined)).toBe(false);
    expect(
      isMigrationEntrypoint(fileURLToPath(new URL("../src/migrate.ts", import.meta.url))),
    ).toBe(true);
  });
});
