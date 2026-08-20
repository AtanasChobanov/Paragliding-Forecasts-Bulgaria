import { desc, sql } from "drizzle-orm";
import {
  check,
  foreignKey,
  index,
  integer,
  primaryKey,
  real,
  sqliteTable,
  text,
  unique,
  uniqueIndex,
} from "drizzle-orm/sqlite-core";

const utcTimestampGlob =
  "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z";
const localDateGlob = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]";

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

export const flightIngestionRuns = sqliteTable(
  "flight_ingestion_runs",
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
      foreignColumns: [flightIngestionRuns.id, flightIngestionRuns.sourceId],
      name: "flight_records_created_run_source_fk",
    }).onDelete("restrict"),
    foreignKey({
      columns: [table.lastValidatedByIngestionRunId, table.sourceId],
      foreignColumns: [flightIngestionRuns.id, flightIngestionRuns.sourceId],
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

export const weatherSources = sqliteTable(
  "weather_sources",
  {
    id: integer("id").primaryKey(),
    code: text("code").notNull(),
    providerName: text("provider_name").notNull(),
    datasetName: text("dataset_name").notNull(),
    sourceKind: text("source_kind").notNull(),
    baseUrl: text("base_url").notNull(),
    isActive: integer("is_active").notNull().default(1),
  },
  (table) => [
    unique("weather_sources_code_unique").on(table.code),
    check(
      "weather_sources_code_lower_snake_case_check",
      sql`length(${table.code}) BETWEEN 1 AND 80
        AND substr(${table.code}, 1, 1) GLOB '[a-z]'
        AND ${table.code} NOT GLOB '*[^a-z0-9_]*'
        AND ${table.code} NOT GLOB '*__*'
        AND substr(${table.code}, -1) <> '_'`,
    ),
    check(
      "weather_sources_provider_name_non_empty_check",
      sql`length(trim(${table.providerName})) > 0`,
    ),
    check(
      "weather_sources_dataset_name_non_empty_check",
      sql`length(trim(${table.datasetName})) > 0`,
    ),
    check(
      "weather_sources_source_kind_check",
      sql`${table.sourceKind} IN ('forecast', 'reanalysis')`,
    ),
    check("weather_sources_base_url_non_empty_check", sql`length(trim(${table.baseUrl})) > 0`),
    check("weather_sources_is_active_boolean_check", sql`${table.isActive} IN (0, 1)`),
  ],
);

export const weatherIngestionRuns = sqliteTable(
  "weather_ingestion_runs",
  {
    id: integer("id").primaryKey(),
    runKey: text("run_key").notNull(),
    sourceId: integer("source_id")
      .notNull()
      .references(() => weatherSources.id, { onDelete: "restrict" }),
    ingestionMethod: text("ingestion_method").notNull(),
    requestPurpose: text("request_purpose").notNull(),
    status: text("status").notNull(),
    sourceUrl: text("source_url").notNull(),
    permissionBasis: text("permission_basis").notNull(),
    permissionReference: text("permission_reference").notNull(),
    attributionText: text("attribution_text"),
    modelTrainingAllowed: integer("model_training_allowed").notNull().default(0),
    operationalUseAllowed: integer("operational_use_allowed").notNull().default(0),
    rawManifestPath: text("raw_manifest_path").notNull(),
    rawManifestSha256: text("raw_manifest_sha256").notNull(),
    pipelineVersion: text("pipeline_version").notNull(),
    startedAtUtc: text("started_at_utc").notNull(),
    completedAtUtc: text("completed_at_utc"),
    samplesSeen: integer("samples_seen").notNull().default(0),
    samplesAccepted: integer("samples_accepted").notNull().default(0),
    samplesRejected: integer("samples_rejected").notNull().default(0),
    samplesQuarantined: integer("samples_quarantined").notNull().default(0),
    samplesDeduplicated: integer("samples_deduplicated").notNull().default(0),
    errorSummary: text("error_summary"),
    notes: text("notes"),
  },
  (table) => [
    unique("weather_ingestion_runs_run_key_unique").on(table.runKey),
    unique("weather_ingestion_runs_id_source_id_parent_key_unique").on(table.id, table.sourceId),
    index("weather_ingestion_runs_source_started_at_index").on(
      table.sourceId,
      desc(table.startedAtUtc),
    ),
    index("weather_ingestion_runs_status_started_at_index").on(
      table.status,
      desc(table.startedAtUtc),
    ),
    index("weather_ingestion_runs_purpose_status_index").on(table.requestPurpose, table.status),
    check(
      "weather_ingestion_runs_run_key_uuid_v4_check",
      sql`${table.runKey} GLOB
        '[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]-[0-9a-f][0-9a-f][0-9a-f][0-9a-f]-4[0-9a-f][0-9a-f][0-9a-f]-[89ab][0-9a-f][0-9a-f][0-9a-f]-[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]'`,
    ),
    check(
      "weather_ingestion_runs_ingestion_method_check",
      sql`${table.ingestionMethod} IN ('public_object_archive', 'official_api', 'offline_replay')`,
    ),
    check(
      "weather_ingestion_runs_request_purpose_check",
      sql`${table.requestPurpose} IN (
        'historical_forecast',
        'operational_forecast',
        'reanalysis_backfill',
        'replay_validation'
      )`,
    ),
    check(
      "weather_ingestion_runs_status_check",
      sql`${table.status} IN ('running', 'succeeded', 'failed')`,
    ),
    check(
      "weather_ingestion_runs_source_url_non_empty_check",
      sql`length(trim(${table.sourceUrl})) > 0`,
    ),
    check(
      "weather_ingestion_runs_permission_basis_non_empty_check",
      sql`length(trim(${table.permissionBasis})) > 0`,
    ),
    check(
      "weather_ingestion_runs_permission_reference_non_empty_check",
      sql`length(trim(${table.permissionReference})) > 0`,
    ),
    check(
      "weather_ingestion_runs_attribution_text_non_empty_check",
      sql`${table.attributionText} IS NULL OR length(trim(${table.attributionText})) > 0`,
    ),
    check(
      "weather_ingestion_runs_model_training_allowed_boolean_check",
      sql`${table.modelTrainingAllowed} IN (0, 1)`,
    ),
    check(
      "weather_ingestion_runs_operational_use_allowed_boolean_check",
      sql`${table.operationalUseAllowed} IN (0, 1)`,
    ),
    check(
      "weather_ingestion_runs_raw_manifest_path_check",
      sql`${table.rawManifestPath} LIKE 'data/raw/%'
        AND ${table.rawManifestPath} NOT LIKE '%..%'`,
    ),
    check(
      "weather_ingestion_runs_raw_manifest_sha256_check",
      sql`length(${table.rawManifestSha256}) = 64
        AND ${table.rawManifestSha256} NOT GLOB '*[^0-9a-f]*'`,
    ),
    check(
      "weather_ingestion_runs_pipeline_version_check",
      sql`length(trim(${table.pipelineVersion})) > 0
        AND ${table.pipelineVersion} LIKE '%/%'
        AND ${table.pipelineVersion} NOT LIKE '|%'
        AND ${table.pipelineVersion} NOT LIKE '%|'
        AND ${table.pipelineVersion} NOT LIKE '%||%'`,
    ),
    check(
      "weather_ingestion_runs_started_at_utc_shape_check",
      sql`${table.startedAtUtc} GLOB '${sql.raw(utcTimestampGlob)}'`,
    ),
    check(
      "weather_ingestion_runs_completed_at_utc_shape_check",
      sql`${table.completedAtUtc} IS NULL
        OR ${table.completedAtUtc} GLOB '${sql.raw(utcTimestampGlob)}'`,
    ),
    check(
      "weather_ingestion_runs_completion_lifecycle_check",
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
      "weather_ingestion_runs_counters_non_negative_check",
      sql`${table.samplesSeen} >= 0
        AND ${table.samplesAccepted} >= 0
        AND ${table.samplesRejected} >= 0
        AND ${table.samplesQuarantined} >= 0
        AND ${table.samplesDeduplicated} >= 0`,
    ),
    check(
      "weather_ingestion_runs_counter_outcomes_check",
      sql`${table.samplesAccepted} + ${table.samplesRejected} + ${table.samplesQuarantined}
        <= ${table.samplesSeen}`,
    ),
  ],
);

export const weatherProductRuns = sqliteTable(
  "weather_product_runs",
  {
    id: integer("id").primaryKey(),
    sourceId: integer("source_id")
      .notNull()
      .references(() => weatherSources.id, { onDelete: "restrict" }),
    sourceProductKey: text("source_product_key").notNull(),
    referenceAtUtc: text("reference_at_utc"),
    availableAtUtc: text("available_at_utc"),
    validFromUtc: text("valid_from_utc").notNull(),
    validToUtc: text("valid_to_utc").notNull(),
    createdByIngestionRunId: integer("created_by_ingestion_run_id").notNull(),
    lastValidatedByIngestionRunId: integer("last_validated_by_ingestion_run_id").notNull(),
  },
  (table) => [
    unique("weather_product_runs_source_product_unique").on(table.sourceId, table.sourceProductKey),
    index("weather_product_runs_source_reference_at_index").on(
      table.sourceId,
      desc(table.referenceAtUtc),
    ),
    index("weather_product_runs_valid_range_index").on(table.validFromUtc, table.validToUtc),
    index("weather_product_runs_created_by_ingestion_run_index").on(table.createdByIngestionRunId),
    foreignKey({
      columns: [table.createdByIngestionRunId, table.sourceId],
      foreignColumns: [weatherIngestionRuns.id, weatherIngestionRuns.sourceId],
      name: "weather_product_runs_created_run_source_fk",
    }).onDelete("restrict"),
    foreignKey({
      columns: [table.lastValidatedByIngestionRunId, table.sourceId],
      foreignColumns: [weatherIngestionRuns.id, weatherIngestionRuns.sourceId],
      name: "weather_product_runs_last_validated_run_source_fk",
    }).onDelete("restrict"),
    check(
      "weather_product_runs_source_product_key_non_empty_check",
      sql`length(trim(${table.sourceProductKey})) > 0`,
    ),
    check(
      "weather_product_runs_reference_at_utc_shape_check",
      sql`${table.referenceAtUtc} IS NULL
        OR ${table.referenceAtUtc} GLOB '${sql.raw(utcTimestampGlob)}'`,
    ),
    check(
      "weather_product_runs_available_at_utc_shape_check",
      sql`${table.availableAtUtc} IS NULL
        OR ${table.availableAtUtc} GLOB '${sql.raw(utcTimestampGlob)}'`,
    ),
    check(
      "weather_product_runs_valid_from_utc_shape_check",
      sql`${table.validFromUtc} GLOB '${sql.raw(utcTimestampGlob)}'`,
    ),
    check(
      "weather_product_runs_valid_to_utc_shape_check",
      sql`${table.validToUtc} GLOB '${sql.raw(utcTimestampGlob)}'`,
    ),
    check(
      "weather_product_runs_valid_range_check",
      sql`${table.validToUtc} >= ${table.validFromUtc}`,
    ),
  ],
);

export const weatherSiteSamplingConfigs = sqliteTable(
  "weather_site_sampling_configs",
  {
    siteId: integer("site_id")
      .primaryKey()
      .references(() => sites.id, { onDelete: "restrict" }),
    latitudeDeg: real("latitude_deg").notNull(),
    longitudeDeg: real("longitude_deg").notNull(),
    coordinateReference: text("coordinate_reference").notNull(),
    referenceElevationMslM: real("reference_elevation_msl_m"),
    elevationReference: text("elevation_reference"),
  },
  (table) => [
    index("weather_site_sampling_configs_coordinate_index").on(
      table.latitudeDeg,
      table.longitudeDeg,
    ),
    check(
      "weather_site_sampling_configs_latitude_range_check",
      sql`${table.latitudeDeg} BETWEEN -90 AND 90`,
    ),
    check(
      "weather_site_sampling_configs_longitude_range_check",
      sql`${table.longitudeDeg} BETWEEN -180 AND 180`,
    ),
    check(
      "weather_site_sampling_configs_coordinate_reference_non_empty_check",
      sql`length(trim(${table.coordinateReference})) > 0`,
    ),
    check(
      "weather_site_sampling_configs_elevation_reference_pair_check",
      sql`(
          ${table.referenceElevationMslM} IS NULL
          AND ${table.elevationReference} IS NULL
        )
        OR (
          ${table.referenceElevationMslM} IS NOT NULL
          AND ${table.elevationReference} IS NOT NULL
          AND length(trim(${table.elevationReference})) > 0
        )`,
    ),
  ],
);

export const weatherGrids = sqliteTable(
  "weather_grids",
  {
    id: integer("id").primaryKey(),
    sourceId: integer("source_id")
      .notNull()
      .references(() => weatherSources.id, { onDelete: "restrict" }),
    gridKey: text("grid_key").notNull(),
    gridType: text("grid_type").notNull(),
    latitudeStepDeg: real("latitude_step_deg").notNull(),
    longitudeStepDeg: real("longitude_step_deg").notNull(),
    nativeRowCount: integer("native_row_count").notNull(),
    nativeColumnCount: integer("native_column_count").notNull(),
    definitionSha256: text("definition_sha256").notNull(),
    isActive: integer("is_active").notNull().default(1),
  },
  (table) => [
    unique("weather_grids_source_key_definition_unique").on(
      table.sourceId,
      table.gridKey,
      table.definitionSha256,
    ),
    uniqueIndex("weather_grids_active_key_unique")
      .on(table.sourceId, table.gridKey)
      .where(sql`${table.isActive} = 1`),
    index("weather_grids_source_active_index").on(table.sourceId, table.isActive),
    check("weather_grids_grid_key_non_empty_check", sql`length(trim(${table.gridKey})) > 0`),
    check("weather_grids_grid_type_check", sql`${table.gridType} IN ('regular_latlon')`),
    check("weather_grids_latitude_step_positive_check", sql`${table.latitudeStepDeg} > 0`),
    check("weather_grids_longitude_step_positive_check", sql`${table.longitudeStepDeg} > 0`),
    check("weather_grids_native_row_count_positive_check", sql`${table.nativeRowCount} > 0`),
    check("weather_grids_native_column_count_positive_check", sql`${table.nativeColumnCount} > 0`),
    check(
      "weather_grids_definition_sha256_check",
      sql`length(${table.definitionSha256}) = 64
        AND ${table.definitionSha256} NOT GLOB '*[^0-9a-f]*'`,
    ),
    check("weather_grids_is_active_boolean_check", sql`${table.isActive} IN (0, 1)`),
  ],
);

export const weatherGridPoints = sqliteTable(
  "weather_grid_points",
  {
    id: integer("id").primaryKey(),
    gridId: integer("grid_id")
      .notNull()
      .references(() => weatherGrids.id, { onDelete: "restrict" }),
    latitudeDeg: real("latitude_deg").notNull(),
    longitudeDeg: real("longitude_deg").notNull(),
    modelElevationMslM: real("model_elevation_msl_m"),
    firstSeenIngestionRunId: integer("first_seen_ingestion_run_id")
      .notNull()
      .references(() => weatherIngestionRuns.id, { onDelete: "restrict" }),
  },
  (table) => [
    unique("weather_grid_points_grid_coordinate_unique").on(
      table.gridId,
      table.latitudeDeg,
      table.longitudeDeg,
    ),
    index("weather_grid_points_first_seen_run_index").on(table.firstSeenIngestionRunId),
    check("weather_grid_points_latitude_range_check", sql`${table.latitudeDeg} BETWEEN -90 AND 90`),
    check(
      "weather_grid_points_longitude_range_check",
      sql`${table.longitudeDeg} BETWEEN -180 AND 180`,
    ),
  ],
);

export const weatherSamplingFootprints = sqliteTable(
  "weather_sampling_footprints",
  {
    id: integer("id").primaryKey(),
    siteId: integer("site_id")
      .notNull()
      .references(() => weatherSiteSamplingConfigs.siteId, { onDelete: "restrict" }),
    gridId: integer("grid_id")
      .notNull()
      .references(() => weatherGrids.id, { onDelete: "restrict" }),
    purpose: text("purpose").notNull(),
    samplingMethod: text("sampling_method").notNull(),
    samplingMethodVersion: text("sampling_method_version").notNull(),
    radiusKm: real("radius_km"),
    footprintVersion: integer("footprint_version").notNull(),
    definitionSha256: text("definition_sha256").notNull(),
  },
  (table) => [
    unique("weather_sampling_footprints_identity_unique").on(
      table.siteId,
      table.gridId,
      table.purpose,
      table.footprintVersion,
    ),
    index("weather_sampling_footprints_site_purpose_version_index").on(
      table.siteId,
      table.purpose,
      desc(table.footprintVersion),
    ),
    index("weather_sampling_footprints_grid_index").on(table.gridId),
    check(
      "weather_sampling_footprints_purpose_check",
      sql`${table.purpose} IN ('point', 'neighbourhood')`,
    ),
    check(
      "weather_sampling_footprints_sampling_method_check",
      sql`${table.samplingMethod} IN ('nearest', 'bilinear', 'radius')`,
    ),
    check(
      "weather_sampling_footprints_method_purpose_shape_check",
      sql`(
          ${table.purpose} = 'point'
          AND ${table.samplingMethod} IN ('nearest', 'bilinear')
          AND ${table.radiusKm} IS NULL
        )
        OR (
          ${table.purpose} = 'neighbourhood'
          AND ${table.samplingMethod} = 'radius'
          AND ${table.radiusKm} IS NOT NULL
          AND ${table.radiusKm} > 0
        )`,
    ),
    check(
      "weather_sampling_footprints_method_version_non_empty_check",
      sql`length(trim(${table.samplingMethodVersion})) > 0`,
    ),
    check(
      "weather_sampling_footprints_footprint_version_positive_check",
      sql`${table.footprintVersion} > 0`,
    ),
    check(
      "weather_sampling_footprints_definition_sha256_check",
      sql`length(${table.definitionSha256}) = 64
        AND ${table.definitionSha256} NOT GLOB '*[^0-9a-f]*'`,
    ),
  ],
);

export const weatherSamplingFootprintNodes = sqliteTable(
  "weather_sampling_footprint_nodes",
  {
    footprintId: integer("footprint_id")
      .notNull()
      .references(() => weatherSamplingFootprints.id, { onDelete: "restrict" }),
    gridPointId: integer("grid_point_id")
      .notNull()
      .references(() => weatherGridPoints.id, { onDelete: "restrict" }),
    distanceKm: real("distance_km").notNull(),
    interpolationWeight: real("interpolation_weight"),
  },
  (table) => [
    primaryKey({
      columns: [table.footprintId, table.gridPointId],
      name: "weather_sampling_footprint_nodes_pk",
    }),
    index("weather_sampling_footprint_nodes_grid_point_index").on(table.gridPointId),
    check(
      "weather_sampling_footprint_nodes_distance_non_negative_check",
      sql`${table.distanceKm} >= 0`,
    ),
    check(
      "weather_sampling_footprint_nodes_weight_range_check",
      sql`${table.interpolationWeight} IS NULL
        OR ${table.interpolationWeight} BETWEEN 0 AND 1`,
    ),
  ],
);
export const weatherSamples = sqliteTable(
  "weather_samples",
  {
    id: integer("id").primaryKey(),
    productRunId: integer("product_run_id")
      .notNull()
      .references(() => weatherProductRuns.id, { onDelete: "restrict" }),
    pointFootprintId: integer("point_footprint_id")
      .notNull()
      .references(() => weatherSamplingFootprints.id, { onDelete: "restrict" }),
    validAtUtc: text("valid_at_utc").notNull(),
    validLocalDate: text("valid_local_date").notNull(),
    leadHours: real("lead_hours"),
    coverageStatus: text("coverage_status").notNull(),
    airTemperature2mK: real("air_temperature_2m_k"),
    dewPointTemperature2mK: real("dew_point_temperature_2m_k"),
    relativeHumidity2mPercent: real("relative_humidity_2m_percent"),
    surfacePressurePa: real("surface_pressure_pa"),
    meanSeaLevelPressurePa: real("mean_sea_level_pressure_pa"),
    windU10mMS: real("wind_u_10m_m_s"),
    windV10mMS: real("wind_v_10m_m_s"),
    windSpeed10mMS: real("wind_speed_10m_m_s"),
    windDirection10mDegreesFromNorth: real("wind_direction_10m_degrees_from_north"),
    providerBoundaryLayerHeightMslM: real("provider_boundary_layer_height_msl_m"),
    providerBoundaryLayerMethod: text("provider_boundary_layer_method"),
    providerCloudBaseAglM: real("provider_cloud_base_agl_m"),
    providerCloudBaseMslM: real("provider_cloud_base_msl_m"),
    providerCloudBaseMethod: text("provider_cloud_base_method"),
    totalColumnWaterVapourKgM2: real("total_column_water_vapour_kg_m2"),
    totalCloudCoverPercent: real("total_cloud_cover_percent"),
    lowCloudCoverPercent: real("low_cloud_cover_percent"),
    midCloudCoverPercent: real("mid_cloud_cover_percent"),
    highCloudCoverPercent: real("high_cloud_cover_percent"),
    createdByIngestionRunId: integer("created_by_ingestion_run_id")
      .notNull()
      .references(() => weatherIngestionRuns.id, { onDelete: "restrict" }),
    lastValidatedByIngestionRunId: integer("last_validated_by_ingestion_run_id")
      .notNull()
      .references(() => weatherIngestionRuns.id, { onDelete: "restrict" }),
  },
  (table) => [
    unique("weather_samples_product_footprint_valid_unique").on(
      table.productRunId,
      table.pointFootprintId,
      table.validAtUtc,
    ),
    index("weather_samples_footprint_valid_at_index").on(table.pointFootprintId, table.validAtUtc),
    index("weather_samples_product_valid_at_index").on(table.productRunId, table.validAtUtc),
    index("weather_samples_valid_local_date_index").on(table.validLocalDate),
    index("weather_samples_created_by_ingestion_run_index").on(table.createdByIngestionRunId),
    index("weather_samples_coverage_status_index").on(table.coverageStatus),
    check(
      "weather_samples_valid_at_utc_shape_check",
      sql`${table.validAtUtc} GLOB '${sql.raw(utcTimestampGlob)}'`,
    ),
    check(
      "weather_samples_valid_local_date_shape_check",
      sql`${table.validLocalDate} GLOB '${sql.raw(localDateGlob)}'`,
    ),
    check(
      "weather_samples_lead_hours_non_negative_check",
      sql`${table.leadHours} IS NULL OR ${table.leadHours} >= 0`,
    ),
    check(
      "weather_samples_coverage_status_check",
      sql`${table.coverageStatus} IN ('complete', 'partial', 'insufficient')`,
    ),
    check(
      "weather_samples_air_temperature_2m_positive_check",
      sql`${table.airTemperature2mK} IS NULL OR ${table.airTemperature2mK} > 0`,
    ),
    check(
      "weather_samples_dew_point_temperature_2m_positive_check",
      sql`${table.dewPointTemperature2mK} IS NULL OR ${table.dewPointTemperature2mK} > 0`,
    ),
    check(
      "weather_samples_relative_humidity_2m_range_check",
      sql`${table.relativeHumidity2mPercent} IS NULL
        OR ${table.relativeHumidity2mPercent} BETWEEN 0 AND 100`,
    ),
    check(
      "weather_samples_surface_pressure_positive_check",
      sql`${table.surfacePressurePa} IS NULL OR ${table.surfacePressurePa} > 0`,
    ),
    check(
      "weather_samples_mean_sea_level_pressure_positive_check",
      sql`${table.meanSeaLevelPressurePa} IS NULL OR ${table.meanSeaLevelPressurePa} > 0`,
    ),
    check(
      "weather_samples_wind_speed_10m_non_negative_check",
      sql`${table.windSpeed10mMS} IS NULL OR ${table.windSpeed10mMS} >= 0`,
    ),
    check(
      "weather_samples_wind_direction_10m_range_check",
      sql`${table.windDirection10mDegreesFromNorth} IS NULL
        OR (
          ${table.windDirection10mDegreesFromNorth} >= 0
          AND ${table.windDirection10mDegreesFromNorth} < 360
        )`,
    ),
    check(
      "weather_samples_boundary_layer_method_shape_check",
      sql`(${table.providerBoundaryLayerMethod} IS NULL
          OR length(trim(${table.providerBoundaryLayerMethod})) > 0)
        AND (${table.providerBoundaryLayerHeightMslM} IS NULL
          OR ${table.providerBoundaryLayerMethod} IS NOT NULL)`,
    ),
    check(
      "weather_samples_cloud_base_agl_non_negative_check",
      sql`${table.providerCloudBaseAglM} IS NULL OR ${table.providerCloudBaseAglM} >= 0`,
    ),
    check(
      "weather_samples_cloud_base_method_shape_check",
      sql`(${table.providerCloudBaseMethod} IS NULL
          OR length(trim(${table.providerCloudBaseMethod})) > 0)
        AND ((${table.providerCloudBaseAglM} IS NULL
            AND ${table.providerCloudBaseMslM} IS NULL)
          OR ${table.providerCloudBaseMethod} IS NOT NULL)`,
    ),
    check(
      "weather_samples_total_column_water_vapour_non_negative_check",
      sql`${table.totalColumnWaterVapourKgM2} IS NULL
        OR ${table.totalColumnWaterVapourKgM2} >= 0`,
    ),
    check(
      "weather_samples_total_cloud_cover_range_check",
      sql`${table.totalCloudCoverPercent} IS NULL
        OR ${table.totalCloudCoverPercent} BETWEEN 0 AND 100`,
    ),
    check(
      "weather_samples_low_cloud_cover_range_check",
      sql`${table.lowCloudCoverPercent} IS NULL
        OR ${table.lowCloudCoverPercent} BETWEEN 0 AND 100`,
    ),
    check(
      "weather_samples_mid_cloud_cover_range_check",
      sql`${table.midCloudCoverPercent} IS NULL
        OR ${table.midCloudCoverPercent} BETWEEN 0 AND 100`,
    ),
    check(
      "weather_samples_high_cloud_cover_range_check",
      sql`${table.highCloudCoverPercent} IS NULL
        OR ${table.highCloudCoverPercent} BETWEEN 0 AND 100`,
    ),
  ],
);

export const weatherProfileLevels = sqliteTable(
  "weather_profile_levels",
  {
    id: integer("id").primaryKey(),
    weatherSampleId: integer("weather_sample_id")
      .notNull()
      .references(() => weatherSamples.id, { onDelete: "restrict" }),
    pressurePa: real("pressure_pa").notNull(),
    geopotentialHeightMslM: real("geopotential_height_msl_m"),
    levelHeightAglM: real("level_height_agl_m"),
    airTemperatureK: real("air_temperature_k"),
    dewPointTemperatureK: real("dew_point_temperature_k"),
    relativeHumidityPercent: real("relative_humidity_percent"),
    specificHumidityKgPerKg: real("specific_humidity_kg_per_kg"),
    windUMS: real("wind_u_m_s"),
    windVMS: real("wind_v_m_s"),
    windSpeedMS: real("wind_speed_m_s"),
    windDirectionDegreesFromNorth: real("wind_direction_degrees_from_north"),
  },
  (table) => [
    unique("weather_profile_levels_sample_pressure_unique").on(
      table.weatherSampleId,
      table.pressurePa,
    ),
    index("weather_profile_levels_pressure_sample_index").on(
      table.pressurePa,
      table.weatherSampleId,
    ),
    check("weather_profile_levels_pressure_positive_check", sql`${table.pressurePa} > 0`),
    check(
      "weather_profile_levels_height_agl_non_negative_check",
      sql`${table.levelHeightAglM} IS NULL OR ${table.levelHeightAglM} >= 0`,
    ),
    check(
      "weather_profile_levels_air_temperature_positive_check",
      sql`${table.airTemperatureK} IS NULL OR ${table.airTemperatureK} > 0`,
    ),
    check(
      "weather_profile_levels_dew_point_temperature_positive_check",
      sql`${table.dewPointTemperatureK} IS NULL OR ${table.dewPointTemperatureK} > 0`,
    ),
    check(
      "weather_profile_levels_relative_humidity_range_check",
      sql`${table.relativeHumidityPercent} IS NULL
        OR ${table.relativeHumidityPercent} BETWEEN 0 AND 100`,
    ),
    check(
      "weather_profile_levels_specific_humidity_non_negative_check",
      sql`${table.specificHumidityKgPerKg} IS NULL
        OR ${table.specificHumidityKgPerKg} >= 0`,
    ),
    check(
      "weather_profile_levels_wind_speed_non_negative_check",
      sql`${table.windSpeedMS} IS NULL OR ${table.windSpeedMS} >= 0`,
    ),
    check(
      "weather_profile_levels_wind_direction_range_check",
      sql`${table.windDirectionDegreesFromNorth} IS NULL
        OR (
          ${table.windDirectionDegreesFromNorth} >= 0
          AND ${table.windDirectionDegreesFromNorth} < 360
        )`,
    ),
  ],
);

export const weatherConvectionMeasurements = sqliteTable(
  "weather_convection_measurements",
  {
    id: integer("id").primaryKey(),
    weatherSampleId: integer("weather_sample_id")
      .notNull()
      .references(() => weatherSamples.id, { onDelete: "restrict" }),
    parcelMethod: text("parcel_method").notNull(),
    calculationMethod: text("calculation_method").notNull(),
    calculationMethodVersion: text("calculation_method_version"),
    layerBottomPressureFromGroundPa: real("layer_bottom_pressure_from_ground_pa"),
    layerTopPressureFromGroundPa: real("layer_top_pressure_from_ground_pa"),
    capeJPerKg: real("cape_j_per_kg"),
    cinMagnitudeJPerKg: real("cin_magnitude_j_per_kg"),
  },
  (table) => [
    uniqueIndex("weather_convection_no_layer_no_version_unique")
      .on(table.weatherSampleId, table.parcelMethod, table.calculationMethod)
      .where(
        sql`${table.layerBottomPressureFromGroundPa} IS NULL
          AND ${table.layerTopPressureFromGroundPa} IS NULL
          AND ${table.calculationMethodVersion} IS NULL`,
      ),
    uniqueIndex("weather_convection_no_layer_version_unique")
      .on(
        table.weatherSampleId,
        table.parcelMethod,
        table.calculationMethod,
        table.calculationMethodVersion,
      )
      .where(
        sql`${table.layerBottomPressureFromGroundPa} IS NULL
          AND ${table.layerTopPressureFromGroundPa} IS NULL
          AND ${table.calculationMethodVersion} IS NOT NULL`,
      ),
    uniqueIndex("weather_convection_layer_no_version_unique")
      .on(
        table.weatherSampleId,
        table.parcelMethod,
        table.calculationMethod,
        table.layerBottomPressureFromGroundPa,
        table.layerTopPressureFromGroundPa,
      )
      .where(
        sql`${table.layerBottomPressureFromGroundPa} IS NOT NULL
          AND ${table.layerTopPressureFromGroundPa} IS NOT NULL
          AND ${table.calculationMethodVersion} IS NULL`,
      ),
    uniqueIndex("weather_convection_layer_version_unique")
      .on(
        table.weatherSampleId,
        table.parcelMethod,
        table.calculationMethod,
        table.layerBottomPressureFromGroundPa,
        table.layerTopPressureFromGroundPa,
        table.calculationMethodVersion,
      )
      .where(
        sql`${table.layerBottomPressureFromGroundPa} IS NOT NULL
          AND ${table.layerTopPressureFromGroundPa} IS NOT NULL
          AND ${table.calculationMethodVersion} IS NOT NULL`,
      ),
    index("weather_convection_measurements_sample_index").on(table.weatherSampleId),
    check(
      "weather_convection_measurements_parcel_method_check",
      sql`${table.parcelMethod} IN (
        'surface',
        'mixed_layer',
        'most_unstable',
        'provider_unspecified'
      )`,
    ),
    check(
      "weather_convection_measurements_calculation_method_check",
      sql`${table.calculationMethod} IN ('provider', 'project_profile')`,
    ),
    check(
      "weather_convection_measurements_method_version_check",
      sql`(${table.calculationMethodVersion} IS NULL
          OR length(trim(${table.calculationMethodVersion})) > 0)
        AND (
          ${table.calculationMethod} <> 'project_profile'
          OR ${table.calculationMethodVersion} IS NOT NULL
        )`,
    ),
    check(
      "weather_convection_measurements_layer_shape_check",
      sql`(
          ${table.layerBottomPressureFromGroundPa} IS NULL
          AND ${table.layerTopPressureFromGroundPa} IS NULL
        )
        OR (
          ${table.layerBottomPressureFromGroundPa} IS NOT NULL
          AND ${table.layerTopPressureFromGroundPa} IS NOT NULL
          AND ${table.layerBottomPressureFromGroundPa} >= 0
          AND ${table.layerTopPressureFromGroundPa} > ${table.layerBottomPressureFromGroundPa}
        )`,
    ),
    check(
      "weather_convection_measurements_cape_non_negative_check",
      sql`${table.capeJPerKg} IS NULL OR ${table.capeJPerKg} >= 0`,
    ),
    check(
      "weather_convection_measurements_cin_non_negative_check",
      sql`${table.cinMagnitudeJPerKg} IS NULL OR ${table.cinMagnitudeJPerKg} >= 0`,
    ),
  ],
);

export const weatherIntervalMeasurements = sqliteTable(
  "weather_interval_measurements",
  {
    id: integer("id").primaryKey(),
    weatherSampleId: integer("weather_sample_id")
      .notNull()
      .references(() => weatherSamples.id, { onDelete: "restrict" }),
    fieldCode: text("field_code").notNull(),
    component: text("component").notNull(),
    intervalStartUtc: text("interval_start_utc").notNull(),
    intervalEndUtc: text("interval_end_utc").notNull(),
    statisticType: text("statistic_type").notNull(),
    canonicalValue: real("canonical_value"),
    sourceStepStartHours: real("source_step_start_hours"),
    sourceStepEndHours: real("source_step_end_hours"),
  },
  (table) => [
    unique("weather_interval_measurements_identity_unique").on(
      table.weatherSampleId,
      table.fieldCode,
      table.component,
      table.statisticType,
      table.intervalStartUtc,
      table.intervalEndUtc,
    ),
    index("weather_interval_measurements_sample_interval_index").on(
      table.weatherSampleId,
      table.intervalStartUtc,
      table.intervalEndUtc,
    ),
    index("weather_interval_measurements_field_interval_index").on(
      table.fieldCode,
      table.intervalStartUtc,
      table.intervalEndUtc,
    ),
    check(
      "weather_interval_measurements_field_code_check",
      sql`${table.fieldCode} IN (
        'precipitation_amount_mm',
        'shortwave_radiation_w_m2',
        'surface_sensible_heat_flux_upward_w_m2',
        'surface_latent_heat_flux_upward_w_m2'
      )`,
    ),
    check(
      "weather_interval_measurements_component_check",
      sql`${table.component} IN ('total', 'convective', 'large_scale', 'not_applicable')`,
    ),
    check(
      "weather_interval_measurements_component_field_check",
      sql`(
          ${table.fieldCode} = 'precipitation_amount_mm'
          AND ${table.component} IN ('total', 'convective', 'large_scale')
        )
        OR (
          ${table.fieldCode} <> 'precipitation_amount_mm'
          AND ${table.component} = 'not_applicable'
        )`,
    ),
    check(
      "weather_interval_measurements_interval_start_shape_check",
      sql`${table.intervalStartUtc} GLOB '${sql.raw(utcTimestampGlob)}'`,
    ),
    check(
      "weather_interval_measurements_interval_end_shape_check",
      sql`${table.intervalEndUtc} GLOB '${sql.raw(utcTimestampGlob)}'`,
    ),
    check(
      "weather_interval_measurements_statistic_type_check",
      sql`${table.statisticType} IN ('instantaneous', 'interval_average', 'accumulation')`,
    ),
    check(
      "weather_interval_measurements_interval_semantics_check",
      sql`(
          ${table.statisticType} = 'instantaneous'
          AND ${table.intervalStartUtc} = ${table.intervalEndUtc}
        )
        OR (
          ${table.statisticType} IN ('interval_average', 'accumulation')
          AND ${table.intervalEndUtc} > ${table.intervalStartUtc}
        )`,
    ),
    check(
      "weather_interval_measurements_non_negative_fields_check",
      sql`${table.canonicalValue} IS NULL
        OR ${table.fieldCode} IN (
          'surface_sensible_heat_flux_upward_w_m2',
          'surface_latent_heat_flux_upward_w_m2'
        )
        OR ${table.canonicalValue} >= 0`,
    ),
    check(
      "weather_interval_measurements_source_step_shape_check",
      sql`(
          ${table.sourceStepStartHours} IS NULL
          AND ${table.sourceStepEndHours} IS NULL
        )
        OR (
          ${table.sourceStepStartHours} IS NOT NULL
          AND ${table.sourceStepEndHours} IS NOT NULL
          AND ${table.sourceStepStartHours} >= 0
          AND ${table.sourceStepEndHours} >= ${table.sourceStepStartHours}
        )`,
    ),
  ],
);
export const weatherFeatureSnapshots = sqliteTable(
  "weather_feature_snapshots",
  {
    id: integer("id").primaryKey(),
    weatherSampleId: integer("weather_sample_id")
      .notNull()
      .references(() => weatherSamples.id, { onDelete: "restrict" }),
    neighbourhoodFootprintId: integer("neighbourhood_footprint_id")
      .notNull()
      .references(() => weatherSamplingFootprints.id, { onDelete: "restrict" }),
    featureContractVersion: text("feature_contract_version").notNull(),
    inputFingerprintSha256: text("input_fingerprint_sha256").notNull(),
    derivedBoundaryLayerHeightAglM: real("derived_boundary_layer_height_agl_m"),
    boundaryLayerMethod: text("boundary_layer_method"),
    mixedLayerLclAglM: real("mixed_layer_lcl_agl_m"),
    mixedLayerLclMslM: real("mixed_layer_lcl_msl_m"),
    lclMethod: text("lcl_method"),
    surfaceBuoyancyFluxKinematicKMS: real("surface_buoyancy_flux_kinematic_k_m_s"),
    buoyancyFluxMethod: text("buoyancy_flux_method"),
    convectiveVelocityScaleMS: real("convective_velocity_scale_m_s"),
    convectiveVelocityMethod: text("convective_velocity_method"),
    temperatureLapseRateKPerKm: real("temperature_lapse_rate_k_per_km"),
    lapseLayerBaseAglM: real("lapse_layer_base_agl_m"),
    lapseLayerTopAglM: real("lapse_layer_top_agl_m"),
    windShearMSPerKm: real("wind_shear_m_s_per_km"),
    shearLayerBaseAglM: real("shear_layer_base_agl_m"),
    shearLayerTopAglM: real("shear_layer_top_agl_m"),
    neighbourhoodPressureGradientPaPerKm: real("neighbourhood_pressure_gradient_pa_per_km"),
    neighbourhoodLowLevelDivergenceSInverse: real("neighbourhood_low_level_divergence_s_inverse"),
    spatialMethodVersion: text("spatial_method_version"),
    createdByIngestionRunId: integer("created_by_ingestion_run_id")
      .notNull()
      .references(() => weatherIngestionRuns.id, { onDelete: "restrict" }),
  },
  (table) => [
    unique("weather_feature_snapshots_identity_unique").on(
      table.weatherSampleId,
      table.neighbourhoodFootprintId,
      table.featureContractVersion,
    ),
    index("weather_feature_snapshots_sample_index").on(table.weatherSampleId),
    index("weather_feature_snapshots_contract_index").on(table.featureContractVersion),
    index("weather_feature_snapshots_created_by_run_index").on(table.createdByIngestionRunId),
    check(
      "weather_feature_snapshots_contract_version_non_empty_check",
      sql`length(trim(${table.featureContractVersion})) > 0`,
    ),
    check(
      "weather_feature_snapshots_input_fingerprint_sha256_check",
      sql`length(${table.inputFingerprintSha256}) = 64
        AND ${table.inputFingerprintSha256} NOT GLOB '*[^0-9a-f]*'`,
    ),
    check(
      "weather_feature_snapshots_boundary_layer_shape_check",
      sql`(${table.derivedBoundaryLayerHeightAglM} IS NULL
          OR ${table.derivedBoundaryLayerHeightAglM} >= 0)
        AND (${table.boundaryLayerMethod} IS NULL
          OR length(trim(${table.boundaryLayerMethod})) > 0)
        AND (${table.derivedBoundaryLayerHeightAglM} IS NULL
          OR ${table.boundaryLayerMethod} IS NOT NULL)`,
    ),
    check(
      "weather_feature_snapshots_lcl_shape_check",
      sql`(${table.mixedLayerLclAglM} IS NULL OR ${table.mixedLayerLclAglM} >= 0)
        AND (${table.lclMethod} IS NULL OR length(trim(${table.lclMethod})) > 0)
        AND ((${table.mixedLayerLclAglM} IS NULL AND ${table.mixedLayerLclMslM} IS NULL)
          OR ${table.lclMethod} IS NOT NULL)`,
    ),
    check(
      "weather_feature_snapshots_buoyancy_flux_method_check",
      sql`(${table.buoyancyFluxMethod} IS NULL
          OR length(trim(${table.buoyancyFluxMethod})) > 0)
        AND (${table.surfaceBuoyancyFluxKinematicKMS} IS NULL
          OR ${table.buoyancyFluxMethod} IS NOT NULL)`,
    ),
    check(
      "weather_feature_snapshots_convective_velocity_shape_check",
      sql`(${table.convectiveVelocityScaleMS} IS NULL
          OR ${table.convectiveVelocityScaleMS} >= 0)
        AND (${table.convectiveVelocityMethod} IS NULL
          OR length(trim(${table.convectiveVelocityMethod})) > 0)
        AND (${table.convectiveVelocityScaleMS} IS NULL
          OR ${table.convectiveVelocityMethod} IS NOT NULL)`,
    ),
    check(
      "weather_feature_snapshots_lapse_layer_shape_check",
      sql`(
          ${table.temperatureLapseRateKPerKm} IS NULL
          AND ${table.lapseLayerBaseAglM} IS NULL
          AND ${table.lapseLayerTopAglM} IS NULL
        )
        OR (
          ${table.temperatureLapseRateKPerKm} IS NOT NULL
          AND ${table.lapseLayerBaseAglM} IS NOT NULL
          AND ${table.lapseLayerTopAglM} IS NOT NULL
          AND ${table.lapseLayerBaseAglM} >= 0
          AND ${table.lapseLayerTopAglM} > ${table.lapseLayerBaseAglM}
        )`,
    ),
    check(
      "weather_feature_snapshots_shear_layer_shape_check",
      sql`(
          ${table.windShearMSPerKm} IS NULL
          AND ${table.shearLayerBaseAglM} IS NULL
          AND ${table.shearLayerTopAglM} IS NULL
        )
        OR (
          ${table.windShearMSPerKm} IS NOT NULL
          AND ${table.shearLayerBaseAglM} IS NOT NULL
          AND ${table.shearLayerTopAglM} IS NOT NULL
          AND ${table.windShearMSPerKm} >= 0
          AND ${table.shearLayerBaseAglM} >= 0
          AND ${table.shearLayerTopAglM} > ${table.shearLayerBaseAglM}
        )`,
    ),
    check(
      "weather_feature_snapshots_spatial_method_version_non_empty_check",
      sql`${table.spatialMethodVersion} IS NULL
        OR length(trim(${table.spatialMethodVersion})) > 0`,
    ),
  ],
);

export const weatherFieldProvenance = sqliteTable(
  "weather_field_provenance",
  {
    id: integer("id").primaryKey(),
    weatherSampleId: integer("weather_sample_id").references(() => weatherSamples.id, {
      onDelete: "restrict",
    }),
    convectionMeasurementId: integer("convection_measurement_id").references(
      () => weatherConvectionMeasurements.id,
      { onDelete: "restrict" },
    ),
    intervalMeasurementId: integer("interval_measurement_id").references(
      () => weatherIntervalMeasurements.id,
      { onDelete: "restrict" },
    ),
    profileLevelId: integer("profile_level_id").references(() => weatherProfileLevels.id, {
      onDelete: "restrict",
    }),
    featureSnapshotId: integer("feature_snapshot_id").references(() => weatherFeatureSnapshots.id, {
      onDelete: "restrict",
    }),
    fieldCode: text("field_code").notNull(),
    fieldVariant: text("field_variant").notNull().default("canonical"),
    qualityState: text("quality_state").notNull(),
    sourceReferenceAtUtc: text("source_reference_at_utc"),
    nativeFieldName: text("native_field_name"),
    nativeUnit: text("native_unit"),
    nativeValue: real("native_value"),
    nativeSignConvention: text("native_sign_convention"),
    nativeStepType: text("native_step_type"),
    stepStartHours: real("step_start_hours"),
    stepEndHours: real("step_end_hours"),
    statisticType: text("statistic_type"),
    normalizationMethod: text("normalization_method"),
    normalizationVersion: text("normalization_version"),
    derivationMethod: text("derivation_method"),
    derivationVersion: text("derivation_version"),
    rawArtifactKey: text("raw_artifact_key"),
    nativeMessageReference: text("native_message_reference"),
  },
  (table) => [
    uniqueIndex("weather_field_provenance_sample_field_unique")
      .on(table.weatherSampleId, table.fieldCode, table.fieldVariant)
      .where(sql`${table.weatherSampleId} IS NOT NULL`),
    uniqueIndex("weather_field_provenance_convection_field_unique")
      .on(table.convectionMeasurementId, table.fieldCode, table.fieldVariant)
      .where(sql`${table.convectionMeasurementId} IS NOT NULL`),
    uniqueIndex("weather_field_provenance_interval_field_unique")
      .on(table.intervalMeasurementId, table.fieldCode, table.fieldVariant)
      .where(sql`${table.intervalMeasurementId} IS NOT NULL`),
    uniqueIndex("weather_field_provenance_profile_field_unique")
      .on(table.profileLevelId, table.fieldCode, table.fieldVariant)
      .where(sql`${table.profileLevelId} IS NOT NULL`),
    uniqueIndex("weather_field_provenance_feature_field_unique")
      .on(table.featureSnapshotId, table.fieldCode, table.fieldVariant)
      .where(sql`${table.featureSnapshotId} IS NOT NULL`),
    index("weather_field_provenance_field_quality_index").on(table.fieldCode, table.qualityState),
    index("weather_field_provenance_source_reference_index").on(table.sourceReferenceAtUtc),
    check(
      "weather_field_provenance_exactly_one_owner_check",
      sql`(
          (${table.weatherSampleId} IS NOT NULL)
          + (${table.convectionMeasurementId} IS NOT NULL)
          + (${table.intervalMeasurementId} IS NOT NULL)
          + (${table.profileLevelId} IS NOT NULL)
          + (${table.featureSnapshotId} IS NOT NULL)
        ) = 1`,
    ),
    check(
      "weather_field_provenance_field_code_non_empty_check",
      sql`length(trim(${table.fieldCode})) > 0`,
    ),
    check(
      "weather_field_provenance_field_variant_non_empty_check",
      sql`length(trim(${table.fieldVariant})) > 0`,
    ),
    check(
      "weather_field_provenance_quality_state_check",
      sql`${table.qualityState} IN (
        'real',
        'derived',
        'missing',
        'sentinel_missing',
        'invalid_payload'
      )`,
    ),
    check(
      "weather_field_provenance_source_reference_at_utc_shape_check",
      sql`${table.sourceReferenceAtUtc} IS NULL
        OR ${table.sourceReferenceAtUtc} GLOB '${sql.raw(utcTimestampGlob)}'`,
    ),
    check(
      "weather_field_provenance_optional_text_non_empty_check",
      sql`(${table.nativeFieldName} IS NULL OR length(trim(${table.nativeFieldName})) > 0)
        AND (${table.nativeUnit} IS NULL OR length(trim(${table.nativeUnit})) > 0)
        AND (${table.nativeSignConvention} IS NULL
          OR length(trim(${table.nativeSignConvention})) > 0)
        AND (${table.nativeStepType} IS NULL OR length(trim(${table.nativeStepType})) > 0)
        AND (${table.statisticType} IS NULL OR length(trim(${table.statisticType})) > 0)
        AND (${table.rawArtifactKey} IS NULL OR length(trim(${table.rawArtifactKey})) > 0)
        AND (${table.nativeMessageReference} IS NULL
          OR length(trim(${table.nativeMessageReference})) > 0)`,
    ),
    check(
      "weather_field_provenance_step_shape_check",
      sql`(
          ${table.stepStartHours} IS NULL
          AND ${table.stepEndHours} IS NULL
        )
        OR (
          ${table.stepStartHours} IS NOT NULL
          AND ${table.stepEndHours} IS NOT NULL
          AND ${table.stepStartHours} >= 0
          AND ${table.stepEndHours} >= ${table.stepStartHours}
        )`,
    ),
    check(
      "weather_field_provenance_normalization_pair_check",
      sql`(
          ${table.normalizationMethod} IS NULL
          AND ${table.normalizationVersion} IS NULL
        )
        OR (
          ${table.normalizationMethod} IS NOT NULL
          AND length(trim(${table.normalizationMethod})) > 0
          AND ${table.normalizationVersion} IS NOT NULL
          AND length(trim(${table.normalizationVersion})) > 0
        )`,
    ),
    check(
      "weather_field_provenance_derivation_pair_check",
      sql`(
          ${table.derivationMethod} IS NULL
          AND ${table.derivationVersion} IS NULL
        )
        OR (
          ${table.derivationMethod} IS NOT NULL
          AND length(trim(${table.derivationMethod})) > 0
          AND ${table.derivationVersion} IS NOT NULL
          AND length(trim(${table.derivationVersion})) > 0
        )`,
    ),
    check(
      "weather_field_provenance_missing_native_value_check",
      sql`${table.qualityState} NOT IN ('missing', 'sentinel_missing')
        OR ${table.nativeValue} IS NULL`,
    ),
  ],
);
