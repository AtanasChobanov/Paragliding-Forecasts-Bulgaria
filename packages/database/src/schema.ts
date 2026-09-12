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
    productRunId: integer("product_run_id")
      .notNull()
      .references(() => weatherProductRuns.id, { onDelete: "restrict" }),
    targetLocalDate: text("target_local_date").notNull(),
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
    featureManifestPath: text("feature_manifest_path"),
    featureManifestSha256: text("feature_manifest_sha256"),
    persistenceInputSha256: text("persistence_input_sha256"),
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
    index("weather_ingestion_runs_product_target_date_index").on(
      table.productRunId,
      table.targetLocalDate,
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
      "weather_ingestion_runs_target_local_date_shape_check",
      sql`${table.targetLocalDate} GLOB '${sql.raw(localDateGlob)}'`,
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
      "weather_ingestion_runs_feature_manifest_path_check",
      sql`${table.featureManifestPath} IS NULL
        OR (
          ${table.featureManifestPath} LIKE 'data/interim/%'
          AND ${table.featureManifestPath} NOT LIKE '%..%'
        )`,
    ),
    check(
      "weather_ingestion_runs_feature_manifest_sha256_check",
      sql`${table.featureManifestSha256} IS NULL
        OR (
          length(${table.featureManifestSha256}) = 64
          AND ${table.featureManifestSha256} NOT GLOB '*[^0-9a-f]*'
        )`,
    ),
    check(
      "weather_ingestion_runs_persistence_input_sha256_check",
      sql`${table.persistenceInputSha256} IS NULL
        OR (
          length(${table.persistenceInputSha256}) = 64
          AND ${table.persistenceInputSha256} NOT GLOB '*[^0-9a-f]*'
        )`,
    ),
    check(
      "weather_ingestion_runs_feature_persistence_lifecycle_check",
      sql`(
          ${table.status} IN ('running', 'failed')
          AND ${table.featureManifestPath} IS NULL
          AND ${table.featureManifestSha256} IS NULL
          AND ${table.persistenceInputSha256} IS NULL
        )
        OR (
          ${table.status} = 'succeeded'
          AND ${table.featureManifestPath} IS NOT NULL
          AND ${table.featureManifestSha256} IS NOT NULL
          AND ${table.persistenceInputSha256} IS NOT NULL
        )`,
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
  },
  (table) => [
    unique("weather_product_runs_source_product_unique").on(table.sourceId, table.sourceProductKey),
    index("weather_product_runs_source_reference_at_index").on(
      table.sourceId,
      desc(table.referenceAtUtc),
    ),
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
  ],
);

export const weatherProductValidTimes = sqliteTable(
  "weather_product_valid_times",
  {
    id: integer("id").primaryKey(),
    productRunId: integer("product_run_id")
      .notNull()
      .references(() => weatherProductRuns.id, { onDelete: "restrict" }),
    validAtUtc: text("valid_at_utc").notNull(),
    leadHours: real("lead_hours"),
  },
  (table) => [
    unique("weather_product_valid_times_product_valid_unique").on(
      table.productRunId,
      table.validAtUtc,
    ),
    index("weather_product_valid_times_valid_at_index").on(table.validAtUtc),
    check(
      "weather_product_valid_times_valid_at_utc_shape_check",
      sql`${table.validAtUtc} GLOB '${sql.raw(utcTimestampGlob)}'`,
    ),
    check(
      "weather_product_valid_times_lead_hours_non_negative_check",
      sql`${table.leadHours} IS NULL OR ${table.leadHours} >= 0`,
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
  },
  (table) => [
    unique("weather_grids_source_key_unique").on(table.sourceId, table.gridKey),
    check("weather_grids_grid_key_non_empty_check", sql`length(trim(${table.gridKey})) > 0`),
    check(
      "weather_grids_grid_key_supported_check",
      sql`${table.gridKey} IN ('gfs_0p25_global', 'era5_0p25_global')`,
    ),
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
  },
  (table) => [
    unique("weather_grid_points_grid_coordinate_unique").on(
      table.gridId,
      table.latitudeDeg,
      table.longitudeDeg,
    ),
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
  },
  (table) => [
    uniqueIndex("weather_sampling_footprints_point_identity_unique")
      .on(table.siteId, table.gridId, table.samplingMethod, table.samplingMethodVersion)
      .where(sql`${table.purpose} = 'point'`),
    uniqueIndex("weather_sampling_footprints_neighbourhood_identity_unique")
      .on(
        table.siteId,
        table.gridId,
        table.samplingMethod,
        table.samplingMethodVersion,
        table.radiusKm,
      )
      .where(sql`${table.purpose} = 'neighbourhood'`),
    index("weather_sampling_footprints_site_purpose_index").on(table.siteId, table.purpose),
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
export const weatherPointSamples = sqliteTable(
  "weather_point_samples",
  {
    id: integer("id").primaryKey(),
    ingestionRunId: integer("ingestion_run_id")
      .notNull()
      .references(() => weatherIngestionRuns.id, { onDelete: "restrict" }),
    productValidTimeId: integer("product_valid_time_id")
      .notNull()
      .references(() => weatherProductValidTimes.id, { onDelete: "restrict" }),
    pointFootprintId: integer("point_footprint_id")
      .notNull()
      .references(() => weatherSamplingFootprints.id, { onDelete: "restrict" }),
    coverageStatus: text("coverage_status").notNull(),
    airTemperature2mK: real("air_temperature_2m_k"),
    dewPointTemperature2mK: real("dew_point_temperature_2m_k"),
    relativeHumidity2mPercent: real("relative_humidity_2m_percent"),
    specificHumidity2mKgPerKg: real("specific_humidity_2m_kg_per_kg"),
    surfacePressurePa: real("surface_pressure_pa"),
    meanSeaLevelPressurePa: real("mean_sea_level_pressure_pa"),
    windU10mMS: real("wind_u_10m_m_s"),
    windV10mMS: real("wind_v_10m_m_s"),
    windSpeed10mMS: real("wind_speed_10m_m_s"),
    windDirection10mDegreesFromNorth: real("wind_direction_10m_degrees_from_north"),
    providerBoundaryLayerHeightAglM: real("provider_boundary_layer_height_agl_m"),
    providerBoundaryLayerMethod: text("provider_boundary_layer_method"),
    providerCloudBaseAglM: real("provider_cloud_base_agl_m"),
    providerCloudBaseMethod: text("provider_cloud_base_method"),
    mixedLayerLclAglM: real("mixed_layer_lcl_agl_m"),
    pblMinusLclM: real("pbl_minus_lcl_m"),
    surfaceBuoyancyFluxKinematicM2S3: real("surface_buoyancy_flux_kinematic_m2_s3"),
    convectiveVelocityScaleMS: real("convective_velocity_scale_m_s"),
    totalColumnWaterVapourKgM2: real("total_column_water_vapour_kg_m2"),
    totalCloudCoverPercent: real("total_cloud_cover_percent"),
    lowCloudCoverPercent: real("low_cloud_cover_percent"),
    midCloudCoverPercent: real("mid_cloud_cover_percent"),
    highCloudCoverPercent: real("high_cloud_cover_percent"),
  },
  (table) => [
    unique("weather_point_samples_run_footprint_valid_time_unique").on(
      table.ingestionRunId,
      table.pointFootprintId,
      table.productValidTimeId,
    ),
    index("weather_point_samples_footprint_index").on(table.pointFootprintId),
    index("weather_point_samples_run_valid_time_index").on(
      table.ingestionRunId,
      table.productValidTimeId,
    ),
    index("weather_point_samples_coverage_status_index").on(table.coverageStatus),
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
      "weather_samples_specific_humidity_2m_range_check",
      sql`${table.specificHumidity2mKgPerKg} IS NULL
        OR ${table.specificHumidity2mKgPerKg} BETWEEN 0 AND 1`,
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
      "weather_samples_boundary_layer_agl_non_negative_check",
      sql`${table.providerBoundaryLayerHeightAglM} IS NULL
        OR ${table.providerBoundaryLayerHeightAglM} >= 0`,
    ),
    check(
      "weather_samples_boundary_layer_method_shape_check",
      sql`(${table.providerBoundaryLayerMethod} IS NULL
          OR length(trim(${table.providerBoundaryLayerMethod})) > 0)
        AND ((${table.providerBoundaryLayerHeightAglM} IS NULL
            AND ${table.providerBoundaryLayerMethod} IS NULL)
          OR (${table.providerBoundaryLayerHeightAglM} IS NOT NULL
            AND ${table.providerBoundaryLayerMethod} IS NOT NULL))`,
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
            AND ${table.providerCloudBaseMethod} IS NULL)
          OR (${table.providerCloudBaseAglM} IS NOT NULL
            AND ${table.providerCloudBaseMethod} IS NOT NULL))`,
    ),
    check(
      "weather_samples_s08_derived_non_negative_check",
      sql`(${table.mixedLayerLclAglM} IS NULL OR ${table.mixedLayerLclAglM} >= 0)
        AND (${table.convectiveVelocityScaleMS} IS NULL OR ${table.convectiveVelocityScaleMS} >= 0)`,
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

export const weatherPointProfileLevels = sqliteTable(
  "weather_point_profile_levels",
  {
    id: integer("id").primaryKey(),
    weatherPointSampleId: integer("weather_point_sample_id")
      .notNull()
      .references(() => weatherPointSamples.id, { onDelete: "restrict" }),
    pressurePa: real("pressure_pa").notNull(),
    geopotentialHeightMslM: real("geopotential_height_msl_m"),
    levelHeightSiteAglM: real("level_height_site_agl_m"),
    airTemperatureK: real("air_temperature_k"),
    dewPointTemperatureK: real("dew_point_temperature_k"),
    relativeHumidityPercent: real("relative_humidity_percent"),
    specificHumidityKgPerKg: real("specific_humidity_kg_per_kg"),
    windUMS: real("wind_u_m_s"),
    windVMS: real("wind_v_m_s"),
    windSpeedMS: real("wind_speed_m_s"),
    windDirectionDegreesFromNorth: real("wind_direction_degrees_from_north"),
    verticalVelocityPaS: real("vertical_velocity_pa_s"),
  },
  (table) => [
    unique("weather_profile_levels_sample_pressure_unique").on(
      table.weatherPointSampleId,
      table.pressurePa,
    ),
    index("weather_profile_levels_pressure_sample_index").on(
      table.pressurePa,
      table.weatherPointSampleId,
    ),
    check("weather_profile_levels_pressure_positive_check", sql`${table.pressurePa} > 0`),
    check(
      "weather_profile_levels_height_agl_non_negative_check",
      sql`${table.levelHeightSiteAglM} IS NULL OR ${table.levelHeightSiteAglM} >= 0`,
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

export const weatherPointConvectionMeasurements = sqliteTable(
  "weather_point_convection_measurements",
  {
    id: integer("id").primaryKey(),
    weatherPointSampleId: integer("weather_point_sample_id")
      .notNull()
      .references(() => weatherPointSamples.id, { onDelete: "restrict" }),
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
      .on(table.weatherPointSampleId, table.parcelMethod, table.calculationMethod)
      .where(
        sql`${table.layerBottomPressureFromGroundPa} IS NULL
          AND ${table.layerTopPressureFromGroundPa} IS NULL
          AND ${table.calculationMethodVersion} IS NULL`,
      ),
    uniqueIndex("weather_convection_no_layer_version_unique")
      .on(
        table.weatherPointSampleId,
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
        table.weatherPointSampleId,
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
        table.weatherPointSampleId,
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
    index("weather_point_convection_measurements_sample_index").on(table.weatherPointSampleId),
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

export const weatherPointIntervalMeasurements = sqliteTable(
  "weather_point_interval_measurements",
  {
    id: integer("id").primaryKey(),
    weatherPointSampleId: integer("weather_point_sample_id")
      .notNull()
      .references(() => weatherPointSamples.id, { onDelete: "restrict" }),
    fieldCode: text("field_code").notNull(),
    component: text("component").notNull(),
    intervalStartUtc: text("interval_start_utc").notNull(),
    intervalEndUtc: text("interval_end_utc").notNull(),
    statisticType: text("statistic_type").notNull(),
    canonicalValue: real("canonical_value"),
  },
  (table) => [
    unique("weather_interval_measurements_identity_unique").on(
      table.weatherPointSampleId,
      table.fieldCode,
      table.component,
      table.statisticType,
      table.intervalStartUtc,
      table.intervalEndUtc,
    ),
    index("weather_interval_measurements_sample_interval_index").on(
      table.weatherPointSampleId,
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
  ],
);
export const weatherDailyFeatureSnapshots = sqliteTable(
  "weather_daily_feature_snapshots",
  {
    id: integer("id").primaryKey(),
    ingestionRunId: integer("ingestion_run_id")
      .notNull()
      .references(() => weatherIngestionRuns.id, { onDelete: "restrict" }),
    pointFootprintId: integer("point_footprint_id")
      .notNull()
      .references(() => weatherSamplingFootprints.id, { onDelete: "restrict" }),
    neighbourhoodFootprintId: integer("neighbourhood_footprint_id")
      .notNull()
      .references(() => weatherSamplingFootprints.id, { onDelete: "restrict" }),
    featureContractVersion: text("feature_contract_version").notNull(),
    airTemperature2mMeanK: real("air_temperature_2m_mean_k"),
    airTemperature2mMinK: real("air_temperature_2m_min_k"),
    airTemperature2mMaxK: real("air_temperature_2m_max_k"),
    dewPointTemperature2mMeanK: real("dew_point_temperature_2m_mean_k"),
    relativeHumidity2mMeanPercent: real("relative_humidity_2m_mean_percent"),
    relativeHumidity2mMaxPercent: real("relative_humidity_2m_max_percent"),
    surfacePressureMeanPa: real("surface_pressure_mean_pa"),
    meanSeaLevelPressureMeanPa: real("mean_sea_level_pressure_mean_pa"),
    windU10mMeanMS: real("wind_u_10m_mean_m_s"),
    windV10mMeanMS: real("wind_v_10m_mean_m_s"),
    windSpeed10mMeanMS: real("wind_speed_10m_mean_m_s"),
    windSpeed10mMaxMS: real("wind_speed_10m_max_m_s"),
    windDirection10mMeanDegreesFromNorth: real("wind_direction_10m_mean_degrees_from_north"),
    providerBoundaryLayerHeightAglMeanM: real("provider_boundary_layer_height_agl_mean_m"),
    providerBoundaryLayerHeightAglMaxM: real("provider_boundary_layer_height_agl_max_m"),
    providerCloudBaseAglMeanM: real("provider_cloud_base_agl_mean_m"),
    providerCloudBaseAglMinM: real("provider_cloud_base_agl_min_m"),
    providerCloudBaseAglMaxM: real("provider_cloud_base_agl_max_m"),
    mixedLayerLclAglMeanM: real("mixed_layer_lcl_agl_mean_m"),
    mixedLayerLclAglMinM: real("mixed_layer_lcl_agl_min_m"),
    mixedLayerLclAglMaxM: real("mixed_layer_lcl_agl_max_m"),
    pblMinusLclMeanM: real("pbl_minus_lcl_mean_m"),
    pblMinusLclMaxM: real("pbl_minus_lcl_max_m"),
    surfaceBuoyancyFluxKinematicMeanM2S3: real("surface_buoyancy_flux_kinematic_mean_m2_s3"),
    surfaceBuoyancyFluxKinematicMaxM2S3: real("surface_buoyancy_flux_kinematic_max_m2_s3"),
    convectiveVelocityScaleMeanMS: real("convective_velocity_scale_mean_m_s"),
    convectiveVelocityScaleMaxMS: real("convective_velocity_scale_max_m_s"),
    totalColumnWaterVapourMeanKgM2: real("total_column_water_vapour_mean_kg_m2"),
    totalCloudCoverMeanPercent: real("total_cloud_cover_mean_percent"),
    totalCloudCoverMaxPercent: real("total_cloud_cover_max_percent"),
    lowCloudCoverMeanPercent: real("low_cloud_cover_mean_percent"),
    lowCloudCoverMaxPercent: real("low_cloud_cover_max_percent"),
    midCloudCoverMeanPercent: real("mid_cloud_cover_mean_percent"),
    highCloudCoverMeanPercent: real("high_cloud_cover_mean_percent"),
    precipitationTotalMm: real("precipitation_total_mm"),
    precipitationMaxHourlyMm: real("precipitation_max_hourly_mm"),
    shortwaveRadiationMeanWM2: real("shortwave_radiation_mean_w_m2"),
    shortwaveRadiationMaxWM2: real("shortwave_radiation_max_w_m2"),
    surfaceSensibleHeatFluxMeanWM2: real("surface_sensible_heat_flux_mean_w_m2"),
    surfaceLatentHeatFluxMeanWM2: real("surface_latent_heat_flux_mean_w_m2"),
    capeMaxJPerKg: real("cape_max_j_per_kg"),
    cinMagnitudeMaxJPerKg: real("cin_magnitude_max_j_per_kg"),
    neighbourhoodPressureGradientMeanPaPerKm: real(
      "neighbourhood_pressure_gradient_mean_pa_per_km",
    ),
    neighbourhoodPressureGradientMaxPaPerKm: real("neighbourhood_pressure_gradient_max_pa_per_km"),
    neighbourhoodLowLevelDivergenceMeanSInverse: real(
      "neighbourhood_low_level_divergence_mean_s_inverse",
    ),
    neighbourhoodLowLevelDivergenceMinSInverse: real(
      "neighbourhood_low_level_divergence_min_s_inverse",
    ),
  },
  (table) => [
    unique("weather_daily_feature_snapshots_identity_unique").on(
      table.ingestionRunId,
      table.pointFootprintId,
      table.featureContractVersion,
    ),
    index("weather_daily_feature_snapshots_contract_index").on(table.featureContractVersion),
    index("weather_daily_feature_snapshots_point_footprint_index").on(table.pointFootprintId),
    check(
      "weather_daily_feature_snapshots_contract_version_non_empty_check",
      sql`length(trim(${table.featureContractVersion})) > 0`,
    ),
    check(
      "weather_daily_feature_snapshots_temperature_positive_check",
      sql`(${table.airTemperature2mMeanK} IS NULL OR ${table.airTemperature2mMeanK} > 0)
        AND (${table.airTemperature2mMinK} IS NULL OR ${table.airTemperature2mMinK} > 0)
        AND (${table.airTemperature2mMaxK} IS NULL OR ${table.airTemperature2mMaxK} > 0)
        AND (${table.dewPointTemperature2mMeanK} IS NULL OR ${table.dewPointTemperature2mMeanK} > 0)`,
    ),
    check(
      "weather_daily_feature_snapshots_temperature_order_check",
      sql`${table.airTemperature2mMinK} IS NULL OR ${table.airTemperature2mMaxK} IS NULL
        OR ${table.airTemperature2mMaxK} >= ${table.airTemperature2mMinK}`,
    ),
    check(
      "weather_daily_feature_snapshots_s08_derived_shape_check",
      sql`(${table.mixedLayerLclAglMeanM} IS NULL OR ${table.mixedLayerLclAglMeanM} >= 0)
        AND (${table.mixedLayerLclAglMinM} IS NULL OR ${table.mixedLayerLclAglMinM} >= 0)
        AND (${table.mixedLayerLclAglMaxM} IS NULL OR ${table.mixedLayerLclAglMaxM} >= 0)
        AND (${table.mixedLayerLclAglMinM} IS NULL OR ${table.mixedLayerLclAglMeanM} IS NULL
          OR ${table.mixedLayerLclAglMinM} <= ${table.mixedLayerLclAglMeanM})
        AND (${table.mixedLayerLclAglMeanM} IS NULL OR ${table.mixedLayerLclAglMaxM} IS NULL
          OR ${table.mixedLayerLclAglMeanM} <= ${table.mixedLayerLclAglMaxM})
        AND (${table.convectiveVelocityScaleMeanMS} IS NULL OR ${table.convectiveVelocityScaleMeanMS} >= 0)
        AND (${table.convectiveVelocityScaleMaxMS} IS NULL OR ${table.convectiveVelocityScaleMaxMS} >= 0)
        AND (${table.convectiveVelocityScaleMeanMS} IS NULL OR ${table.convectiveVelocityScaleMaxMS} IS NULL
          OR ${table.convectiveVelocityScaleMeanMS} <= ${table.convectiveVelocityScaleMaxMS})`,
    ),
    check(
      "weather_daily_feature_snapshots_percent_range_check",
      sql`(${table.relativeHumidity2mMeanPercent} IS NULL OR ${table.relativeHumidity2mMeanPercent} BETWEEN 0 AND 100)
        AND (${table.relativeHumidity2mMaxPercent} IS NULL OR ${table.relativeHumidity2mMaxPercent} BETWEEN 0 AND 100)
        AND (${table.totalCloudCoverMeanPercent} IS NULL OR ${table.totalCloudCoverMeanPercent} BETWEEN 0 AND 100)
        AND (${table.totalCloudCoverMaxPercent} IS NULL OR ${table.totalCloudCoverMaxPercent} BETWEEN 0 AND 100)
        AND (${table.lowCloudCoverMeanPercent} IS NULL OR ${table.lowCloudCoverMeanPercent} BETWEEN 0 AND 100)
        AND (${table.lowCloudCoverMaxPercent} IS NULL OR ${table.lowCloudCoverMaxPercent} BETWEEN 0 AND 100)
        AND (${table.midCloudCoverMeanPercent} IS NULL OR ${table.midCloudCoverMeanPercent} BETWEEN 0 AND 100)
        AND (${table.highCloudCoverMeanPercent} IS NULL OR ${table.highCloudCoverMeanPercent} BETWEEN 0 AND 100)`,
    ),
    check(
      "weather_daily_feature_snapshots_direction_range_check",
      sql`${table.windDirection10mMeanDegreesFromNorth} IS NULL OR (${table.windDirection10mMeanDegreesFromNorth} >= 0 AND ${table.windDirection10mMeanDegreesFromNorth} < 360)`,
    ),
    check(
      "weather_daily_feature_snapshots_non_negative_check",
      sql`(${table.surfacePressureMeanPa} IS NULL OR ${table.surfacePressureMeanPa} > 0)
        AND (${table.meanSeaLevelPressureMeanPa} IS NULL OR ${table.meanSeaLevelPressureMeanPa} > 0)
        AND (${table.windSpeed10mMeanMS} IS NULL OR ${table.windSpeed10mMeanMS} >= 0)
        AND (${table.windSpeed10mMaxMS} IS NULL OR ${table.windSpeed10mMaxMS} >= 0)
        AND (${table.providerBoundaryLayerHeightAglMeanM} IS NULL OR ${table.providerBoundaryLayerHeightAglMeanM} >= 0)
        AND (${table.providerBoundaryLayerHeightAglMaxM} IS NULL OR ${table.providerBoundaryLayerHeightAglMaxM} >= 0)
        AND (${table.providerCloudBaseAglMeanM} IS NULL OR ${table.providerCloudBaseAglMeanM} >= 0)
        AND (${table.providerCloudBaseAglMinM} IS NULL OR ${table.providerCloudBaseAglMinM} >= 0)
        AND (${table.providerCloudBaseAglMaxM} IS NULL OR ${table.providerCloudBaseAglMaxM} >= 0)
        AND (${table.totalColumnWaterVapourMeanKgM2} IS NULL OR ${table.totalColumnWaterVapourMeanKgM2} >= 0)
        AND (${table.precipitationTotalMm} IS NULL OR ${table.precipitationTotalMm} >= 0)
        AND (${table.precipitationMaxHourlyMm} IS NULL OR ${table.precipitationMaxHourlyMm} >= 0)
        AND (${table.shortwaveRadiationMeanWM2} IS NULL OR ${table.shortwaveRadiationMeanWM2} >= 0)
        AND (${table.shortwaveRadiationMaxWM2} IS NULL OR ${table.shortwaveRadiationMaxWM2} >= 0)
        AND (${table.capeMaxJPerKg} IS NULL OR ${table.capeMaxJPerKg} >= 0)
        AND (${table.cinMagnitudeMaxJPerKg} IS NULL OR ${table.cinMagnitudeMaxJPerKg} >= 0)
        AND (${table.neighbourhoodPressureGradientMeanPaPerKm} IS NULL OR ${table.neighbourhoodPressureGradientMeanPaPerKm} >= 0)
        AND (${table.neighbourhoodPressureGradientMaxPaPerKm} IS NULL OR ${table.neighbourhoodPressureGradientMaxPaPerKm} >= 0)`,
    ),
  ],
);

export const weatherDailyFeatureSnapshotInputs = sqliteTable(
  "weather_daily_feature_snapshot_inputs",
  {
    dailyFeatureSnapshotId: integer("daily_feature_snapshot_id")
      .notNull()
      .references(() => weatherDailyFeatureSnapshots.id, { onDelete: "restrict" }),
    weatherPointSampleId: integer("weather_point_sample_id")
      .notNull()
      .references(() => weatherPointSamples.id, { onDelete: "restrict" }),
  },
  (table) => [
    primaryKey({
      columns: [table.dailyFeatureSnapshotId, table.weatherPointSampleId],
      name: "weather_daily_feature_snapshot_inputs_pk",
    }),
    index("weather_daily_feature_snapshot_inputs_sample_index").on(table.weatherPointSampleId),
  ],
);

export const weatherDailyFeatureProfileLayers = sqliteTable(
  "weather_daily_feature_profile_layers",
  {
    id: integer("id").primaryKey(),
    dailyFeatureSnapshotId: integer("daily_feature_snapshot_id")
      .notNull()
      .references(() => weatherDailyFeatureSnapshots.id, { onDelete: "restrict" }),
    layerBaseAglM: real("layer_base_agl_m").notNull(),
    layerTopAglM: real("layer_top_agl_m").notNull(),
    temperatureLapseRateMeanKPerKm: real("temperature_lapse_rate_mean_k_per_km"),
    temperatureLapseRateMaxKPerKm: real("temperature_lapse_rate_max_k_per_km"),
    relativeHumidityMeanPercent: real("relative_humidity_mean_percent"),
    specificHumidityMeanKgPerKg: real("specific_humidity_mean_kg_per_kg"),
    windUMeanMS: real("wind_u_mean_m_s"),
    windVMeanMS: real("wind_v_mean_m_s"),
    windSpeedMeanMS: real("wind_speed_mean_m_s"),
    windSpeedMaxMS: real("wind_speed_max_m_s"),
    windDirectionMeanDegreesFromNorth: real("wind_direction_mean_degrees_from_north"),
    windShearMeanMSPerKm: real("wind_shear_mean_m_s_per_km"),
    windShearMaxMSPerKm: real("wind_shear_max_m_s_per_km"),
    verticalVelocityMeanPaS: real("vertical_velocity_mean_pa_s"),
    verticalVelocityMinPaS: real("vertical_velocity_min_pa_s"),
  },
  (table) => [
    unique("weather_daily_feature_profile_layers_identity_unique").on(
      table.dailyFeatureSnapshotId,
      table.layerBaseAglM,
      table.layerTopAglM,
    ),
    check(
      "weather_daily_feature_profile_layers_bounds_check",
      sql`${table.layerBaseAglM} >= 0 AND ${table.layerTopAglM} > ${table.layerBaseAglM}`,
    ),
    check(
      "weather_daily_feature_profile_layers_humidity_range_check",
      sql`(${table.relativeHumidityMeanPercent} IS NULL OR ${table.relativeHumidityMeanPercent} BETWEEN 0 AND 100)
        AND (${table.specificHumidityMeanKgPerKg} IS NULL OR ${table.specificHumidityMeanKgPerKg} >= 0)`,
    ),
    check(
      "weather_daily_feature_profile_layers_wind_shape_check",
      sql`(${table.windSpeedMeanMS} IS NULL OR ${table.windSpeedMeanMS} >= 0)
        AND (${table.windSpeedMaxMS} IS NULL OR ${table.windSpeedMaxMS} >= 0)
        AND (${table.windDirectionMeanDegreesFromNorth} IS NULL OR (${table.windDirectionMeanDegreesFromNorth} >= 0 AND ${table.windDirectionMeanDegreesFromNorth} < 360))
        AND (${table.windShearMeanMSPerKm} IS NULL OR ${table.windShearMeanMSPerKm} >= 0)
        AND (${table.windShearMaxMSPerKm} IS NULL OR ${table.windShearMaxMSPerKm} >= 0)`,
    ),
  ],
);

export const weatherFieldProvenance = sqliteTable(
  "weather_field_provenance",
  {
    id: integer("id").primaryKey(),
    weatherPointSampleId: integer("weather_point_sample_id").references(
      () => weatherPointSamples.id,
      {
        onDelete: "restrict",
      },
    ),
    pointConvectionMeasurementId: integer("point_convection_measurement_id").references(
      () => weatherPointConvectionMeasurements.id,
      { onDelete: "restrict" },
    ),
    pointIntervalMeasurementId: integer("point_interval_measurement_id").references(
      () => weatherPointIntervalMeasurements.id,
      { onDelete: "restrict" },
    ),
    pointProfileLevelId: integer("point_profile_level_id").references(
      () => weatherPointProfileLevels.id,
      { onDelete: "restrict" },
    ),
    dailyFeatureSnapshotId: integer("daily_feature_snapshot_id").references(
      () => weatherDailyFeatureSnapshots.id,
      { onDelete: "restrict" },
    ),
    dailyFeatureProfileLayerId: integer("daily_feature_profile_layer_id").references(
      () => weatherDailyFeatureProfileLayers.id,
      { onDelete: "restrict" },
    ),
    fieldCode: text("field_code").notNull(),
    fieldVariant: text("field_variant").notNull().default("canonical"),
    qualityState: text("quality_state").notNull(),
    missingReasonCode: text("missing_reason_code"),
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
      .on(table.weatherPointSampleId, table.fieldCode, table.fieldVariant)
      .where(sql`${table.weatherPointSampleId} IS NOT NULL`),
    uniqueIndex("weather_field_provenance_convection_field_unique")
      .on(table.pointConvectionMeasurementId, table.fieldCode, table.fieldVariant)
      .where(sql`${table.pointConvectionMeasurementId} IS NOT NULL`),
    uniqueIndex("weather_field_provenance_interval_field_unique")
      .on(table.pointIntervalMeasurementId, table.fieldCode, table.fieldVariant)
      .where(sql`${table.pointIntervalMeasurementId} IS NOT NULL`),
    uniqueIndex("weather_field_provenance_profile_field_unique")
      .on(table.pointProfileLevelId, table.fieldCode, table.fieldVariant)
      .where(sql`${table.pointProfileLevelId} IS NOT NULL`),
    uniqueIndex("weather_field_provenance_feature_field_unique")
      .on(table.dailyFeatureSnapshotId, table.fieldCode, table.fieldVariant, table.statisticType)
      .where(sql`${table.dailyFeatureSnapshotId} IS NOT NULL`),
    uniqueIndex("weather_field_provenance_feature_layer_field_unique")
      .on(
        table.dailyFeatureProfileLayerId,
        table.fieldCode,
        table.fieldVariant,
        table.statisticType,
      )
      .where(sql`${table.dailyFeatureProfileLayerId} IS NOT NULL`),
    index("weather_field_provenance_field_quality_index").on(table.fieldCode, table.qualityState),
    index("weather_field_provenance_source_reference_index").on(table.sourceReferenceAtUtc),
    check(
      "weather_field_provenance_exactly_one_owner_check",
      sql`(
          (${table.weatherPointSampleId} IS NOT NULL)
          + (${table.pointConvectionMeasurementId} IS NOT NULL)
          + (${table.pointIntervalMeasurementId} IS NOT NULL)
          + (${table.pointProfileLevelId} IS NOT NULL)
          + (${table.dailyFeatureSnapshotId} IS NOT NULL)
          + (${table.dailyFeatureProfileLayerId} IS NOT NULL)
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
        'invalid_payload',
        'unsupported'
      )`,
    ),
    check(
      "weather_field_provenance_missing_reason_shape_check",
      sql`(
          ${table.qualityState} IN ('missing', 'sentinel_missing', 'invalid_payload', 'unsupported')
          AND ${table.missingReasonCode} IS NOT NULL
          AND ${table.missingReasonCode} GLOB '[a-z]*'
          AND ${table.missingReasonCode} NOT GLOB '*[^a-z0-9_]*'
        )
        OR (
          ${table.qualityState} IN ('real', 'derived')
          AND ${table.missingReasonCode} IS NULL
        )`,
    ),
    check(
      "weather_field_provenance_daily_statistic_required_check",
      sql`(
          ${table.dailyFeatureSnapshotId} IS NULL
          AND ${table.dailyFeatureProfileLayerId} IS NULL
        )
        OR (
          ${table.statisticType} IS NOT NULL
          AND length(trim(${table.statisticType})) > 0
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
      sql`${table.qualityState} NOT IN ('missing', 'sentinel_missing', 'invalid_payload', 'unsupported')
        OR ${table.nativeValue} IS NULL`,
    ),
  ],
);
