import { mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { basename, join } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { openDatabase, type DatabaseConnection } from "../src/connection.js";
import { runMigrations } from "../src/migrate.js";

const dataLocalDirectory = fileURLToPath(new URL("../../../data/local/", import.meta.url));

let connection: DatabaseConnection | undefined;
let databaseUrl: string | undefined;
let testDirectory: string | undefined;

const activeConnection = (): DatabaseConnection => {
  if (connection === undefined) {
    throw new Error("The migration test database is not available.");
  }

  return connection;
};

const expectSqlFailure = (statement: string): void => {
  expect(() => {
    activeConnection().sqlite.exec(statement);
  }).toThrow();
};

const insertReferenceRows = (): void => {
  activeConnection().sqlite.exec(`
    INSERT INTO flight_sources (id, code, name, base_url, is_active)
    VALUES (2, 'sky_nomad', 'SkyNomad', 'https://www.skynomad.example', 1);

    INSERT INTO source_site_mappings (
      id, source_id, site_id, key_type, key_value, status
    ) VALUES
      (100, 1, 1, 'source_takeoff_id', 'source-one-takeoff', 'provisional'),
      (200, 2, 2, 'source_takeoff_id', 'source-two-takeoff', 'provisional');

    INSERT INTO ingestion_runs (
      id, run_key, source_id, ingestion_method, status, source_url,
      permission_basis, permission_reference, model_training_allowed,
      operational_use_allowed, raw_manifest_path, raw_manifest_sha256,
      pipeline_version, started_at_utc, completed_at_utc, records_seen,
      records_accepted, records_rejected, records_quarantined, records_deduplicated
    ) VALUES
      (
        1000, '11111111-1111-4111-8111-111111111111', 1, 'manual_export', 'succeeded',
        'https://www.xcontest.org/world/en/flights/', 'written_permission', 'test permission',
        1, 0, 'data/raw/xccontest/test-run-one/manifest.json',
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        'test-pipeline', '2026-08-02T10:00:00Z', '2026-08-02T10:01:00Z', 1, 1, 0, 0, 0
      ),
      (
        2000, '22222222-2222-4222-8222-222222222222', 2, 'owner_export', 'succeeded',
        'https://www.skynomad.example/export', 'owner_export', 'test owner export',
        0, 0, 'data/raw/skynomad/test-run-two/manifest.json',
        'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
        'test-pipeline', '2026-08-02T10:00:00Z', '2026-08-02T10:01:00Z', 1, 1, 0, 0, 0
      );
  `);
};

const validFlightSql = (
  id: number,
  sourceFlightId: string,
  validationLevel = "metadata",
): string => `
  INSERT INTO flight_records (
    id, source_id, source_flight_id, source_flight_url, source_site_mapping_id,
    takeoff_at_utc, duration_seconds, scored_distance_km, route_type, track_url,
    validation_level, validation_notes, validated_at_utc,
    created_by_ingestion_run_id, last_validated_by_ingestion_run_id,
    created_at_utc, updated_at_utc
  ) VALUES (
    ${String(id)}, 1, '${sourceFlightId}', 'https://www.xcontest.org/world/en/flights/detail:test', 100,
    '2026-08-01T12:00:00Z', 3600, 150, 'free_flight',
    ${validationLevel === "track" ? "'https://www.xcontest.org/track.php?id=test'" : "NULL"},
    '${validationLevel}', 'validated test record', '2026-08-02T10:00:00Z',
    1000, 1000, '2026-08-02T10:00:00Z', '2026-08-02T10:00:00Z'
  );`;

beforeEach(() => {
  mkdirSync(dataLocalDirectory, { recursive: true });
  testDirectory = mkdtempSync(join(dataLocalDirectory, "t012-migration-test-"));
  databaseUrl = `file:./data/local/${basename(testDirectory)}/foundation.db`;
  runMigrations(databaseUrl);
  connection = openDatabase(databaseUrl);
});

afterEach(() => {
  connection?.close();
  connection = undefined;
  databaseUrl = undefined;

  if (testDirectory !== undefined) {
    rmSync(testDirectory, { force: true, maxRetries: 3, recursive: true, retryDelay: 20 });
    testDirectory = undefined;
  }
});

describe("flight foundation migrations", () => {
  it("migrates a fresh database, seeds the catalog, and is idempotent", () => {
    const sqlite = activeConnection().sqlite;

    expect(sqlite.prepare("PRAGMA foreign_keys").get()).toEqual({ foreign_keys: 1 });
    expect(sqlite.prepare("SELECT count(*) AS count FROM __drizzle_migrations").get()).toEqual({
      count: 4,
    });

    if (databaseUrl === undefined) {
      throw new Error("The migration test database URL is not available.");
    }

    runMigrations(databaseUrl);

    expect(sqlite.prepare("SELECT count(*) AS count FROM __drizzle_migrations").get()).toEqual({
      count: 4,
    });
    expect(
      sqlite
        .prepare(
          `SELECT id, slug, latitude_deg, longitude_deg, catchment_radius_km,
            country_code_iso2, time_zone, is_active
           FROM sites ORDER BY id`,
        )
        .all(),
    ).toEqual([
      {
        catchment_radius_km: 5,
        country_code_iso2: "BG",
        id: 1,
        is_active: 1,
        latitude_deg: 42.6013,
        longitude_deg: 23.2844,
        slug: "sofia-vitosha-kominite",
        time_zone: "Europe/Sofia",
      },
      {
        catchment_radius_km: 5,
        country_code_iso2: "BG",
        id: 2,
        is_active: 1,
        latitude_deg: 42.7302,
        longitude_deg: 24.0923,
        slug: "zlatitsa",
        time_zone: "Europe/Sofia",
      },
      {
        catchment_radius_km: 5,
        country_code_iso2: "BG",
        id: 3,
        is_active: 1,
        latitude_deg: 42.68733,
        longitude_deg: 24.749962,
        slug: "sopot",
        time_zone: "Europe/Sofia",
      },
      {
        catchment_radius_km: 5,
        country_code_iso2: "BG",
        id: 4,
        is_active: 1,
        latitude_deg: 43.2622,
        longitude_deg: 27.2846,
        slug: "nevsha",
        time_zone: "Europe/Sofia",
      },
      {
        catchment_radius_km: 5,
        country_code_iso2: "BG",
        id: 5,
        is_active: 1,
        latitude_deg: 43.2575,
        longitude_deg: 26.9258,
        slug: "shumen",
        time_zone: "Europe/Sofia",
      },
      {
        catchment_radius_km: 5,
        country_code_iso2: "BG",
        id: 6,
        is_active: 1,
        latitude_deg: 43.4282,
        longitude_deg: 23.3032,
        slug: "pastrina",
        time_zone: "Europe/Sofia",
      },
      {
        catchment_radius_km: 30,
        country_code_iso2: "BG",
        id: 7,
        is_active: 1,
        latitude_deg: 43.56667,
        longitude_deg: 27.83333,
        slug: "dobrich-region",
        time_zone: "Europe/Sofia",
      },
    ]);
    expect(sqlite.prepare("SELECT code, name, is_active FROM flight_sources").all()).toEqual([
      { code: "xccontest", is_active: 1, name: "XCContest" },
    ]);
  });

  it("creates strict tables and all required named indexes", () => {
    const sqlite = activeConnection().sqlite;

    expect(
      sqlite
        .prepare(
          `SELECT name, strict FROM pragma_table_list
           WHERE name IN (
             'flight_sources', 'sites', 'source_site_mappings', 'ingestion_runs', 'flight_records'
           )
           ORDER BY name`,
        )
        .all(),
    ).toEqual([
      { name: "flight_records", strict: 1 },
      { name: "flight_sources", strict: 1 },
      { name: "ingestion_runs", strict: 1 },
      { name: "sites", strict: 1 },
      { name: "source_site_mappings", strict: 1 },
    ]);
    expect(
      sqlite
        .prepare(
          `SELECT name FROM sqlite_master
           WHERE type = 'index' AND name IN (
             'flight_records_created_by_ingestion_run_index',
             'flight_records_mapping_takeoff_at_index',
             'flight_records_takeoff_distance_index',
             'ingestion_runs_source_started_at_index',
             'source_site_mappings_active_key_unique',
             'source_site_mappings_active_point_unique',
             'source_site_mappings_site_source_status_index'
           )
           ORDER BY name`,
        )
        .all(),
    ).toEqual([
      { name: "flight_records_created_by_ingestion_run_index" },
      { name: "flight_records_mapping_takeoff_at_index" },
      { name: "flight_records_takeoff_distance_index" },
      { name: "ingestion_runs_source_started_at_index" },
      { name: "source_site_mappings_active_key_unique" },
      { name: "source_site_mappings_active_point_unique" },
      { name: "source_site_mappings_site_source_status_index" },
    ]);
  });

  it("accepts browser UI as an explicit ingestion method", () => {
    activeConnection().sqlite.exec(`
      INSERT INTO ingestion_runs (
        id, run_key, source_id, ingestion_method, status, source_url, permission_basis,
        permission_reference, raw_manifest_path, raw_manifest_sha256, pipeline_version,
        started_at_utc, completed_at_utc
      ) VALUES (
        3000, '33333333-3333-4333-8333-333333333333', 1, 'browser_ui', 'succeeded',
        'https://www.xcontest.org/world/en/flights/', 'written_permission', 'test permission',
        'data/raw/xccontest/test-run/manifest.json',
        'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
        'test-pipeline', '2026-08-11T08:00:00Z', '2026-08-11T08:01:00Z'
      );
    `);
  });
  it("enforces source consistency, flight identity, and validation levels", () => {
    insertReferenceRows();
    const sqlite = activeConnection().sqlite;

    sqlite.exec(validFlightSql(1, "source-flight-1"));
    sqlite.exec(validFlightSql(2, "source-flight-2", "track"));
    expectSqlFailure(validFlightSql(3, "source-flight-1"));
    expectSqlFailure(`
      INSERT INTO flight_records (
        id, source_id, source_flight_id, source_flight_url, source_site_mapping_id,
        takeoff_at_utc, scored_distance_km, route_type, validation_level, validation_notes,
        validated_at_utc, created_by_ingestion_run_id, last_validated_by_ingestion_run_id,
        created_at_utc, updated_at_utc
      ) VALUES (
        4, 1, 'wrong-mapping-source', 'https://example.test/flight', 200,
        '2026-08-01T12:00:00Z', 150, 'free_flight', 'metadata', 'test',
        '2026-08-02T10:00:00Z', 1000, 1000, '2026-08-02T10:00:00Z', '2026-08-02T10:00:00Z'
      );
    `);
    expectSqlFailure(`
      INSERT INTO flight_records (
        id, source_id, source_flight_id, source_flight_url, source_site_mapping_id,
        takeoff_at_utc, scored_distance_km, route_type, validation_level, validation_notes,
        validated_at_utc, created_by_ingestion_run_id, last_validated_by_ingestion_run_id,
        created_at_utc, updated_at_utc
      ) VALUES (
        5, 1, 'wrong-created-run-source', 'https://example.test/flight', 100,
        '2026-08-01T12:00:00Z', 150, 'free_flight', 'metadata', 'test',
        '2026-08-02T10:00:00Z', 2000, 1000, '2026-08-02T10:00:00Z', '2026-08-02T10:00:00Z'
      );
    `);
    expectSqlFailure(`
      INSERT INTO flight_records (
        id, source_id, source_flight_id, source_flight_url, source_site_mapping_id,
        takeoff_at_utc, scored_distance_km, route_type, validation_level, validation_notes,
        validated_at_utc, created_by_ingestion_run_id, last_validated_by_ingestion_run_id,
        created_at_utc, updated_at_utc
      ) VALUES (
        6, 1, 'wrong-last-run-source', 'https://example.test/flight', 100,
        '2026-08-01T12:00:00Z', 150, 'free_flight', 'metadata', 'test',
        '2026-08-02T10:00:00Z', 1000, 2000, '2026-08-02T10:00:00Z', '2026-08-02T10:00:00Z'
      );
    `);
    expectSqlFailure(`
      INSERT INTO flight_records (
        id, source_id, source_flight_id, source_flight_url, source_site_mapping_id,
        takeoff_at_utc, scored_distance_km, route_type, validation_level, validation_notes,
        validated_at_utc, created_by_ingestion_run_id, last_validated_by_ingestion_run_id,
        created_at_utc, updated_at_utc
      ) VALUES (
        7, 1, 'unknown-validation-level', 'https://example.test/flight', 100,
        '2026-08-01T12:00:00Z', 150, 'free_flight', 'unverified', 'test',
        '2026-08-02T10:00:00Z', 1000, 1000, '2026-08-02T10:00:00Z', '2026-08-02T10:00:00Z'
      );
    `);
  });

  it("rejects invalid mapping, run, flight, and strict-type values", () => {
    insertReferenceRows();

    expectSqlFailure(`
      INSERT INTO source_site_mappings (id, source_id, site_id, key_type, key_value, status)
      VALUES (300, 1, 1, 'source_takeoff_id', NULL, 'provisional');
    `);
    expectSqlFailure(`
      INSERT INTO source_site_mappings (
        id, source_id, site_id, key_type, key_value, status, verification_reference, verified_at_utc
      ) VALUES (301, 1, 1, 'normalized_name', 'Sopot', 'approved', NULL, NULL);
    `);
    expectSqlFailure(`
      INSERT INTO source_site_mappings (
        id, source_id, site_id, key_type, point_latitude_deg, point_longitude_deg, status
      ) VALUES (302, 1, 1, 'source_point', 42.6, NULL, 'provisional');
    `);
    activeConnection().sqlite.exec(`
      INSERT INTO source_site_mappings (id, source_id, site_id, key_type, key_value, status)
      VALUES (303, 1, 1, 'source_site_token', 'shared-token', 'provisional');
    `);
    expectSqlFailure(`
      INSERT INTO source_site_mappings (id, source_id, site_id, key_type, key_value, status)
      VALUES (304, 1, 2, 'source_site_token', 'shared-token', 'approved');
    `);

    expectSqlFailure(`
      INSERT INTO ingestion_runs (
        id, run_key, source_id, ingestion_method, status, source_url, permission_basis,
        permission_reference, raw_manifest_path, raw_manifest_sha256, pipeline_version,
        started_at_utc, completed_at_utc
      ) VALUES (
        3000, '33333333-3333-4333-8333-333333333333', 1, 'manual_export', 'running',
        'https://example.test/source', 'written_permission', 'test',
        'data/raw/test/manifest.json',
        'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
        'test', '2026-08-02T10:00:00Z', '2026-08-02T10:01:00Z'
      );
    `);
    expectSqlFailure(`
      INSERT INTO ingestion_runs (
        id, run_key, source_id, ingestion_method, status, source_url, permission_basis,
        permission_reference, raw_manifest_path, raw_manifest_sha256, pipeline_version,
        started_at_utc, records_seen, records_accepted
      ) VALUES (
        3001, '33333333-3333-4333-8333-333333333334', 1, 'manual_export', 'running',
        'https://example.test/source', 'written_permission', 'test',
        'data/../manifest.json',
        'CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC',
        'test', '2026-08-02T10:00:00Z', 1, 2
      );
    `);

    expectSqlFailure(`
      INSERT INTO flight_records (
        id, source_id, source_flight_id, source_flight_url, source_site_mapping_id,
        takeoff_at_utc, duration_seconds, scored_distance_km, route_type, validation_level,
        validation_notes, validated_at_utc, created_by_ingestion_run_id,
        last_validated_by_ingestion_run_id, created_at_utc, updated_at_utc
      ) VALUES (
        8, 1, 'invalid-range-time', 'https://example.test/flight', 100,
        '2026-08-01T12:00Z', 0, 99, 'not-a-route', 'metadata', 'test',
        '2026-08-02T10:00:00Z', 1000, 1000, '2026-08-02T10:00:01Z', '2026-08-02T10:00:00Z'
      );
    `);
    expectSqlFailure(`
      INSERT INTO sites (
        id, slug, name, country_code_iso2, site_type, latitude_deg, longitude_deg, time_zone, is_active
      ) VALUES (99, 'strict-test', 'Strict test', 'BG', 'launch_area', 42, 23, 'Europe/Sofia', 'true');
    `);
  });
});
