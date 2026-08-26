CREATE TABLE `__t018_weather_source_seed_guard` (
  `conflict_count` integer NOT NULL
  CONSTRAINT `__t018_weather_source_seed_guard_count_check`
  CHECK (`conflict_count` = 0)
) STRICT;--> statement-breakpoint
INSERT INTO `__t018_weather_source_seed_guard` (`conflict_count`)
SELECT count(*)
FROM `weather_sources`
WHERE `code` IN ('noaa_gfs_0p25_aws_grib2', 'copernicus_era5')
  AND NOT (
    (`code` = 'noaa_gfs_0p25_aws_grib2'
      AND `provider_name` = 'NOAA'
      AND `dataset_name` = 'Global Forecast System 0.25° GRIB2'
      AND `source_kind` = 'forecast'
      AND `base_url` = 'https://noaa-gfs-bdp-pds.s3.amazonaws.com'
      AND `is_active` = 1)
    OR (`code` = 'copernicus_era5'
      AND `provider_name` = 'Copernicus Climate Change Service (ECMWF)'
      AND `dataset_name` = 'ERA5'
      AND `source_kind` = 'reanalysis'
      AND `base_url` = 'https://cds.climate.copernicus.eu'
      AND `is_active` = 1)
  );--> statement-breakpoint
INSERT INTO `weather_sources` (
  `code`, `provider_name`, `dataset_name`, `source_kind`, `base_url`, `is_active`
)
SELECT
  'noaa_gfs_0p25_aws_grib2', 'NOAA', 'Global Forecast System 0.25° GRIB2',
  'forecast', 'https://noaa-gfs-bdp-pds.s3.amazonaws.com', 1
WHERE NOT EXISTS (
  SELECT 1 FROM `weather_sources` WHERE `code` = 'noaa_gfs_0p25_aws_grib2'
);--> statement-breakpoint
INSERT INTO `weather_sources` (
  `code`, `provider_name`, `dataset_name`, `source_kind`, `base_url`, `is_active`
)
SELECT
  'copernicus_era5', 'Copernicus Climate Change Service (ECMWF)', 'ERA5',
  'reanalysis', 'https://cds.climate.copernicus.eu', 1
WHERE NOT EXISTS (
  SELECT 1 FROM `weather_sources` WHERE `code` = 'copernicus_era5'
);--> statement-breakpoint
CREATE TABLE `__t018_weather_source_seed_verification` (
  `matched_config_count` integer NOT NULL
  CONSTRAINT `__t018_weather_source_seed_verification_count_check`
  CHECK (`matched_config_count` = 2)
) STRICT;--> statement-breakpoint
INSERT INTO `__t018_weather_source_seed_verification` (`matched_config_count`)
SELECT count(*)
FROM `weather_sources`
WHERE (`code` = 'noaa_gfs_0p25_aws_grib2'
    AND `provider_name` = 'NOAA'
    AND `dataset_name` = 'Global Forecast System 0.25° GRIB2'
    AND `source_kind` = 'forecast'
    AND `base_url` = 'https://noaa-gfs-bdp-pds.s3.amazonaws.com'
    AND `is_active` = 1)
   OR (`code` = 'copernicus_era5'
    AND `provider_name` = 'Copernicus Climate Change Service (ECMWF)'
    AND `dataset_name` = 'ERA5'
    AND `source_kind` = 'reanalysis'
    AND `base_url` = 'https://cds.climate.copernicus.eu'
    AND `is_active` = 1);--> statement-breakpoint
DROP TABLE `__t018_weather_source_seed_verification`;--> statement-breakpoint
DROP TABLE `__t018_weather_source_seed_guard`;