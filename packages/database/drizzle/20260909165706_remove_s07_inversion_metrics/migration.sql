PRAGMA foreign_keys=OFF;--> statement-breakpoint
CREATE TABLE `__new_weather_daily_feature_profile_layers` (
	`id` integer PRIMARY KEY,
	`daily_feature_snapshot_id` integer NOT NULL,
	`layer_base_agl_m` real NOT NULL,
	`layer_top_agl_m` real NOT NULL,
	`temperature_lapse_rate_mean_k_per_km` real,
	`temperature_lapse_rate_max_k_per_km` real,
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
	CONSTRAINT "weather_daily_feature_profile_layers_humidity_range_check" CHECK(("relative_humidity_mean_percent" IS NULL OR "relative_humidity_mean_percent" BETWEEN 0 AND 100)
        AND ("specific_humidity_mean_kg_per_kg" IS NULL OR "specific_humidity_mean_kg_per_kg" >= 0)),
	CONSTRAINT "weather_daily_feature_profile_layers_wind_shape_check" CHECK(("wind_speed_mean_m_s" IS NULL OR "wind_speed_mean_m_s" >= 0)
        AND ("wind_speed_max_m_s" IS NULL OR "wind_speed_max_m_s" >= 0)
        AND ("wind_direction_mean_degrees_from_north" IS NULL OR ("wind_direction_mean_degrees_from_north" >= 0 AND "wind_direction_mean_degrees_from_north" < 360))
        AND ("wind_shear_mean_m_s_per_km" IS NULL OR "wind_shear_mean_m_s_per_km" >= 0)
        AND ("wind_shear_max_m_s_per_km" IS NULL OR "wind_shear_max_m_s_per_km" >= 0))
) STRICT;
--> statement-breakpoint
INSERT INTO `__new_weather_daily_feature_profile_layers`(`id`, `daily_feature_snapshot_id`, `layer_base_agl_m`, `layer_top_agl_m`, `temperature_lapse_rate_mean_k_per_km`, `temperature_lapse_rate_max_k_per_km`, `relative_humidity_mean_percent`, `specific_humidity_mean_kg_per_kg`, `wind_u_mean_m_s`, `wind_v_mean_m_s`, `wind_speed_mean_m_s`, `wind_speed_max_m_s`, `wind_direction_mean_degrees_from_north`, `wind_shear_mean_m_s_per_km`, `wind_shear_max_m_s_per_km`, `vertical_velocity_mean_pa_s`, `vertical_velocity_min_pa_s`) SELECT `id`, `daily_feature_snapshot_id`, `layer_base_agl_m`, `layer_top_agl_m`, `temperature_lapse_rate_mean_k_per_km`, `temperature_lapse_rate_max_k_per_km`, `relative_humidity_mean_percent`, `specific_humidity_mean_kg_per_kg`, `wind_u_mean_m_s`, `wind_v_mean_m_s`, `wind_speed_mean_m_s`, `wind_speed_max_m_s`, `wind_direction_mean_degrees_from_north`, `wind_shear_mean_m_s_per_km`, `wind_shear_max_m_s_per_km`, `vertical_velocity_mean_pa_s`, `vertical_velocity_min_pa_s` FROM `weather_daily_feature_profile_layers`;--> statement-breakpoint
DROP TABLE `weather_daily_feature_profile_layers`;--> statement-breakpoint
ALTER TABLE `__new_weather_daily_feature_profile_layers` RENAME TO `weather_daily_feature_profile_layers`;--> statement-breakpoint
PRAGMA foreign_keys=ON;