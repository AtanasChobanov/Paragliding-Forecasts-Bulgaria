import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { loadEnvFile } from "node:process";
import { fileURLToPath } from "node:url";

import { migrate } from "drizzle-orm/node-sqlite/migrator";

import { openDatabase } from "./connection.js";

const rootEnvPath = fileURLToPath(new URL("../../../.env", import.meta.url));
const migrationsFolder = fileURLToPath(new URL("../drizzle", import.meta.url));

export const loadRootEnvironmentIfNeeded = (
  databaseUrl: string | undefined,
  environmentDatabaseUrl = process.env.DATABASE_URL,
  rootEnvironmentFileExists = existsSync(rootEnvPath),
  loadEnvironmentFile: (path: string) => void = loadEnvFile,
): void => {
  if (
    databaseUrl === undefined &&
    environmentDatabaseUrl === undefined &&
    rootEnvironmentFileExists
  ) {
    loadEnvironmentFile(rootEnvPath);
  }
};

export const runMigrations = (databaseUrl?: string): void => {
  loadRootEnvironmentIfNeeded(databaseUrl);

  const connection = openDatabase(databaseUrl);

  try {
    const hasObsoleteProductTiming = connection.sqlite
      .prepare("PRAGMA table_info(weather_product_runs)")
      .all()
      .some((column) => column.name === "available_at_utc");
    if (!hasObsoleteProductTiming) {
      migrate(connection.db, { migrationsFolder });
      return;
    }

    if (connection.sqlite.prepare("PRAGMA foreign_keys").get()?.foreign_keys !== 1) {
      throw new Error("Weather schema migration requires enabled foreign-key checks.");
    }
    if (connection.sqlite.prepare("PRAGMA foreign_key_check").get() !== undefined) {
      throw new Error("Weather schema migration requires an existing valid foreign-key graph.");
    }

    // SQLite's documented table-rebuild sequence requires this outside the
    // transaction that Drizzle opens. The migration checks the rebuilt graph
    // before that transaction commits; the connection always restores FK mode.
    connection.sqlite.exec("PRAGMA foreign_keys = OFF");
    try {
      migrate(connection.db, { migrationsFolder });
    } finally {
      connection.sqlite.exec("PRAGMA foreign_keys = ON");
    }
    if (connection.sqlite.prepare("PRAGMA foreign_keys").get()?.foreign_keys !== 1) {
      throw new Error("Weather schema migration did not restore foreign-key enforcement.");
    }
    if (connection.sqlite.prepare("PRAGMA foreign_key_check").get() !== undefined) {
      throw new Error("Weather schema migration broke foreign-key relationships.");
    }
  } finally {
    connection.close();
  }
};

export const isMigrationEntrypoint = (scriptPath = process.argv[1]): boolean =>
  scriptPath !== undefined && resolve(scriptPath) === fileURLToPath(import.meta.url);

/* v8 ignore next -- executed by the npm script; the exported predicate is unit-tested. */
if (isMigrationEntrypoint()) {
  runMigrations();
}
