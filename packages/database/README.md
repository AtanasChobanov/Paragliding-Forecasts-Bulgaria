# Database workspace

`@paragliding-forecasts/database` is the sole owner of SQLite schema
declarations, Drizzle migration history, and the Node-side connection boundary.
It owns both the validated-flight foundation and the T-018 source-neutral
weather persistence contract. Python may write rows through a non-migrating
adapter, but it never owns DDL.

The default database is `data/local/paragliding.db`, configured as
`DATABASE_URL=file:./data/local/paragliding.db`. The connection accepts only a
relative `file:` URL that resolves below the repository `data/` directory and
enables `PRAGMA foreign_keys = ON` for every Node connection.

## Commands

Run these from the repository root:

```powershell
npm.cmd run db:generate --workspace @paragliding-forecasts/database -- --name <lower_snake_case_name>
npm.cmd run db:check --workspace @paragliding-forecasts/database
npm.cmd run db:migrate --workspace @paragliding-forecasts/database
npm.cmd run test --workspace @paragliding-forecasts/database
```

`db:generate` creates Drizzle migration files. Review SQL and its metadata
before `db:migrate`; never use `drizzle-kit push`. The migrator applies only the
committed files in `drizzle/`, so a second run records no duplicate work.

The migrations use SQLite `STRICT` tables. Drizzle Kit does not yet declare
that table option in the TypeScript schema, so every reviewed generated
migration receives only the minimum explicit `STRICT` amendment before review.

## Current schema boundary

The flight path uses `flight_sources`, `sites`, `source_site_mappings`,
`flight_ingestion_runs`, and `flight_records`. T-018 renames the former
`ingestion_runs` table without rebuilding it, preserving existing rows and
foreign keys. Its legacy internal constraint and index names intentionally stay
unchanged because renaming those objects would require an unsafe, unnecessary
SQLite table rebuild.

The weather path uses fourteen normalized tables:

- source and execution identity: `weather_sources`, `weather_ingestion_runs`,
  and `weather_product_runs`;
- approved site/grid sampling: `weather_site_sampling_configs`,
  `weather_grids`, `weather_grid_points`, `weather_sampling_footprints`, and
  `weather_sampling_footprint_nodes`;
- canonical and repeated measurements: `weather_samples`,
  `weather_profile_levels`, `weather_convection_measurements`, and
  `weather_interval_measurements`;
- derived ML-ready values and per-field audit meaning:
  `weather_feature_snapshots` and `weather_field_provenance`.

Raw/interim artifacts remain files under `data/raw` and `data/interim`; the
run's manifest path and SHA-256 are the database pointer. There is deliberately
no `weather_artifacts` table. Field quality such as `real`, `derived`, or
`missing` is stored per field in `weather_field_provenance`, not once for a
multi-field record.

The generated T-018 weather migration contains schema only. It does not seed
GFS/ERA5 source rows, site sampling coordinates, grids, or footprints; those
records require separately reviewed collector/configuration inputs. Applying
the migration to the configured local database is an explicit review step and
must not be inferred from migration generation or temporary test-database runs.