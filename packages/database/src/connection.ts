import { mkdirSync } from "node:fs";
import { dirname, isAbsolute, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { drizzle } from "drizzle-orm/node-sqlite";
import { DatabaseSync } from "node:sqlite";

const repositoryRoot = fileURLToPath(new URL("../../../", import.meta.url));
const defaultDatabaseUrl = "file:./data/local/paragliding.db";

export interface DatabaseConnection {
  readonly databasePath: string;
  readonly db: ReturnType<typeof drizzle>;
  readonly sqlite: DatabaseSync;
  close(): void;
}

export const resolveDatabaseFilePath = (
  databaseUrl: string,
  rootDirectory = repositoryRoot,
): string => {
  if (!databaseUrl.startsWith("file:")) {
    throw new Error("DATABASE_URL must use the file: scheme.");
  }

  const rawPath = databaseUrl.slice("file:".length);
  if (rawPath.length === 0 || rawPath.includes("?") || rawPath.includes("#")) {
    throw new Error(
      "DATABASE_URL must identify a local file without query or fragment components.",
    );
  }

  const filePath = rawPath.replaceAll("/", sep);
  if (isAbsolute(filePath)) {
    throw new Error("DATABASE_URL must be relative to the repository root.");
  }

  const dataRoot = resolve(rootDirectory, "data");
  const databasePath = resolve(rootDirectory, filePath);
  const dataRelativePath = relative(dataRoot, databasePath);
  if (
    dataRelativePath.length === 0 ||
    dataRelativePath === ".." ||
    dataRelativePath.startsWith(`..${sep}`) ||
    isAbsolute(dataRelativePath)
  ) {
    throw new Error("DATABASE_URL must resolve below the repository data directory.");
  }

  return databasePath;
};

export const openDatabase = (
  databaseUrl = process.env.DATABASE_URL ?? defaultDatabaseUrl,
): DatabaseConnection => {
  const databasePath = resolveDatabaseFilePath(databaseUrl);
  mkdirSync(dirname(databasePath), { recursive: true });

  const sqlite = new DatabaseSync(databasePath);
  sqlite.exec("PRAGMA foreign_keys = ON");

  return {
    databasePath,
    db: drizzle({ client: sqlite }),
    sqlite,
    close: () => {
      sqlite.close();
    },
  };
};
