CREATE TABLE `__t018_copernicus_elevation_guard` (
  `matched_config_count` integer NOT NULL
  CONSTRAINT `__t018_copernicus_elevation_guard_count_check`
  CHECK (`matched_config_count` = 7)
) STRICT;--> statement-breakpoint
INSERT INTO `__t018_copernicus_elevation_guard` (`matched_config_count`)
SELECT count(*)
FROM `weather_site_sampling_configs`
WHERE `reference_elevation_msl_m` IS NULL
  AND `elevation_reference` IS NULL
  AND (
    (`site_id` = 1 AND `latitude_deg` = 42.6013 AND `longitude_deg` = 23.2844 AND `coordinate_reference` = 'canonical_site_coordinate_v1')
    OR (`site_id` = 2 AND `latitude_deg` = 42.7302 AND `longitude_deg` = 24.0923 AND `coordinate_reference` = 'canonical_site_coordinate_v1')
    OR (`site_id` = 3 AND `latitude_deg` = 42.68733 AND `longitude_deg` = 24.749962 AND `coordinate_reference` = 'canonical_site_coordinate_v1')
    OR (`site_id` = 4 AND `latitude_deg` = 43.2622 AND `longitude_deg` = 27.2846 AND `coordinate_reference` = 'canonical_site_coordinate_v1')
    OR (`site_id` = 5 AND `latitude_deg` = 43.2575 AND `longitude_deg` = 26.9258 AND `coordinate_reference` = 'canonical_site_coordinate_v1')
    OR (`site_id` = 6 AND `latitude_deg` = 43.4282 AND `longitude_deg` = 23.3032 AND `coordinate_reference` = 'canonical_site_coordinate_v1')
    OR (`site_id` = 7 AND `latitude_deg` = 43.746321 AND `longitude_deg` = 28.074025 AND `coordinate_reference` = 'kardam_accepted_flight_centroid_v1')
  );--> statement-breakpoint
UPDATE `weather_site_sampling_configs`
SET
  `reference_elevation_msl_m` = CASE `site_id`
    WHEN 1 THEN 1793.929
    WHEN 2 THEN 1129.007
    WHEN 3 THEN 1445.337
    WHEN 4 THEN 307.87
    WHEN 5 THEN 447.1
    WHEN 6 THEN 522.765
    WHEN 7 THEN 190.402
  END,
  `elevation_reference` = 'copernicus_dem_glo30_egm2008_orthometric_bilinear_v1'
WHERE `site_id` BETWEEN 1 AND 7;--> statement-breakpoint
DROP TABLE `__t018_copernicus_elevation_guard`;
