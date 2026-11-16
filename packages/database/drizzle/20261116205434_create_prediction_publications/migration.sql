CREATE TABLE `prediction_cloudbase_hours` (
	`prediction_id` integer NOT NULL,
	`valid_at_utc` text NOT NULL,
	`regime` text NOT NULL,
	`estimated_cloudbase_msl_m` real,
	`estimated_cloudbase_model_agl_m` real,
	`estimated_cloudbase_site_agl_m` real,
	`confidence_level` text,
	`reason_code` text NOT NULL,
	`note` text,
	CONSTRAINT `prediction_cloudbase_hours_pk` PRIMARY KEY(`prediction_id`, `valid_at_utc`),
	CONSTRAINT `fk_prediction_cloudbase_hours_prediction_id_predictions_id_fk` FOREIGN KEY (`prediction_id`) REFERENCES `predictions`(`id`) ON DELETE RESTRICT,
	CONSTRAINT "prediction_cloudbase_hours_valid_at_utc_check" CHECK("valid_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "prediction_cloudbase_hours_regime_check" CHECK("regime" IN ('cumulus', 'blue', 'other_cloud', 'indeterminate', 'missing')),
	CONSTRAINT "prediction_cloudbase_hours_heights_check" CHECK((
          "regime" <> 'cumulus'
          AND "estimated_cloudbase_msl_m" IS NULL
          AND "estimated_cloudbase_model_agl_m" IS NULL
          AND "estimated_cloudbase_site_agl_m" IS NULL
        ) OR (
          "regime" IN ('cumulus', 'indeterminate')
          AND "estimated_cloudbase_msl_m" IS NOT NULL
          AND "estimated_cloudbase_model_agl_m" IS NOT NULL
          AND "estimated_cloudbase_model_agl_m" >= 0
          AND "estimated_cloudbase_site_agl_m" IS NOT NULL
        )),
	CONSTRAINT "prediction_cloudbase_hours_confidence_check" CHECK(("confidence_level" IS NULL
          OR "confidence_level" IN ('low', 'medium', 'high'))
        AND ("regime" <> 'missing' OR "confidence_level" IS NULL)),
	CONSTRAINT "prediction_cloudbase_hours_reason_check" CHECK(length(trim("reason_code")) > 0)
) STRICT;
--> statement-breakpoint
CREATE TABLE `prediction_driver_inputs` (
	`prediction_driver_id` integer NOT NULL,
	`input_ordinal` integer NOT NULL,
	`input_key` text NOT NULL,
	`valid_at_utc` text,
	`interval_end_utc` text,
	`weather_field_provenance_id` integer,
	CONSTRAINT `prediction_driver_inputs_pk` PRIMARY KEY(`prediction_driver_id`, `input_ordinal`),
	CONSTRAINT `fk_prediction_driver_inputs_prediction_driver_id_prediction_drivers_id_fk` FOREIGN KEY (`prediction_driver_id`) REFERENCES `prediction_drivers`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_prediction_driver_inputs_weather_field_provenance_id_weather_field_provenance_id_fk` FOREIGN KEY (`weather_field_provenance_id`) REFERENCES `weather_field_provenance`(`id`) ON DELETE RESTRICT,
	CONSTRAINT "prediction_driver_inputs_input_check" CHECK("input_ordinal" >= 1 AND length(trim("input_key")) > 0),
	CONSTRAINT "prediction_driver_inputs_window_check" CHECK(("valid_at_utc" IS NULL OR "valid_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z')
        AND ("interval_end_utc" IS NULL OR (
          "interval_end_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'
          AND "valid_at_utc" IS NOT NULL
          AND "interval_end_utc" > "valid_at_utc"
        )))
) STRICT;
--> statement-breakpoint
CREATE TABLE `prediction_drivers` (
	`id` integer PRIMARY KEY,
	`prediction_id` integer NOT NULL,
	`metric_code` text NOT NULL,
	`rank` integer NOT NULL,
	`kind` text NOT NULL,
	`code` text NOT NULL,
	`message` text NOT NULL,
	`xc_stage` text,
	`direction` text,
	`contribution_logit` real,
	`score_points` real,
	`support_successes` integer,
	`support_total` integer,
	CONSTRAINT `prediction_drivers_metric_fk` FOREIGN KEY (`prediction_id`,`metric_code`) REFERENCES `prediction_metric_details`(`prediction_id`,`metric_code`) ON DELETE RESTRICT,
	CONSTRAINT `prediction_drivers_metric_rank_unique` UNIQUE(`prediction_id`,`metric_code`,`rank`),
	CONSTRAINT "prediction_drivers_rank_check" CHECK("rank" BETWEEN 1 AND 3),
	CONSTRAINT "prediction_drivers_message_check" CHECK(length(trim("code")) > 0 AND length(trim("message")) > 0),
	CONSTRAINT "prediction_drivers_kind_check" CHECK((
          "kind" = 'xc_contribution'
          AND "xc_stage" IS NOT NULL
          AND (("metric_code" = 'p100' AND "xc_stage" = 'p100')
            OR ("metric_code" = 'p200' AND "xc_stage" = 'q200'))
          AND "direction" IS NOT NULL
          AND "direction" IN ('raises', 'lowers', 'zero')
          AND "contribution_logit" IS NOT NULL
        ) OR (
          (("metric_code" = 'p300' AND "kind" = 'pooled_conversion')
            OR ("metric_code" = 'overdevelopment'
              AND "kind" IN ('od_override', 'od_score_component'))
            OR ("metric_code" = 'cloudbase' AND "kind" = 'cloudbase_reason'))
          AND "xc_stage" IS NULL
          AND "direction" IS NULL
          AND "contribution_logit" IS NULL
        )),
	CONSTRAINT "prediction_drivers_score_points_check" CHECK("score_points" IS NULL
        OR ("kind" = 'od_score_component' AND "score_points" BETWEEN 0 AND 100)),
	CONSTRAINT "prediction_drivers_support_check" CHECK((
          "kind" <> 'pooled_conversion'
          AND "support_successes" IS NULL
          AND "support_total" IS NULL
        ) OR (
          "kind" = 'pooled_conversion'
          AND "support_successes" IS NOT NULL
          AND "support_total" IS NOT NULL
          AND "support_total" > 0
          AND "support_successes" BETWEEN 0 AND "support_total"
        ))
) STRICT;
--> statement-breakpoint
CREATE TABLE `prediction_metric_details` (
	`prediction_id` integer NOT NULL,
	`metric_code` text NOT NULL,
	`data_status` text NOT NULL,
	`confidence_level` text,
	`confidence_note` text,
	`missing_reason_code` text,
	`limitations_note` text,
	CONSTRAINT `prediction_metric_details_pk` PRIMARY KEY(`prediction_id`, `metric_code`),
	CONSTRAINT `fk_prediction_metric_details_prediction_id_predictions_id_fk` FOREIGN KEY (`prediction_id`) REFERENCES `predictions`(`id`) ON DELETE RESTRICT,
	CONSTRAINT "prediction_metric_details_metric_check" CHECK("metric_code" IN ('p100', 'p200', 'p300', 'overdevelopment', 'cloudbase')),
	CONSTRAINT "prediction_metric_details_status_check" CHECK((
          "data_status" = 'missing'
          AND "confidence_level" IS NULL
          AND "missing_reason_code" IS NOT NULL
          AND length(trim("missing_reason_code")) > 0
        ) OR (
          "data_status" = 'baseline'
          AND "confidence_level" IS NOT NULL
          AND "confidence_level" IN ('low', 'medium', 'high')
          AND "missing_reason_code" IS NULL
        ))
) STRICT;
--> statement-breakpoint
CREATE TABLE `prediction_runs` (
	`id` integer PRIMARY KEY,
	`weather_ingestion_run_id` integer NOT NULL,
	`created_at_utc` text NOT NULL,
	`xc_model_id` text NOT NULL,
	`cloudbase_method_version` text NOT NULL,
	`overdevelopment_policy_version` text NOT NULL,
	CONSTRAINT `fk_prediction_runs_weather_ingestion_run_id_weather_ingestion_runs_id_fk` FOREIGN KEY (`weather_ingestion_run_id`) REFERENCES `weather_ingestion_runs`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `prediction_runs_weather_model_unique` UNIQUE(`weather_ingestion_run_id`,`xc_model_id`),
	CONSTRAINT "prediction_runs_created_at_utc_check" CHECK("created_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'),
	CONSTRAINT "prediction_runs_model_versions_check" CHECK(length(trim("xc_model_id")) > 0
        AND length(trim("cloudbase_method_version")) > 0
        AND length(trim("overdevelopment_policy_version")) > 0)
) STRICT;
--> statement-breakpoint
CREATE TABLE `predictions` (
	`id` integer PRIMARY KEY,
	`prediction_run_id` integer NOT NULL,
	`daily_feature_snapshot_id` integer NOT NULL,
	`p_100km` real,
	`p_200km` real,
	`p_300km` real,
	`overdevelopment_risk` text,
	`overdevelopment_score` real,
	`cloudbase_summary_state` text NOT NULL,
	`cloudbase_max_at_utc` text,
	`conditional_lcl_max_at_utc` text,
	CONSTRAINT `fk_predictions_prediction_run_id_prediction_runs_id_fk` FOREIGN KEY (`prediction_run_id`) REFERENCES `prediction_runs`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `fk_predictions_daily_feature_snapshot_id_weather_daily_feature_snapshots_id_fk` FOREIGN KEY (`daily_feature_snapshot_id`) REFERENCES `weather_daily_feature_snapshots`(`id`) ON DELETE RESTRICT,
	CONSTRAINT `predictions_run_snapshot_unique` UNIQUE(`prediction_run_id`,`daily_feature_snapshot_id`),
	CONSTRAINT "predictions_probability_check" CHECK(("p_100km" IS NULL OR "p_100km" BETWEEN 0 AND 1)
        AND ("p_200km" IS NULL OR
          ("p_100km" IS NOT NULL AND "p_200km" BETWEEN 0 AND "p_100km"))
        AND ("p_300km" IS NULL OR
          ("p_200km" IS NOT NULL AND "p_300km" BETWEEN 0 AND "p_200km"))),
	CONSTRAINT "predictions_overdevelopment_check" CHECK(("overdevelopment_risk" IS NULL AND "overdevelopment_score" IS NULL)
        OR ("overdevelopment_risk" IS NOT NULL
          AND "overdevelopment_risk" IN ('low', 'medium', 'high')
          AND (("overdevelopment_score" IS NOT NULL
            AND "overdevelopment_score" BETWEEN 0 AND 100)
          OR ("overdevelopment_risk" = 'high' AND "overdevelopment_score" IS NULL)))),
	CONSTRAINT "predictions_cloudbase_summary_check" CHECK("cloudbase_summary_state" IN (
          'cloudbase_available', 'potential_base_available', 'blue', 'other_cloud',
          'indeterminate', 'missing'
        )
        AND ("cloudbase_summary_state" = 'cloudbase_available') =
          ("cloudbase_max_at_utc" IS NOT NULL)
        AND ("cloudbase_summary_state" <> 'potential_base_available'
          OR "conditional_lcl_max_at_utc" IS NOT NULL)
        AND ("conditional_lcl_max_at_utc" IS NULL
          OR "cloudbase_summary_state" IN ('cloudbase_available', 'potential_base_available'))),
	CONSTRAINT "predictions_cloudbase_max_times_check" CHECK(("cloudbase_max_at_utc" IS NULL
          OR "cloudbase_max_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z')
        AND ("conditional_lcl_max_at_utc" IS NULL
          OR "conditional_lcl_max_at_utc" GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'))
) STRICT;
--> statement-breakpoint
CREATE INDEX `prediction_driver_inputs_provenance_index` ON `prediction_driver_inputs` (`weather_field_provenance_id`);--> statement-breakpoint
CREATE INDEX `predictions_snapshot_index` ON `predictions` (`daily_feature_snapshot_id`);
--> statement-breakpoint
CREATE TRIGGER `predictions_snapshot_run_insert_guard` BEFORE INSERT ON `predictions` BEGIN
  SELECT RAISE(ABORT, 'Prediction snapshot differs from publication weather run')
  WHERE (SELECT ingestion_run_id FROM weather_daily_feature_snapshots WHERE id = NEW.daily_feature_snapshot_id)
     <> (SELECT weather_ingestion_run_id FROM prediction_runs WHERE id = NEW.prediction_run_id);
END;
--> statement-breakpoint
CREATE TRIGGER `predictions_snapshot_run_update_guard` BEFORE UPDATE OF prediction_run_id, daily_feature_snapshot_id ON `predictions` BEGIN
  SELECT RAISE(ABORT, 'Prediction snapshot differs from publication weather run')
  WHERE (SELECT ingestion_run_id FROM weather_daily_feature_snapshots WHERE id = NEW.daily_feature_snapshot_id)
     <> (SELECT weather_ingestion_run_id FROM prediction_runs WHERE id = NEW.prediction_run_id);
END;
--> statement-breakpoint
CREATE TRIGGER `prediction_runs_weather_update_guard` BEFORE UPDATE OF weather_ingestion_run_id ON `prediction_runs` BEGIN
  SELECT RAISE(ABORT, 'Prediction publication update breaks snapshot weather run identity')
  WHERE EXISTS (SELECT 1 FROM predictions AS prediction
    JOIN weather_daily_feature_snapshots AS snapshot ON snapshot.id = prediction.daily_feature_snapshot_id
    WHERE prediction.prediction_run_id = OLD.id AND snapshot.ingestion_run_id <> NEW.weather_ingestion_run_id);
END;
--> statement-breakpoint
CREATE TRIGGER `prediction_snapshot_weather_update_guard` BEFORE UPDATE OF ingestion_run_id ON `weather_daily_feature_snapshots` BEGIN
  SELECT RAISE(ABORT, 'Weather snapshot update breaks prediction run identity')
  WHERE EXISTS (SELECT 1 FROM predictions AS prediction
    JOIN prediction_runs AS publication ON publication.id = prediction.prediction_run_id
    WHERE prediction.daily_feature_snapshot_id = OLD.id AND publication.weather_ingestion_run_id <> NEW.ingestion_run_id);
END;
