# Project Handoff

## Read first

1. `AGENTS.md` for repository rules.
2. `docs/tasks.md` for ticket status and scope.
3. This handoff for the T-019 sounding-ingestion planning state.
4. The relevant sections of `docs/project-brief.md` and
   `docs/architecture.md` for product/system constraints.
5. DEC-031 through DEC-054 in `docs/decisions.md` for accepted weather
   decisions, including the ERA5 deferral boundary.

Keep durable decisions in `docs/decisions.md`, ticket lifecycle in
`docs/tasks.md`, and only current actionable state here.

## Current state — 2026-09-17

| Field | Value |
| --- | --- |
| Branch | `feature/T-019-sounding-ingestion` |
| Ticket | `T-019` is **In Progress**. The artifact-first IGRA implementation and offline automated verification are complete; the owner has not run the bounded live NOAA acceptance. `T-018` remains done and ERA5 remains deferred to T-038. |
| Next work | Owner: run `igra-ingest inventory`, review its five HEAD sizes and cap, then run the reviewed bounded `fresh` and offline `resume` below. Record the output and only then consider task completion. Do not add SQL, a T-020 training join, GFS/IGRA comparison, ERA5, BUFR, or image/OCR scope. |
| Fresh evidence | T-019: Ruff passed; `uv run --project services/ml pytest` passed **291** tests; `npm.cmd run repo:check`, `format:check`, `typecheck`, `lint`, and `test` passed. All T-019 execution used local fixtures/fake transport; no live NOAA request was made. |
| Local DB | The primary and temporary restoration SQLite databases were migrated by the owner for T-018 acceptance. They are local ignored artifacts and must not be committed. |
| User work | `docs/T-019-implementation-plan.md` is a local planning reference. Per owner instruction, do not stage or commit it. |
## T-019 implementation-plan boundary

The accepted research and executable implementation logic are in
[`T-019-implementation-plan.md`](T-019-implementation-plan.md)
and DEC-054. T-019 is **In Progress**: its artifact-first ingestion code is
implemented, but its owner-operated live NOAA acceptance has not run in this
branch.

- Source: official NOAA/NCEI IGRA v2.2 raw and provider-derived station ZIPs
  for Sofia `BUM00015614`; station snapshots update daily and observations are
  normally published with roughly two days of delay.
- Command boundary: `igra-ingest inventory`, bounded-network `fresh`, and
  hash-verified offline `resume`, for explicit nominal UTC dates.
- Storage: immutable raw station snapshots plus selected, normalized,
  validated JSONL/report artifacts only. No SQLite or Drizzle work belongs in
  T-019.
- Time policy: ingest every actual sounding on requested UTC dates. The Sofia
  10:00–20:00 flying window is classification applied later, not an ingestion
  filter.
- ML boundary: T-020 joins flight labels to pre-flight exact GFS features only.
  IGRA observations are not predictors and are not a required join.
- Comparison boundary: T-039 will sample GFS at the exact IGRA station and
  nominal time, then quantify profile errors and calibration/bias evidence.

The bounded live spike artifacts are local and ignored under
`data/raw/sounding-spike/20260915-igra-sofia/`. The current raw plus derived
period-of-record ZIP pair totals 75,420,975 bytes (71.93 MiB); this is evidence
for the documented explicit 80 MiB example cap, not a permanent assumed size.
### Verified offline implementation

The implementation performs a fresh five-object HEAD inventory, validates
identity encoding and source metadata, checks the reviewed compressed-byte cap
before streaming any GET, verifies the expected ZIP members, and publishes only
immutable, SHA-256-addressed snapshots and stage outputs. Parser input is read
line-by-line from the ZIP members, retaining selected records rather than whole
expanded archives. `resume` constructs no transport and recursively verifies
all referenced evidence before processing.

On 2026-09-17, `uv run --project services/ml ruff check services/ml` passed and
`uv run --project services/ml pytest` passed 291 tests. Repository
`repo:check`, formatting, TypeScript typecheck/lint, and workspace tests also
passed. These checks used only local fixtures and a fake transport; they are not
live source acceptance.

### Owner-operated live acceptance — not run

Run this HEAD-only inventory first and record all five `Content-Length` values,
`minimum_required_mib`, selected archive, and source metadata:

```powershell
uv run --project services/ml igra-ingest inventory `
  --station-id BUM00015614 `
  --date 2025-08-02 `
  --archive period-of-record `
  --allow-live-network
```

If and only if the reviewed inventory is at most the explicit 80 MiB cap, run
one fresh collection, inspect its JSON result, then rerun the exact completed
run offline:

```powershell
uv run --project services/ml igra-ingest fresh `
  --station-id BUM00015614 `
  --date 2025-08-02 `
  --archive period-of-record `
  --maximum-total-mib 80 `
  --allow-live-network

uv run --project services/ml igra-ingest resume --run-key <fresh-run-key>
```

Do not automatically increase the cap if inventory is larger. Review the
validated manifest/report and record the outcome here before marking T-019
done. The CLI and resulting artifacts remain exactly scoped to IGRA observation
handling; T-020 and T-039 remain separate.

### Storage scaling

The retained GFS run is dominated by derived global arrays, not SQLite rows:
raw payloads are about 1.09 GiB, active parser v5 artifacts about 10.92 GiB,
and active normalizer v7 artifacts about 12.01 GiB; spatial/validator/features
total only about 18 MiB. With superseded history, one retained day is about
47 GiB, so naive 100-day retention is not viable.

The compact design is locked:

- Decode and validate the full GRIB message in memory, preserving bitmap and
  sentinel semantics; persist only the deterministic rectangular crop required
  by configured site footprints.
- The current seven sites need 77 unique nodes inside an 8 × 24 (192-cell)
  crop, versus the provider's 1440 × 721 global grid. Derive this crop from the
  immutable site snapshot and sampling policy; do not hard-code it.
- A rectangle, rather than sparse nodes, preserves current bilinear/radius
  sampling. Preserve float64 values, packed masks, global-to-local node
  translation, and `gfs_0p25_global` SQLite identity.
- Bind site-config SHA, sampling-policy SHA, and crop-selection version into
  acquisition/artifact identity. Changed footprint inputs may not silently
  reuse a compact or persisted graph.
- Keep raw source evidence and existing completed artifacts. Do not introduce
  raw pruning, new dependencies, or SQLite columns.

Given identical raw GRIB, site snapshot, and policy, selected-node canonical
and SQLite business values must be unchanged. Only derived on-disk representation
and repeated verification work may change.

## Commands and safety

Use `uv run --project services/ml ...` for ML commands. Do not make a live
network request unless the current phase explicitly calls for the owner-
authorized bounded fresh operation. Resume must not construct or call a source
transport. Do not mark S09, S10, or T-018 complete without the documented
operational evidence.
