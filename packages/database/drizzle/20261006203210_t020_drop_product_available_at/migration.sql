CREATE TABLE `__new_weather_product_runs` (
	`id` integer PRIMARY KEY,
	`source_id` integer NOT NULL,
	`source_product_key` text NOT NULL,
	`reference_at_utc` text,
	CONSTRAINT `fk_weather_product_runs_source_id_weather_sources_id_fk` FOREIGN KEY (`source_id`) REFERENCES `weather_sources`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `weather_product_runs_source_product_unique` UNIQUE(`source_id`,`source_product_key`),
	CONSTRAINT "weather_product_runs_source_product_key_non_empty_check" CHECK(length(trim("source_product_key")) > 0),
	CONSTRAINT "weather_product_runs_reference_at_utc_shape_check" CHECK("reference_at_utc" IS NULL
        OR "reference_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z')
) STRICT;
--> statement-breakpoint
INSERT INTO `__new_weather_product_runs`(`id`, `source_id`, `source_product_key`, `reference_at_utc`) SELECT `id`, `source_id`, `source_product_key`, `reference_at_utc` FROM `weather_product_runs`;--> statement-breakpoint
DROP TABLE `weather_product_runs`;--> statement-breakpoint
ALTER TABLE `__new_weather_product_runs` RENAME TO `weather_product_runs`;--> statement-breakpoint
CREATE INDEX `weather_product_runs_source_reference_at_index` ON `weather_product_runs` (`source_id`,"reference_at_utc" desc);
--> statement-breakpoint
CREATE TEMP TABLE `__t020_product_rebuild_guard` (`violations` integer NOT NULL CHECK (`violations` = 0));
--> statement-breakpoint
INSERT INTO `__t020_product_rebuild_guard` SELECT count(*) FROM pragma_foreign_key_check;
--> statement-breakpoint
DROP TABLE `__t020_product_rebuild_guard`;
