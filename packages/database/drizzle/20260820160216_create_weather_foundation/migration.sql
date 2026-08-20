CREATE TABLE `weather_convection_measurements` (
	`id` integer PRIMARY KEY,
	`weather_sample_id` integer NOT NULL,
	`parcel_method` text NOT NULL,
	`calculation_method` text NOT NULL,
	`calculation_method_version` text,
	`layer_bottom_pressure_from_ground_pa` real,
	`layer_top_pressure_from_ground_pa` real,
	`cape_j_per_kg` real,
	`cin_magnitude_j_per_kg` real,
	CONSTRAINT `fk_weather_convection_measurements_weather_sample_id_weather_samples_id_fk` FOREIGN KEY (`weather_sample_id`) REFERENCES `weather_samples`(`id`) ON DELETE RESTRICT,
	CONSTRAINT "weather_convection_measurements_parcel_method_check" CHECK("parcel_method" IN (
        'surface',
        'mixed_layer',
        'most_unstable',
        'provider_unspecified'
      )),
	CONSTRAINT "weather_convection_measurements_calculation_method_check" CHECK("calculation_method" IN ('provider', 'project_profile')),
	CONSTRAINT "weather_convection_measurements_method_version_check" CHECK(("calculation_method_version" IS NULL
          OR length(trim("calculation_method_version")) > 0)
        AND (
          "calculation_method" <> 'project_profile'
          OR "calculation_method_version" IS NOT NULL
        )),
	CONSTRAINT "weather_convection_measurements_layer_shape_check" CHECK((
          "layer_bottom_pressure_from_ground_pa" IS NULL
          AND "layer_top_pressure_from_ground_pa" IS NULL
        )
        OR (
          "layer_bottom_pressure_from_ground_pa" IS NOT NULL
          AND "layer_top_pressure_from_ground_pa" IS NOT NULL
          AND "layer_bottom_pressure_from_ground_pa" >= 0
          AND "layer_top_pressure_from_ground_pa" > "layer_bottom_pressure_from_ground_pa"
        )),
	CONSTRAINT "weather_convection_measurements_cape_non_negative_check" CHECK("cape_j_per_kg" IS NULL OR "cape_j_per_kg" >= 0),
	CONSTRAINT "weather_convection_measurements_cin_non_negative_check" CHECK("cin_magnitude_j_per_kg" IS NULL OR "cin_magnitude_j_per_kg" >= 0)
) STRICT;
--> statement-breakpoint
CREATE TABLE `weather_feature_snapshots` (
	`id` integer PRIMARY KEY,
	`weather_sample_id` integer NOT NULL,
	`neighbourhood_footprint_id` integer NOT NULL,
	`feature_contract_version` text NOT NULL,
	`input_fingerprint_sha256` text NOT NULL,
	`derived_boundary_layer_height_agl_m` real,
	`boundary_layer_method` text,
	`mixed_layer_lcl_agl_m` real,
	`mixed_layer_lcl_msl_m` real,
	`lcl_method` text,
	`surface_buoyancy_flux_kinematic_k_m_s` real,
	`buoyancy_flux_method` text,
	`convective_velocity_scale_m_s` real,
	`convective_velocity_method` text,
	`temperature_lapse_rate_k_per_km` real,
	`lapse_layer_base_agl_m` real,
	`lapse_layer_top_agl_m` real,
	`wind_shear_m_s_per_km` real,
	`shear_layer_base_agl_m` real,
	`shear_layer_top_agl_m` real,
	`neighbourhood_pressure_gradient_pa_per_km` real,
	`neighbourhood_low_level_divergence_s_inverse` real,
	`spatial_method_version` text,
	`created_by_ingestion_run_id` integer NOT NULL,
	CONSTRAINT `fk_weather_feature_snapshots_weather_sample_id_weather_samples_id_fk` FOREIGN KEY (`weather_sample_id`) REFERENCES `weather_samples`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_feature_snapshots_neighbourhood_footprint_id_weather_sampling_footprints_id_fk` FOREIGN KEY (`neighbourhood_footprint_id`) REFERENCES `weather_sampling_footprints`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_feature_snapshots_created_by_ingestion_run_id_weather_ingestion_runs_id_fk` FOREIGN KEY (`created_by_ingestion_run_id`) REFERENCES `weather_ingestion_runs`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `weather_feature_snapshots_identity_unique` UNIQUE(`weather_sample_id`,`neighbourhood_footprint_id`,`feature_contract_version`),
	CONSTRAINT "weather_feature_snapshots_contract_version_non_empty_check" CHECK(length(trim("feature_contract_version")) > 0),
	CONSTRAINT "weather_feature_snapshots_input_fingerprint_sha256_check" CHECK(length("input_fingerprint_sha256") = 64
        AND "input_fingerprint_sha256" NOT GLOB '*[^0-9a-f]*'),
	CONSTRAINT "weather_feature_snapshots_boundary_layer_shape_check" CHECK(("derived_boundary_layer_height_agl_m" IS NULL
          OR "derived_boundary_layer_height_agl_m" >= 0)
        AND ("boundary_layer_method" IS NULL
          OR length(trim("boundary_layer_method")) > 0)
        AND ("derived_boundary_layer_height_agl_m" IS NULL
          OR "boundary_layer_method" IS NOT NULL)),
	CONSTRAINT "weather_feature_snapshots_lcl_shape_check" CHECK(("mixed_layer_lcl_agl_m" IS NULL OR "mixed_layer_lcl_agl_m" >= 0)
        AND ("lcl_method" IS NULL OR length(trim("lcl_method")) > 0)
        AND (("mixed_layer_lcl_agl_m" IS NULL AND "mixed_layer_lcl_msl_m" IS NULL)
          OR "lcl_method" IS NOT NULL)),
	CONSTRAINT "weather_feature_snapshots_buoyancy_flux_method_check" CHECK(("buoyancy_flux_method" IS NULL
          OR length(trim("buoyancy_flux_method")) > 0)
        AND ("surface_buoyancy_flux_kinematic_k_m_s" IS NULL
          OR "buoyancy_flux_method" IS NOT NULL)),
	CONSTRAINT "weather_feature_snapshots_convective_velocity_shape_check" CHECK(("convective_velocity_scale_m_s" IS NULL
          OR "convective_velocity_scale_m_s" >= 0)
        AND ("convective_velocity_method" IS NULL
          OR length(trim("convective_velocity_method")) > 0)
        AND ("convective_velocity_scale_m_s" IS NULL
          OR "convective_velocity_method" IS NOT NULL)),
	CONSTRAINT "weather_feature_snapshots_lapse_layer_shape_check" CHECK((
          "temperature_lapse_rate_k_per_km" IS NULL
          AND "lapse_layer_base_agl_m" IS NULL
          AND "lapse_layer_top_agl_m" IS NULL
        )
        OR (
          "temperature_lapse_rate_k_per_km" IS NOT NULL
          AND "lapse_layer_base_agl_m" IS NOT NULL
          AND "lapse_layer_top_agl_m" IS NOT NULL
          AND "lapse_layer_base_agl_m" >= 0
          AND "lapse_layer_top_agl_m" > "lapse_layer_base_agl_m"
        )),
	CONSTRAINT "weather_feature_snapshots_shear_layer_shape_check" CHECK((
          "wind_shear_m_s_per_km" IS NULL
          AND "shear_layer_base_agl_m" IS NULL
          AND "shear_layer_top_agl_m" IS NULL
        )
        OR (
          "wind_shear_m_s_per_km" IS NOT NULL
          AND "shear_layer_base_agl_m" IS NOT NULL
          AND "shear_layer_top_agl_m" IS NOT NULL
          AND "wind_shear_m_s_per_km" >= 0
          AND "shear_layer_base_agl_m" >= 0
          AND "shear_layer_top_agl_m" > "shear_layer_base_agl_m"
        )),
	CONSTRAINT "weather_feature_snapshots_spatial_method_version_non_empty_check" CHECK("spatial_method_version" IS NULL
        OR length(trim("spatial_method_version")) > 0)
) STRICT;
--> statement-breakpoint
CREATE TABLE `weather_field_provenance` (
	`id` integer PRIMARY KEY,
	`weather_sample_id` integer,
	`convection_measurement_id` integer,
	`interval_measurement_id` integer,
	`profile_level_id` integer,
	`feature_snapshot_id` integer,
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
	CONSTRAINT `fk_weather_field_provenance_weather_sample_id_weather_samples_id_fk` FOREIGN KEY (`weather_sample_id`) REFERENCES `weather_samples`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_field_provenance_convection_measurement_id_weather_convection_measurements_id_fk` FOREIGN KEY (`convection_measurement_id`) REFERENCES `weather_convection_measurements`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_field_provenance_interval_measurement_id_weather_interval_measurements_id_fk` FOREIGN KEY (`interval_measurement_id`) REFERENCES `weather_interval_measurements`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_field_provenance_profile_level_id_weather_profile_levels_id_fk` FOREIGN KEY (`profile_level_id`) REFERENCES `weather_profile_levels`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_field_provenance_feature_snapshot_id_weather_feature_snapshots_id_fk` FOREIGN KEY (`feature_snapshot_id`) REFERENCES `weather_feature_snapshots`(`id`) ON DELETE RESTRICT,
	CONSTRAINT "weather_field_provenance_exactly_one_owner_check" CHECK((
          ("weather_sample_id" IS NOT NULL)
          + ("convection_measurement_id" IS NOT NULL)
          + ("interval_measurement_id" IS NOT NULL)
          + ("profile_level_id" IS NOT NULL)
          + ("feature_snapshot_id" IS NOT NULL)
        ) = 1),
	CONSTRAINT "weather_field_provenance_field_code_non_empty_check" CHECK(length(trim("field_code")) > 0),
	CONSTRAINT "weather_field_provenance_field_variant_non_empty_check" CHECK(length(trim("field_variant")) > 0),
	CONSTRAINT "weather_field_provenance_quality_state_check" CHECK("quality_state" IN (
        'real',
        'derived',
        'missing',
        'sentinel_missing',
        'invalid_payload'
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
	CONSTRAINT "weather_field_provenance_missing_native_value_check" CHECK("quality_state" NOT IN ('missing', 'sentinel_missing')
        OR "native_value" IS NULL)
) STRICT;
--> statement-breakpoint
CREATE TABLE `weather_grid_points` (
	`id` integer PRIMARY KEY,
	`grid_id` integer NOT NULL,
	`latitude_deg` real NOT NULL,
	`longitude_deg` real NOT NULL,
	`model_elevation_msl_m` real,
	`first_seen_ingestion_run_id` integer NOT NULL,
	CONSTRAINT `fk_weather_grid_points_grid_id_weather_grids_id_fk` FOREIGN KEY (`grid_id`) REFERENCES `weather_grids`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_grid_points_first_seen_ingestion_run_id_weather_ingestion_runs_id_fk` FOREIGN KEY (`first_seen_ingestion_run_id`) REFERENCES `weather_ingestion_runs`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `weather_grid_points_grid_coordinate_unique` UNIQUE(`grid_id`,`latitude_deg`,`longitude_deg`),
	CONSTRAINT "weather_grid_points_latitude_range_check" CHECK("latitude_deg" BETWEEN -90 AND 90),
	CONSTRAINT "weather_grid_points_longitude_range_check" CHECK("longitude_deg" BETWEEN -180 AND 180)
) STRICT;
--> statement-breakpoint
CREATE TABLE `weather_grids` (
	`id` integer PRIMARY KEY,
	`source_id` integer NOT NULL,
	`grid_key` text NOT NULL,
	`grid_type` text NOT NULL,
	`latitude_step_deg` real NOT NULL,
	`longitude_step_deg` real NOT NULL,
	`native_row_count` integer NOT NULL,
	`native_column_count` integer NOT NULL,
	`definition_sha256` text NOT NULL,
	`is_active` integer DEFAULT 1 NOT NULL,
	CONSTRAINT `fk_weather_grids_source_id_weather_sources_id_fk` FOREIGN KEY (`source_id`) REFERENCES `weather_sources`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `weather_grids_source_key_definition_unique` UNIQUE(`source_id`,`grid_key`,`definition_sha256`),
	CONSTRAINT "weather_grids_grid_key_non_empty_check" CHECK(length(trim("grid_key")) > 0),
	CONSTRAINT "weather_grids_grid_type_check" CHECK("grid_type" IN ('regular_latlon')),
	CONSTRAINT "weather_grids_latitude_step_positive_check" CHECK("latitude_step_deg" > 0),
	CONSTRAINT "weather_grids_longitude_step_positive_check" CHECK("longitude_step_deg" > 0),
	CONSTRAINT "weather_grids_native_row_count_positive_check" CHECK("native_row_count" > 0),
	CONSTRAINT "weather_grids_native_column_count_positive_check" CHECK("native_column_count" > 0),
	CONSTRAINT "weather_grids_definition_sha256_check" CHECK(length("definition_sha256") = 64
        AND "definition_sha256" NOT GLOB '*[^0-9a-f]*'),
	CONSTRAINT "weather_grids_is_active_boolean_check" CHECK("is_active" IN (0, 1))
) STRICT;
--> statement-breakpoint
CREATE TABLE `weather_ingestion_runs` (
	`id` integer PRIMARY KEY,
	`run_key` text NOT NULL CONSTRAINT `weather_ingestion_runs_run_key_unique` UNIQUE,
	`source_id` integer NOT NULL,
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
	CONSTRAINT `fk_weather_ingestion_runs_source_id_weather_sources_id_fk` FOREIGN KEY (`source_id`) REFERENCES `weather_sources`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `weather_ingestion_runs_id_source_id_parent_key_unique` UNIQUE(`id`,`source_id`),
	CONSTRAINT "weather_ingestion_runs_run_key_uuid_v4_check" CHECK("run_key" GLOB
        '[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]-[0-9a-f][0-9a-f][0-9a-f][0-9a-f]-4[0-9a-f][0-9a-f][0-9a-f]-[89ab][0-9a-f][0-9a-f][0-9a-f]-[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]'),
	CONSTRAINT "weather_ingestion_runs_ingestion_method_check" CHECK("ingestion_method" IN ('public_object_archive', 'official_api', 'offline_replay')),
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
CREATE TABLE `weather_interval_measurements` (
	`id` integer PRIMARY KEY,
	`weather_sample_id` integer NOT NULL,
	`field_code` text NOT NULL,
	`component` text NOT NULL,
	`interval_start_utc` text NOT NULL,
	`interval_end_utc` text NOT NULL,
	`statistic_type` text NOT NULL,
	`canonical_value` real,
	`source_step_start_hours` real,
	`source_step_end_hours` real,
	CONSTRAINT `fk_weather_interval_measurements_weather_sample_id_weather_samples_id_fk` FOREIGN KEY (`weather_sample_id`) REFERENCES `weather_samples`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `weather_interval_measurements_identity_unique` UNIQUE(`weather_sample_id`,`field_code`,`component`,`statistic_type`,`interval_start_utc`,`interval_end_utc`),
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
        OR "canonical_value" >= 0),
	CONSTRAINT "weather_interval_measurements_source_step_shape_check" CHECK((
          "source_step_start_hours" IS NULL
          AND "source_step_end_hours" IS NULL
        )
        OR (
          "source_step_start_hours" IS NOT NULL
          AND "source_step_end_hours" IS NOT NULL
          AND "source_step_start_hours" >= 0
          AND "source_step_end_hours" >= "source_step_start_hours"
        ))
) STRICT;
--> statement-breakpoint
CREATE TABLE `weather_product_runs` (
	`id` integer PRIMARY KEY,
	`source_id` integer NOT NULL,
	`source_product_key` text NOT NULL,
	`reference_at_utc` text,
	`available_at_utc` text,
	`valid_from_utc` text NOT NULL,
	`valid_to_utc` text NOT NULL,
	`created_by_ingestion_run_id` integer NOT NULL,
	`last_validated_by_ingestion_run_id` integer NOT NULL,
	CONSTRAINT `fk_weather_product_runs_source_id_weather_sources_id_fk` FOREIGN KEY (`source_id`) REFERENCES `weather_sources`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `weather_product_runs_created_run_source_fk` FOREIGN KEY (`created_by_ingestion_run_id`,`source_id`) REFERENCES `weather_ingestion_runs`(`id`,`source_id`) ON DELETE RESTRICT,
	CONSTRAINT `weather_product_runs_last_validated_run_source_fk` FOREIGN KEY (`last_validated_by_ingestion_run_id`,`source_id`) REFERENCES `weather_ingestion_runs`(`id`,`source_id`) ON DELETE RESTRICT,
	CONSTRAINT `weather_product_runs_source_product_unique` UNIQUE(`source_id`,`source_product_key`),
	CONSTRAINT "weather_product_runs_source_product_key_non_empty_check" CHECK(length(trim("source_product_key")) > 0),
	CONSTRAINT "weather_product_runs_reference_at_utc_shape_check" CHECK("reference_at_utc" IS NULL
        OR "reference_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "weather_product_runs_available_at_utc_shape_check" CHECK("available_at_utc" IS NULL
        OR "available_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "weather_product_runs_valid_from_utc_shape_check" CHECK("valid_from_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "weather_product_runs_valid_to_utc_shape_check" CHECK("valid_to_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "weather_product_runs_valid_range_check" CHECK("valid_to_utc" >= "valid_from_utc")
) STRICT;
--> statement-breakpoint
CREATE TABLE `weather_profile_levels` (
	`id` integer PRIMARY KEY,
	`weather_sample_id` integer NOT NULL,
	`pressure_pa` real NOT NULL,
	`geopotential_height_msl_m` real,
	`level_height_agl_m` real,
	`air_temperature_k` real,
	`dew_point_temperature_k` real,
	`relative_humidity_percent` real,
	`specific_humidity_kg_per_kg` real,
	`wind_u_m_s` real,
	`wind_v_m_s` real,
	`wind_speed_m_s` real,
	`wind_direction_degrees_from_north` real,
	CONSTRAINT `fk_weather_profile_levels_weather_sample_id_weather_samples_id_fk` FOREIGN KEY (`weather_sample_id`) REFERENCES `weather_samples`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `weather_profile_levels_sample_pressure_unique` UNIQUE(`weather_sample_id`,`pressure_pa`),
	CONSTRAINT "weather_profile_levels_pressure_positive_check" CHECK("pressure_pa" > 0),
	CONSTRAINT "weather_profile_levels_height_agl_non_negative_check" CHECK("level_height_agl_m" IS NULL OR "level_height_agl_m" >= 0),
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
CREATE TABLE `weather_samples` (
	`id` integer PRIMARY KEY,
	`product_run_id` integer NOT NULL,
	`point_footprint_id` integer NOT NULL,
	`valid_at_utc` text NOT NULL,
	`valid_local_date` text NOT NULL,
	`lead_hours` real,
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
	`provider_boundary_layer_height_msl_m` real,
	`provider_boundary_layer_method` text,
	`provider_cloud_base_agl_m` real,
	`provider_cloud_base_msl_m` real,
	`provider_cloud_base_method` text,
	`total_column_water_vapour_kg_m2` real,
	`total_cloud_cover_percent` real,
	`low_cloud_cover_percent` real,
	`mid_cloud_cover_percent` real,
	`high_cloud_cover_percent` real,
	`created_by_ingestion_run_id` integer NOT NULL,
	`last_validated_by_ingestion_run_id` integer NOT NULL,
	CONSTRAINT `fk_weather_samples_product_run_id_weather_product_runs_id_fk` FOREIGN KEY (`product_run_id`) REFERENCES `weather_product_runs`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_samples_point_footprint_id_weather_sampling_footprints_id_fk` FOREIGN KEY (`point_footprint_id`) REFERENCES `weather_sampling_footprints`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_samples_created_by_ingestion_run_id_weather_ingestion_runs_id_fk` FOREIGN KEY (`created_by_ingestion_run_id`) REFERENCES `weather_ingestion_runs`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_samples_last_validated_by_ingestion_run_id_weather_ingestion_runs_id_fk` FOREIGN KEY (`last_validated_by_ingestion_run_id`) REFERENCES `weather_ingestion_runs`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `weather_samples_product_footprint_valid_unique` UNIQUE(`product_run_id`,`point_footprint_id`,`valid_at_utc`),
	CONSTRAINT "weather_samples_valid_at_utc_shape_check" CHECK("valid_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "weather_samples_valid_local_date_shape_check" CHECK("valid_local_date" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
	CONSTRAINT "weather_samples_lead_hours_non_negative_check" CHECK("lead_hours" IS NULL OR "lead_hours" >= 0),
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
	CONSTRAINT "weather_samples_boundary_layer_method_shape_check" CHECK(("provider_boundary_layer_method" IS NULL
          OR length(trim("provider_boundary_layer_method")) > 0)
        AND ("provider_boundary_layer_height_msl_m" IS NULL
          OR "provider_boundary_layer_method" IS NOT NULL)),
	CONSTRAINT "weather_samples_cloud_base_agl_non_negative_check" CHECK("provider_cloud_base_agl_m" IS NULL OR "provider_cloud_base_agl_m" >= 0),
	CONSTRAINT "weather_samples_cloud_base_method_shape_check" CHECK(("provider_cloud_base_method" IS NULL
          OR length(trim("provider_cloud_base_method")) > 0)
        AND (("provider_cloud_base_agl_m" IS NULL
            AND "provider_cloud_base_msl_m" IS NULL)
          OR "provider_cloud_base_method" IS NOT NULL)),
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
CREATE TABLE `weather_sampling_footprint_nodes` (
	`footprint_id` integer NOT NULL,
	`grid_point_id` integer NOT NULL,
	`distance_km` real NOT NULL,
	`interpolation_weight` real,
	CONSTRAINT `weather_sampling_footprint_nodes_pk` PRIMARY KEY(`footprint_id`, `grid_point_id`),
	CONSTRAINT `fk_weather_sampling_footprint_nodes_footprint_id_weather_sampling_footprints_id_fk` FOREIGN KEY (`footprint_id`) REFERENCES `weather_sampling_footprints`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_sampling_footprint_nodes_grid_point_id_weather_grid_points_id_fk` FOREIGN KEY (`grid_point_id`) REFERENCES `weather_grid_points`(`id`) ON DELETE RESTRICT,
	CONSTRAINT "weather_sampling_footprint_nodes_distance_non_negative_check" CHECK("distance_km" >= 0),
	CONSTRAINT "weather_sampling_footprint_nodes_weight_range_check" CHECK("interpolation_weight" IS NULL
        OR "interpolation_weight" BETWEEN 0 AND 1)
) STRICT;
--> statement-breakpoint
CREATE TABLE `weather_sampling_footprints` (
	`id` integer PRIMARY KEY,
	`site_id` integer NOT NULL,
	`grid_id` integer NOT NULL,
	`purpose` text NOT NULL,
	`sampling_method` text NOT NULL,
	`sampling_method_version` text NOT NULL,
	`radius_km` real,
	`footprint_version` integer NOT NULL,
	`definition_sha256` text NOT NULL,
	CONSTRAINT `fk_weather_sampling_footprints_site_id_weather_site_sampling_configs_site_id_fk` FOREIGN KEY (`site_id`) REFERENCES `weather_site_sampling_configs`(`site_id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_weather_sampling_footprints_grid_id_weather_grids_id_fk` FOREIGN KEY (`grid_id`) REFERENCES `weather_grids`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `weather_sampling_footprints_identity_unique` UNIQUE(`site_id`,`grid_id`,`purpose`,`footprint_version`),
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
	CONSTRAINT "weather_sampling_footprints_method_version_non_empty_check" CHECK(length(trim("sampling_method_version")) > 0),
	CONSTRAINT "weather_sampling_footprints_footprint_version_positive_check" CHECK("footprint_version" > 0),
	CONSTRAINT "weather_sampling_footprints_definition_sha256_check" CHECK(length("definition_sha256") = 64
        AND "definition_sha256" NOT GLOB '*[^0-9a-f]*')
) STRICT;
--> statement-breakpoint
CREATE TABLE `weather_site_sampling_configs` (
	`site_id` integer PRIMARY KEY,
	`latitude_deg` real NOT NULL,
	`longitude_deg` real NOT NULL,
	`coordinate_reference` text NOT NULL,
	`reference_elevation_msl_m` real,
	`elevation_reference` text,
	CONSTRAINT `fk_weather_site_sampling_configs_site_id_sites_id_fk` FOREIGN KEY (`site_id`) REFERENCES `sites`(`id`) ON DELETE RESTRICT,
	CONSTRAINT "weather_site_sampling_configs_latitude_range_check" CHECK("latitude_deg" BETWEEN -90 AND 90),
	CONSTRAINT "weather_site_sampling_configs_longitude_range_check" CHECK("longitude_deg" BETWEEN -180 AND 180),
	CONSTRAINT "weather_site_sampling_configs_coordinate_reference_non_empty_check" CHECK(length(trim("coordinate_reference")) > 0),
	CONSTRAINT "weather_site_sampling_configs_elevation_reference_pair_check" CHECK((
          "reference_elevation_msl_m" IS NULL
          AND "elevation_reference" IS NULL
        )
        OR (
          "reference_elevation_msl_m" IS NOT NULL
          AND "elevation_reference" IS NOT NULL
          AND length(trim("elevation_reference")) > 0
        ))
) STRICT;
--> statement-breakpoint
CREATE TABLE `weather_sources` (
	`id` integer PRIMARY KEY,
	`code` text NOT NULL CONSTRAINT `weather_sources_code_unique` UNIQUE,
	`provider_name` text NOT NULL,
	`dataset_name` text NOT NULL,
	`source_kind` text NOT NULL,
	`base_url` text NOT NULL,
	`is_active` integer DEFAULT 1 NOT NULL,
	CONSTRAINT "weather_sources_code_lower_snake_case_check" CHECK(length("code") BETWEEN 1 AND 80
        AND substr("code", 1, 1) GLOB '[a-z]'
        AND "code" NOT GLOB '*[^a-z0-9_]*'
        AND "code" NOT GLOB '*__*'
        AND substr("code", -1) <> '_'),
	CONSTRAINT "weather_sources_provider_name_non_empty_check" CHECK(length(trim("provider_name")) > 0),
	CONSTRAINT "weather_sources_dataset_name_non_empty_check" CHECK(length(trim("dataset_name")) > 0),
	CONSTRAINT "weather_sources_source_kind_check" CHECK("source_kind" IN ('forecast', 'reanalysis')),
	CONSTRAINT "weather_sources_base_url_non_empty_check" CHECK(length(trim("base_url")) > 0),
	CONSTRAINT "weather_sources_is_active_boolean_check" CHECK("is_active" IN (0, 1))
) STRICT;
--> statement-breakpoint
ALTER TABLE `ingestion_runs` RENAME TO `flight_ingestion_runs`;--> statement-breakpoint
CREATE UNIQUE INDEX `weather_convection_no_layer_no_version_unique` ON `weather_convection_measurements` (`weather_sample_id`,`parcel_method`,`calculation_method`) WHERE "weather_convection_measurements"."layer_bottom_pressure_from_ground_pa" IS NULL
          AND "weather_convection_measurements"."layer_top_pressure_from_ground_pa" IS NULL
          AND "weather_convection_measurements"."calculation_method_version" IS NULL;--> statement-breakpoint
CREATE UNIQUE INDEX `weather_convection_no_layer_version_unique` ON `weather_convection_measurements` (`weather_sample_id`,`parcel_method`,`calculation_method`,`calculation_method_version`) WHERE "weather_convection_measurements"."layer_bottom_pressure_from_ground_pa" IS NULL
          AND "weather_convection_measurements"."layer_top_pressure_from_ground_pa" IS NULL
          AND "weather_convection_measurements"."calculation_method_version" IS NOT NULL;--> statement-breakpoint
CREATE UNIQUE INDEX `weather_convection_layer_no_version_unique` ON `weather_convection_measurements` (`weather_sample_id`,`parcel_method`,`calculation_method`,`layer_bottom_pressure_from_ground_pa`,`layer_top_pressure_from_ground_pa`) WHERE "weather_convection_measurements"."layer_bottom_pressure_from_ground_pa" IS NOT NULL
          AND "weather_convection_measurements"."layer_top_pressure_from_ground_pa" IS NOT NULL
          AND "weather_convection_measurements"."calculation_method_version" IS NULL;--> statement-breakpoint
CREATE UNIQUE INDEX `weather_convection_layer_version_unique` ON `weather_convection_measurements` (`weather_sample_id`,`parcel_method`,`calculation_method`,`layer_bottom_pressure_from_ground_pa`,`layer_top_pressure_from_ground_pa`,`calculation_method_version`) WHERE "weather_convection_measurements"."layer_bottom_pressure_from_ground_pa" IS NOT NULL
          AND "weather_convection_measurements"."layer_top_pressure_from_ground_pa" IS NOT NULL
          AND "weather_convection_measurements"."calculation_method_version" IS NOT NULL;--> statement-breakpoint
CREATE INDEX `weather_convection_measurements_sample_index` ON `weather_convection_measurements` (`weather_sample_id`);--> statement-breakpoint
CREATE INDEX `weather_feature_snapshots_sample_index` ON `weather_feature_snapshots` (`weather_sample_id`);--> statement-breakpoint
CREATE INDEX `weather_feature_snapshots_contract_index` ON `weather_feature_snapshots` (`feature_contract_version`);--> statement-breakpoint
CREATE INDEX `weather_feature_snapshots_created_by_run_index` ON `weather_feature_snapshots` (`created_by_ingestion_run_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `weather_field_provenance_sample_field_unique` ON `weather_field_provenance` (`weather_sample_id`,`field_code`,`field_variant`) WHERE "weather_field_provenance"."weather_sample_id" IS NOT NULL;--> statement-breakpoint
CREATE UNIQUE INDEX `weather_field_provenance_convection_field_unique` ON `weather_field_provenance` (`convection_measurement_id`,`field_code`,`field_variant`) WHERE "weather_field_provenance"."convection_measurement_id" IS NOT NULL;--> statement-breakpoint
CREATE UNIQUE INDEX `weather_field_provenance_interval_field_unique` ON `weather_field_provenance` (`interval_measurement_id`,`field_code`,`field_variant`) WHERE "weather_field_provenance"."interval_measurement_id" IS NOT NULL;--> statement-breakpoint
CREATE UNIQUE INDEX `weather_field_provenance_profile_field_unique` ON `weather_field_provenance` (`profile_level_id`,`field_code`,`field_variant`) WHERE "weather_field_provenance"."profile_level_id" IS NOT NULL;--> statement-breakpoint
CREATE UNIQUE INDEX `weather_field_provenance_feature_field_unique` ON `weather_field_provenance` (`feature_snapshot_id`,`field_code`,`field_variant`) WHERE "weather_field_provenance"."feature_snapshot_id" IS NOT NULL;--> statement-breakpoint
CREATE INDEX `weather_field_provenance_field_quality_index` ON `weather_field_provenance` (`field_code`,`quality_state`);--> statement-breakpoint
CREATE INDEX `weather_field_provenance_source_reference_index` ON `weather_field_provenance` (`source_reference_at_utc`);--> statement-breakpoint
CREATE INDEX `weather_grid_points_first_seen_run_index` ON `weather_grid_points` (`first_seen_ingestion_run_id`);--> statement-breakpoint
CREATE UNIQUE INDEX `weather_grids_active_key_unique` ON `weather_grids` (`source_id`,`grid_key`) WHERE "weather_grids"."is_active" = 1;--> statement-breakpoint
CREATE INDEX `weather_grids_source_active_index` ON `weather_grids` (`source_id`,`is_active`);--> statement-breakpoint
CREATE INDEX `weather_ingestion_runs_source_started_at_index` ON `weather_ingestion_runs` (`source_id`,"started_at_utc" desc);--> statement-breakpoint
CREATE INDEX `weather_ingestion_runs_status_started_at_index` ON `weather_ingestion_runs` (`status`,"started_at_utc" desc);--> statement-breakpoint
CREATE INDEX `weather_ingestion_runs_purpose_status_index` ON `weather_ingestion_runs` (`request_purpose`,`status`);--> statement-breakpoint
CREATE INDEX `weather_interval_measurements_sample_interval_index` ON `weather_interval_measurements` (`weather_sample_id`,`interval_start_utc`,`interval_end_utc`);--> statement-breakpoint
CREATE INDEX `weather_interval_measurements_field_interval_index` ON `weather_interval_measurements` (`field_code`,`interval_start_utc`,`interval_end_utc`);--> statement-breakpoint
CREATE INDEX `weather_product_runs_source_reference_at_index` ON `weather_product_runs` (`source_id`,"reference_at_utc" desc);--> statement-breakpoint
CREATE INDEX `weather_product_runs_valid_range_index` ON `weather_product_runs` (`valid_from_utc`,`valid_to_utc`);--> statement-breakpoint
CREATE INDEX `weather_product_runs_created_by_ingestion_run_index` ON `weather_product_runs` (`created_by_ingestion_run_id`);--> statement-breakpoint
CREATE INDEX `weather_profile_levels_pressure_sample_index` ON `weather_profile_levels` (`pressure_pa`,`weather_sample_id`);--> statement-breakpoint
CREATE INDEX `weather_samples_footprint_valid_at_index` ON `weather_samples` (`point_footprint_id`,`valid_at_utc`);--> statement-breakpoint
CREATE INDEX `weather_samples_product_valid_at_index` ON `weather_samples` (`product_run_id`,`valid_at_utc`);--> statement-breakpoint
CREATE INDEX `weather_samples_valid_local_date_index` ON `weather_samples` (`valid_local_date`);--> statement-breakpoint
CREATE INDEX `weather_samples_created_by_ingestion_run_index` ON `weather_samples` (`created_by_ingestion_run_id`);--> statement-breakpoint
CREATE INDEX `weather_samples_coverage_status_index` ON `weather_samples` (`coverage_status`);--> statement-breakpoint
CREATE INDEX `weather_sampling_footprint_nodes_grid_point_index` ON `weather_sampling_footprint_nodes` (`grid_point_id`);--> statement-breakpoint
CREATE INDEX `weather_sampling_footprints_site_purpose_version_index` ON `weather_sampling_footprints` (`site_id`,`purpose`,"footprint_version" desc);--> statement-breakpoint
CREATE INDEX `weather_sampling_footprints_grid_index` ON `weather_sampling_footprints` (`grid_id`);--> statement-breakpoint
CREATE INDEX `weather_site_sampling_configs_coordinate_index` ON `weather_site_sampling_configs` (`latitude_deg`,`longitude_deg`);
