UPDATE `sites`
SET `catchment_radius_km` = 5
WHERE `id` IN (1, 2, 3, 4, 5, 6)
  AND `site_type` = 'launch_area';
