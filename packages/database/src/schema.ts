import { desc, sql } from "drizzle-orm";
import {
  check,
  foreignKey,
  index,
  integer,
  real,
  sqliteTable,
  text,
  unique,
  uniqueIndex,
} from "drizzle-orm/sqlite-core";

const utcTimestampGlob =
  "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z";

export const flightSources = sqliteTable(
  "flight_sources",
  {
    id: integer("id").primaryKey(),
    code: text("code").notNull(),
    name: text("name").notNull(),
    baseUrl: text("base_url").notNull(),
    isActive: integer("is_active").notNull().default(1),
  },
  (table) => [
    unique("flight_sources_code_unique").on(table.code),
    check(
      "flight_sources_code_lower_snake_case_check",
      sql`length(${table.code}) BETWEEN 1 AND 80
        AND substr(${table.code}, 1, 1) GLOB '[a-z]'
        AND ${table.code} NOT GLOB '*[^a-z0-9_]*'
        AND ${table.code} NOT GLOB '*__*'
        AND substr(${table.code}, -1) <> '_'`,
    ),
    check("flight_sources_name_non_empty_check", sql`length(trim(${table.name})) > 0`),
    check("flight_sources_base_url_non_empty_check", sql`length(trim(${table.baseUrl})) > 0`),
    check("flight_sources_is_active_boolean_check", sql`${table.isActive} IN (0, 1)`),
  ],
);

export const sites = sqliteTable(
  "sites",
  {
    id: integer("id").primaryKey(),
    slug: text("slug").notNull(),
    name: text("name").notNull(),
    countryCodeIso2: text("country_code_iso2").notNull().default("BG"),
    siteType: text("site_type").notNull(),
    latitudeDeg: real("latitude_deg").notNull(),
    longitudeDeg: real("longitude_deg").notNull(),
    catchmentRadiusKm: real("catchment_radius_km"),
    timeZone: text("time_zone").notNull().default("Europe/Sofia"),
    isActive: integer("is_active").notNull().default(1),
  },
  (table) => [
    unique("sites_slug_unique").on(table.slug),
    check(
      "sites_slug_lower_kebab_case_check",
      sql`length(${table.slug}) BETWEEN 1 AND 80
        AND substr(${table.slug}, 1, 1) GLOB '[a-z0-9]'
        AND ${table.slug} NOT GLOB '*[^a-z0-9-]*'
        AND ${table.slug} NOT GLOB '*--*'
        AND substr(${table.slug}, -1) <> '-'`,
    ),
    check("sites_name_non_empty_check", sql`length(trim(${table.name})) > 0`),
    check("sites_country_code_iso2_check", sql`${table.countryCodeIso2} GLOB '[A-Z][A-Z]'`),
    check("sites_site_type_check", sql`${table.siteType} IN ('launch_area', 'region')`),
    check("sites_latitude_deg_range_check", sql`${table.latitudeDeg} BETWEEN -90 AND 90`),
    check("sites_longitude_deg_range_check", sql`${table.longitudeDeg} BETWEEN -180 AND 180`),
    check(
      "sites_catchment_radius_km_range_check",
      sql`${table.catchmentRadiusKm} IS NULL
        OR (${table.catchmentRadiusKm} > 0 AND ${table.catchmentRadiusKm} <= 250)`,
    ),
    check("sites_time_zone_non_empty_check", sql`length(trim(${table.timeZone})) > 0`),
    check("sites_is_active_boolean_check", sql`${table.isActive} IN (0, 1)`),
  ],
);

export const sourceSiteMappings = sqliteTable(
  "source_site_mappings",
  {
    id: integer("id").primaryKey(),
    sourceId: integer("source_id")
      .notNull()
      .references(() => flightSources.id, { onDelete: "restrict" }),
    siteId: integer("site_id")
      .notNull()
      .references(() => sites.id, { onDelete: "restrict" }),
    keyType: text("key_type").notNull(),
    keyValue: text("key_value"),
    sourceDisplayName: text("source_display_name"),
    pointLatitudeDeg: real("point_latitude_deg"),
    pointLongitudeDeg: real("point_longitude_deg"),
    status: text("status").notNull(),
    verificationReference: text("verification_reference"),
    verifiedAtUtc: text("verified_at_utc"),
    notes: text("notes"),
  },
  (table) => [
    // SQLite requires an exact UNIQUE parent key for the composite flight FK.
    // `id` remains the sole business identity; `source_id` enforces source consistency.
    unique("source_site_mappings_id_source_id_parent_key_unique").on(table.id, table.sourceId),
    uniqueIndex("source_site_mappings_active_key_unique")
      .on(table.sourceId, table.keyType, table.keyValue)
      .where(sql`${table.status} <> 'retired' AND ${table.keyType} <> 'source_point'`),
    uniqueIndex("source_site_mappings_active_point_unique")
      .on(table.sourceId, table.pointLatitudeDeg, table.pointLongitudeDeg)
      .where(sql`${table.status} <> 'retired' AND ${table.keyType} = 'source_point'`),
    index("source_site_mappings_site_source_status_index").on(
      table.siteId,
      table.sourceId,
      table.status,
    ),
    check(
      "source_site_mappings_key_type_check",
      sql`${table.keyType} IN (
        'source_takeoff_id',
        'source_site_token',
        'normalized_name',
        'source_point'
      )`,
    ),
    check(
      "source_site_mappings_key_shape_check",
      sql`(
          ${table.keyType} IN ('source_takeoff_id', 'source_site_token', 'normalized_name')
          AND ${table.keyValue} IS NOT NULL
          AND length(trim(${table.keyValue})) > 0
          AND ${table.pointLatitudeDeg} IS NULL
          AND ${table.pointLongitudeDeg} IS NULL
        )
        OR (
          ${table.keyType} = 'source_point'
          AND ${table.keyValue} IS NULL
          AND ${table.pointLatitudeDeg} IS NOT NULL
          AND ${table.pointLongitudeDeg} IS NOT NULL
        )`,
    ),
    check(
      "source_site_mappings_point_latitude_deg_range_check",
      sql`${table.pointLatitudeDeg} IS NULL
        OR ${table.pointLatitudeDeg} BETWEEN -90 AND 90`,
    ),
    check(
      "source_site_mappings_point_longitude_deg_range_check",
      sql`${table.pointLongitudeDeg} IS NULL
        OR ${table.pointLongitudeDeg} BETWEEN -180 AND 180`,
    ),
    check(
      "source_site_mappings_status_check",
      sql`${table.status} IN ('provisional', 'approved', 'retired')`,
    ),
    check(
      "source_site_mappings_verified_at_utc_shape_check",
      sql`${table.verifiedAtUtc} IS NULL OR ${table.verifiedAtUtc} GLOB '${sql.raw(utcTimestampGlob)}'`,
    ),
    check(
      "source_site_mappings_approved_evidence_check",
      sql`${table.status} <> 'approved'
        OR (
          ${table.verificationReference} IS NOT NULL
          AND length(trim(${table.verificationReference})) > 0
          AND ${table.verifiedAtUtc} IS NOT NULL
        )`,
    ),
  ],
);

export const ingestionRuns = sqliteTable(
  "ingestion_runs",
  {
    id: integer("id").primaryKey(),
    runKey: text("run_key").notNull(),
    sourceId: integer("source_id")
      .notNull()
      .references(() => flightSources.id, { onDelete: "restrict" }),
    ingestionMethod: text("ingestion_method").notNull(),
    status: text("status").notNull(),
    sourceUrl: text("source_url").notNull(),
    permissionBasis: text("permission_basis").notNull(),
    permissionReference: text("permission_reference").notNull(),
    modelTrainingAllowed: integer("model_training_allowed").notNull().default(0),
    operationalUseAllowed: integer("operational_use_allowed").notNull().default(0),
    rawManifestPath: text("raw_manifest_path").notNull(),
    rawManifestSha256: text("raw_manifest_sha256").notNull(),
    pipelineVersion: text("pipeline_version").notNull(),
    startedAtUtc: text("started_at_utc").notNull(),
    completedAtUtc: text("completed_at_utc"),
    recordsSeen: integer("records_seen").notNull().default(0),
    recordsAccepted: integer("records_accepted").notNull().default(0),
    recordsRejected: integer("records_rejected").notNull().default(0),
    recordsQuarantined: integer("records_quarantined").notNull().default(0),
    recordsDeduplicated: integer("records_deduplicated").notNull().default(0),
    errorSummary: text("error_summary"),
    notes: text("notes"),
  },
  (table) => [
    unique("ingestion_runs_run_key_unique").on(table.runKey),
    // SQLite requires this exact UNIQUE parent key for the composite flight FKs.
    // `id` remains the sole business identity; `source_id` enforces source consistency.
    unique("ingestion_runs_id_source_id_parent_key_unique").on(table.id, table.sourceId),
    index("ingestion_runs_source_started_at_index").on(table.sourceId, desc(table.startedAtUtc)),
    check(
      "ingestion_runs_run_key_uuid_v4_check",
      sql`${table.runKey} GLOB
        '[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]-[0-9a-f][0-9a-f][0-9a-f][0-9a-f]-4[0-9a-f][0-9a-f][0-9a-f]-[89ab][0-9a-f][0-9a-f][0-9a-f]-[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]'`,
    ),
    check(
      "ingestion_runs_ingestion_method_check",
      sql`${table.ingestionMethod} IN (
        'manual_export',
        'owner_export',
        'official_api',
        'authorized_http',
        'browser_ui',
        'pilot_provided'
      )`,
    ),
    check(
      "ingestion_runs_status_check",
      sql`${table.status} IN ('running', 'succeeded', 'failed')`,
    ),
    check("ingestion_runs_source_url_non_empty_check", sql`length(trim(${table.sourceUrl})) > 0`),
    check(
      "ingestion_runs_permission_basis_check",
      sql`${table.permissionBasis} IN (
        'written_permission',
        'source_terms',
        'owner_export',
        'official_api_terms',
        'pilot_provided'
      )`,
    ),
    check(
      "ingestion_runs_permission_reference_non_empty_check",
      sql`length(trim(${table.permissionReference})) > 0`,
    ),
    check(
      "ingestion_runs_model_training_allowed_boolean_check",
      sql`${table.modelTrainingAllowed} IN (0, 1)`,
    ),
    check(
      "ingestion_runs_operational_use_allowed_boolean_check",
      sql`${table.operationalUseAllowed} IN (0, 1)`,
    ),
    check(
      "ingestion_runs_raw_manifest_path_check",
      sql`${table.rawManifestPath} LIKE 'data/raw/%' AND ${table.rawManifestPath} NOT LIKE '%..%'`,
    ),
    check(
      "ingestion_runs_raw_manifest_sha256_check",
      sql`length(${table.rawManifestSha256}) = 64
        AND ${table.rawManifestSha256} NOT GLOB '*[^0-9a-f]*'`,
    ),
    check(
      "ingestion_runs_pipeline_version_non_empty_check",
      sql`length(trim(${table.pipelineVersion})) > 0`,
    ),
    check(
      "ingestion_runs_started_at_utc_shape_check",
      sql`${table.startedAtUtc} GLOB '${sql.raw(utcTimestampGlob)}'`,
    ),
    check(
      "ingestion_runs_completed_at_utc_shape_check",
      sql`${table.completedAtUtc} IS NULL
        OR ${table.completedAtUtc} GLOB '${sql.raw(utcTimestampGlob)}'`,
    ),
    check(
      "ingestion_runs_completion_lifecycle_check",
      sql`(
          ${table.status} = 'running'
          AND ${table.completedAtUtc} IS NULL
        )
        OR (
          ${table.status} IN ('succeeded', 'failed')
          AND ${table.completedAtUtc} IS NOT NULL
          AND ${table.completedAtUtc} >= ${table.startedAtUtc}
        )`,
    ),
    check(
      "ingestion_runs_counters_non_negative_check",
      sql`${table.recordsSeen} >= 0
        AND ${table.recordsAccepted} >= 0
        AND ${table.recordsRejected} >= 0
        AND ${table.recordsQuarantined} >= 0
        AND ${table.recordsDeduplicated} >= 0`,
    ),
    check(
      "ingestion_runs_counter_outcomes_check",
      sql`${table.recordsAccepted} + ${table.recordsRejected} + ${table.recordsQuarantined}
        <= ${table.recordsSeen}`,
    ),
  ],
);

export const flightRecords = sqliteTable(
  "flight_records",
  {
    id: integer("id").primaryKey(),
    sourceId: integer("source_id")
      .notNull()
      .references(() => flightSources.id, { onDelete: "restrict" }),
    sourceFlightId: text("source_flight_id").notNull(),
    sourceFlightUrl: text("source_flight_url").notNull(),
    sourceSiteMappingId: integer("source_site_mapping_id").notNull(),
    takeoffAtUtc: text("takeoff_at_utc").notNull(),
    durationSeconds: integer("duration_seconds"),
    scoredDistanceKm: real("scored_distance_km").notNull(),
    routeType: text("route_type").notNull(),
    trackUrl: text("track_url"),
    validationLevel: text("validation_level").notNull(),
    validationNotes: text("validation_notes").notNull(),
    validatedAtUtc: text("validated_at_utc").notNull(),
    createdByIngestionRunId: integer("created_by_ingestion_run_id").notNull(),
    lastValidatedByIngestionRunId: integer("last_validated_by_ingestion_run_id").notNull(),
    createdAtUtc: text("created_at_utc").notNull(),
    updatedAtUtc: text("updated_at_utc").notNull(),
  },
  (table) => [
    unique("flight_records_source_flight_unique").on(table.sourceId, table.sourceFlightId),
    index("flight_records_mapping_takeoff_at_index").on(
      table.sourceSiteMappingId,
      table.takeoffAtUtc,
    ),
    index("flight_records_takeoff_distance_index").on(
      table.takeoffAtUtc,
      desc(table.scoredDistanceKm),
    ),
    index("flight_records_created_by_ingestion_run_index").on(table.createdByIngestionRunId),
    foreignKey({
      columns: [table.sourceSiteMappingId, table.sourceId],
      foreignColumns: [sourceSiteMappings.id, sourceSiteMappings.sourceId],
      name: "flight_records_mapping_source_fk",
    }).onDelete("restrict"),
    foreignKey({
      columns: [table.createdByIngestionRunId, table.sourceId],
      foreignColumns: [ingestionRuns.id, ingestionRuns.sourceId],
      name: "flight_records_created_run_source_fk",
    }).onDelete("restrict"),
    foreignKey({
      columns: [table.lastValidatedByIngestionRunId, table.sourceId],
      foreignColumns: [ingestionRuns.id, ingestionRuns.sourceId],
      name: "flight_records_last_validated_run_source_fk",
    }).onDelete("restrict"),
    check(
      "flight_records_source_flight_id_non_empty_check",
      sql`length(trim(${table.sourceFlightId})) > 0`,
    ),
    check(
      "flight_records_source_flight_url_non_empty_check",
      sql`length(trim(${table.sourceFlightUrl})) > 0`,
    ),
    check(
      "flight_records_takeoff_at_utc_shape_check",
      sql`${table.takeoffAtUtc} GLOB '${sql.raw(utcTimestampGlob)}'`,
    ),
    check(
      "flight_records_duration_seconds_range_check",
      sql`${table.durationSeconds} IS NULL
        OR ${table.durationSeconds} BETWEEN 1 AND 86400`,
    ),
    check(
      "flight_records_scored_distance_km_range_check",
      sql`${table.scoredDistanceKm} BETWEEN 100 AND 2000`,
    ),
    check(
      "flight_records_route_type_check",
      sql`${table.routeType} IN (
        'free_flight',
        'free_triangle',
        'fai_triangle',
        'closed_free_triangle',
        'closed_fai_triangle',
        'other',
        'unknown'
      )`,
    ),
    check(
      "flight_records_validation_level_check",
      sql`${table.validationLevel} IN ('metadata', 'track')`,
    ),
    check(
      "flight_records_validation_notes_non_empty_check",
      sql`length(trim(${table.validationNotes})) > 0`,
    ),
    check(
      "flight_records_validated_at_utc_shape_check",
      sql`${table.validatedAtUtc} GLOB '${sql.raw(utcTimestampGlob)}'`,
    ),
    check(
      "flight_records_created_at_utc_shape_check",
      sql`${table.createdAtUtc} GLOB '${sql.raw(utcTimestampGlob)}'`,
    ),
    check(
      "flight_records_updated_at_utc_shape_check",
      sql`${table.updatedAtUtc} GLOB '${sql.raw(utcTimestampGlob)}'`,
    ),
    check(
      "flight_records_updated_not_before_created_check",
      sql`${table.updatedAtUtc} >= ${table.createdAtUtc}`,
    ),
  ],
);
