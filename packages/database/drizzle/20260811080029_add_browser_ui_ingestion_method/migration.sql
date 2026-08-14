PRAGMA foreign_keys=OFF;--> statement-breakpoint
CREATE TABLE `__new_ingestion_runs` (
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
	CONSTRAINT `ingestion_runs_id_source_id_parent_key_unique` UNIQUE(`id`,`source_id`),
	CONSTRAINT "ingestion_runs_run_key_uuid_v4_check" CHECK("run_key" GLOB
        '[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]-[0-9a-f][0-9a-f][0-9a-f][0-9a-f]-4[0-9a-f][0-9a-f][0-9a-f]-[89ab][0-9a-f][0-9a-f][0-9a-f]-[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]'),
	CONSTRAINT "ingestion_runs_ingestion_method_check" CHECK("ingestion_method" IN (
        'manual_export',
        'owner_export',
        'official_api',
        'authorized_http',
        'browser_ui',
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
INSERT INTO `__new_ingestion_runs`(`id`, `run_key`, `source_id`, `ingestion_method`, `status`, `source_url`, `permission_basis`, `permission_reference`, `model_training_allowed`, `operational_use_allowed`, `raw_manifest_path`, `raw_manifest_sha256`, `pipeline_version`, `started_at_utc`, `completed_at_utc`, `records_seen`, `records_accepted`, `records_rejected`, `records_quarantined`, `records_deduplicated`, `error_summary`, `notes`) SELECT `id`, `run_key`, `source_id`, `ingestion_method`, `status`, `source_url`, `permission_basis`, `permission_reference`, `model_training_allowed`, `operational_use_allowed`, `raw_manifest_path`, `raw_manifest_sha256`, `pipeline_version`, `started_at_utc`, `completed_at_utc`, `records_seen`, `records_accepted`, `records_rejected`, `records_quarantined`, `records_deduplicated`, `error_summary`, `notes` FROM `ingestion_runs`;--> statement-breakpoint
DROP TABLE `ingestion_runs`;--> statement-breakpoint
ALTER TABLE `__new_ingestion_runs` RENAME TO `ingestion_runs`;--> statement-breakpoint
PRAGMA foreign_keys=ON;--> statement-breakpoint
CREATE INDEX `ingestion_runs_source_started_at_index` ON `ingestion_runs` (`source_id`,"started_at_utc" desc);