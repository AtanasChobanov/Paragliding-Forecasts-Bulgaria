import { cpSync, mkdirSync, mkdtempSync, readdirSync, rmSync } from "node:fs";
import { basename, join } from "node:path";
import { fileURLToPath } from "node:url";

import { migrate } from "drizzle-orm/node-sqlite/migrator";
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

    INSERT INTO flight_ingestion_runs (
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

const insertWeatherGraph = (targetConnection = activeConnection()): void => {
  targetConnection.sqlite.exec(`
    INSERT INTO weather_sources (
      id, code, provider_name, dataset_name, source_kind, base_url, is_active
    ) VALUES (
      10, 'noaa_gfs', 'NOAA', 'Global Forecast System', 'forecast',
      'https://nomads.ncep.noaa.gov/', 1
    );

    INSERT INTO weather_ingestion_runs (
      id, run_key, source_id, ingestion_method, request_purpose, status, source_url,
      permission_basis, permission_reference, model_training_allowed,
      operational_use_allowed, raw_manifest_path, raw_manifest_sha256,
      pipeline_version, started_at_utc, completed_at_utc, samples_seen, samples_accepted
    ) VALUES (
      10, 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 10, 'public_object_archive',
      'historical_forecast', 'succeeded', 'https://noaa.example/gfs-cycle',
      'us_government_work', 'https://www.noaa.gov/disclaimer', 1, 1,
      'data/raw/weather/noaa-gfs/test/manifest.json',
      'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'gfs-collector/1|gfs-decoder/1|weather-validation/1|weather-persistence/1',
      '2026-08-20T00:00:00Z', '2026-08-20T00:05:00Z', 1, 1
    );

    INSERT INTO weather_product_runs (
      id, source_id, source_product_key, reference_at_utc, available_at_utc,
      valid_from_utc, valid_to_utc, created_by_ingestion_run_id,
      last_validated_by_ingestion_run_id
    ) VALUES (
      10, 10, 'gfs.20260820/00/atmos', '2026-08-20T00:00:00Z',
      '2026-08-20T03:30:00Z', '2026-08-20T00:00:00Z', '2026-08-20T06:00:00Z',
      10, 10
    );

    INSERT INTO weather_grids (
      id, source_id, grid_key, grid_type, latitude_step_deg, longitude_step_deg,
      native_row_count, native_column_count, definition_sha256, is_active
    ) VALUES (
      10, 10, 'gfs_0p25_global', 'regular_latlon', 0.25, 0.25, 721, 1440,
      'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', 1
    );

    INSERT INTO weather_grid_points (
      id, grid_id, latitude_deg, longitude_deg, model_elevation_msl_m,
      first_seen_ingestion_run_id
    ) VALUES (10, 10, 42.5, 23.25, 830, 10);

    INSERT INTO weather_sampling_footprints (
      id, site_id, grid_id, purpose, sampling_method, sampling_method_version,
      radius_km, footprint_version, definition_sha256
    ) VALUES
      (
        10, 1, 10, 'point', 'bilinear', 'bilinear-v1', NULL, 1,
        'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc'
      ),
      (
        11, 1, 10, 'neighbourhood', 'radius', 'radius-v1', 50, 1,
        'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd'
      );

    INSERT INTO weather_sampling_footprint_nodes (
      footprint_id, grid_point_id, distance_km, interpolation_weight
    ) VALUES (10, 10, 12.5, 1), (11, 10, 12.5, NULL);

    INSERT INTO weather_samples (
      id, product_run_id, point_footprint_id, valid_at_utc, valid_local_date,
      lead_hours, coverage_status, air_temperature_2m_k, wind_speed_10m_m_s,
      wind_direction_10m_degrees_from_north, created_by_ingestion_run_id,
      last_validated_by_ingestion_run_id
    ) VALUES (
      10, 10, 10, '2026-08-20T06:00:00Z', '2026-08-20', 6, 'complete',
      293.15, 4.2, 270, 10, 10
    );

    INSERT INTO weather_profile_levels (
      id, weather_sample_id, pressure_pa, geopotential_height_msl_m,
      level_height_agl_m, air_temperature_k, wind_speed_m_s,
      wind_direction_degrees_from_north
    ) VALUES (10, 10, 85000, 1500, 700, 285.15, 7, 280);

    INSERT INTO weather_convection_measurements (
      id, weather_sample_id, parcel_method, calculation_method,
      cape_j_per_kg, cin_magnitude_j_per_kg
    ) VALUES (10, 10, 'provider_unspecified', 'provider', NULL, NULL);

    INSERT INTO weather_interval_measurements (
      id, weather_sample_id, field_code, component, interval_start_utc,
      interval_end_utc, statistic_type, canonical_value,
      source_step_start_hours, source_step_end_hours
    ) VALUES (
      10, 10, 'precipitation_amount_mm', 'total', '2026-08-20T03:00:00Z',
      '2026-08-20T06:00:00Z', 'accumulation', 0, 3, 6
    );

    INSERT INTO weather_feature_snapshots (
      id, weather_sample_id, neighbourhood_footprint_id, feature_contract_version,
      input_fingerprint_sha256, created_by_ingestion_run_id
    ) VALUES (
      10, 10, 11, 'weather-features-v1',
      'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee', 10
    );

    INSERT INTO weather_field_provenance (
      weather_sample_id, field_code, quality_state, source_reference_at_utc,
      native_field_name, native_unit, native_value, normalization_method,
      normalization_version, raw_artifact_key, native_message_reference
    ) VALUES (
      10, 'air_temperature_2m_k', 'real', '2026-08-20T00:00:00Z',
      'TMP:2 m above ground', 'K', 293.15, 'identity', '1',
      'data/raw/weather/noaa-gfs/test/gfs.t00z.pgrb2.0p25.f006', 'message-1'
    );

    INSERT INTO weather_field_provenance (
      convection_measurement_id, field_code, quality_state
    ) VALUES
      (10, 'cape_j_per_kg', 'missing'),
      (10, 'cin_magnitude_j_per_kg', 'missing');

    INSERT INTO weather_field_provenance (
      interval_measurement_id, field_code, quality_state, source_reference_at_utc,
      native_field_name, native_unit, native_value, normalization_method,
      normalization_version
    ) VALUES (
      10, 'precipitation_amount_mm', 'real', '2026-08-20T00:00:00Z',
      'APCP:surface:3-6 hour acc', 'kg m-2', 0, 'kg_m2_to_mm', '1'
    );

    INSERT INTO weather_field_provenance (
      profile_level_id, field_code, quality_state, native_field_name,
      native_unit, native_value, normalization_method, normalization_version
    ) VALUES (
      10, 'air_temperature_k', 'real', 'TMP:850 mb', 'K', 285.15, 'identity', '1'
    );

    INSERT INTO weather_field_provenance (
      feature_snapshot_id, field_code, quality_state, derivation_method,
      derivation_version
    ) VALUES (
      10, 'derived_boundary_layer_height_agl_m', 'derived',
      'profile_threshold', '1'
    );
  `);
};

describe("database foundation migrations", () => {
  it("migrates a fresh database, seeds the catalog, and is idempotent", () => {
    const sqlite = activeConnection().sqlite;

    expect(sqlite.prepare("PRAGMA foreign_keys").get()).toEqual({ foreign_keys: 1 });
    expect(sqlite.prepare("SELECT count(*) AS count FROM __drizzle_migrations").get()).toEqual({
      count: 9,
    });

    if (databaseUrl === undefined) {
      throw new Error("The migration test database URL is not available.");
    }

    runMigrations(databaseUrl);

    expect(sqlite.prepare("SELECT count(*) AS count FROM __drizzle_migrations").get()).toEqual({
      count: 9,
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
    expect(
      sqlite
        .prepare(
          `SELECT code, provider_name, dataset_name, source_kind, base_url, is_active
           FROM weather_sources ORDER BY code`,
        )
        .all(),
    ).toEqual([
      {
        base_url: "https://cds.climate.copernicus.eu",
        code: "copernicus_era5",
        dataset_name: "ERA5",
        is_active: 1,
        provider_name: "Copernicus Climate Change Service (ECMWF)",
        source_kind: "reanalysis",
      },
      {
        base_url: "https://noaa-gfs-bdp-pds.s3.amazonaws.com",
        code: "noaa_gfs_0p25_aws_grib2",
        dataset_name: "Global Forecast System 0.25° GRIB2",
        is_active: 1,
        provider_name: "NOAA",
        source_kind: "forecast",
      },
    ]);
  });

  it("creates strict tables and all required named indexes", () => {
    const sqlite = activeConnection().sqlite;

    expect(
      sqlite
        .prepare(
          `SELECT name, strict FROM pragma_table_list
           WHERE name IN (
             'flight_sources', 'sites', 'source_site_mappings', 'flight_ingestion_runs', 'flight_records'
           )
           ORDER BY name`,
        )
        .all(),
    ).toEqual([
      { name: "flight_ingestion_runs", strict: 1 },
      { name: "flight_records", strict: 1 },
      { name: "flight_sources", strict: 1 },
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
      INSERT INTO flight_ingestion_runs (
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
      INSERT INTO flight_ingestion_runs (
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
      INSERT INTO flight_ingestion_runs (
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

  it("creates all accepted weather tables as STRICT tables", () => {
    const rows = activeConnection()
      .sqlite.prepare(
        `SELECT name, strict FROM pragma_table_list
         WHERE name LIKE 'weather_%'
         ORDER BY name`,
      )
      .all();

    expect(rows).toHaveLength(14);
    expect(rows.every((row) => (row as { strict: number }).strict === 1)).toBe(true);
    expect(rows.map((row) => (row as { name: string }).name)).toEqual([
      "weather_convection_measurements",
      "weather_feature_snapshots",
      "weather_field_provenance",
      "weather_grid_points",
      "weather_grids",
      "weather_ingestion_runs",
      "weather_interval_measurements",
      "weather_product_runs",
      "weather_profile_levels",
      "weather_samples",
      "weather_sampling_footprint_nodes",
      "weather_sampling_footprints",
      "weather_site_sampling_configs",
      "weather_sources",
    ]);
  });

  it("seeds one reviewed sampling coordinate and Copernicus elevation per site", () => {
    const rows = activeConnection()
      .sqlite.prepare(
        `SELECT site_id, latitude_deg, longitude_deg, coordinate_reference,
                reference_elevation_msl_m, elevation_reference
         FROM weather_site_sampling_configs
         ORDER BY site_id`,
      )
      .all();

    expect(rows).toEqual([
      {
        site_id: 1,
        latitude_deg: 42.6013,
        longitude_deg: 23.2844,
        coordinate_reference: "canonical_site_coordinate_v1",
        reference_elevation_msl_m: 1793.929,
        elevation_reference: "copernicus_dem_glo30_egm2008_orthometric_bilinear_v1",
      },
      {
        site_id: 2,
        latitude_deg: 42.7302,
        longitude_deg: 24.0923,
        coordinate_reference: "canonical_site_coordinate_v1",
        reference_elevation_msl_m: 1129.007,
        elevation_reference: "copernicus_dem_glo30_egm2008_orthometric_bilinear_v1",
      },
      {
        site_id: 3,
        latitude_deg: 42.68733,
        longitude_deg: 24.749962,
        coordinate_reference: "canonical_site_coordinate_v1",
        reference_elevation_msl_m: 1445.337,
        elevation_reference: "copernicus_dem_glo30_egm2008_orthometric_bilinear_v1",
      },
      {
        site_id: 4,
        latitude_deg: 43.2622,
        longitude_deg: 27.2846,
        coordinate_reference: "canonical_site_coordinate_v1",
        reference_elevation_msl_m: 307.87,
        elevation_reference: "copernicus_dem_glo30_egm2008_orthometric_bilinear_v1",
      },
      {
        site_id: 5,
        latitude_deg: 43.2575,
        longitude_deg: 26.9258,
        coordinate_reference: "canonical_site_coordinate_v1",
        reference_elevation_msl_m: 447.1,
        elevation_reference: "copernicus_dem_glo30_egm2008_orthometric_bilinear_v1",
      },
      {
        site_id: 6,
        latitude_deg: 43.4282,
        longitude_deg: 23.3032,
        coordinate_reference: "canonical_site_coordinate_v1",
        reference_elevation_msl_m: 522.765,
        elevation_reference: "copernicus_dem_glo30_egm2008_orthometric_bilinear_v1",
      },
      {
        site_id: 7,
        latitude_deg: 43.746321,
        longitude_deg: 28.074025,
        coordinate_reference: "kardam_accepted_flight_centroid_v1",
        reference_elevation_msl_m: 190.402,
        elevation_reference: "copernicus_dem_glo30_egm2008_orthometric_bilinear_v1",
      },
    ]);
  });

  it("accepts a normalized weather graph and explicit per-field missingness", () => {
    insertWeatherGraph();

    expect(
      activeConnection()
        .sqlite.prepare("SELECT count(*) AS count FROM weather_field_provenance")
        .get(),
    ).toEqual({ count: 6 });
    expect(
      activeConnection()
        .sqlite.prepare(
          `SELECT cape_j_per_kg, cin_magnitude_j_per_kg
           FROM weather_convection_measurements WHERE id = 10`,
        )
        .get(),
    ).toEqual({ cape_j_per_kg: null, cin_magnitude_j_per_kg: null });
  });

  it("rejects broken source, interval, footprint, identity, and provenance semantics", () => {
    insertWeatherGraph();

    activeConnection().sqlite.exec(`
      INSERT INTO weather_sources (
        id, code, provider_name, dataset_name, source_kind, base_url
      ) VALUES (11, 'cds_era5', 'ECMWF', 'ERA5', 'reanalysis', 'https://cds.climate.copernicus.eu/');

      INSERT INTO weather_ingestion_runs (
        id, run_key, source_id, ingestion_method, request_purpose, status,
        source_url, permission_basis, permission_reference, raw_manifest_path,
        raw_manifest_sha256, pipeline_version, started_at_utc, completed_at_utc
      ) VALUES (
        11, 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 11, 'official_api',
        'reanalysis_backfill', 'succeeded', 'https://cds.example/request',
        'copernicus_licence', 'https://cds.example/licence',
        'data/raw/weather/era5/test/manifest.json',
        'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff',
        'era5-collector/1|era5-decoder/1|weather-persistence/1',
        '2026-08-20T00:00:00Z', '2026-08-20T01:00:00Z'
      );
    `);

    expectSqlFailure(`
      INSERT INTO weather_product_runs (
        id, source_id, source_product_key, valid_from_utc, valid_to_utc,
        created_by_ingestion_run_id, last_validated_by_ingestion_run_id
      ) VALUES (
        99, 10, 'wrong-source-run', '2026-08-20T00:00:00Z',
        '2026-08-20T01:00:00Z', 11, 10
      );
    `);
    expectSqlFailure(`
      INSERT INTO weather_grids (
        id, source_id, grid_key, grid_type, latitude_step_deg, longitude_step_deg,
        native_row_count, native_column_count, definition_sha256, is_active
      ) VALUES (
        99, 10, 'gfs_0p25_global', 'regular_latlon', 0.25, 0.25, 721, 1440,
        '9999999999999999999999999999999999999999999999999999999999999999', 1
      );
    `);
    expectSqlFailure(`
      INSERT INTO weather_sampling_footprints (
        id, site_id, grid_id, purpose, sampling_method, sampling_method_version,
        radius_km, footprint_version, definition_sha256
      ) VALUES (
        99, 1, 10, 'point', 'radius', 'bad-v1', 25, 2,
        '9999999999999999999999999999999999999999999999999999999999999999'
      );
    `);
    expectSqlFailure(`
      INSERT INTO weather_sampling_footprints (
        id, site_id, grid_id, purpose, sampling_method, sampling_method_version,
        radius_km, footprint_version, definition_sha256
      ) VALUES (
        98, 1, 10, 'neighbourhood', 'radius', 'bad-v2', NULL, 2,
        '9898989898989898989898989898989898989898989898989898989898989898'
      );
    `);
    expectSqlFailure(`
      INSERT INTO weather_sampling_footprint_nodes (
        footprint_id, grid_point_id, distance_km, interpolation_weight
      ) VALUES (10, 10, 12.5, 1.1);
    `);
    expectSqlFailure(`
      UPDATE weather_samples
      SET provider_boundary_layer_height_agl_m = -1,
          provider_boundary_layer_method = 'provider'
      WHERE id = 10;
    `);
    expectSqlFailure(`
      UPDATE weather_samples
      SET provider_boundary_layer_height_agl_m = 100,
          provider_boundary_layer_method = NULL
      WHERE id = 10;
    `);
    expectSqlFailure(`
      INSERT INTO weather_convection_measurements (
        weather_sample_id, parcel_method, calculation_method
      ) VALUES (10, 'provider_unspecified', 'provider');
    `);
    expectSqlFailure(`
      INSERT INTO weather_interval_measurements (
        weather_sample_id, field_code, component, interval_start_utc,
        interval_end_utc, statistic_type, canonical_value
      ) VALUES (
        10, 'shortwave_radiation_w_m2', 'not_applicable',
        '2026-08-20T03:00:00Z', '2026-08-20T06:00:00Z', 'instantaneous', -1
      );
    `);
    expectSqlFailure(`
      INSERT INTO weather_feature_snapshots (
        id, weather_sample_id, neighbourhood_footprint_id,
        feature_contract_version, input_fingerprint_sha256,
        temperature_lapse_rate_k_per_km, created_by_ingestion_run_id
      ) VALUES (
        99, 10, 11, 'invalid-lapse-v1',
        '9999999999999999999999999999999999999999999999999999999999999999',
        -6.5, 10
      );
    `);
    expectSqlFailure(`
      INSERT INTO weather_field_provenance (
        weather_sample_id, interval_measurement_id, field_code, quality_state
      ) VALUES (10, 10, 'invalid_owner', 'real');
    `);
    expectSqlFailure(`
      INSERT INTO weather_field_provenance (
        weather_sample_id, field_code, quality_state
      ) VALUES (10, 'air_temperature_2m_k', 'real');
    `);
    expectSqlFailure(`
      INSERT INTO weather_field_provenance (
        weather_sample_id, field_code, quality_state, native_value
      ) VALUES (10, 'missing_with_value', 'missing', 0);
    `);
  });
});

const migrationsDirectory = fileURLToPath(new URL("../drizzle/", import.meta.url));
const weatherMigrationDirectory = "20260820160216_create_weather_foundation";
const pblAglMigrationDirectory = "20260824183235_add_provider_pbl_agl";
const copernicusElevationMigrationDirectory = "20260824184712_set_copernicus_site_elevations";

let upgradeConnection: DatabaseConnection | undefined;
let upgradeTestDirectory: string | undefined;

afterEach(() => {
  upgradeConnection?.close();
  upgradeConnection = undefined;

  if (upgradeTestDirectory !== undefined) {
    rmSync(upgradeTestDirectory, { force: true, maxRetries: 3, recursive: true, retryDelay: 20 });
    upgradeTestDirectory = undefined;
  }
});

describe("weather foundation upgrade", () => {
  it("renames the populated flight ingestion table without losing rows or foreign keys", () => {
    mkdirSync(dataLocalDirectory, { recursive: true });
    upgradeTestDirectory = mkdtempSync(join(dataLocalDirectory, "t018-upgrade-test-"));
    const oldMigrationsDirectory = join(upgradeTestDirectory, "old-migrations");
    mkdirSync(oldMigrationsDirectory);

    for (const entry of readdirSync(migrationsDirectory, { withFileTypes: true })) {
      if (entry.isDirectory() && entry.name < weatherMigrationDirectory) {
        cpSync(join(migrationsDirectory, entry.name), join(oldMigrationsDirectory, entry.name), {
          recursive: true,
        });
      }
    }

    const databaseUrl = `file:./data/local/${basename(upgradeTestDirectory)}/upgrade.db`;
    upgradeConnection = openDatabase(databaseUrl);
    migrate(upgradeConnection.db, { migrationsFolder: oldMigrationsDirectory });
    upgradeConnection.sqlite.exec(`
      INSERT INTO source_site_mappings (
        id, source_id, site_id, key_type, key_value, status
      ) VALUES (500, 1, 1, 'source_takeoff_id', 'upgrade-takeoff', 'provisional');

      INSERT INTO ingestion_runs (
        id, run_key, source_id, ingestion_method, status, source_url,
        permission_basis, permission_reference, model_training_allowed,
        operational_use_allowed, raw_manifest_path, raw_manifest_sha256,
        pipeline_version, started_at_utc, completed_at_utc,
        records_seen, records_accepted
      ) VALUES (
        500, '55555555-5555-4555-8555-555555555555', 1, 'manual_export', 'succeeded',
        'https://www.xcontest.org/world/en/flights/', 'written_permission',
        'upgrade test permission', 1, 0,
        'data/raw/xccontest/upgrade-test/manifest.json',
        '5555555555555555555555555555555555555555555555555555555555555555',
        'xccontest-collector/2|xccontest-parser/2|xccontest-validation/2|xccontest-persistence/1',
        '2026-08-20T10:00:00Z', '2026-08-20T10:01:00Z', 1, 1
      );

      INSERT INTO flight_records (
        id, source_id, source_flight_id, source_flight_url, source_site_mapping_id,
        takeoff_at_utc, scored_distance_km, route_type, validation_level,
        validation_notes, validated_at_utc, created_by_ingestion_run_id,
        last_validated_by_ingestion_run_id, created_at_utc, updated_at_utc
      ) VALUES (
        500, 1, 'upgrade-flight', 'https://example.test/upgrade-flight', 500,
        '2026-08-19T10:00:00Z', 150, 'free_flight', 'metadata', 'upgrade test',
        '2026-08-20T10:00:00Z', 500, 500,
        '2026-08-20T10:00:00Z', '2026-08-20T10:00:00Z'
      );
    `);
    upgradeConnection.close();
    upgradeConnection = undefined;

    runMigrations(databaseUrl);
    upgradeConnection = openDatabase(databaseUrl);

    expect(
      upgradeConnection.sqlite
        .prepare("SELECT run_key FROM flight_ingestion_runs WHERE id = 500")
        .get(),
    ).toEqual({ run_key: "55555555-5555-4555-8555-555555555555" });
    expect(
      upgradeConnection.sqlite
        .prepare(
          `SELECT created_by_ingestion_run_id, last_validated_by_ingestion_run_id
           FROM flight_records WHERE id = 500`,
        )
        .get(),
    ).toEqual({
      created_by_ingestion_run_id: 500,
      last_validated_by_ingestion_run_id: 500,
    });
    expect(upgradeConnection.sqlite.prepare("PRAGMA foreign_key_check").all()).toEqual([]);
  });

  it("adds provider PBL AGL storage without losing an existing weather graph", () => {
    mkdirSync(dataLocalDirectory, { recursive: true });
    upgradeTestDirectory = mkdtempSync(join(dataLocalDirectory, "t018-pbl-upgrade-test-"));
    const oldMigrationsDirectory = join(upgradeTestDirectory, "old-migrations");
    mkdirSync(oldMigrationsDirectory);

    for (const entry of readdirSync(migrationsDirectory, { withFileTypes: true })) {
      if (entry.isDirectory() && entry.name < pblAglMigrationDirectory) {
        cpSync(join(migrationsDirectory, entry.name), join(oldMigrationsDirectory, entry.name), {
          recursive: true,
        });
      }
    }

    const databaseUrl = `file:./data/local/${basename(upgradeTestDirectory)}/upgrade.db`;
    upgradeConnection = openDatabase(databaseUrl);
    migrate(upgradeConnection.db, { migrationsFolder: oldMigrationsDirectory });
    insertWeatherGraph(upgradeConnection);
    upgradeConnection.close();
    upgradeConnection = undefined;

    runMigrations(databaseUrl);
    upgradeConnection = openDatabase(databaseUrl);

    expect(
      upgradeConnection.sqlite
        .prepare(
          `SELECT air_temperature_2m_k, provider_boundary_layer_height_agl_m
           FROM weather_samples WHERE id = 10`,
        )
        .get(),
    ).toEqual({
      air_temperature_2m_k: 293.15,
      provider_boundary_layer_height_agl_m: null,
    });
    expect(
      upgradeConnection.sqlite
        .prepare("SELECT count(*) AS count FROM weather_field_provenance")
        .get(),
    ).toEqual({ count: 6 });
    expect(upgradeConnection.sqlite.prepare("PRAGMA foreign_key_check").all()).toEqual([]);
  });

  it("refuses to overwrite drifted sampling coordinates with Copernicus elevations", () => {
    mkdirSync(dataLocalDirectory, { recursive: true });
    upgradeTestDirectory = mkdtempSync(join(dataLocalDirectory, "t018-dem-guard-test-"));
    const oldMigrationsDirectory = join(upgradeTestDirectory, "old-migrations");
    mkdirSync(oldMigrationsDirectory);

    for (const entry of readdirSync(migrationsDirectory, { withFileTypes: true })) {
      if (entry.isDirectory() && entry.name < copernicusElevationMigrationDirectory) {
        cpSync(join(migrationsDirectory, entry.name), join(oldMigrationsDirectory, entry.name), {
          recursive: true,
        });
      }
    }

    const databaseUrl = `file:./data/local/${basename(upgradeTestDirectory)}/guard.db`;
    upgradeConnection = openDatabase(databaseUrl);
    migrate(upgradeConnection.db, { migrationsFolder: oldMigrationsDirectory });
    upgradeConnection.sqlite.exec(
      "UPDATE weather_site_sampling_configs SET latitude_deg = 43.7 WHERE site_id = 7",
    );
    upgradeConnection.close();
    upgradeConnection = undefined;

    expect(() => {
      runMigrations(databaseUrl);
    }).toThrow();
  });
});
