# Database workspace

`@paragliding-forecasts/database` is the sole owner of SQLite schema
declarations, Drizzle migration history, and the Node-side connection boundary.
It currently defines only the T-012 flight-data foundation: sources, canonical
sites, reviewed source-site mappings, ingestion provenance, and validated
flight records.

The default database is `data/local/paragliding.db`, configured as
`DATABASE_URL=file:./data/local/paragliding.db`. The connection accepts only a
relative `file:` URL that resolves below the repository `data/` directory, and
enables `PRAGMA foreign_keys = ON` for every Node connection. Python must use a
migrated SQLite file, enable the same pragma, and never own DDL or migrations.

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
that table option in the TypeScript schema, so the reviewed migration contains
the minimum explicit SQLite clause needed to preserve the accepted schema.

No T-012 command imports data, calls an external source, stores raw payloads,
or changes the API's in-memory repositories.
