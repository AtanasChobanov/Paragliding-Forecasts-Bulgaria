CREATE TEMP TABLE `__t020_weather_graph_guard` (`violations` integer NOT NULL CHECK (`violations` = 0));--> statement-breakpoint
INSERT INTO `__t020_weather_graph_guard` SELECT count(*) FROM `weather_point_samples` AS point JOIN `weather_ingestion_runs` AS run ON run.id = point.ingestion_run_id JOIN `weather_product_valid_times` AS valid ON valid.id = point.product_valid_time_id WHERE run.product_run_id <> valid.product_run_id;--> statement-breakpoint
INSERT INTO `__t020_weather_graph_guard` SELECT count(*) FROM `weather_daily_feature_snapshot_inputs` AS link JOIN `weather_daily_feature_snapshots` AS daily ON daily.id = link.daily_feature_snapshot_id JOIN `weather_point_samples` AS point ON point.id = link.weather_point_sample_id WHERE daily.ingestion_run_id <> point.ingestion_run_id OR daily.point_footprint_id <> point.point_footprint_id;--> statement-breakpoint
DROP TABLE `__t020_weather_graph_guard`;--> statement-breakpoint
ALTER TABLE `weather_product_valid_times`
ADD COLUMN `required_inputs_last_modified_at_utc` text
CONSTRAINT `weather_product_valid_times_required_inputs_last_modified_at_utc_shape_check`
CHECK (`required_inputs_last_modified_at_utc` IS NULL OR
  `required_inputs_last_modified_at_utc` GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z');
--> statement-breakpoint
CREATE TRIGGER `weather_point_product_insert_guard` BEFORE INSERT ON `weather_point_samples` BEGIN
  SELECT RAISE(ABORT, 'Weather point sample product differs from ingestion run')
  WHERE (SELECT product_run_id FROM weather_ingestion_runs WHERE id = NEW.ingestion_run_id)
     <> (SELECT product_run_id FROM weather_product_valid_times WHERE id = NEW.product_valid_time_id);
END;
--> statement-breakpoint
CREATE TRIGGER `weather_point_product_update_guard` BEFORE UPDATE OF ingestion_run_id, product_valid_time_id ON `weather_point_samples` BEGIN
  SELECT RAISE(ABORT, 'Weather point sample product differs from ingestion run')
  WHERE (SELECT product_run_id FROM weather_ingestion_runs WHERE id = NEW.ingestion_run_id)
     <> (SELECT product_run_id FROM weather_product_valid_times WHERE id = NEW.product_valid_time_id);
  SELECT RAISE(ABORT, 'Weather point sample update breaks daily input identity')
  WHERE EXISTS (SELECT 1 FROM weather_daily_feature_snapshot_inputs AS link
    JOIN weather_daily_feature_snapshots AS daily ON daily.id = link.daily_feature_snapshot_id
    WHERE link.weather_point_sample_id = OLD.id
      AND (daily.ingestion_run_id <> NEW.ingestion_run_id OR daily.point_footprint_id <> NEW.point_footprint_id));
END;
--> statement-breakpoint
CREATE TRIGGER `weather_run_product_update_guard` BEFORE UPDATE OF product_run_id ON `weather_ingestion_runs` BEGIN
  SELECT RAISE(ABORT, 'Weather ingestion product update breaks point sample identity')
  WHERE EXISTS (SELECT 1 FROM weather_point_samples AS point
    JOIN weather_product_valid_times AS valid ON valid.id = point.product_valid_time_id
    WHERE point.ingestion_run_id = OLD.id AND valid.product_run_id <> NEW.product_run_id);
END;
--> statement-breakpoint
CREATE TRIGGER `weather_valid_product_update_guard` BEFORE UPDATE OF product_run_id ON `weather_product_valid_times` BEGIN
  SELECT RAISE(ABORT, 'Weather valid-time product update breaks point sample identity')
  WHERE EXISTS (SELECT 1 FROM weather_point_samples AS point
    JOIN weather_ingestion_runs AS run ON run.id = point.ingestion_run_id
    WHERE point.product_valid_time_id = OLD.id AND run.product_run_id <> NEW.product_run_id);
END;
--> statement-breakpoint
CREATE TRIGGER `weather_daily_input_insert_guard` BEFORE INSERT ON `weather_daily_feature_snapshot_inputs` BEGIN
  SELECT RAISE(ABORT, 'Weather daily input differs from snapshot run or footprint')
  WHERE EXISTS (SELECT 1 FROM weather_daily_feature_snapshots AS daily
    JOIN weather_point_samples AS point ON point.id = NEW.weather_point_sample_id
    WHERE daily.id = NEW.daily_feature_snapshot_id
      AND (daily.ingestion_run_id <> point.ingestion_run_id OR daily.point_footprint_id <> point.point_footprint_id));
END;
--> statement-breakpoint
CREATE TRIGGER `weather_daily_input_update_guard` BEFORE UPDATE OF daily_feature_snapshot_id, weather_point_sample_id ON `weather_daily_feature_snapshot_inputs` BEGIN
  SELECT RAISE(ABORT, 'Weather daily input differs from snapshot run or footprint')
  WHERE EXISTS (SELECT 1 FROM weather_daily_feature_snapshots AS daily
    JOIN weather_point_samples AS point ON point.id = NEW.weather_point_sample_id
    WHERE daily.id = NEW.daily_feature_snapshot_id
      AND (daily.ingestion_run_id <> point.ingestion_run_id OR daily.point_footprint_id <> point.point_footprint_id));
END;
--> statement-breakpoint
CREATE TRIGGER `weather_daily_snapshot_identity_update_guard` BEFORE UPDATE OF ingestion_run_id, point_footprint_id ON `weather_daily_feature_snapshots` BEGIN
  SELECT RAISE(ABORT, 'Weather daily snapshot update breaks hourly input identity')
  WHERE EXISTS (SELECT 1 FROM weather_daily_feature_snapshot_inputs AS link
    JOIN weather_point_samples AS point ON point.id = link.weather_point_sample_id
    WHERE link.daily_feature_snapshot_id = OLD.id
      AND (point.ingestion_run_id <> NEW.ingestion_run_id OR point.point_footprint_id <> NEW.point_footprint_id));
END;
--> statement-breakpoint
CREATE TRIGGER `weather_point_footprint_update_guard` BEFORE UPDATE OF point_footprint_id ON `weather_point_samples` BEGIN
  SELECT RAISE(ABORT, 'Weather point footprint update breaks daily input identity')
  WHERE EXISTS (SELECT 1 FROM weather_daily_feature_snapshot_inputs AS link
    JOIN weather_daily_feature_snapshots AS daily ON daily.id = link.daily_feature_snapshot_id
    WHERE link.weather_point_sample_id = OLD.id AND daily.point_footprint_id <> NEW.point_footprint_id);
END;
