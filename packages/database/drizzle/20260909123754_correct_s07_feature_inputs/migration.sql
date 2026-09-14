ALTER TABLE `weather_point_samples` ADD `specific_humidity_2m_kg_per_kg` real;--> statement-breakpoint
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
INSERT INTO `__new_weather_point_samples`(`id`, `ingestion_run_id`, `product_valid_time_id`, `point_footprint_id`, `coverage_status`, `air_temperature_2m_k`, `dew_point_temperature_2m_k`, `relative_humidity_2m_percent`, `surface_pressure_pa`, `mean_sea_level_pressure_pa`, `wind_u_10m_m_s`, `wind_v_10m_m_s`, `wind_speed_10m_m_s`, `wind_direction_10m_degrees_from_north`, `provider_boundary_layer_height_agl_m`, `provider_boundary_layer_method`, `provider_cloud_base_agl_m`, `provider_cloud_base_method`, `total_column_water_vapour_kg_m2`, `total_cloud_cover_percent`, `low_cloud_cover_percent`, `mid_cloud_cover_percent`, `high_cloud_cover_percent`) SELECT `id`, `ingestion_run_id`, `product_valid_time_id`, `point_footprint_id`, `coverage_status`, `air_temperature_2m_k`, `dew_point_temperature_2m_k`, `relative_humidity_2m_percent`, `surface_pressure_pa`, `mean_sea_level_pressure_pa`, `wind_u_10m_m_s`, `wind_v_10m_m_s`, `wind_speed_10m_m_s`, `wind_direction_10m_degrees_from_north`, `provider_boundary_layer_height_agl_m`, `provider_boundary_layer_method`, `provider_cloud_base_agl_m`, `provider_cloud_base_method`, `total_column_water_vapour_kg_m2`, `total_cloud_cover_percent`, `low_cloud_cover_percent`, `mid_cloud_cover_percent`, `high_cloud_cover_percent` FROM `weather_point_samples`;--> statement-breakpoint
DROP TABLE `weather_point_samples`;--> statement-breakpoint
ALTER TABLE `__new_weather_point_samples` RENAME TO `weather_point_samples`;--> statement-breakpoint
PRAGMA foreign_keys=ON;--> statement-breakpoint
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
CREATE INDEX `weather_point_samples_footprint_index` ON `weather_point_samples` (`point_footprint_id`);--> statement-breakpoint
CREATE INDEX `weather_point_samples_run_valid_time_index` ON `weather_point_samples` (`ingestion_run_id`,`product_valid_time_id`);--> statement-breakpoint
CREATE INDEX `weather_point_samples_coverage_status_index` ON `weather_point_samples` (`coverage_status`);--> statement-breakpoint
CREATE INDEX `weather_daily_feature_snapshots_contract_index` ON `weather_daily_feature_snapshots` (`feature_contract_version`);--> statement-breakpoint
CREATE INDEX `weather_daily_feature_snapshots_point_footprint_index` ON `weather_daily_feature_snapshots` (`point_footprint_id`);