CREATE TABLE `source_site_exclusions` (
	`id` integer PRIMARY KEY,
	`source_id` integer NOT NULL,
	`key_type` text NOT NULL,
	`key_value` text NOT NULL,
	`origin_run_key` text NOT NULL,
	`origin_proposal_id` text NOT NULL,
	`notes` text,
	`status` text DEFAULT 'active' NOT NULL,
	`created_at_utc` text NOT NULL,
	`retired_at_utc` text,
	`retirement_reason` text,
	CONSTRAINT `fk_source_site_exclusions_source_id_flight_sources_id_fk` FOREIGN KEY (`source_id`) REFERENCES `flight_sources`(`id`) ON DELETE RESTRICT,
	CONSTRAINT "source_site_exclusions_key_type_check" CHECK("key_type" IN ('source_site_token', 'source_takeoff_id')),
	CONSTRAINT "source_site_exclusions_non_empty_text_check" CHECK(length(trim("key_value")) > 0
        AND length(trim("origin_run_key")) > 0
        AND length(trim("origin_proposal_id")) > 0),
	CONSTRAINT "source_site_exclusions_status_check" CHECK("status" IN ('active', 'retired')),
	CONSTRAINT "source_site_exclusions_created_at_utc_shape_check" CHECK("created_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "source_site_exclusions_retired_at_utc_shape_check" CHECK("retired_at_utc" IS NULL
        OR "retired_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "source_site_exclusions_retirement_shape_check" CHECK((
          "status" = 'active'
          AND "retired_at_utc" IS NULL
          AND "retirement_reason" IS NULL
        )
        OR (
          "status" = 'retired'
          AND "retired_at_utc" IS NOT NULL
          AND "retirement_reason" IS NOT NULL
          AND length(trim("retirement_reason")) > 0
        ))
) STRICT;
--> statement-breakpoint
CREATE UNIQUE INDEX `source_site_exclusions_active_key_unique` ON `source_site_exclusions` (`source_id`,`key_type`,`key_value`) WHERE "source_site_exclusions"."status" = 'active';--> statement-breakpoint
CREATE INDEX `source_site_exclusions_lookup_index` ON `source_site_exclusions` (`source_id`,`key_type`,`key_value`,`status`);--> statement-breakpoint
CREATE INDEX `source_site_exclusions_origin_audit_index` ON `source_site_exclusions` (`origin_run_key`,`origin_proposal_id`);