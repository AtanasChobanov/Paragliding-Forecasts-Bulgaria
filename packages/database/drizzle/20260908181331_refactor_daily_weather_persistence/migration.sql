CREATE TEMP TABLE `__weather_daily_refactor_guard` (
	`existing_runtime_rows` integer NOT NULL CHECK (`existing_runtime_rows` = 0)
) STRICT;
--> statement-breakpoint
INSERT INTO `__weather_daily_refactor_guard` (`existing_runtime_rows`)
SELECT
	(SELECT count(*) FROM `weather_ingestion_runs`)
	+ (SELECT count(*) FROM `weather_product_runs`)
	+ (SELECT count(*) FROM `weather_grids`)
	+ (SELECT count(*) FROM `weather_grid_points`)
	+ (SELECT count(*) FROM `weather_sampling_footprints`)
	+ (SELECT count(*) FROM `weather_sampling_footprint_nodes`)
	+ (SELECT count(*) FROM `weather_samples`)
	+ (SELECT count(*) FROM `weather_profile_levels`)
	+ (SELECT count(*) FROM `weather_convection_measurements`)
	+ (SELECT count(*) FROM `weather_interval_measurements`)
	+ (SELECT count(*) FROM `weather_feature_snapshots`)
	+ (SELECT count(*) FROM `weather_field_provenance`);
--> statement-breakpoint
DROP TABLE `__weather_daily_refactor_guard`;
--> statement-breakpoint
CREATE TABLE `weather_daily_feature_profile_layers` (
	`id` integer PRIMARY KEY,
	`daily_feature_snapshot_id` integer NOT NULL,
	`layer_base_agl_m` real NOT NULL,
	`layer_top_agl_m` real NOT NULL,
	`temperature_lapse_rate_mean_k_per_km` real,
	`temperature_lapse_rate_max_k_per_km` real,
	`inversion_strength_max_k` real,
	`inversion_depth_at_max_m` real,
	`relative_humidity_mean_percent` real,
	`specific_humidity_mean_kg_per_kg` real,
	`wind_u_mean_m_s` real,
	`wind_v_mean_m_s` real,
	`wind_speed_mean_m_s` real,
	`wind_speed_max_m_s` real,
	`wind_direction_mean_degrees_from_north` real,
	`wind_shear_mean_m_s_per_km` real,
	`wind_shear_max_m_s_per_km` real,
	`vertical_velocity_mean_pa_s` real,
	`vertical_velocity_min_pa_s` real,
	CONSTRAINT `fk_weather_daily_feature_profile_layers_daily_feature_snapshot_id_weather_daily_feature_snapshots_id_fk` FOREIGN KEY (`daily_feature_snapshot_id`) REFERENCES `weather_daily_feature_snapshots`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `weather_daily_feature_profile_layers_identity_unique` UNIQUE(`daily_feature_snapshot_id`,`layer_base_agl_m`,`layer_top_agl_m`),
	CONSTRAINT "weather_daily_feature_profile_layers_bounds_check" CHECK("layer_base_agl_m" >= 0 AND "layer_top_agl_m" > "layer_base_agl_m"),
	CONSTRAINT "weather_daily_feature_profile_layers_inversion_pair_check" CHECK(("inversion_strength_max_k" IS NULL AND "inversion_depth_at_max_m" IS NULL)
        OR ("inversion_strength_max_k" IS NOT NULL AND "inversion_strength_max_k" >= 0 AND "inversion_depth_at_max_m" IS NOT NULL AND "inversion_depth_at_max_m" >= 0)),
	CONSTRAINT "weather_daily_feature_profile_layers_humidity_range_check" CHECK(("relative_humidity_mean_percent" IS NULL OR "relative_humidity_mean_percent" BETWEEN 0 AND 100)
        AND ("specific_humidity_mean_kg_per_kg" IS NULL OR "specific_humidity_mean_kg_per_kg" >= 0)),
	CONSTRAINT "weather_daily_feature_profile_layers_wind_shape_check" CHECK(("wind_speed_mean_m_s" IS NULL OR "wind_speed_mean_m_s" >= 0)
        AND ("wind_speed_max_m_s" IS NULL OR "wind_speed_max_m_s" >= 0)
        AND ("wind_direction_mean_degrees_from_north" IS NULL OR ("wind_direction_mean_degrees_from_north" >= 0 AND "wind_direction_mean_degrees_from_north" < 360))
        AND ("wind_shear_mean_m_s_per_km" IS NULL OR "wind_shear_mean_m_s_per_km" >= 0)
        AND ("wind_shear_max_m_s_per_km" IS NULL OR "wind_shear_max_m_s_per_km" >= 0))
) STRICT;
--> statement-breakpoint
CREATE TABLE `weather_daily_feature_snapshot_inputs` (
	`daily_feature_snapshot_id` integer NOT NULL,
	`weather_point_sample_id` integer NOT NULL,
	CONSTRAINT `weather_daily_feature_snapshot_inputs_pk` PRIMARY KEY(`daily_feature_snapshot_id`, `weather_point_sample_id`),
	CONSTRAINT `fk_weather_daily_feature_snapshot_inputs_daily_feature_snapshot_id_weather_daily_feature_snapshots_id_fk` FOREIGN KEY (`daily_feature_snapshot_id`) REFERENCES `weather_daily_feature_snapshots`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_daily_feature_snapshot_inputs_weather_point_sample_id_weather_point_samples_id_fk` FOREIGN KEY (`weather_point_sample_id`) REFERENCES `weather_point_samples`(`id`) ON DELETE RESTRICT
) STRICT;
--> statement-breakpoint
CREATE TABLE `weather_product_valid_times` (
	`id` integer PRIMARY KEY,
	`product_run_id` integer NOT NULL,
	`valid_at_utc` text NOT NULL,
	`lead_hours` real,
	CONSTRAINT `fk_weather_product_valid_times_product_run_id_weather_product_runs_id_fk` FOREIGN KEY (`product_run_id`) REFERENCES `weather_product_runs`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `weather_product_valid_times_product_valid_unique` UNIQUE(`product_run_id`,`valid_at_utc`),
	CONSTRAINT "weather_product_valid_times_valid_at_utc_shape_check" CHECK("valid_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "weather_product_valid_times_lead_hours_non_negative_check" CHECK("lead_hours" IS NULL OR "lead_hours" >= 0)
) STRICT;
--> statement-breakpoint
ALTER TABLE `weather_feature_snapshots` RENAME TO `weather_daily_feature_snapshots`;--> statement-breakpoint
ALTER TABLE `weather_convection_measurements` RENAME TO `weather_point_convection_measurements`;--> statement-breakpoint
ALTER TABLE `weather_interval_measurements` RENAME TO `weather_point_interval_measurements`;--> statement-breakpoint
ALTER TABLE `weather_profile_levels` RENAME TO `weather_point_profile_levels`;--> statement-breakpoint
ALTER TABLE `weather_samples` RENAME TO `weather_point_samples`;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` RENAME COLUMN `created_by_ingestion_run_id` TO `ingestion_run_id`;--> statement-breakpoint
ALTER TABLE `weather_field_provenance` RENAME COLUMN `weather_sample_id` TO `weather_point_sample_id`;--> statement-breakpoint
ALTER TABLE `weather_field_provenance` RENAME COLUMN `convection_measurement_id` TO `point_convection_measurement_id`;--> statement-breakpoint
ALTER TABLE `weather_field_provenance` RENAME COLUMN `interval_measurement_id` TO `point_interval_measurement_id`;--> statement-breakpoint
ALTER TABLE `weather_field_provenance` RENAME COLUMN `profile_level_id` TO `point_profile_level_id`;--> statement-breakpoint
ALTER TABLE `weather_field_provenance` RENAME COLUMN `feature_snapshot_id` TO `daily_feature_snapshot_id`;--> statement-breakpoint
ALTER TABLE `weather_point_convection_measurements` RENAME COLUMN `weather_sample_id` TO `weather_point_sample_id`;--> statement-breakpoint
ALTER TABLE `weather_point_interval_measurements` RENAME COLUMN `weather_sample_id` TO `weather_point_sample_id`;--> statement-breakpoint
ALTER TABLE `weather_point_profile_levels` RENAME COLUMN `weather_sample_id` TO `weather_point_sample_id`;--> statement-breakpoint
ALTER TABLE `weather_point_profile_levels` RENAME COLUMN `level_height_agl_m` TO `level_height_site_agl_m`;--> statement-breakpoint
ALTER TABLE `weather_point_samples` RENAME COLUMN `created_by_ingestion_run_id` TO `ingestion_run_id`;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `point_footprint_id` integer NOT NULL REFERENCES weather_sampling_footprints(id) ON DELETE RESTRICT;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `air_temperature_2m_mean_k` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `air_temperature_2m_min_k` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `air_temperature_2m_max_k` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `dew_point_temperature_2m_mean_k` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `relative_humidity_2m_mean_percent` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `relative_humidity_2m_max_percent` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `surface_pressure_mean_pa` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `mean_sea_level_pressure_mean_pa` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `wind_u_10m_mean_m_s` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `wind_v_10m_mean_m_s` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `wind_speed_10m_mean_m_s` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `wind_speed_10m_max_m_s` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `wind_direction_10m_mean_degrees_from_north` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `provider_boundary_layer_height_agl_mean_m` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `provider_boundary_layer_height_agl_max_m` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `provider_cloud_base_agl_mean_m` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `provider_cloud_base_agl_min_m` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `provider_cloud_base_agl_max_m` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `total_column_water_vapour_mean_kg_m2` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `total_cloud_cover_mean_percent` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `total_cloud_cover_max_percent` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `low_cloud_cover_mean_percent` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `low_cloud_cover_max_percent` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `mid_cloud_cover_mean_percent` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `high_cloud_cover_mean_percent` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `precipitation_total_mm` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `precipitation_max_hourly_mm` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `shortwave_radiation_mean_w_m2` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `shortwave_radiation_max_w_m2` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `surface_sensible_heat_flux_mean_w_m2` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `surface_latent_heat_flux_mean_w_m2` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `cape_max_j_per_kg` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `cin_magnitude_min_j_per_kg` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `mixed_layer_lcl_agl_mean_m` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `mixed_layer_lcl_agl_max_m` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `surface_buoyancy_flux_kinematic_mean_k_m_s` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `convective_velocity_scale_mean_m_s` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `convective_velocity_scale_max_m_s` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `neighbourhood_pressure_gradient_mean_pa_per_km` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `neighbourhood_pressure_gradient_max_pa_per_km` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `neighbourhood_low_level_divergence_mean_s_inverse` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `neighbourhood_low_level_divergence_min_s_inverse` real;--> statement-breakpoint
ALTER TABLE `weather_field_provenance` ADD `daily_feature_profile_layer_id` integer REFERENCES weather_daily_feature_profile_layers(id) ON DELETE RESTRICT;--> statement-breakpoint
ALTER TABLE `weather_ingestion_runs` ADD `product_run_id` integer NOT NULL REFERENCES weather_product_runs(id) ON DELETE RESTRICT;--> statement-breakpoint
ALTER TABLE `weather_ingestion_runs` ADD `target_local_date` text NOT NULL;--> statement-breakpoint
ALTER TABLE `weather_point_profile_levels` ADD `vertical_velocity_pa_s` real;--> statement-breakpoint
ALTER TABLE `weather_point_samples` ADD `product_valid_time_id` integer NOT NULL REFERENCES weather_product_valid_times(id) ON DELETE RESTRICT;--> statement-breakpoint
PRAGMA foreign_keys=OFF;--> statement-breakpoint
CREATE TABLE `__new_weather_daily_feature_snapshots` (
	`id` integer PRIMARY KEY,
	`ingestion_run_id` integer NOT NULL,
	`point_footprint_id` integer NOT NULL,
	`neighbourhood_footprint_id` integer NOT NULL,
	`feature_contract_version` text NOT NULL,
	`air_temperature_2m_mean_k` real,
	`air_temperature_2m_min_k` real,
	`air_temperature_2m_max_k` real,
	`dew_point_temperature_2m_mean_k` real,
	`relative_humidity_2m_mean_percent` real,
	`relative_humidity_2m_max_percent` real,
	`surface_pressure_mean_pa` real,
	`mean_sea_level_pressure_mean_pa` real,
	`wind_u_10m_mean_m_s` real,
	`wind_v_10m_mean_m_s` real,
	`wind_speed_10m_mean_m_s` real,
	`wind_speed_10m_max_m_s` real,
	`wind_direction_10m_mean_degrees_from_north` real,
	`provider_boundary_layer_height_agl_mean_m` real,
	`provider_boundary_layer_height_agl_max_m` real,
	`provider_cloud_base_agl_mean_m` real,
	`provider_cloud_base_agl_min_m` real,
	`provider_cloud_base_agl_max_m` real,
	`total_column_water_vapour_mean_kg_m2` real,
	`total_cloud_cover_mean_percent` real,
	`total_cloud_cover_max_percent` real,
	`low_cloud_cover_mean_percent` real,
	`low_cloud_cover_max_percent` real,
	`mid_cloud_cover_mean_percent` real,
	`high_cloud_cover_mean_percent` real,
	`precipitation_total_mm` real,
	`precipitation_max_hourly_mm` real,
	`shortwave_radiation_mean_w_m2` real,
	`shortwave_radiation_max_w_m2` real,
	`surface_sensible_heat_flux_mean_w_m2` real,
	`surface_latent_heat_flux_mean_w_m2` real,
	`cape_max_j_per_kg` real,
	`cin_magnitude_min_j_per_kg` real,
	`mixed_layer_lcl_agl_mean_m` real,
	`mixed_layer_lcl_agl_max_m` real,
	`surface_buoyancy_flux_kinematic_mean_k_m_s` real,
	`convective_velocity_scale_mean_m_s` real,
	`convective_velocity_scale_max_m_s` real,
	`neighbourhood_pressure_gradient_mean_pa_per_km` real,
	`neighbourhood_pressure_gradient_max_pa_per_km` real,
	`neighbourhood_low_level_divergence_mean_s_inverse` real,
	`neighbourhood_low_level_divergence_min_s_inverse` real,
	CONSTRAINT `fk_weather_feature_snapshots_created_by_ingestion_run_id_weather_ingestion_runs_id_fk` FOREIGN KEY (`ingestion_run_id`) REFERENCES `weather_ingestion_runs`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_daily_feature_snapshots_point_footprint_id_weather_sampling_footprints_id_fk` FOREIGN KEY (`point_footprint_id`) REFERENCES `weather_sampling_footprints`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_feature_snapshots_neighbourhood_footprint_id_weather_sampling_footprints_id_fk` FOREIGN KEY (`neighbourhood_footprint_id`) REFERENCES `weather_sampling_footprints`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `weather_daily_feature_snapshots_identity_unique` UNIQUE(`ingestion_run_id`,`point_footprint_id`,`feature_contract_version`),
	CONSTRAINT "weather_daily_feature_snapshots_contract_version_non_empty_check" CHECK(length(trim("feature_contract_version")) > 0),
	CONSTRAINT "weather_daily_feature_snapshots_temperature_positive_check" CHECK(("air_temperature_2m_mean_k" IS NULL OR "air_temperature_2m_mean_k" > 0)
        AND ("air_temperature_2m_min_k" IS NULL OR "air_temperature_2m_min_k" > 0)
        AND ("air_temperature_2m_max_k" IS NULL OR "air_temperature_2m_max_k" > 0)
        AND ("dew_point_temperature_2m_mean_k" IS NULL OR "dew_point_temperature_2m_mean_k" > 0)),
	CONSTRAINT "weather_daily_feature_snapshots_temperature_order_check" CHECK("air_temperature_2m_min_k" IS NULL OR "air_temperature_2m_max_k" IS NULL
        OR "air_temperature_2m_max_k" >= "air_temperature_2m_min_k"),
	CONSTRAINT "weather_daily_feature_snapshots_percent_range_check" CHECK(("relative_humidity_2m_mean_percent" IS NULL OR "relative_humidity_2m_mean_percent" BETWEEN 0 AND 100)
        AND ("relative_humidity_2m_max_percent" IS NULL OR "relative_humidity_2m_max_percent" BETWEEN 0 AND 100)
        AND ("total_cloud_cover_mean_percent" IS NULL OR "total_cloud_cover_mean_percent" BETWEEN 0 AND 100)
        AND ("total_cloud_cover_max_percent" IS NULL OR "total_cloud_cover_max_percent" BETWEEN 0 AND 100)
        AND ("low_cloud_cover_mean_percent" IS NULL OR "low_cloud_cover_mean_percent" BETWEEN 0 AND 100)
        AND ("low_cloud_cover_max_percent" IS NULL OR "low_cloud_cover_max_percent" BETWEEN 0 AND 100)
        AND ("mid_cloud_cover_mean_percent" IS NULL OR "mid_cloud_cover_mean_percent" BETWEEN 0 AND 100)
        AND ("high_cloud_cover_mean_percent" IS NULL OR "high_cloud_cover_mean_percent" BETWEEN 0 AND 100)),
	CONSTRAINT "weather_daily_feature_snapshots_direction_range_check" CHECK("wind_direction_10m_mean_degrees_from_north" IS NULL OR ("wind_direction_10m_mean_degrees_from_north" >= 0 AND "wind_direction_10m_mean_degrees_from_north" < 360)),
	CONSTRAINT "weather_daily_feature_snapshots_non_negative_check" CHECK(("surface_pressure_mean_pa" IS NULL OR "surface_pressure_mean_pa" > 0)
        AND ("mean_sea_level_pressure_mean_pa" IS NULL OR "mean_sea_level_pressure_mean_pa" > 0)
        AND ("wind_speed_10m_mean_m_s" IS NULL OR "wind_speed_10m_mean_m_s" >= 0)
        AND ("wind_speed_10m_max_m_s" IS NULL OR "wind_speed_10m_max_m_s" >= 0)
        AND ("provider_boundary_layer_height_agl_mean_m" IS NULL OR "provider_boundary_layer_height_agl_mean_m" >= 0)
        AND ("provider_boundary_layer_height_agl_max_m" IS NULL OR "provider_boundary_layer_height_agl_max_m" >= 0)
        AND ("provider_cloud_base_agl_mean_m" IS NULL OR "provider_cloud_base_agl_mean_m" >= 0)
        AND ("provider_cloud_base_agl_min_m" IS NULL OR "provider_cloud_base_agl_min_m" >= 0)
        AND ("provider_cloud_base_agl_max_m" IS NULL OR "provider_cloud_base_agl_max_m" >= 0)
        AND ("total_column_water_vapour_mean_kg_m2" IS NULL OR "total_column_water_vapour_mean_kg_m2" >= 0)
        AND ("precipitation_total_mm" IS NULL OR "precipitation_total_mm" >= 0)
        AND ("precipitation_max_hourly_mm" IS NULL OR "precipitation_max_hourly_mm" >= 0)
        AND ("shortwave_radiation_mean_w_m2" IS NULL OR "shortwave_radiation_mean_w_m2" >= 0)
        AND ("shortwave_radiation_max_w_m2" IS NULL OR "shortwave_radiation_max_w_m2" >= 0)
        AND ("cape_max_j_per_kg" IS NULL OR "cape_max_j_per_kg" >= 0)
        AND ("cin_magnitude_min_j_per_kg" IS NULL OR "cin_magnitude_min_j_per_kg" >= 0)
        AND ("mixed_layer_lcl_agl_mean_m" IS NULL OR "mixed_layer_lcl_agl_mean_m" >= 0)
        AND ("mixed_layer_lcl_agl_max_m" IS NULL OR "mixed_layer_lcl_agl_max_m" >= 0)
        AND ("convective_velocity_scale_mean_m_s" IS NULL OR "convective_velocity_scale_mean_m_s" >= 0)
        AND ("convective_velocity_scale_max_m_s" IS NULL OR "convective_velocity_scale_max_m_s" >= 0)
        AND ("neighbourhood_pressure_gradient_mean_pa_per_km" IS NULL OR "neighbourhood_pressure_gradient_mean_pa_per_km" >= 0)
        AND ("neighbourhood_pressure_gradient_max_pa_per_km" IS NULL OR "neighbourhood_pressure_gradient_max_pa_per_km" >= 0))
) STRICT;
--> statement-breakpoint
INSERT INTO `__new_weather_daily_feature_snapshots`(`id`, `neighbourhood_footprint_id`, `feature_contract_version`, `ingestion_run_id`) SELECT `id`, `neighbourhood_footprint_id`, `feature_contract_version`, `ingestion_run_id` FROM `weather_daily_feature_snapshots`;--> statement-breakpoint
DROP TABLE `weather_daily_feature_snapshots`;--> statement-breakpoint
ALTER TABLE `__new_weather_daily_feature_snapshots` RENAME TO `weather_daily_feature_snapshots`;--> statement-breakpoint
PRAGMA foreign_keys=ON;--> statement-breakpoint
PRAGMA foreign_keys=OFF;--> statement-breakpoint
CREATE TABLE `__new_weather_ingestion_runs` (
	`id` integer PRIMARY KEY,
	`run_key` text NOT NULL CONSTRAINT `weather_ingestion_runs_run_key_unique` UNIQUE,
	`product_run_id` integer NOT NULL,
	`target_local_date` text NOT NULL,
	`ingestion_method` text NOT NULL,
	`request_purpose` text NOT NULL,
	`status` text NOT NULL,
	`source_url` text NOT NULL,
	`permission_basis` text NOT NULL,
	`permission_reference` text NOT NULL,
	`attribution_text` text,
	`model_training_allowed` integer DEFAULT 0 NOT NULL,
	`operational_use_allowed` integer DEFAULT 0 NOT NULL,
	`raw_manifest_path` text NOT NULL,
	`raw_manifest_sha256` text NOT NULL,
	`pipeline_version` text NOT NULL,
	`started_at_utc` text NOT NULL,
	`completed_at_utc` text,
	`samples_seen` integer DEFAULT 0 NOT NULL,
	`samples_accepted` integer DEFAULT 0 NOT NULL,
	`samples_rejected` integer DEFAULT 0 NOT NULL,
	`samples_quarantined` integer DEFAULT 0 NOT NULL,
	`samples_deduplicated` integer DEFAULT 0 NOT NULL,
	`error_summary` text,
	`notes` text,
	CONSTRAINT `fk_weather_ingestion_runs_product_run_id_weather_product_runs_id_fk` FOREIGN KEY (`product_run_id`) REFERENCES `weather_product_runs`(`id`) ON DELETE RESTRICT,
	CONSTRAINT "weather_ingestion_runs_run_key_uuid_v4_check" CHECK("run_key" GLOB
        '[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]-[0-9a-f][0-9a-f][0-9a-f][0-9a-f]-4[0-9a-f][0-9a-f][0-9a-f]-[89ab][0-9a-f][0-9a-f][0-9a-f]-[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]'),
	CONSTRAINT "weather_ingestion_runs_ingestion_method_check" CHECK("ingestion_method" IN ('public_object_archive', 'official_api', 'offline_replay')),
	CONSTRAINT "weather_ingestion_runs_target_local_date_shape_check" CHECK("target_local_date" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
	CONSTRAINT "weather_ingestion_runs_request_purpose_check" CHECK("request_purpose" IN (
        'historical_forecast',
        'operational_forecast',
        'reanalysis_backfill',
        'replay_validation'
      )),
	CONSTRAINT "weather_ingestion_runs_status_check" CHECK("status" IN ('running', 'succeeded', 'failed')),
	CONSTRAINT "weather_ingestion_runs_source_url_non_empty_check" CHECK(length(trim("source_url")) > 0),
	CONSTRAINT "weather_ingestion_runs_permission_basis_non_empty_check" CHECK(length(trim("permission_basis")) > 0),
	CONSTRAINT "weather_ingestion_runs_permission_reference_non_empty_check" CHECK(length(trim("permission_reference")) > 0),
	CONSTRAINT "weather_ingestion_runs_attribution_text_non_empty_check" CHECK("attribution_text" IS NULL OR length(trim("attribution_text")) > 0),
	CONSTRAINT "weather_ingestion_runs_model_training_allowed_boolean_check" CHECK("model_training_allowed" IN (0, 1)),
	CONSTRAINT "weather_ingestion_runs_operational_use_allowed_boolean_check" CHECK("operational_use_allowed" IN (0, 1)),
	CONSTRAINT "weather_ingestion_runs_raw_manifest_path_check" CHECK("raw_manifest_path" LIKE 'data/raw/%'
        AND "raw_manifest_path" NOT LIKE '%..%'),
	CONSTRAINT "weather_ingestion_runs_raw_manifest_sha256_check" CHECK(length("raw_manifest_sha256") = 64
        AND "raw_manifest_sha256" NOT GLOB '*[^0-9a-f]*'),
	CONSTRAINT "weather_ingestion_runs_pipeline_version_check" CHECK(length(trim("pipeline_version")) > 0
        AND "pipeline_version" LIKE '%/%'
        AND "pipeline_version" NOT LIKE '|%'
        AND "pipeline_version" NOT LIKE '%|'
        AND "pipeline_version" NOT LIKE '%||%'),
	CONSTRAINT "weather_ingestion_runs_started_at_utc_shape_check" CHECK("started_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "weather_ingestion_runs_completed_at_utc_shape_check" CHECK("completed_at_utc" IS NULL
        OR "completed_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "weather_ingestion_runs_completion_lifecycle_check" CHECK((
          "status" = 'running'
          AND "completed_at_utc" IS NULL
        )
        OR (
          "status" IN ('succeeded', 'failed')
          AND "completed_at_utc" IS NOT NULL
          AND "completed_at_utc" >= "started_at_utc"
        )),
	CONSTRAINT "weather_ingestion_runs_counters_non_negative_check" CHECK("samples_seen" >= 0
        AND "samples_accepted" >= 0
        AND "samples_rejected" >= 0
        AND "samples_quarantined" >= 0
        AND "samples_deduplicated" >= 0),
	CONSTRAINT "weather_ingestion_runs_counter_outcomes_check" CHECK("samples_accepted" + "samples_rejected" + "samples_quarantined"
        <= "samples_seen")
) STRICT;
--> statement-breakpoint
INSERT INTO `__new_weather_ingestion_runs`(`id`, `run_key`, `ingestion_method`, `request_purpose`, `status`, `source_url`, `permission_basis`, `permission_reference`, `attribution_text`, `model_training_allowed`, `operational_use_allowed`, `raw_manifest_path`, `raw_manifest_sha256`, `pipeline_version`, `started_at_utc`, `completed_at_utc`, `samples_seen`, `samples_accepted`, `samples_rejected`, `samples_quarantined`, `samples_deduplicated`, `error_summary`, `notes`) SELECT `id`, `run_key`, `ingestion_method`, `request_purpose`, `status`, `source_url`, `permission_basis`, `permission_reference`, `attribution_text`, `model_training_allowed`, `operational_use_allowed`, `raw_manifest_path`, `raw_manifest_sha256`, `pipeline_version`, `started_at_utc`, `completed_at_utc`, `samples_seen`, `samples_accepted`, `samples_rejected`, `samples_quarantined`, `samples_deduplicated`, `error_summary`, `notes` FROM `weather_ingestion_runs`;--> statement-breakpoint
DROP TABLE `weather_ingestion_runs`;--> statement-breakpoint
ALTER TABLE `__new_weather_ingestion_runs` RENAME TO `weather_ingestion_runs`;--> statement-breakpoint
PRAGMA foreign_keys=ON;--> statement-breakpoint
PRAGMA foreign_keys=OFF;--> statement-breakpoint
CREATE TABLE `__new_weather_grids` (
	`id` integer PRIMARY KEY,
	`source_id` integer NOT NULL,
	`grid_key` text NOT NULL,
	CONSTRAINT `fk_weather_grids_source_id_weather_sources_id_fk` FOREIGN KEY (`source_id`) REFERENCES `weather_sources`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `weather_grids_source_key_unique` UNIQUE(`source_id`,`grid_key`),
	CONSTRAINT "weather_grids_grid_key_non_empty_check" CHECK(length(trim("grid_key")) > 0)
) STRICT;
--> statement-breakpoint
INSERT INTO `__new_weather_grids`(`id`, `source_id`, `grid_key`) SELECT `id`, `source_id`, `grid_key` FROM `weather_grids`;--> statement-breakpoint
DROP TABLE `weather_grids`;--> statement-breakpoint
ALTER TABLE `__new_weather_grids` RENAME TO `weather_grids`;--> statement-breakpoint
PRAGMA foreign_keys=ON;--> statement-breakpoint
PRAGMA foreign_keys=OFF;--> statement-breakpoint
CREATE TABLE `__new_weather_point_interval_measurements` (
	`id` integer PRIMARY KEY,
	`weather_point_sample_id` integer NOT NULL,
	`field_code` text NOT NULL,
	`component` text NOT NULL,
	`interval_start_utc` text NOT NULL,
	`interval_end_utc` text NOT NULL,
	`statistic_type` text NOT NULL,
	`canonical_value` real,
	CONSTRAINT `fk_weather_interval_measurements_weather_sample_id_weather_samples_id_fk` FOREIGN KEY (`weather_point_sample_id`) REFERENCES `weather_point_samples`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `weather_interval_measurements_identity_unique` UNIQUE(`weather_point_sample_id`,`field_code`,`component`,`statistic_type`,`interval_start_utc`,`interval_end_utc`),
	CONSTRAINT "weather_interval_measurements_field_code_check" CHECK("field_code" IN (
        'precipitation_amount_mm',
        'shortwave_radiation_w_m2',
        'surface_sensible_heat_flux_upward_w_m2',
        'surface_latent_heat_flux_upward_w_m2'
      )),
	CONSTRAINT "weather_interval_measurements_component_check" CHECK("component" IN ('total', 'convective', 'large_scale', 'not_applicable')),
	CONSTRAINT "weather_interval_measurements_component_field_check" CHECK((
          "field_code" = 'precipitation_amount_mm'
          AND "component" IN ('total', 'convective', 'large_scale')
        )
        OR (
          "field_code" <> 'precipitation_amount_mm'
          AND "component" = 'not_applicable'
        )),
	CONSTRAINT "weather_interval_measurements_interval_start_shape_check" CHECK("interval_start_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "weather_interval_measurements_interval_end_shape_check" CHECK("interval_end_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "weather_interval_measurements_statistic_type_check" CHECK("statistic_type" IN ('instantaneous', 'interval_average', 'accumulation')),
	CONSTRAINT "weather_interval_measurements_interval_semantics_check" CHECK((
          "statistic_type" = 'instantaneous'
          AND "interval_start_utc" = "interval_end_utc"
        )
        OR (
          "statistic_type" IN ('interval_average', 'accumulation')
          AND "interval_end_utc" > "interval_start_utc"
        )),
	CONSTRAINT "weather_interval_measurements_non_negative_fields_check" CHECK("canonical_value" IS NULL
        OR "field_code" IN (
          'surface_sensible_heat_flux_upward_w_m2',
          'surface_latent_heat_flux_upward_w_m2'
        )
        OR "canonical_value" >= 0)
) STRICT;
--> statement-breakpoint
INSERT INTO `__new_weather_point_interval_measurements`(`id`, `weather_point_sample_id`, `field_code`, `component`, `interval_start_utc`, `interval_end_utc`, `statistic_type`, `canonical_value`) SELECT `id`, `weather_point_sample_id`, `field_code`, `component`, `interval_start_utc`, `interval_end_utc`, `statistic_type`, `canonical_value` FROM `weather_point_interval_measurements`;--> statement-breakpoint
DROP TABLE `weather_point_interval_measurements`;--> statement-breakpoint
ALTER TABLE `__new_weather_point_interval_measurements` RENAME TO `weather_point_interval_measurements`;--> statement-breakpoint
PRAGMA foreign_keys=ON;--> statement-breakpoint
PRAGMA foreign_keys=OFF;--> statement-breakpoint
CREATE TABLE `__new_weather_product_runs` (
	`id` integer PRIMARY KEY,
	`source_id` integer NOT NULL,
	`source_product_key` text NOT NULL,
	`reference_at_utc` text,
	`available_at_utc` text,
	CONSTRAINT `fk_weather_product_runs_source_id_weather_sources_id_fk` FOREIGN KEY (`source_id`) REFERENCES `weather_sources`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `weather_product_runs_source_product_unique` UNIQUE(`source_id`,`source_product_key`),
	CONSTRAINT "weather_product_runs_source_product_key_non_empty_check" CHECK(length(trim("source_product_key")) > 0),
	CONSTRAINT "weather_product_runs_reference_at_utc_shape_check" CHECK("reference_at_utc" IS NULL
        OR "reference_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "weather_product_runs_available_at_utc_shape_check" CHECK("available_at_utc" IS NULL
        OR "available_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z')
) STRICT;
--> statement-breakpoint
INSERT INTO `__new_weather_product_runs`(`id`, `source_id`, `source_product_key`, `reference_at_utc`, `available_at_utc`) SELECT `id`, `source_id`, `source_product_key`, `reference_at_utc`, `available_at_utc` FROM `weather_product_runs`;--> statement-breakpoint
DROP TABLE `weather_product_runs`;--> statement-breakpoint
ALTER TABLE `__new_weather_product_runs` RENAME TO `weather_product_runs`;--> statement-breakpoint
PRAGMA foreign_keys=ON;--> statement-breakpoint
PRAGMA foreign_keys=OFF;--> statement-breakpoint
CREATE TABLE `__new_weather_point_samples` (
	`id` integer PRIMARY KEY,
	`ingestion_run_id` integer NOT NULL,
	`product_valid_time_id` integer NOT NULL,
	`point_footprint_id` integer NOT NULL,
	`coverage_status` text NOT NULL,
	`air_temperature_2m_k` real,
	`dew_point_temperature_2m_k` real,
	`relative_humidity_2m_percent` real,
	`surface_pressure_pa` real,
	`mean_sea_level_pressure_pa` real,
	`wind_u_10m_m_s` real,
	`wind_v_10m_m_s` real,
	`wind_speed_10m_m_s` real,
	`wind_direction_10m_degrees_from_north` real,
	`provider_boundary_layer_height_agl_m` real,
	`provider_boundary_layer_method` text,
	`provider_cloud_base_agl_m` real,
	`provider_cloud_base_method` text,
	`total_column_water_vapour_kg_m2` real,
	`total_cloud_cover_percent` real,
	`low_cloud_cover_percent` real,
	`mid_cloud_cover_percent` real,
	`high_cloud_cover_percent` real,
	CONSTRAINT `fk_weather_samples_created_by_ingestion_run_id_weather_ingestion_runs_id_fk` FOREIGN KEY (`ingestion_run_id`) REFERENCES `weather_ingestion_runs`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_point_samples_product_valid_time_id_weather_product_valid_times_id_fk` FOREIGN KEY (`product_valid_time_id`) REFERENCES `weather_product_valid_times`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_samples_point_footprint_id_weather_sampling_footprints_id_fk` FOREIGN KEY (`point_footprint_id`) REFERENCES `weather_sampling_footprints`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `weather_point_samples_run_footprint_valid_time_unique` UNIQUE(`ingestion_run_id`,`point_footprint_id`,`product_valid_time_id`),
	CONSTRAINT "weather_samples_coverage_status_check" CHECK("coverage_status" IN ('complete', 'partial', 'insufficient')),
	CONSTRAINT "weather_samples_air_temperature_2m_positive_check" CHECK("air_temperature_2m_k" IS NULL OR "air_temperature_2m_k" > 0),
	CONSTRAINT "weather_samples_dew_point_temperature_2m_positive_check" CHECK("dew_point_temperature_2m_k" IS NULL OR "dew_point_temperature_2m_k" > 0),
	CONSTRAINT "weather_samples_relative_humidity_2m_range_check" CHECK("relative_humidity_2m_percent" IS NULL
        OR "relative_humidity_2m_percent" BETWEEN 0 AND 100),
	CONSTRAINT "weather_samples_surface_pressure_positive_check" CHECK("surface_pressure_pa" IS NULL OR "surface_pressure_pa" > 0),
	CONSTRAINT "weather_samples_mean_sea_level_pressure_positive_check" CHECK("mean_sea_level_pressure_pa" IS NULL OR "mean_sea_level_pressure_pa" > 0),
	CONSTRAINT "weather_samples_wind_speed_10m_non_negative_check" CHECK("wind_speed_10m_m_s" IS NULL OR "wind_speed_10m_m_s" >= 0),
	CONSTRAINT "weather_samples_wind_direction_10m_range_check" CHECK("wind_direction_10m_degrees_from_north" IS NULL
        OR (
          "wind_direction_10m_degrees_from_north" >= 0
          AND "wind_direction_10m_degrees_from_north" < 360
        )),
	CONSTRAINT "weather_samples_boundary_layer_agl_non_negative_check" CHECK("provider_boundary_layer_height_agl_m" IS NULL
        OR "provider_boundary_layer_height_agl_m" >= 0),
	CONSTRAINT "weather_samples_boundary_layer_method_shape_check" CHECK(("provider_boundary_layer_method" IS NULL
          OR length(trim("provider_boundary_layer_method")) > 0)
        AND (("provider_boundary_layer_height_agl_m" IS NULL
            AND "provider_boundary_layer_method" IS NULL)
          OR ("provider_boundary_layer_height_agl_m" IS NOT NULL
            AND "provider_boundary_layer_method" IS NOT NULL))),
	CONSTRAINT "weather_samples_cloud_base_agl_non_negative_check" CHECK("provider_cloud_base_agl_m" IS NULL OR "provider_cloud_base_agl_m" >= 0),
	CONSTRAINT "weather_samples_cloud_base_method_shape_check" CHECK(("provider_cloud_base_method" IS NULL
          OR length(trim("provider_cloud_base_method")) > 0)
        AND (("provider_cloud_base_agl_m" IS NULL
            AND "provider_cloud_base_method" IS NULL)
          OR ("provider_cloud_base_agl_m" IS NOT NULL
            AND "provider_cloud_base_method" IS NOT NULL))),
	CONSTRAINT "weather_samples_total_column_water_vapour_non_negative_check" CHECK("total_column_water_vapour_kg_m2" IS NULL
        OR "total_column_water_vapour_kg_m2" >= 0),
	CONSTRAINT "weather_samples_total_cloud_cover_range_check" CHECK("total_cloud_cover_percent" IS NULL
        OR "total_cloud_cover_percent" BETWEEN 0 AND 100),
	CONSTRAINT "weather_samples_low_cloud_cover_range_check" CHECK("low_cloud_cover_percent" IS NULL
        OR "low_cloud_cover_percent" BETWEEN 0 AND 100),
	CONSTRAINT "weather_samples_mid_cloud_cover_range_check" CHECK("mid_cloud_cover_percent" IS NULL
        OR "mid_cloud_cover_percent" BETWEEN 0 AND 100),
	CONSTRAINT "weather_samples_high_cloud_cover_range_check" CHECK("high_cloud_cover_percent" IS NULL
        OR "high_cloud_cover_percent" BETWEEN 0 AND 100)
) STRICT;
--> statement-breakpoint
INSERT INTO `__new_weather_point_samples`(`id`, `point_footprint_id`, `coverage_status`, `air_temperature_2m_k`, `dew_point_temperature_2m_k`, `relative_humidity_2m_percent`, `surface_pressure_pa`, `mean_sea_level_pressure_pa`, `wind_u_10m_m_s`, `wind_v_10m_m_s`, `wind_speed_10m_m_s`, `wind_direction_10m_degrees_from_north`, `provider_boundary_layer_height_agl_m`, `provider_boundary_layer_method`, `provider_cloud_base_agl_m`, `provider_cloud_base_method`, `total_column_water_vapour_kg_m2`, `total_cloud_cover_percent`, `low_cloud_cover_percent`, `mid_cloud_cover_percent`, `high_cloud_cover_percent`, `ingestion_run_id`) SELECT `id`, `point_footprint_id`, `coverage_status`, `air_temperature_2m_k`, `dew_point_temperature_2m_k`, `relative_humidity_2m_percent`, `surface_pressure_pa`, `mean_sea_level_pressure_pa`, `wind_u_10m_m_s`, `wind_v_10m_m_s`, `wind_speed_10m_m_s`, `wind_direction_10m_degrees_from_north`, `provider_boundary_layer_height_agl_m`, `provider_boundary_layer_method`, `provider_cloud_base_agl_m`, `provider_cloud_base_method`, `total_column_water_vapour_kg_m2`, `total_cloud_cover_percent`, `low_cloud_cover_percent`, `mid_cloud_cover_percent`, `high_cloud_cover_percent`, `ingestion_run_id` FROM `weather_point_samples`;--> statement-breakpoint
DROP TABLE `weather_point_samples`;--> statement-breakpoint
ALTER TABLE `__new_weather_point_samples` RENAME TO `weather_point_samples`;--> statement-breakpoint
PRAGMA foreign_keys=ON;--> statement-breakpoint
PRAGMA foreign_keys=OFF;--> statement-breakpoint
CREATE TABLE `__new_weather_sampling_footprints` (
	`id` integer PRIMARY KEY,
	`site_id` integer NOT NULL,
	`grid_id` integer NOT NULL,
	`purpose` text NOT NULL,
	`sampling_method` text NOT NULL,
	`sampling_method_version` text NOT NULL,
	`radius_km` real,
	CONSTRAINT `fk_weather_sampling_footprints_site_id_weather_site_sampling_configs_site_id_fk` FOREIGN KEY (`site_id`) REFERENCES `weather_site_sampling_configs`(`site_id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_sampling_footprints_grid_id_weather_grids_id_fk` FOREIGN KEY (`grid_id`) REFERENCES `weather_grids`(`id`) ON DELETE RESTRICT,
	CONSTRAINT "weather_sampling_footprints_purpose_check" CHECK("purpose" IN ('point', 'neighbourhood')),
	CONSTRAINT "weather_sampling_footprints_sampling_method_check" CHECK("sampling_method" IN ('nearest', 'bilinear', 'radius')),
	CONSTRAINT "weather_sampling_footprints_method_purpose_shape_check" CHECK((
          "purpose" = 'point'
          AND "sampling_method" IN ('nearest', 'bilinear')
          AND "radius_km" IS NULL
        )
        OR (
          "purpose" = 'neighbourhood'
          AND "sampling_method" = 'radius'
          AND "radius_km" IS NOT NULL
          AND "radius_km" > 0
        )),
	CONSTRAINT "weather_sampling_footprints_method_version_non_empty_check" CHECK(length(trim("sampling_method_version")) > 0)
) STRICT;
--> statement-breakpoint
INSERT INTO `__new_weather_sampling_footprints`(`id`, `site_id`, `grid_id`, `purpose`, `sampling_method`, `sampling_method_version`, `radius_km`) SELECT `id`, `site_id`, `grid_id`, `purpose`, `sampling_method`, `sampling_method_version`, `radius_km` FROM `weather_sampling_footprints`;--> statement-breakpoint
DROP TABLE `weather_sampling_footprints`;--> statement-breakpoint
ALTER TABLE `__new_weather_sampling_footprints` RENAME TO `weather_sampling_footprints`;--> statement-breakpoint
PRAGMA foreign_keys=ON;--> statement-breakpoint
PRAGMA foreign_keys=OFF;--> statement-breakpoint
CREATE TABLE `__new_weather_grid_points` (
	`id` integer PRIMARY KEY,
	`grid_id` integer NOT NULL,
	`latitude_deg` real NOT NULL,
	`longitude_deg` real NOT NULL,
	`model_elevation_msl_m` real,
	CONSTRAINT `fk_weather_grid_points_grid_id_weather_grids_id_fk` FOREIGN KEY (`grid_id`) REFERENCES `weather_grids`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `weather_grid_points_grid_coordinate_unique` UNIQUE(`grid_id`,`latitude_deg`,`longitude_deg`),
	CONSTRAINT "weather_grid_points_latitude_range_check" CHECK("latitude_deg" BETWEEN -90 AND 90),
	CONSTRAINT "weather_grid_points_longitude_range_check" CHECK("longitude_deg" BETWEEN -180 AND 180)
) STRICT;
--> statement-breakpoint
INSERT INTO `__new_weather_grid_points`(`id`, `grid_id`, `latitude_deg`, `longitude_deg`, `model_elevation_msl_m`) SELECT `id`, `grid_id`, `latitude_deg`, `longitude_deg`, `model_elevation_msl_m` FROM `weather_grid_points`;--> statement-breakpoint
DROP TABLE `weather_grid_points`;--> statement-breakpoint
ALTER TABLE `__new_weather_grid_points` RENAME TO `weather_grid_points`;--> statement-breakpoint
PRAGMA foreign_keys=ON;--> statement-breakpoint
PRAGMA foreign_keys=OFF;--> statement-breakpoint
CREATE TABLE `__new_weather_field_provenance` (
	`id` integer PRIMARY KEY,
	`weather_point_sample_id` integer,
	`point_convection_measurement_id` integer,
	`point_interval_measurement_id` integer,
	`point_profile_level_id` integer,
	`daily_feature_snapshot_id` integer,
	`daily_feature_profile_layer_id` integer,
	`field_code` text NOT NULL,
	`field_variant` text DEFAULT 'canonical' NOT NULL,
	`quality_state` text NOT NULL,
	`source_reference_at_utc` text,
	`native_field_name` text,
	`native_unit` text,
	`native_value` real,
	`native_sign_convention` text,
	`native_step_type` text,
	`step_start_hours` real,
	`step_end_hours` real,
	`statistic_type` text,
	`normalization_method` text,
	`normalization_version` text,
	`derivation_method` text,
	`derivation_version` text,
	`raw_artifact_key` text,
	`native_message_reference` text,
	CONSTRAINT `fk_weather_field_provenance_weather_sample_id_weather_samples_id_fk` FOREIGN KEY (`weather_point_sample_id`) REFERENCES `weather_point_samples`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_field_provenance_convection_measurement_id_weather_convection_measurements_id_fk` FOREIGN KEY (`point_convection_measurement_id`) REFERENCES `weather_point_convection_measurements`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_field_provenance_interval_measurement_id_weather_interval_measurements_id_fk` FOREIGN KEY (`point_interval_measurement_id`) REFERENCES `weather_point_interval_measurements`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_field_provenance_profile_level_id_weather_profile_levels_id_fk` FOREIGN KEY (`point_profile_level_id`) REFERENCES `weather_point_profile_levels`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_field_provenance_feature_snapshot_id_weather_feature_snapshots_id_fk` FOREIGN KEY (`daily_feature_snapshot_id`) REFERENCES `weather_daily_feature_snapshots`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_field_provenance_daily_feature_profile_layer_id_weather_daily_feature_profile_layers_id_fk` FOREIGN KEY (`daily_feature_profile_layer_id`) REFERENCES `weather_daily_feature_profile_layers`(`id`) ON DELETE RESTRICT,
	CONSTRAINT "weather_field_provenance_exactly_one_owner_check" CHECK((
          ("weather_point_sample_id" IS NOT NULL)
          + ("point_convection_measurement_id" IS NOT NULL)
          + ("point_interval_measurement_id" IS NOT NULL)
          + ("point_profile_level_id" IS NOT NULL)
          + ("daily_feature_snapshot_id" IS NOT NULL)
          + ("daily_feature_profile_layer_id" IS NOT NULL)
        ) = 1),
	CONSTRAINT "weather_field_provenance_field_code_non_empty_check" CHECK(length(trim("field_code")) > 0),
	CONSTRAINT "weather_field_provenance_field_variant_non_empty_check" CHECK(length(trim("field_variant")) > 0),
	CONSTRAINT "weather_field_provenance_quality_state_check" CHECK("quality_state" IN (
        'real',
        'derived',
        'missing',
        'sentinel_missing',
        'invalid_payload',
        'unsupported'
      )),
	CONSTRAINT "weather_field_provenance_source_reference_at_utc_shape_check" CHECK("source_reference_at_utc" IS NULL
        OR "source_reference_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "weather_field_provenance_optional_text_non_empty_check" CHECK(("native_field_name" IS NULL OR length(trim("native_field_name")) > 0)
        AND ("native_unit" IS NULL OR length(trim("native_unit")) > 0)
        AND ("native_sign_convention" IS NULL
          OR length(trim("native_sign_convention")) > 0)
        AND ("native_step_type" IS NULL OR length(trim("native_step_type")) > 0)
        AND ("statistic_type" IS NULL OR length(trim("statistic_type")) > 0)
        AND ("raw_artifact_key" IS NULL OR length(trim("raw_artifact_key")) > 0)
        AND ("native_message_reference" IS NULL
          OR length(trim("native_message_reference")) > 0)),
	CONSTRAINT "weather_field_provenance_step_shape_check" CHECK((
          "step_start_hours" IS NULL
          AND "step_end_hours" IS NULL
        )
        OR (
          "step_start_hours" IS NOT NULL
          AND "step_end_hours" IS NOT NULL
          AND "step_start_hours" >= 0
          AND "step_end_hours" >= "step_start_hours"
        )),
	CONSTRAINT "weather_field_provenance_normalization_pair_check" CHECK((
          "normalization_method" IS NULL
          AND "normalization_version" IS NULL
        )
        OR (
          "normalization_method" IS NOT NULL
          AND length(trim("normalization_method")) > 0
          AND "normalization_version" IS NOT NULL
          AND length(trim("normalization_version")) > 0
        )),
	CONSTRAINT "weather_field_provenance_derivation_pair_check" CHECK((
          "derivation_method" IS NULL
          AND "derivation_version" IS NULL
        )
        OR (
          "derivation_method" IS NOT NULL
          AND length(trim("derivation_method")) > 0
          AND "derivation_version" IS NOT NULL
          AND length(trim("derivation_version")) > 0
        )),
	CONSTRAINT "weather_field_provenance_missing_native_value_check" CHECK("quality_state" NOT IN ('missing', 'sentinel_missing', 'unsupported')
        OR "native_value" IS NULL)
) STRICT;
--> statement-breakpoint
INSERT INTO `__new_weather_field_provenance`(`id`, `weather_point_sample_id`, `point_convection_measurement_id`, `point_interval_measurement_id`, `point_profile_level_id`, `daily_feature_snapshot_id`, `field_code`, `field_variant`, `quality_state`, `source_reference_at_utc`, `native_field_name`, `native_unit`, `native_value`, `native_sign_convention`, `native_step_type`, `step_start_hours`, `step_end_hours`, `statistic_type`, `normalization_method`, `normalization_version`, `derivation_method`, `derivation_version`, `raw_artifact_key`, `native_message_reference`) SELECT `id`, `weather_point_sample_id`, `point_convection_measurement_id`, `point_interval_measurement_id`, `point_profile_level_id`, `daily_feature_snapshot_id`, `field_code`, `field_variant`, `quality_state`, `source_reference_at_utc`, `native_field_name`, `native_unit`, `native_value`, `native_sign_convention`, `native_step_type`, `step_start_hours`, `step_end_hours`, `statistic_type`, `normalization_method`, `normalization_version`, `derivation_method`, `derivation_version`, `raw_artifact_key`, `native_message_reference` FROM `weather_field_provenance`;--> statement-breakpoint
DROP TABLE `weather_field_provenance`;--> statement-breakpoint
ALTER TABLE `__new_weather_field_provenance` RENAME TO `weather_field_provenance`;--> statement-breakpoint
PRAGMA foreign_keys=ON;--> statement-breakpoint
PRAGMA foreign_keys=OFF;--> statement-breakpoint
CREATE TABLE `__new_weather_point_profile_levels` (
	`id` integer PRIMARY KEY,
	`weather_point_sample_id` integer NOT NULL,
	`pressure_pa` real NOT NULL,
	`geopotential_height_msl_m` real,
	`level_height_site_agl_m` real,
	`air_temperature_k` real,
	`dew_point_temperature_k` real,
	`relative_humidity_percent` real,
	`specific_humidity_kg_per_kg` real,
	`wind_u_m_s` real,
	`wind_v_m_s` real,
	`wind_speed_m_s` real,
	`wind_direction_degrees_from_north` real,
	`vertical_velocity_pa_s` real,
	CONSTRAINT `fk_weather_profile_levels_weather_sample_id_weather_samples_id_fk` FOREIGN KEY (`weather_point_sample_id`) REFERENCES `weather_point_samples`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `weather_profile_levels_sample_pressure_unique` UNIQUE(`weather_point_sample_id`,`pressure_pa`),
	CONSTRAINT "weather_profile_levels_pressure_positive_check" CHECK("pressure_pa" > 0),
	CONSTRAINT "weather_profile_levels_height_agl_non_negative_check" CHECK("level_height_site_agl_m" IS NULL OR "level_height_site_agl_m" >= 0),
	CONSTRAINT "weather_profile_levels_air_temperature_positive_check" CHECK("air_temperature_k" IS NULL OR "air_temperature_k" > 0),
	CONSTRAINT "weather_profile_levels_dew_point_temperature_positive_check" CHECK("dew_point_temperature_k" IS NULL OR "dew_point_temperature_k" > 0),
	CONSTRAINT "weather_profile_levels_relative_humidity_range_check" CHECK("relative_humidity_percent" IS NULL
        OR "relative_humidity_percent" BETWEEN 0 AND 100),
	CONSTRAINT "weather_profile_levels_specific_humidity_non_negative_check" CHECK("specific_humidity_kg_per_kg" IS NULL
        OR "specific_humidity_kg_per_kg" >= 0),
	CONSTRAINT "weather_profile_levels_wind_speed_non_negative_check" CHECK("wind_speed_m_s" IS NULL OR "wind_speed_m_s" >= 0),
	CONSTRAINT "weather_profile_levels_wind_direction_range_check" CHECK("wind_direction_degrees_from_north" IS NULL
        OR (
          "wind_direction_degrees_from_north" >= 0
          AND "wind_direction_degrees_from_north" < 360
        ))
) STRICT;
--> statement-breakpoint
INSERT INTO `__new_weather_point_profile_levels`(`id`, `weather_point_sample_id`, `pressure_pa`, `geopotential_height_msl_m`, `level_height_site_agl_m`, `air_temperature_k`, `dew_point_temperature_k`, `relative_humidity_percent`, `specific_humidity_kg_per_kg`, `wind_u_m_s`, `wind_v_m_s`, `wind_speed_m_s`, `wind_direction_degrees_from_north`) SELECT `id`, `weather_point_sample_id`, `pressure_pa`, `geopotential_height_msl_m`, `level_height_site_agl_m`, `air_temperature_k`, `dew_point_temperature_k`, `relative_humidity_percent`, `specific_humidity_kg_per_kg`, `wind_u_m_s`, `wind_v_m_s`, `wind_speed_m_s`, `wind_direction_degrees_from_north` FROM `weather_point_profile_levels`;--> statement-breakpoint
DROP TABLE `weather_point_profile_levels`;--> statement-breakpoint
ALTER TABLE `__new_weather_point_profile_levels` RENAME TO `weather_point_profile_levels`;--> statement-breakpoint
PRAGMA foreign_keys=ON;--> statement-breakpoint
DROP INDEX IF EXISTS `weather_feature_snapshots_sample_index`;--> statement-breakpoint
DROP INDEX IF EXISTS `weather_feature_snapshots_contract_index`;--> statement-breakpoint
DROP INDEX IF EXISTS `weather_feature_snapshots_created_by_run_index`;--> statement-breakpoint
DROP INDEX IF EXISTS `weather_ingestion_runs_source_started_at_index`;--> statement-breakpoint
DROP INDEX IF EXISTS `weather_convection_measurements_sample_index`;--> statement-breakpoint
DROP INDEX IF EXISTS `weather_samples_footprint_valid_at_index`;--> statement-breakpoint
DROP INDEX IF EXISTS `weather_samples_product_valid_at_index`;--> statement-breakpoint
DROP INDEX IF EXISTS `weather_samples_valid_local_date_index`;--> statement-breakpoint
DROP INDEX IF EXISTS `weather_samples_created_by_ingestion_run_index`;--> statement-breakpoint
DROP INDEX IF EXISTS `weather_samples_coverage_status_index`;--> statement-breakpoint
DROP INDEX IF EXISTS `weather_sampling_footprints_site_purpose_version_index`;--> statement-breakpoint
DROP INDEX IF EXISTS `weather_grid_points_first_seen_run_index`;--> statement-breakpoint
DROP INDEX IF EXISTS `weather_grids_active_key_unique`;--> statement-breakpoint
DROP INDEX IF EXISTS `weather_grids_source_active_index`;--> statement-breakpoint
DROP INDEX IF EXISTS `weather_product_runs_valid_range_index`;--> statement-breakpoint
DROP INDEX IF EXISTS `weather_product_runs_created_by_ingestion_run_index`;--> statement-breakpoint
CREATE INDEX `weather_daily_feature_snapshots_contract_index` ON `weather_daily_feature_snapshots` (`feature_contract_version`);--> statement-breakpoint
CREATE INDEX `weather_daily_feature_snapshots_point_footprint_index` ON `weather_daily_feature_snapshots` (`point_footprint_id`);--> statement-breakpoint
CREATE INDEX `weather_ingestion_runs_product_target_date_index` ON `weather_ingestion_runs` (`product_run_id`,`target_local_date`);--> statement-breakpoint
CREATE INDEX `weather_ingestion_runs_status_started_at_index` ON `weather_ingestion_runs` (`status`,"started_at_utc" desc);--> statement-breakpoint
CREATE INDEX `weather_ingestion_runs_purpose_status_index` ON `weather_ingestion_runs` (`request_purpose`,`status`);--> statement-breakpoint
CREATE INDEX `weather_interval_measurements_sample_interval_index` ON `weather_point_interval_measurements` (`weather_point_sample_id`,`interval_start_utc`,`interval_end_utc`);--> statement-breakpoint
CREATE INDEX `weather_interval_measurements_field_interval_index` ON `weather_point_interval_measurements` (`field_code`,`interval_start_utc`,`interval_end_utc`);--> statement-breakpoint
CREATE INDEX `weather_product_runs_source_reference_at_index` ON `weather_product_runs` (`source_id`,"reference_at_utc" desc);--> statement-breakpoint
CREATE INDEX `weather_point_samples_footprint_index` ON `weather_point_samples` (`point_footprint_id`);--> statement-breakpoint
CREATE INDEX `weather_point_samples_run_valid_time_index` ON `weather_point_samples` (`ingestion_run_id`,`product_valid_time_id`);--> statement-breakpoint
CREATE INDEX `weather_point_samples_coverage_status_index` ON `weather_point_samples` (`coverage_status`);--> statement-breakpoint
CREATE UNIQUE INDEX `weather_sampling_footprints_point_identity_unique` ON `weather_sampling_footprints` (`site_id`,`grid_id`,`sampling_method`,`sampling_method_version`) WHERE "weather_sampling_footprints"."purpose" = 'point';--> statement-breakpoint
CREATE UNIQUE INDEX `weather_sampling_footprints_neighbourhood_identity_unique` ON `weather_sampling_footprints` (`site_id`,`grid_id`,`sampling_method`,`sampling_method_version`,`radius_km`) WHERE "weather_sampling_footprints"."purpose" = 'neighbourhood';--> statement-breakpoint
CREATE INDEX `weather_sampling_footprints_site_purpose_index` ON `weather_sampling_footprints` (`site_id`,`purpose`);--> statement-breakpoint
CREATE INDEX `weather_sampling_footprints_grid_index` ON `weather_sampling_footprints` (`grid_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `weather_field_provenance_sample_field_unique` ON `weather_field_provenance` (`weather_point_sample_id`,`field_code`,`field_variant`) WHERE "weather_field_provenance"."weather_point_sample_id" IS NOT NULL;--> statement-breakpoint
CREATE UNIQUE INDEX `weather_field_provenance_convection_field_unique` ON `weather_field_provenance` (`point_convection_measurement_id`,`field_code`,`field_variant`) WHERE "weather_field_provenance"."point_convection_measurement_id" IS NOT NULL;--> statement-breakpoint
CREATE UNIQUE INDEX `weather_field_provenance_interval_field_unique` ON `weather_field_provenance` (`point_interval_measurement_id`,`field_code`,`field_variant`) WHERE "weather_field_provenance"."point_interval_measurement_id" IS NOT NULL;--> statement-breakpoint
CREATE UNIQUE INDEX `weather_field_provenance_profile_field_unique` ON `weather_field_provenance` (`point_profile_level_id`,`field_code`,`field_variant`) WHERE "weather_field_provenance"."point_profile_level_id" IS NOT NULL;--> statement-breakpoint
CREATE UNIQUE INDEX `weather_field_provenance_feature_field_unique` ON `weather_field_provenance` (`daily_feature_snapshot_id`,`field_code`,`field_variant`) WHERE "weather_field_provenance"."daily_feature_snapshot_id" IS NOT NULL;--> statement-breakpoint
CREATE UNIQUE INDEX `weather_field_provenance_feature_layer_field_unique` ON `weather_field_provenance` (`daily_feature_profile_layer_id`,`field_code`,`field_variant`) WHERE "weather_field_provenance"."daily_feature_profile_layer_id" IS NOT NULL;--> statement-breakpoint
CREATE INDEX `weather_field_provenance_field_quality_index` ON `weather_field_provenance` (`field_code`,`quality_state`);--> statement-breakpoint
CREATE INDEX `weather_field_provenance_source_reference_index` ON `weather_field_provenance` (`source_reference_at_utc`);--> statement-breakpoint
CREATE INDEX `weather_profile_levels_pressure_sample_index` ON `weather_point_profile_levels` (`pressure_pa`,`weather_point_sample_id`);--> statement-breakpoint
CREATE INDEX `weather_daily_feature_snapshot_inputs_sample_index` ON `weather_daily_feature_snapshot_inputs` (`weather_point_sample_id`);--> statement-breakpoint
CREATE INDEX `weather_point_convection_measurements_sample_index` ON `weather_point_convection_measurements` (`weather_point_sample_id`);--> statement-breakpoint
CREATE INDEX `weather_product_valid_times_valid_at_index` ON `weather_product_valid_times` (`valid_at_utc`);
