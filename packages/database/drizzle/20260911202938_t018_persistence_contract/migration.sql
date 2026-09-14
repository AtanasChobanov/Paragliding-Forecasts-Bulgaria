ALTER TABLE `weather_daily_feature_snapshots` ADD `mixed_layer_lcl_agl_mean_m` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `mixed_layer_lcl_agl_min_m` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `mixed_layer_lcl_agl_max_m` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `pbl_minus_lcl_mean_m` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `pbl_minus_lcl_max_m` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `surface_buoyancy_flux_kinematic_mean_m2_s3` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `surface_buoyancy_flux_kinematic_max_m2_s3` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `convective_velocity_scale_mean_m_s` real;--> statement-breakpoint
ALTER TABLE `weather_daily_feature_snapshots` ADD `convective_velocity_scale_max_m_s` real;--> statement-breakpoint
ALTER TABLE `weather_field_provenance` ADD `missing_reason_code` text;--> statement-breakpoint
ALTER TABLE `weather_ingestion_runs` ADD `feature_manifest_path` text;--> statement-breakpoint
ALTER TABLE `weather_ingestion_runs` ADD `feature_manifest_sha256` text;--> statement-breakpoint
ALTER TABLE `weather_ingestion_runs` ADD `persistence_input_sha256` text;--> statement-breakpoint
ALTER TABLE `weather_point_samples` ADD `mixed_layer_lcl_agl_m` real;--> statement-breakpoint
ALTER TABLE `weather_point_samples` ADD `pbl_minus_lcl_m` real;--> statement-breakpoint
ALTER TABLE `weather_point_samples` ADD `surface_buoyancy_flux_kinematic_m2_s3` real;--> statement-breakpoint
ALTER TABLE `weather_point_samples` ADD `convective_velocity_scale_m_s` real;--> statement-breakpoint
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
	`mixed_layer_lcl_agl_mean_m` real,
	`mixed_layer_lcl_agl_min_m` real,
	`mixed_layer_lcl_agl_max_m` real,
	`pbl_minus_lcl_mean_m` real,
	`pbl_minus_lcl_max_m` real,
	`surface_buoyancy_flux_kinematic_mean_m2_s3` real,
	`surface_buoyancy_flux_kinematic_max_m2_s3` real,
	`convective_velocity_scale_mean_m_s` real,
	`convective_velocity_scale_max_m_s` real,
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
	`cin_magnitude_max_j_per_kg` real,
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
	CONSTRAINT "weather_daily_feature_snapshots_s08_derived_shape_check" CHECK(("mixed_layer_lcl_agl_mean_m" IS NULL OR "mixed_layer_lcl_agl_mean_m" >= 0)
        AND ("mixed_layer_lcl_agl_min_m" IS NULL OR "mixed_layer_lcl_agl_min_m" >= 0)
        AND ("mixed_layer_lcl_agl_max_m" IS NULL OR "mixed_layer_lcl_agl_max_m" >= 0)
        AND ("mixed_layer_lcl_agl_min_m" IS NULL OR "mixed_layer_lcl_agl_mean_m" IS NULL
          OR "mixed_layer_lcl_agl_min_m" <= "mixed_layer_lcl_agl_mean_m")
        AND ("mixed_layer_lcl_agl_mean_m" IS NULL OR "mixed_layer_lcl_agl_max_m" IS NULL
          OR "mixed_layer_lcl_agl_mean_m" <= "mixed_layer_lcl_agl_max_m")
        AND ("convective_velocity_scale_mean_m_s" IS NULL OR "convective_velocity_scale_mean_m_s" >= 0)
        AND ("convective_velocity_scale_max_m_s" IS NULL OR "convective_velocity_scale_max_m_s" >= 0)
        AND ("convective_velocity_scale_mean_m_s" IS NULL OR "convective_velocity_scale_max_m_s" IS NULL
          OR "convective_velocity_scale_mean_m_s" <= "convective_velocity_scale_max_m_s")),
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
        AND ("cin_magnitude_max_j_per_kg" IS NULL OR "cin_magnitude_max_j_per_kg" >= 0)
        AND ("neighbourhood_pressure_gradient_mean_pa_per_km" IS NULL OR "neighbourhood_pressure_gradient_mean_pa_per_km" >= 0)
        AND ("neighbourhood_pressure_gradient_max_pa_per_km" IS NULL OR "neighbourhood_pressure_gradient_max_pa_per_km" >= 0))
) STRICT;
--> statement-breakpoint
INSERT INTO `__new_weather_daily_feature_snapshots`(`id`, `ingestion_run_id`, `point_footprint_id`, `neighbourhood_footprint_id`, `feature_contract_version`, `air_temperature_2m_mean_k`, `air_temperature_2m_min_k`, `air_temperature_2m_max_k`, `dew_point_temperature_2m_mean_k`, `relative_humidity_2m_mean_percent`, `relative_humidity_2m_max_percent`, `surface_pressure_mean_pa`, `mean_sea_level_pressure_mean_pa`, `wind_u_10m_mean_m_s`, `wind_v_10m_mean_m_s`, `wind_speed_10m_mean_m_s`, `wind_speed_10m_max_m_s`, `wind_direction_10m_mean_degrees_from_north`, `provider_boundary_layer_height_agl_mean_m`, `provider_boundary_layer_height_agl_max_m`, `provider_cloud_base_agl_mean_m`, `provider_cloud_base_agl_min_m`, `provider_cloud_base_agl_max_m`, `total_column_water_vapour_mean_kg_m2`, `total_cloud_cover_mean_percent`, `total_cloud_cover_max_percent`, `low_cloud_cover_mean_percent`, `low_cloud_cover_max_percent`, `mid_cloud_cover_mean_percent`, `high_cloud_cover_mean_percent`, `precipitation_total_mm`, `precipitation_max_hourly_mm`, `shortwave_radiation_mean_w_m2`, `shortwave_radiation_max_w_m2`, `surface_sensible_heat_flux_mean_w_m2`, `surface_latent_heat_flux_mean_w_m2`, `cape_max_j_per_kg`, `cin_magnitude_max_j_per_kg`, `neighbourhood_pressure_gradient_mean_pa_per_km`, `neighbourhood_pressure_gradient_max_pa_per_km`, `neighbourhood_low_level_divergence_mean_s_inverse`, `neighbourhood_low_level_divergence_min_s_inverse`) SELECT `id`, `ingestion_run_id`, `point_footprint_id`, `neighbourhood_footprint_id`, `feature_contract_version`, `air_temperature_2m_mean_k`, `air_temperature_2m_min_k`, `air_temperature_2m_max_k`, `dew_point_temperature_2m_mean_k`, `relative_humidity_2m_mean_percent`, `relative_humidity_2m_max_percent`, `surface_pressure_mean_pa`, `mean_sea_level_pressure_mean_pa`, `wind_u_10m_mean_m_s`, `wind_v_10m_mean_m_s`, `wind_speed_10m_mean_m_s`, `wind_speed_10m_max_m_s`, `wind_direction_10m_mean_degrees_from_north`, `provider_boundary_layer_height_agl_mean_m`, `provider_boundary_layer_height_agl_max_m`, `provider_cloud_base_agl_mean_m`, `provider_cloud_base_agl_min_m`, `provider_cloud_base_agl_max_m`, `total_column_water_vapour_mean_kg_m2`, `total_cloud_cover_mean_percent`, `total_cloud_cover_max_percent`, `low_cloud_cover_mean_percent`, `low_cloud_cover_max_percent`, `mid_cloud_cover_mean_percent`, `high_cloud_cover_mean_percent`, `precipitation_total_mm`, `precipitation_max_hourly_mm`, `shortwave_radiation_mean_w_m2`, `shortwave_radiation_max_w_m2`, `surface_sensible_heat_flux_mean_w_m2`, `surface_latent_heat_flux_mean_w_m2`, `cape_max_j_per_kg`, `cin_magnitude_max_j_per_kg`, `neighbourhood_pressure_gradient_mean_pa_per_km`, `neighbourhood_pressure_gradient_max_pa_per_km`, `neighbourhood_low_level_divergence_mean_s_inverse`, `neighbourhood_low_level_divergence_min_s_inverse` FROM `weather_daily_feature_snapshots`;--> statement-breakpoint
DROP TABLE `weather_daily_feature_snapshots`;--> statement-breakpoint
ALTER TABLE `__new_weather_daily_feature_snapshots` RENAME TO `weather_daily_feature_snapshots`;--> statement-breakpoint
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
	`missing_reason_code` text,
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
	CONSTRAINT "weather_field_provenance_missing_reason_shape_check" CHECK((
          "quality_state" IN ('missing', 'sentinel_missing', 'invalid_payload', 'unsupported')
          AND "missing_reason_code" IS NOT NULL
          AND "missing_reason_code" GLOB '[a-z]*'
          AND "missing_reason_code" NOT GLOB '*[^a-z0-9_]*'
        )
        OR (
          "quality_state" IN ('real', 'derived')
          AND "missing_reason_code" IS NULL
        )),
	CONSTRAINT "weather_field_provenance_daily_statistic_required_check" CHECK((
          "daily_feature_snapshot_id" IS NULL
          AND "daily_feature_profile_layer_id" IS NULL
        )
        OR (
          "statistic_type" IS NOT NULL
          AND length(trim("statistic_type")) > 0
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
	CONSTRAINT "weather_field_provenance_missing_native_value_check" CHECK("quality_state" NOT IN ('missing', 'sentinel_missing', 'invalid_payload', 'unsupported')
        OR "native_value" IS NULL)
) STRICT;
--> statement-breakpoint
INSERT INTO `__new_weather_field_provenance`(`id`, `weather_point_sample_id`, `point_convection_measurement_id`, `point_interval_measurement_id`, `point_profile_level_id`, `daily_feature_snapshot_id`, `daily_feature_profile_layer_id`, `field_code`, `field_variant`, `quality_state`, `source_reference_at_utc`, `native_field_name`, `native_unit`, `native_value`, `native_sign_convention`, `native_step_type`, `step_start_hours`, `step_end_hours`, `statistic_type`, `normalization_method`, `normalization_version`, `derivation_method`, `derivation_version`, `raw_artifact_key`, `native_message_reference`) SELECT `id`, `weather_point_sample_id`, `point_convection_measurement_id`, `point_interval_measurement_id`, `point_profile_level_id`, `daily_feature_snapshot_id`, `daily_feature_profile_layer_id`, `field_code`, `field_variant`, `quality_state`, `source_reference_at_utc`, `native_field_name`, `native_unit`, `native_value`, `native_sign_convention`, `native_step_type`, `step_start_hours`, `step_end_hours`, `statistic_type`, `normalization_method`, `normalization_version`, `derivation_method`, `derivation_version`, `raw_artifact_key`, `native_message_reference` FROM `weather_field_provenance`;--> statement-breakpoint
DROP TABLE `weather_field_provenance`;--> statement-breakpoint
ALTER TABLE `__new_weather_field_provenance` RENAME TO `weather_field_provenance`;--> statement-breakpoint
PRAGMA foreign_keys=ON;--> statement-breakpoint
PRAGMA foreign_keys=OFF;--> statement-breakpoint
CREATE TABLE `__new_weather_grids` (
	`id` integer PRIMARY KEY,
	`source_id` integer NOT NULL,
	`grid_key` text NOT NULL,
	CONSTRAINT `fk_weather_grids_source_id_weather_sources_id_fk` FOREIGN KEY (`source_id`) REFERENCES `weather_sources`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `weather_grids_source_key_unique` UNIQUE(`source_id`,`grid_key`),
	CONSTRAINT "weather_grids_grid_key_non_empty_check" CHECK(length(trim("grid_key")) > 0),
	CONSTRAINT "weather_grids_grid_key_supported_check" CHECK("grid_key" IN ('gfs_0p25_global', 'era5_0p25_global'))
) STRICT;
--> statement-breakpoint
INSERT INTO `__new_weather_grids`(`id`, `source_id`, `grid_key`) SELECT `id`, `source_id`, `grid_key` FROM `weather_grids`;--> statement-breakpoint
DROP TABLE `weather_grids`;--> statement-breakpoint
ALTER TABLE `__new_weather_grids` RENAME TO `weather_grids`;--> statement-breakpoint
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
	`feature_manifest_path` text,
	`feature_manifest_sha256` text,
	`persistence_input_sha256` text,
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
	CONSTRAINT "weather_ingestion_runs_feature_manifest_path_check" CHECK("feature_manifest_path" IS NULL
        OR (
          "feature_manifest_path" LIKE 'data/interim/%'
          AND "feature_manifest_path" NOT LIKE '%..%'
        )),
	CONSTRAINT "weather_ingestion_runs_feature_manifest_sha256_check" CHECK("feature_manifest_sha256" IS NULL
        OR (
          length("feature_manifest_sha256") = 64
          AND "feature_manifest_sha256" NOT GLOB '*[^0-9a-f]*'
        )),
	CONSTRAINT "weather_ingestion_runs_persistence_input_sha256_check" CHECK("persistence_input_sha256" IS NULL
        OR (
          length("persistence_input_sha256") = 64
          AND "persistence_input_sha256" NOT GLOB '*[^0-9a-f]*'
        )),
	CONSTRAINT "weather_ingestion_runs_feature_persistence_lifecycle_check" CHECK((
          "status" IN ('running', 'failed')
          AND "feature_manifest_path" IS NULL
          AND "feature_manifest_sha256" IS NULL
          AND "persistence_input_sha256" IS NULL
        )
        OR (
          "status" = 'succeeded'
          AND "feature_manifest_path" IS NOT NULL
          AND "feature_manifest_sha256" IS NOT NULL
          AND "persistence_input_sha256" IS NOT NULL
        )),
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
INSERT INTO `__new_weather_ingestion_runs`(`id`, `run_key`, `product_run_id`, `target_local_date`, `ingestion_method`, `request_purpose`, `status`, `source_url`, `permission_basis`, `permission_reference`, `attribution_text`, `model_training_allowed`, `operational_use_allowed`, `raw_manifest_path`, `raw_manifest_sha256`, `pipeline_version`, `started_at_utc`, `completed_at_utc`, `samples_seen`, `samples_accepted`, `samples_rejected`, `samples_quarantined`, `samples_deduplicated`, `error_summary`, `notes`) SELECT `id`, `run_key`, `product_run_id`, `target_local_date`, `ingestion_method`, `request_purpose`, `status`, `source_url`, `permission_basis`, `permission_reference`, `attribution_text`, `model_training_allowed`, `operational_use_allowed`, `raw_manifest_path`, `raw_manifest_sha256`, `pipeline_version`, `started_at_utc`, `completed_at_utc`, `samples_seen`, `samples_accepted`, `samples_rejected`, `samples_quarantined`, `samples_deduplicated`, `error_summary`, `notes` FROM `weather_ingestion_runs`;--> statement-breakpoint
DROP TABLE `weather_ingestion_runs`;--> statement-breakpoint
ALTER TABLE `__new_weather_ingestion_runs` RENAME TO `weather_ingestion_runs`;--> statement-breakpoint
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
	`specific_humidity_2m_kg_per_kg` real,
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
	`mixed_layer_lcl_agl_m` real,
	`pbl_minus_lcl_m` real,
	`surface_buoyancy_flux_kinematic_m2_s3` real,
	`convective_velocity_scale_m_s` real,
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
	CONSTRAINT "weather_samples_specific_humidity_2m_range_check" CHECK("specific_humidity_2m_kg_per_kg" IS NULL
        OR "specific_humidity_2m_kg_per_kg" BETWEEN 0 AND 1),
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
	CONSTRAINT "weather_samples_s08_derived_non_negative_check" CHECK(("mixed_layer_lcl_agl_m" IS NULL OR "mixed_layer_lcl_agl_m" >= 0)
        AND ("convective_velocity_scale_m_s" IS NULL OR "convective_velocity_scale_m_s" >= 0)),
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
INSERT INTO `__new_weather_point_samples`(`id`, `ingestion_run_id`, `product_valid_time_id`, `point_footprint_id`, `coverage_status`, `air_temperature_2m_k`, `dew_point_temperature_2m_k`, `relative_humidity_2m_percent`, `specific_humidity_2m_kg_per_kg`, `surface_pressure_pa`, `mean_sea_level_pressure_pa`, `wind_u_10m_m_s`, `wind_v_10m_m_s`, `wind_speed_10m_m_s`, `wind_direction_10m_degrees_from_north`, `provider_boundary_layer_height_agl_m`, `provider_boundary_layer_method`, `provider_cloud_base_agl_m`, `provider_cloud_base_method`, `total_column_water_vapour_kg_m2`, `total_cloud_cover_percent`, `low_cloud_cover_percent`, `mid_cloud_cover_percent`, `high_cloud_cover_percent`) SELECT `id`, `ingestion_run_id`, `product_valid_time_id`, `point_footprint_id`, `coverage_status`, `air_temperature_2m_k`, `dew_point_temperature_2m_k`, `relative_humidity_2m_percent`, `specific_humidity_2m_kg_per_kg`, `surface_pressure_pa`, `mean_sea_level_pressure_pa`, `wind_u_10m_m_s`, `wind_v_10m_m_s`, `wind_speed_10m_m_s`, `wind_direction_10m_degrees_from_north`, `provider_boundary_layer_height_agl_m`, `provider_boundary_layer_method`, `provider_cloud_base_agl_m`, `provider_cloud_base_method`, `total_column_water_vapour_kg_m2`, `total_cloud_cover_percent`, `low_cloud_cover_percent`, `mid_cloud_cover_percent`, `high_cloud_cover_percent` FROM `weather_point_samples`;--> statement-breakpoint
DROP TABLE `weather_point_samples`;--> statement-breakpoint
ALTER TABLE `__new_weather_point_samples` RENAME TO `weather_point_samples`;--> statement-breakpoint
PRAGMA foreign_keys=ON;--> statement-breakpoint
CREATE INDEX `weather_daily_feature_snapshots_contract_index` ON `weather_daily_feature_snapshots` (`feature_contract_version`);--> statement-breakpoint
CREATE INDEX `weather_daily_feature_snapshots_point_footprint_index` ON `weather_daily_feature_snapshots` (`point_footprint_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `weather_field_provenance_sample_field_unique` ON `weather_field_provenance` (`weather_point_sample_id`,`field_code`,`field_variant`) WHERE "weather_field_provenance"."weather_point_sample_id" IS NOT NULL;--> statement-breakpoint
CREATE UNIQUE INDEX `weather_field_provenance_convection_field_unique` ON `weather_field_provenance` (`point_convection_measurement_id`,`field_code`,`field_variant`) WHERE "weather_field_provenance"."point_convection_measurement_id" IS NOT NULL;--> statement-breakpoint
CREATE UNIQUE INDEX `weather_field_provenance_interval_field_unique` ON `weather_field_provenance` (`point_interval_measurement_id`,`field_code`,`field_variant`) WHERE "weather_field_provenance"."point_interval_measurement_id" IS NOT NULL;--> statement-breakpoint
CREATE UNIQUE INDEX `weather_field_provenance_profile_field_unique` ON `weather_field_provenance` (`point_profile_level_id`,`field_code`,`field_variant`) WHERE "weather_field_provenance"."point_profile_level_id" IS NOT NULL;--> statement-breakpoint
CREATE UNIQUE INDEX `weather_field_provenance_feature_field_unique` ON `weather_field_provenance` (`daily_feature_snapshot_id`,`field_code`,`field_variant`,`statistic_type`) WHERE "weather_field_provenance"."daily_feature_snapshot_id" IS NOT NULL;--> statement-breakpoint
CREATE UNIQUE INDEX `weather_field_provenance_feature_layer_field_unique` ON `weather_field_provenance` (`daily_feature_profile_layer_id`,`field_code`,`field_variant`,`statistic_type`) WHERE "weather_field_provenance"."daily_feature_profile_layer_id" IS NOT NULL;--> statement-breakpoint
CREATE INDEX `weather_field_provenance_field_quality_index` ON `weather_field_provenance` (`field_code`,`quality_state`);--> statement-breakpoint
CREATE INDEX `weather_field_provenance_source_reference_index` ON `weather_field_provenance` (`source_reference_at_utc`);--> statement-breakpoint
CREATE INDEX `weather_ingestion_runs_product_target_date_index` ON `weather_ingestion_runs` (`product_run_id`,`target_local_date`);--> statement-breakpoint
CREATE INDEX `weather_ingestion_runs_status_started_at_index` ON `weather_ingestion_runs` (`status`,"started_at_utc" desc);--> statement-breakpoint
CREATE INDEX `weather_ingestion_runs_purpose_status_index` ON `weather_ingestion_runs` (`request_purpose`,`status`);--> statement-breakpoint
CREATE INDEX `weather_point_samples_footprint_index` ON `weather_point_samples` (`point_footprint_id`);--> statement-breakpoint
CREATE INDEX `weather_point_samples_run_valid_time_index` ON `weather_point_samples` (`ingestion_run_id`,`product_valid_time_id`);--> statement-breakpoint
CREATE INDEX `weather_point_samples_coverage_status_index` ON `weather_point_samples` (`coverage_status`);