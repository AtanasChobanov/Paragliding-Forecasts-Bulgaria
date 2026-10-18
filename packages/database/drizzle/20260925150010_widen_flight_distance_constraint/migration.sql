PRAGMA foreign_keys=OFF;--> statement-breakpoint
CREATE TABLE `__new_flight_records` (
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
	CONSTRAINT `flight_records_created_run_source_fk` FOREIGN KEY (`created_by_ingestion_run_id`,`source_id`) REFERENCES `flight_ingestion_runs`(`id`,`source_id`) ON DELETE RESTRICT,
	CONSTRAINT `flight_records_last_validated_run_source_fk` FOREIGN KEY (`last_validated_by_ingestion_run_id`,`source_id`) REFERENCES `flight_ingestion_runs`(`id`,`source_id`) ON DELETE RESTRICT,
	CONSTRAINT `flight_records_source_flight_unique` UNIQUE(`source_id`,`source_flight_id`),
	CONSTRAINT "flight_records_source_flight_id_non_empty_check" CHECK(length(trim("source_flight_id")) > 0),
	CONSTRAINT "flight_records_source_flight_url_non_empty_check" CHECK(length(trim("source_flight_url")) > 0),
	CONSTRAINT "flight_records_takeoff_at_utc_shape_check" CHECK("takeoff_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "flight_records_duration_seconds_range_check" CHECK("duration_seconds" IS NULL
        OR "duration_seconds" BETWEEN 1 AND 86400),
	CONSTRAINT "flight_records_scored_distance_km_range_check" CHECK("scored_distance_km" BETWEEN 0 AND 2000),
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
INSERT INTO `__new_flight_records`(`id`, `source_id`, `source_flight_id`, `source_flight_url`, `source_site_mapping_id`, `takeoff_at_utc`, `duration_seconds`, `scored_distance_km`, `route_type`, `track_url`, `validation_level`, `validation_notes`, `validated_at_utc`, `created_by_ingestion_run_id`, `last_validated_by_ingestion_run_id`, `created_at_utc`, `updated_at_utc`) SELECT `id`, `source_id`, `source_flight_id`, `source_flight_url`, `source_site_mapping_id`, `takeoff_at_utc`, `duration_seconds`, `scored_distance_km`, `route_type`, `track_url`, `validation_level`, `validation_notes`, `validated_at_utc`, `created_by_ingestion_run_id`, `last_validated_by_ingestion_run_id`, `created_at_utc`, `updated_at_utc` FROM `flight_records`;--> statement-breakpoint
DROP TABLE `flight_records`;--> statement-breakpoint
ALTER TABLE `__new_flight_records` RENAME TO `flight_records`;--> statement-breakpoint
PRAGMA foreign_keys=ON;--> statement-breakpoint
CREATE INDEX `flight_records_mapping_takeoff_at_index` ON `flight_records` (`source_site_mapping_id`,`takeoff_at_utc`);--> statement-breakpoint
CREATE INDEX `flight_records_takeoff_distance_index` ON `flight_records` (`takeoff_at_utc`,"scored_distance_km" desc);--> statement-breakpoint
CREATE INDEX `flight_records_created_by_ingestion_run_index` ON `flight_records` (`created_by_ingestion_run_id`);