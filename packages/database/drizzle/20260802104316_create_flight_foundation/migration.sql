CREATE TABLE `flight_records` (
	`id` integer PRIMARY KEY,
	`source_id` integer NOT NULL,
	`source_flight_id` text NOT NULL,
	`source_flight_url` text NOT NULL,
	`source_site_mapping_id` integer NOT NULL,
	`takeoff_at_utc` text NOT NULL,
	`duration_seconds` integer,
	`scored_distance_km` real NOT NULL,
	`route_type` text NOT NULL,
	`track_url` text,
	`validation_level` text NOT NULL,
	`validation_notes` text NOT NULL,
	`validated_at_utc` text NOT NULL,
	`created_by_ingestion_run_id` integer NOT NULL,
	`last_validated_by_ingestion_run_id` integer NOT NULL,
	`created_at_utc` text NOT NULL,
	`updated_at_utc` text NOT NULL,
	CONSTRAINT `fk_flight_records_source_id_flight_sources_id_fk` FOREIGN KEY (`source_id`) REFERENCES `flight_sources`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `flight_records_mapping_source_fk` FOREIGN KEY (`source_site_mapping_id`,`source_id`) REFERENCES `source_site_mappings`(`id`,`source_id`) ON DELETE RESTRICT,
	CONSTRAINT `flight_records_created_run_source_fk` FOREIGN KEY (`created_by_ingestion_run_id`,`source_id`) REFERENCES `ingestion_runs`(`id`,`source_id`) ON DELETE RESTRICT,
	CONSTRAINT `flight_records_last_validated_run_source_fk` FOREIGN KEY (`last_validated_by_ingestion_run_id`,`source_id`) REFERENCES `ingestion_runs`(`id`,`source_id`) ON DELETE RESTRICT,
	CONSTRAINT `flight_records_source_flight_unique` UNIQUE(`source_id`,`source_flight_id`),
	CONSTRAINT "flight_records_source_flight_id_non_empty_check" CHECK(length(trim("source_flight_id")) > 0),
	CONSTRAINT "flight_records_source_flight_url_non_empty_check" CHECK(length(trim("source_flight_url")) > 0),
	CONSTRAINT "flight_records_takeoff_at_utc_shape_check" CHECK("takeoff_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "flight_records_duration_seconds_range_check" CHECK("duration_seconds" IS NULL
        OR "duration_seconds" BETWEEN 1 AND 86400),
	CONSTRAINT "flight_records_scored_distance_km_range_check" CHECK("scored_distance_km" BETWEEN 100 AND 2000),
	CONSTRAINT "flight_records_route_type_check" CHECK("route_type" IN (
        'free_flight',
        'free_triangle',
        'fai_triangle',
        'closed_free_triangle',
        'closed_fai_triangle',
        'other',
        'unknown'
      )),
	CONSTRAINT "flight_records_validation_level_check" CHECK("validation_level" IN ('metadata', 'track')),
	CONSTRAINT "flight_records_validation_notes_non_empty_check" CHECK(length(trim("validation_notes")) > 0),
	CONSTRAINT "flight_records_validated_at_utc_shape_check" CHECK("validated_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "flight_records_created_at_utc_shape_check" CHECK("created_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "flight_records_updated_at_utc_shape_check" CHECK("updated_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "flight_records_updated_not_before_created_check" CHECK("updated_at_utc" >= "created_at_utc")
) STRICT;
--> statement-breakpoint
CREATE TABLE `flight_sources` (
	`id` integer PRIMARY KEY,
	`code` text NOT NULL CONSTRAINT `flight_sources_code_unique` UNIQUE,
	`name` text NOT NULL,
	`base_url` text NOT NULL,
	`is_active` integer DEFAULT 1 NOT NULL,
	CONSTRAINT "flight_sources_code_lower_snake_case_check" CHECK(length("code") BETWEEN 1 AND 80
        AND substr("code", 1, 1) GLOB '[a-z]'
        AND "code" NOT GLOB '*[^a-z0-9_]*'
        AND "code" NOT GLOB '*__*'
        AND substr("code", -1) <> '_'),
	CONSTRAINT "flight_sources_name_non_empty_check" CHECK(length(trim("name")) > 0),
	CONSTRAINT "flight_sources_base_url_non_empty_check" CHECK(length(trim("base_url")) > 0),
	CONSTRAINT "flight_sources_is_active_boolean_check" CHECK("is_active" IN (0, 1))
) STRICT;
--> statement-breakpoint
CREATE TABLE `ingestion_runs` (
	`id` integer PRIMARY KEY,
	`run_key` text NOT NULL CONSTRAINT `ingestion_runs_run_key_unique` UNIQUE,
	`source_id` integer NOT NULL,
	`ingestion_method` text NOT NULL,
	`status` text NOT NULL,
	`source_url` text NOT NULL,
	`permission_basis` text NOT NULL,
	`permission_reference` text NOT NULL,
	`model_training_allowed` integer DEFAULT 0 NOT NULL,
	`operational_use_allowed` integer DEFAULT 0 NOT NULL,
	`raw_manifest_path` text NOT NULL,
	`raw_manifest_sha256` text NOT NULL,
	`pipeline_version` text NOT NULL,
	`started_at_utc` text NOT NULL,
	`completed_at_utc` text,
	`records_seen` integer DEFAULT 0 NOT NULL,
	`records_accepted` integer DEFAULT 0 NOT NULL,
	`records_rejected` integer DEFAULT 0 NOT NULL,
	`records_quarantined` integer DEFAULT 0 NOT NULL,
	`records_deduplicated` integer DEFAULT 0 NOT NULL,
	`error_summary` text,
	`notes` text,
	CONSTRAINT `fk_ingestion_runs_source_id_flight_sources_id_fk` FOREIGN KEY (`source_id`) REFERENCES `flight_sources`(`id`) ON DELETE RESTRICT,
	-- Exact parent key required by the composite flight-record run foreign keys.
	CONSTRAINT `ingestion_runs_id_source_id_parent_key_unique` UNIQUE(`id`,`source_id`),
	CONSTRAINT "ingestion_runs_run_key_uuid_v4_check" CHECK("run_key" GLOB
        '[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]-[0-9a-f][0-9a-f][0-9a-f][0-9a-f]-4[0-9a-f][0-9a-f][0-9a-f]-[89ab][0-9a-f][0-9a-f][0-9a-f]-[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]'),
	CONSTRAINT "ingestion_runs_ingestion_method_check" CHECK("ingestion_method" IN (
        'manual_export',
        'owner_export',
        'official_api',
        'authorized_http',
        'pilot_provided'
      )),
	CONSTRAINT "ingestion_runs_status_check" CHECK("status" IN ('running', 'succeeded', 'failed')),
	CONSTRAINT "ingestion_runs_source_url_non_empty_check" CHECK(length(trim("source_url")) > 0),
	CONSTRAINT "ingestion_runs_permission_basis_check" CHECK("permission_basis" IN (
        'written_permission',
        'source_terms',
        'owner_export',
        'official_api_terms',
        'pilot_provided'
      )),
	CONSTRAINT "ingestion_runs_permission_reference_non_empty_check" CHECK(length(trim("permission_reference")) > 0),
	CONSTRAINT "ingestion_runs_model_training_allowed_boolean_check" CHECK("model_training_allowed" IN (0, 1)),
	CONSTRAINT "ingestion_runs_operational_use_allowed_boolean_check" CHECK("operational_use_allowed" IN (0, 1)),
	CONSTRAINT "ingestion_runs_raw_manifest_path_check" CHECK("raw_manifest_path" LIKE 'data/raw/%' AND "raw_manifest_path" NOT LIKE '%..%'),
	CONSTRAINT "ingestion_runs_raw_manifest_sha256_check" CHECK(length("raw_manifest_sha256") = 64
        AND "raw_manifest_sha256" NOT GLOB '*[^0-9a-f]*'),
	CONSTRAINT "ingestion_runs_pipeline_version_non_empty_check" CHECK(length(trim("pipeline_version")) > 0),
	CONSTRAINT "ingestion_runs_started_at_utc_shape_check" CHECK("started_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "ingestion_runs_completed_at_utc_shape_check" CHECK("completed_at_utc" IS NULL
        OR "completed_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "ingestion_runs_completion_lifecycle_check" CHECK((
          "status" = 'running'
          AND "completed_at_utc" IS NULL
        )
        OR (
          "status" IN ('succeeded', 'failed')
          AND "completed_at_utc" IS NOT NULL
          AND "completed_at_utc" >= "started_at_utc"
        )),
	CONSTRAINT "ingestion_runs_counters_non_negative_check" CHECK("records_seen" >= 0
        AND "records_accepted" >= 0
        AND "records_rejected" >= 0
        AND "records_quarantined" >= 0
        AND "records_deduplicated" >= 0),
	CONSTRAINT "ingestion_runs_counter_outcomes_check" CHECK("records_accepted" + "records_rejected" + "records_quarantined"
		<= "records_seen")
) STRICT;
--> statement-breakpoint
CREATE TABLE `sites` (
	`id` integer PRIMARY KEY,
	`slug` text NOT NULL CONSTRAINT `sites_slug_unique` UNIQUE,
	`name` text NOT NULL,
	`country_code_iso2` text DEFAULT 'BG' NOT NULL,
	`site_type` text NOT NULL,
	`latitude_deg` real NOT NULL,
	`longitude_deg` real NOT NULL,
	`catchment_radius_km` real,
	`time_zone` text DEFAULT 'Europe/Sofia' NOT NULL,
	`is_active` integer DEFAULT 1 NOT NULL,
	CONSTRAINT "sites_slug_lower_kebab_case_check" CHECK(length("slug") BETWEEN 1 AND 80
        AND substr("slug", 1, 1) GLOB '[a-z0-9]'
        AND "slug" NOT GLOB '*[^a-z0-9-]*'
        AND "slug" NOT GLOB '*--*'
        AND substr("slug", -1) <> '-'),
	CONSTRAINT "sites_name_non_empty_check" CHECK(length(trim("name")) > 0),
	CONSTRAINT "sites_country_code_iso2_check" CHECK("country_code_iso2" GLOB '[A-Z][A-Z]'),
	CONSTRAINT "sites_site_type_check" CHECK("site_type" IN ('launch_area', 'region')),
	CONSTRAINT "sites_latitude_deg_range_check" CHECK("latitude_deg" BETWEEN -90 AND 90),
	CONSTRAINT "sites_longitude_deg_range_check" CHECK("longitude_deg" BETWEEN -180 AND 180),
	CONSTRAINT "sites_catchment_radius_km_range_check" CHECK("catchment_radius_km" IS NULL
        OR ("catchment_radius_km" > 0 AND "catchment_radius_km" <= 250)),
	CONSTRAINT "sites_time_zone_non_empty_check" CHECK(length(trim("time_zone")) > 0),
	CONSTRAINT "sites_is_active_boolean_check" CHECK("is_active" IN (0, 1))
) STRICT;
--> statement-breakpoint
CREATE TABLE `source_site_mappings` (
	`id` integer PRIMARY KEY,
	`source_id` integer NOT NULL,
	`site_id` integer NOT NULL,
	`key_type` text NOT NULL,
	`key_value` text,
	`source_display_name` text,
	`point_latitude_deg` real,
	`point_longitude_deg` real,
	`status` text NOT NULL,
	`verification_reference` text,
	`verified_at_utc` text,
	`notes` text,
	CONSTRAINT `fk_source_site_mappings_source_id_flight_sources_id_fk` FOREIGN KEY (`source_id`) REFERENCES `flight_sources`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_source_site_mappings_site_id_sites_id_fk` FOREIGN KEY (`site_id`) REFERENCES `sites`(`id`) ON DELETE RESTRICT,
	-- Exact parent key required by the composite flight-record mapping foreign key.
	CONSTRAINT `source_site_mappings_id_source_id_parent_key_unique` UNIQUE(`id`,`source_id`),
	CONSTRAINT "source_site_mappings_key_type_check" CHECK("key_type" IN (
        'source_takeoff_id',
        'source_site_token',
        'normalized_name',
        'source_point'
      )),
	CONSTRAINT "source_site_mappings_key_shape_check" CHECK((
          "key_type" IN ('source_takeoff_id', 'source_site_token', 'normalized_name')
          AND "key_value" IS NOT NULL
          AND length(trim("key_value")) > 0
          AND "point_latitude_deg" IS NULL
          AND "point_longitude_deg" IS NULL
        )
        OR (
          "key_type" = 'source_point'
          AND "key_value" IS NULL
          AND "point_latitude_deg" IS NOT NULL
          AND "point_longitude_deg" IS NOT NULL
        )),
	CONSTRAINT "source_site_mappings_point_latitude_deg_range_check" CHECK("point_latitude_deg" IS NULL
        OR "point_latitude_deg" BETWEEN -90 AND 90),
	CONSTRAINT "source_site_mappings_point_longitude_deg_range_check" CHECK("point_longitude_deg" IS NULL
        OR "point_longitude_deg" BETWEEN -180 AND 180),
	CONSTRAINT "source_site_mappings_status_check" CHECK("status" IN ('provisional', 'approved', 'retired')),
	CONSTRAINT "source_site_mappings_verified_at_utc_shape_check" CHECK("verified_at_utc" IS NULL OR "verified_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "source_site_mappings_approved_evidence_check" CHECK("status" <> 'approved'
		OR (
		  "verification_reference" IS NOT NULL
		  AND length(trim("verification_reference")) > 0
		  AND "verified_at_utc" IS NOT NULL
		))
) STRICT;
--> statement-breakpoint
CREATE INDEX `flight_records_mapping_takeoff_at_index` ON `flight_records` (`source_site_mapping_id`,`takeoff_at_utc`);--> statement-breakpoint
CREATE INDEX `flight_records_takeoff_distance_index` ON `flight_records` (`takeoff_at_utc`,"scored_distance_km" desc);--> statement-breakpoint
CREATE INDEX `flight_records_created_by_ingestion_run_index` ON `flight_records` (`created_by_ingestion_run_id`);--> statement-breakpoint
CREATE INDEX `ingestion_runs_source_started_at_index` ON `ingestion_runs` (`source_id`,"started_at_utc" desc);--> statement-breakpoint
CREATE UNIQUE INDEX `source_site_mappings_active_key_unique` ON `source_site_mappings` (`source_id`,`key_type`,`key_value`) WHERE "source_site_mappings"."status" <> 'retired' AND "source_site_mappings"."key_type" <> 'source_point';--> statement-breakpoint
CREATE UNIQUE INDEX `source_site_mappings_active_point_unique` ON `source_site_mappings` (`source_id`,`point_latitude_deg`,`point_longitude_deg`) WHERE "source_site_mappings"."status" <> 'retired' AND "source_site_mappings"."key_type" = 'source_point';--> statement-breakpoint
CREATE INDEX `source_site_mappings_site_source_status_index` ON `source_site_mappings` (`site_id`,`source_id`,`status`);
