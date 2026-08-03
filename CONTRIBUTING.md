# Contributing

## Workflow

1. Start from an up-to-date `main` branch.
2. Create a short-lived branch such as `feature/T-001-repository-scaffold` or
   `fix/T-123-forecast-card-state`.
3. Keep each branch focused on one backlog item.
4. Run the checks relevant to the changed subprojects.
5. Open a pull request and reference the ticket in its title or description.
6. Merge only after the acceptance criteria and known limitations are visible.

## Commit messages

Use an imperative summary and include the ticket when useful:

```text
T-001 scaffold monorepo documentation
T-002 add API health endpoint
```

Do not mix unrelated refactors, formatting, and product behavior in one commit.

## Database migrations

Drizzle schema declarations, generated SQL migrations, and Drizzle metadata are
one reviewable unit. When a ticket changes the SQLite schema:

1. change the owning `packages/database` schema declaration;
2. generate a named migration with Drizzle Kit;
3. review the generated SQL, checks, foreign keys, indexes, and seed changes;
4. commit the schema, SQL migration, and `drizzle/meta` files together;
5. prove the migration against a fresh local test database.

Use a concise lowercase `snake_case` migration name, such as
`create_flight_foundation`. Never edit, rename, delete, or regenerate a
migration that has been applied outside a disposable local test database; add a
new migration instead. Do not use `drizzle-kit push`, ad-hoc DDL, or a second
migration system.

Keep migration commits ticket-prefixed and imperative, for example:

```text
T-012 add initial flight database migrations
T-018 add weather feature migration
```

## Documentation ownership

- Update the root `README.md` for repository-wide setup, architecture links,
  and commands used by most contributors.
- Update a subproject README when its own commands, configuration, internal
  layout, or operational behavior changes.
- Update `.env.example` whenever code requires a new environment variable.
- Record known data, model, and safety limitations honestly.

## Pull request checklist

- [ ] The change references a backlog item.
- [ ] Setup/run commands are current.
- [ ] Relevant checks pass from a clean checkout.
- [ ] New configuration is represented in `.env.example` without secrets.
- [ ] Data provenance and data-status labels are preserved.
- [ ] No raw data, credentials, private pilot information, or large artifacts
      are included.
- [ ] Known limitations and follow-up work are documented.
