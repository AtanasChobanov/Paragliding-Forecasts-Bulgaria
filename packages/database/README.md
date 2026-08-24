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

The foundation migration contains schema only. Reviewed follow-up data
migrations provision exactly one `weather_site_sampling_configs` row for every
canonical site. Six use their canonical site coordinates; Dobrich uses the
accepted Kardam weather coordinate `43.746321, 28.074025`. Ingestion never
auto-creates or recommends these rows: a missing/incomplete row fails sampling
preflight.

`20260824184712_set_copernicus_site_elevations` pins the seven reviewed
Copernicus DEM GLO-30 bilinear EGM2008 orthometric elevations. Its guard requires
the exact coordinate/reference pre-state and aborts instead of overwriting
drifted configuration. A repeatable live fetch is a review aid; it does not
update the database. Grids and sampling footprints remain run/model-derived and
are persisted later by T-018/S08.

`20260824183235_add_provider_pbl_agl` adds the missing direct provider boundary-
layer AGL field to `weather_samples`, distinct from the versioned derived PBL
field on `weather_feature_snapshots`.
