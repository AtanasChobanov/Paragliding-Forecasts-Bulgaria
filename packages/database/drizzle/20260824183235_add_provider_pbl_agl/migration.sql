ALTER TABLE `weather_samples`
ADD `provider_boundary_layer_height_agl_m` real
CONSTRAINT `weather_samples_boundary_layer_agl_non_negative_check`
CHECK (
  `provider_boundary_layer_height_agl_m` IS NULL
  OR `provider_boundary_layer_height_agl_m` >= 0
);--> statement-breakpoint
CREATE TRIGGER `weather_samples_boundary_layer_agl_method_insert_trigger`
BEFORE INSERT ON `weather_samples`
WHEN NEW.`provider_boundary_layer_height_agl_m` IS NOT NULL
  AND (
    NEW.`provider_boundary_layer_method` IS NULL
    OR length(trim(NEW.`provider_boundary_layer_method`)) = 0
  )
BEGIN
  SELECT RAISE(ABORT, 'provider boundary-layer AGL height requires a method');
END;--> statement-breakpoint
CREATE TRIGGER `weather_samples_boundary_layer_agl_method_update_trigger`
BEFORE UPDATE OF
  `provider_boundary_layer_height_agl_m`,
  `provider_boundary_layer_method`
ON `weather_samples`
WHEN NEW.`provider_boundary_layer_height_agl_m` IS NOT NULL
  AND (
    NEW.`provider_boundary_layer_method` IS NULL
    OR length(trim(NEW.`provider_boundary_layer_method`)) = 0
  )
BEGIN
  SELECT RAISE(ABORT, 'provider boundary-layer AGL height requires a method');
END;
