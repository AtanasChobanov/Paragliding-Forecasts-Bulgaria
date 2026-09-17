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
| Ticket | `T-019` is **Review**. The artifact-first IGRA pipeline is implemented and owner-operated live acceptance succeeded for the reviewed two-date scope. `T-018` remains in Review and ERA5 remains deferred to T-038. |
| Reviewed live evidence | HEAD-only inventory found five objects totaling `75,714,341` compressed bytes (`73 MiB` minimum) with no warnings. Owner then ran `fresh` for Sofia `BUM00015614`, 2025-08-02 and 2025-08-11, period-of-record, 80 MiB cap. It used verified cache reuse, accepted 4 soundings, quarantined 0, had 0 missing-evidence records, and exited 0. The source snapshot ID was `c7dd598ab2114720d0ee53ae024eebfd6148a480293e5185d171e4155e3a6fe6`. |
| Offline replay evidence | Owner ran `resume` for `5ae72afe-e71e-4c32-ade8-cd57426533e8`. It returned the same four accepted soundings, no quarantine/missing evidence, exit 0, and the identical effective manifest SHA-256 `b7cb4e3100f321a28dcad36ecd456a2c2b1310544db2a9a3cdc10c943b0c4abd`. |
| Next work | Review the task implementation and evidence; do not add SQL, T-020 training joins, GFS/IGRA comparison, ERA5, BUFR, or image/OCR scope. |
| Local DB | The primary and temporary restoration SQLite databases were migrated by the owner for T-018 acceptance. They are local ignored artifacts and must not be committed. |
| User work | `docs/T-019-implementation-plan.md` is a local planning reference. Per owner instruction, do not stage or commit it. |

## T-019 implementation and operational boundary

The accepted research and executable implementation logic are in
[`T-019-implementation-plan.md`](T-019-implementation-plan.md) and DEC-054.
The operational documentation and commands are in
[`../services/ml/README.md`](../services/ml/README.md). The task is now in
**Review**, not Done: its scoped implementation and evidence are ready for
review, while follow-on work remains deliberately separate.

- Source: official NOAA/NCEI IGRA v2.2 raw and provider-derived station ZIPs
  for Sofia `BUM00015614`; station snapshots update daily and observations are
  normally published with roughly two days of delay.
- Command boundary: live HEAD-only `igra-ingest inventory`, bounded live
  `fresh`, then hash-verified offline `resume`, for explicit UTC dates.
- Storage: immutable raw station snapshots plus selected, normalized, and
  validated JSONL/report artifacts only. No SQLite or Drizzle work belongs in
  T-019.
- Time policy: every actual sounding on the requested UTC dates is retained.
  The Sofia 10:00–20:00 flying window is classified later, not filtered here.
- ML boundary: T-020 joins flight labels only to pre-flight exact GFS features.
  IGRA observations are not predictors and are not a required join.
- Comparison boundary: T-039 may consume the effective validated manifest to
  compare GFS at the exact IGRA station and nominal time, then quantify
  profile error and calibration/bias evidence.

### Verified pipeline evidence

The successful fresh command was:

```powershell
uv run --project services/ml igra-ingest fresh `
  --station-id BUM00015614 `
  --date 2025-08-02 `
  --date 2025-08-11 `
  --archive period-of-record `
  --maximum-total-mib 80 `
  --allow-live-network
```

It published run `5ae72afe-e71e-4c32-ade8-cd57426533e8` and its effective
validator manifest at:

```text
data/interim/soundings/5ae72afe-e71e-4c32-ade8-cd57426533e8/validator-v1/af4e1b3b9a8a2aa11de719ae11fd8ec51dafe179d3dea12675b4ddc872b72300/stage-manifest.json
```

`fresh` first checks all five remote objects with HEAD, enforces the compressed
byte cap before any GET, then stores/reuses hash-verified source evidence. It
streams the selected ZIP members, parses fixed-width raw and derived records,
normalizes units/provenance, validates them, partitions accepted/quarantined/
missing evidence, and writes the effective `stage-manifest.json`. Its terminal
JSON is sorted and pretty-printed; `validated_manifest` is the trustworthy
handoff reference for T-039.

The offline replay was:

```powershell
uv run --project services/ml igra-ingest resume `
  --run-key 5ae72afe-e71e-4c32-ade8-cd57426533e8
```

It performed no live transport, verified the artifact chain, and returned the
same outcome and manifest identity. This is the command to use for safe local
inspection or recovery of an interrupted offline stage. New fresh runs use the
explicit `source-snapshot-reference.json` source-stage reference; the old
extensionless `snapshot` reference is intentionally unsupported and old runs
must be re-collected.

Prior local verification passed Ruff and the full ML suite (293 tests). The
current JSON presentation change also passed its formatter, focused Ruff check,
and three focused CLI tests. These local checks use fixtures/fake transport;
the owner commands above are the recorded real NOAA acceptance.
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
