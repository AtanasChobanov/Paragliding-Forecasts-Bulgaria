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
