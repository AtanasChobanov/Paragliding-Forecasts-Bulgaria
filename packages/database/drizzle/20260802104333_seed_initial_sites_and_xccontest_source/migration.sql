INSERT INTO `flight_sources` (`id`, `code`, `name`, `base_url`, `is_active`)
VALUES (1, 'xccontest', 'XCContest', 'https://www.xcontest.org', 1);
--> statement-breakpoint
INSERT INTO `sites` (
  `id`,
  `slug`,
  `name`,
  `country_code_iso2`,
  `site_type`,
  `latitude_deg`,
  `longitude_deg`,
  `catchment_radius_km`,
  `time_zone`,
  `is_active`
)
VALUES
  (1, 'sofia-vitosha-kominite', 'Sofia - Vitosha (Kominite)', 'BG', 'launch_area', 42.6013, 23.2844, NULL, 'Europe/Sofia', 1),
  (2, 'zlatitsa', 'Zlatitsa', 'BG', 'launch_area', 42.7302, 24.0923, NULL, 'Europe/Sofia', 1),
  (3, 'sopot', 'Sopot', 'BG', 'launch_area', 42.68733, 24.749962, NULL, 'Europe/Sofia', 1),
  (4, 'nevsha', 'Nevsha', 'BG', 'launch_area', 43.2622, 27.2846, NULL, 'Europe/Sofia', 1),
  (5, 'shumen', 'Shumen', 'BG', 'launch_area', 43.2575, 26.9258, NULL, 'Europe/Sofia', 1),
  (6, 'pastrina', 'Pastrina', 'BG', 'launch_area', 43.4282, 23.3032, NULL, 'Europe/Sofia', 1),
  (7, 'dobrich-region', 'Dobrich region', 'BG', 'region', 43.56667, 27.83333, 30, 'Europe/Sofia', 1);
