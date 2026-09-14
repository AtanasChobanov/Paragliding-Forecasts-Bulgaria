# T-018/S10 — GFS production hardening, lossless artifacts, and final verification

## Status and authority

This document records the owner-approved implementation plan for Slice 10. It
supersedes the earlier assumption that S09 must implement ERA5 before T-018 can
finish and combines the remaining GFS work into one ordered hardening gate:

1. correct the source-of-truth documentation and defer ERA5 ingestion;
2. remove repeated deep verification from operational ledger reads;
3. replace full-global decoded GFS artifacts with lossless compact grids;
4. harden fresh/offline-resume orchestration through shared service boundaries;
5. complete one bounded live acceptance run followed by offline replay and
   database restoration.

The choices below are implementation requirements, not open architecture
prompts. A future implementation agent should translate them into code and
stop for owner review only if repository evidence proves one of the locked
requirements impossible, unsafe, or internally inconsistent.

Do not implement ERA5, artifact deletion, partial/sampled integrity hashes,
Airflow, another scheduler, or unrelated feature/model work in S10.

This plan does not authorize commits by itself. Preserve all unrelated user
changes. In particular, the current deletions of the former S07 and S08 plan
files are user-owned and must not be restored, staged, or folded into an S10
commit unless the owner separately requests that action.

## Required outcome

Finish T-018 with one production-shaped, reproducible GFS ingestion path whose
runtime and storage are bounded enough for a multi-day historical collection:

```text
weather-ingest fresh
  -> bounded GFS planning and collection
  -> lossless compact parse and normalization
  -> unchanged site sampling, validation, and features
  -> atomic SQLite persistence

weather-ingest resume --run-key <uuid>
  -> zero source requests
  -> verify only the effective immutable lineage once
  -> reuse or rebuild legal derived boundaries
  -> restore or exactly revalidate SQLite persistence
```

S10 preserves the source-neutral schema and future ERA5 compatibility, but its
implementation and completion gate are GFS-only. No ERA5 row may be fabricated
as a fallback, comparison, or substitute for GFS.

The implementation must reduce both storage amplification from global decoded
arrays and command latency from repeated verification. Neither correction may
weaken immutable evidence, exact replay, provenance, missingness, conflict
detection, or final SQLite values.

## Mandatory implementation order

Follow this order; do not start the live gate until prior phases pass:

1. **Documentation and S09 deferral.** Correct stale source-of-truth scope.
2. **Verification hardening.** Stop deep-verifying every historical event so
   compact rebuilding does not repeatedly read the retained 47 GiB lineage.
3. **Compact GFS artifacts.** Apply the lossless crop design below.
4. **Orchestration hardening.** Use shared service functions and one
   command-scoped verification context instead of calling CLI wrappers.
5. **Bounded live acceptance.** Run a new current-catalogue fresh ingestion,
   offline no-op replay, and restore into another fresh migrated database.

The retained run cannot replace the final live gate because DEC-052 rejects
its stale catalogue identity.

## Phase 0 documentation and S09 deferral contract

### Durable scope decision

Add the next available durable decision, currently expected to be DEC-053, and
mark DEC-032 superseded only for its T-018 timing and delivery ownership.

The new decision must state:

- T-018 finishes with the implemented source-neutral schema and a complete GFS
  fresh/offline-resume pipeline through SQLite.
- ERA5 remains the accepted long-history reanalysis baseline from DEC-031, but
  its CDS collector and adapter are deferred until an ML/evaluation task has a
  concrete need for forecast-to-reanalysis pairs, bias analysis, climatology,
  weak cloud-base labels, confidence calibration, or fine-tuning evidence.
- The Project Brief lists ERA5/reanalysis as a candidate or fallback when exact
  historical forecasts are unavailable; it does not require ERA5 ingestion
  after a usable exact GFS archive has been established.
- ERA5 remains a separate `reanalysis` cohort and can never become a GFS row,
  live fallback, or same-example forecast substitute.
- Existing provider-neutral contracts, catalogue entries, source registry,
  usage-policy family, nullable CIN/cloud-base destinations, and
  `era5_0p25_global` schema allowance remain future-compatible. Do not remove
  or pretend to have exercised them.
- No inert ERA5 collector, fake success path, placeholder row, CDS credential
  requirement, or ERA5 command may be added in S10.
- Create a separate backlog task, currently expected to be T-038, for the ERA5
  CDS collector/reanalysis adapter. Its start gate is a demonstrated need from
  the joined GFS dataset, baseline model, calibration, or backtest work, not the
  mere availability of ERA5.

Do not mark former S09 complete. Record it as deferred/removed from the T-018
execution sequence and point to T-038.

### Files to reconcile before code changes

Review and update all of the following in one documentation-only commit:

- `docs/decisions.md`
  - add the superseding decision and index entry;
  - change DEC-032 status to superseded by the new decision;
  - update open wording that currently says T-018 directly uses CDS ERA5.
- `docs/tasks.md`
  - keep T-018 `In Progress` until every S10 gate passes;
  - make its remaining implementation/GFS completion scope accurate;
  - add T-038 as a future Historical Forecast Data task with concrete
    reanalysis use cases and the strict separate-cohort requirement.
- `docs/handoff.md`
  - replace stale S08/S09 next-focus text;
  - record S08 as implemented but still missing fresh operational acceptance;
  - mark S09 deferred to T-038;
  - describe S10 as GFS verification/storage/orchestration hardening;
  - update the read-order decision range and current date/state.
- `docs/architecture.md`
  - preserve the source-neutral forecast/reanalysis boundary;
  - describe ERA5 as supported by the storage design but not yet collected.
- `services/ml/README.md`
  - distinguish implemented GFS commands from future ERA5-compatible
    validation/persistence contracts;
  - remove any implication that an ERA5 end-to-end command exists;
  - retain accurate future policy/provenance requirements.
- root `README.md`
  - update it only if it claims ERA5 ingestion is implemented or required for
    current setup.
- `docs/project-brief.md`
  - normally leave it unchanged because its candidate/fallback wording already
    supports the decision; change it only if a contradictory mandatory
    statement is found.

Do not remove the registered ERA5 source, catalogue semantics, schema capacity,
or source-neutral validator branches merely because collection is deferred.
Do not change code behavior in this first commit. Run Markdown/repository
checks and inspect the diff for accidental claims that ERA5 itself is complete.

## Phase 1 artifact-verification performance hardening

### Verified cause of the latency

`RunStateLedger.load_events()` currently parses the small event files and, for
every event with evidence, recursively verifies that boundary and all inputs
and outputs. Each recursive call creates a new `visited` set. Consequently:

- later events repeatedly hash the same ancestry;
- superseded parser, normalizer, spatial, validator, feature, and failure
  boundaries are hashed although the command will not use them;
- repeated `load_events()` calls inside one CLI restart the work;
- `read_stage_manifest()` recursively verifies the boundary again;
- loaders often call `verify_boundary()` and then `verify_reference()` on the
  same manifest/output;
- `write_stage_manifest()` rereads inputs and newly written outputs;
- the recursive visited branch still verifies an already visited SHA instead
  of returning its verified path.

For the current 18-event retained ledger, manifest-size accounting estimates
approximately 362 GiB of sequential content reads for one old-style
`load_events()` traversal before counting further command-level reloads. The
event JSON chain is tiny and is not the performance problem.

### Separate ledger validity from artifact validity

Introduce an immutable `RunStateSnapshot` loaded once per command. It must:

- enumerate event JSON files in exact sequence order;
- read each event once and validate its strict contract, run key, sequence,
  transition, disposition, supersession target, and terminal rules;
- calculate each event SHA from bytes already read and compare the next
  `previous_event_sha256` without reopening the prior file;
- calculate the effective latest boundary for each stage;
- retain the final event digest and sequence for safe append;
- validate evidence references structurally but never recursively open their
  content during ledger loading.

Prefer a new explicit `load_state()` API. Keep a compatibility `load_events()`
wrapper only if necessary, with unambiguous documentation and no hidden deep
verification.

After loading state, each command explicitly verifies only the effective
upstream boundary it consumes. Recursive verification still follows that
boundary's declared inputs and outputs through raw evidence, so the complete
effective lineage remains protected. Evidence referenced only by superseded or
irrelevant failure events is not part of the operational path.

### Explicit effective and all-history audit modes

Add an offline maintenance command such as:

```text
weather-artifacts audit --run-key <uuid> --scope effective
weather-artifacts audit --run-key <uuid> --scope all
```

`effective` verifies the ledger and every current effective boundary. `all`
deliberately verifies every historical and superseded evidence boundary. The
expensive all-history audit is opt-in and must never run implicitly from parse,
sample, validate, feature, persist, fresh, or resume.

An intact effective lineage must not be blocked merely because unused
superseded evidence was archived or corrupted. The all-history audit must still
report that damage. Tampering with event JSON, an effective manifest/output, or
any transitive effective input remains a hard operational failure.

### One verification session per top-level command

Introduce `ArtifactVerificationSession`, owned by one run and resolved project
root. It is in-memory only: never global, serialized, persisted in SQLite, or
reused across processes.

Key verified files by complete identity, not SHA alone:

```text
(resolved path, artifact key, expected SHA-256, expected byte count,
 media type, record count)
```

Retain the safe path, file-stat snapshot, digest source, and parsed small JSON
manifest/model where reuse is useful. The stat snapshot includes size,
nanosecond modification/change time, and device/inode identity when available.
On a cache hit, stat again. If identity, size, or timestamps changed, invalidate
and fully reverify. Equal bytes at two paths do not let one path bypass
containment or file-identity checks.

Within one unchanged command execution:

- hash each pre-existing artifact at most once;
- parse each raw/stage manifest at most once;
- verify each recursive boundary at most once;
- load each compact NumPy matrix at most once when reused;
- return the cached path for an already visited reference.

### Preserve full SHA-256 integrity

Do not replace full hashes with prefixes, sampled blocks, modification times,
file names, or selected GRIB metadata. Those may be cheap preflight evidence,
but they are not content-integrity proof.

The optimization is to stop hashing unused evidence and repeated effective
files, not to weaken the digest. Retain one full SHA-256 pass for every
pre-existing file that the command trusts.

Raw payloads receive one full on-disk SHA-256 verification per top-level
fresh/resume execution that consumes them. Parser and persistence share that
result inside the same orchestration session; persistence must not start a
second raw pass. A separately launched stage command gets a new session and
therefore performs its own one-time effective-lineage verification.

### Safe write and manifest publication

For bytes produced in the current process:

1. calculate SHA-256 while serializing/writing, without a second in-memory copy
   when streaming is practical;
2. write to a stage-owned temporary file with exclusive creation;
3. flush, `fsync`, close, and validate byte count;
4. atomically publish the immutable final name;
5. register digest and stat evidence in the session;
6. refuse overwrite if the final name exists.

`write_stage_manifest()` verifies that every input is already fully verified
and every output is either just-written-and-registered or fully verified from
disk. Unknown references receive one full verification. It must not blindly
reread every input and output.

The download/write digest does not by itself replace final raw disk
verification. Before a `raw_complete/complete` boundary is consumed by a later
stage, perform one full on-disk pass and cache it for the rest of the top-level
execution.

Only an exact stage-owned temporary file may be cleaned up after failed
publication. Never delete completed artifacts or another run path implicitly.

### Snapshot-aware append

Ledger append consumes the current `RunStateSnapshot` instead of loading the
ledger again. It must validate against that snapshot, reuse its final event
digest, choose the exact next sequence, detect a concurrently appended event,
publish with exclusive creation, and return the updated snapshot/event.

Carry the updated snapshot across stage functions. Do not reload merely to find
a superseded sequence or persistence-attempt number.

### Verification observability and budgets

Collect command-local counters for files/bytes hashed, cache hits, manifests
parsed, boundaries verified, and optional elapsed hashing time. Expose a
secret-free `verification_summary` in structured fresh/resume/audit output, not
in SQLite business tables. Wall time is diagnostic; the output must make the
bounded effective-lineage behavior auditable.

### SQLite SHA fields remain unchanged

Do not add or remove SQLite SHA columns in S10. Existing fields have distinct
immutable roles and storing their strings does not cause bulk file reads:

- `raw_manifest_sha256` binds the run to collected source evidence;
- `feature_manifest_sha256` binds it to the effective feature boundary;
- `persistence_input_sha256` binds source, feature, catalogue, and operator
  policy inputs for exact no-op/conflict decisions.

`persisted_graph_sha256` remains receipt/report evidence, not another table
column. Crop, footprint, grid, per-file, and verification-cache hashes remain
artifact metadata and must not be copied into relational columns.

## Phase 2 lossless compact-grid execution

Replace the persisted full-global-grid parser and normalizer representation
with a compact regular-latitude/longitude crop that contains every node needed
by the accepted site-sampling policy.

The change is an artifact-representation optimization only. It must not change:

- which GFS native messages are requested or accepted;
- native values, units, timestamps, levels, steps, statistics, or provenance;
- the seven reviewed site configurations;
- strict bilinear point interpolation or its weights;
- the inclusive 50 km Haversine neighbourhood footprints;
- terrain comparison or below-terrain pressure-level exclusion;
- missing, sentinel, invalid, unsupported, real, or derived semantics;
- canonical normalization formulas or floating-point evaluation order;
- validator decisions, feature values, or SQLite business facts;
- the source provider grid identity `gfs_0p25_global`;
- immutable replay, conflict, or source-network boundaries.

The compact implementation is accepted only after an automated parity gate
proves that the old full-grid and new compact-grid paths produce identical
business outputs for the same source messages, configuration, and policy.
Until that gate passes, equivalence is a required invariant, not an assumed
claim.

## Why this correction is required before the S10 fresh gate

The retained GFS run `403c5135-8ced-4b54-a999-1c27e7ec78a3` provides the
following measured evidence:

| Boundary                  | Files |                    Size |
| ------------------------- | ----: | ----------------------: |
| Raw GFS payloads          |   606 |  approximately 1.09 GiB |
| Active parser v5          | 2,510 | approximately 10.92 GiB |
| Active normalizer v7      | 1,554 | approximately 12.01 GiB |
| Active spatial v5         |     3 |   approximately 8.6 MiB |
| Active validator v7       |     6 |   approximately 8.5 MiB |
| Active feature builder v4 |     4 |   approximately 1.2 MiB |

One stable-version day therefore needs approximately 24 GiB. One hundred days
would need approximately 2.4 TiB before allowing for superseded immutable
boundaries. The retained run itself occupies roughly 47 GiB because older
parser and normalizer versions remain present under the accepted immutable
supersession policy.

The global GFS grid has `1440 * 721 = 1,038,240` values per message. Parser v5
persists one little-endian float64 value array and one full boolean missing mask
for each of approximately 1,254 messages. Normalizer v7 then writes another
1,552 full-grid arrays. Manifest comparison shows that 1,186 active normalizer
arrays, approximately 9.4 GiB, are byte-identical to parser outputs.

The accepted seven-site policy actually uses only 77 unique global nodes across
all point and neighbourhood footprints. Their minimal enclosing regular crop
is:

| Property         | Current reviewed value |
| ---------------- | ---------------------- |
| Global rows      | `184..191` inclusive   |
| Global columns   | `91..114` inclusive    |
| Shape            | `8 x 24`               |
| Node count       | 192                    |
| Latitude bounds  | `42.25..44.00` degrees |
| Longitude bounds | `22.75..28.50` degrees |

The crop is approximately 5,400 times smaller than the global grid while
retaining all 77 used nodes. At the current message counts, raw parser numeric
values would occupy approximately 1.84 MiB and a fully materialized canonical
matrix approximately 2.27 MiB. Metadata and downstream artifacts will dominate
the compact decoded footprint; retained compressed raw GRIB will become the
main daily storage cost.

## Locked representation decision

### Use a minimal regular crop, not a sparse 77-node array

Persist the minimal row/column rectangle enclosing the exact union of all nodes
required by the active point and neighbourhood footprints. Do not persist only
the 77 nodes as an unordered or sparse vector.

The additional 115 cells are negligible, while a regular 2D crop preserves:

- deterministic row-major geometry;
- existing elementwise normalizations;
- straightforward bilinear interpolation;
- straightforward radius-node lookup;
- simple global-to-local index translation;
- clear grid bounds and scan-order validation;
- compatibility with later neighbourhood calculations within the same crop.

The current `8 x 24` bounds are verification expectations, not hard-coded
production constants. Production code must derive the crop from the reviewed
site snapshot, packaged sampling policy, and verified native grid geometry.
Any site or policy change must produce a different selection fingerprint and a
new immutable derived boundary.

### Keep native provider identity separate from stored representation

The source grid remains `gfs_0p25_global`. Do not create a new SQLite grid row
for `bulgaria_crop`, `site_crop`, or a run-specific subset. SQLite continues to
store minimal provider grid identity; crop geometry and footprint-node evidence
remain immutable filesystem artifacts.

Add an artifact-only compact-grid descriptor containing at least:

- descriptor schema version;
- selection algorithm identity and version;
- native grid key and full `Ni`/`Nj`;
- native first/last coordinates, increments, wrap, and scan flags;
- global inclusive row and column bounds;
- compact row and column counts;
- compact first/last coordinates and value order;
- ordered required-node union;
- point and neighbourhood footprint identities;
- native-grid geometry SHA-256;
- reviewed site-config SHA-256;
- packaged sampling-policy SHA-256;
- deterministic selection SHA-256.

Do not add these artifact identities as new SQLite SHA columns. Existing
relational business data and the accepted minimal-grid storage decision remain
unchanged.

## Deterministic crop planning

Implement one source-neutral regular-grid helper where practical, with the GFS
adapter supplying verified native geometry. Do not duplicate slightly different
footprint mathematics in parser and spatial stages.

The crop requires the reviewed SQLite site configuration earlier than the
current pipeline does. Make this dependency explicit:

- preflight loads one canonical read-only site-sampling snapshot and packaged
  policy;
- the shared run context passes that immutable in-memory snapshot to parser,
  normalizer, and spatial services;
- standalone `gfs-parse` gains the same database-resolution option used by
  sampling and opens SQLite read-only;
- parser configuration/fingerprint includes the exact site snapshot SHA,
  policy SHA, and crop-selection version;
- the compact descriptor persists those identities and the selected site rows;
- spatial reloads or receives the same snapshot and fails closed if its hashes
  differ from the parser descriptor;
- Python remains DML-free at parse/sample time and never creates/migrates the
  database.

Do not hide this input behind the current working database without
fingerprinting it. A changed site/policy snapshot must not reuse a compact
boundary created for different nodes.

For one run:

1. Read the complete reviewed weather-site sampling configuration snapshot
   read-only from the migrated SQLite database.
2. Load and validate the packaged canonical sampling policy.
3. Validate that the source grid is the supported regular 0.25-degree GFS grid,
   including scan direction, row/column order, longitude wrapping, and exact
   dimensions.
4. For every approved site, compute the same strict bilinear footprint used by
   the current spatial stage.
5. For every approved site, compute the same inclusive 50 km Haversine node
   footprint for the fields governed by the current policy.
6. Form the unique set of global `(row_index, column_index)` pairs from both
   footprint types.
7. Derive inclusive `min_row`, `max_row`, `min_column`, and `max_column` from
   that set.
8. Prove every required node lies within those bounds and that translating it
   to compact coordinates and back is exact.
9. Serialize the complete descriptor through the repository canonical JSON
   rules and calculate the selection fingerprint.
10. For the current reviewed configuration, assert the expected 77-node union
    and `8 x 24` crop as a regression fixture. Production behavior must still
    be data-driven rather than constant-driven.

Use global node identities in footprints and provenance. Compact coordinates
are an internal array lookup mechanism:

```text
local_row = global_row - crop_min_row
local_column = global_column - crop_min_column

global_row = local_row + crop_min_row
global_column = local_column + crop_min_column
```

Reject negative or out-of-bounds translations. Never silently clamp a node or
fall back to nearest-neighbour sampling.

## Parser implementation contract

### Preserve current validation; crop before persistence

The first compact parser version must retain the current conservative message
checks:

- selector/profile identity;
- reference and valid time;
- lead, level, unit, step, and statistic metadata;
- regular-grid dimensions and scan order;
- decoded value count equals full native `Ni * Nj`;
- GRIB bitmap/sentinel metadata agrees with the decoded full message;
- missing native values become `NaN` before downstream use.

For the initial implementation, decode one full message into a temporary
float64 array, perform the existing whole-message validation, reshape it using
the verified native scan order, copy only the compact rectangle, and release
the global array before processing the next message. The full decoded grid must
never be written to disk.

The installed ecCodes API provides indexed element access, but it is not a
required first-version optimization. A local retained-message measurement
showed exact selected-value parity but no demonstrated decode-time improvement.
Adopt indexed reads later only if tests prove identical bitmap/sentinel
validation and a measured runtime or memory benefit. Do not weaken the existing
global payload-integrity guard merely to avoid the transient array.

### Consolidate parser files

Do not write one values file and one missing-mask file per native message.
Persist a small fixed set of deterministic artifacts:

1. `compact-native-grid-batch.json`
   - compact descriptor;
   - ordered message metadata;
   - message-to-matrix-row mapping;
   - raw artifact and native message references;
   - per-message quality and missing counts;
   - references to the matrix and packed mask.
2. `compact-native-values.npy`
   - dtype exactly little-endian float64 (`<f8`);
   - shape `[message_count, crop_row_count, crop_column_count]`;
   - messages ordered by the existing deterministic parser order;
   - `allow_pickle=False`.
3. `compact-native-missing-mask.npy`
   - compact mask only, never a global mask;
   - bit-packed with an explicitly fixed bit order and original bit count;
   - sufficient to preserve selected-node sentinel identity independently of
     generic downstream missingness.
4. The existing-style stage manifest referencing all outputs and upstream raw
   evidence.

If deterministic incremental assembly needs temporary files, create them only
inside a stage-owned temporary directory and atomically publish the final
immutable artifacts. A failed attempt must not leave a complete boundary or a
ledger event.

Add a versioned matrix-slice reference contract containing:

- the owning `ArtifactReference`;
- zero-based matrix row;
- expected compact shape;
- expected dtype;
- selection fingerprint.

Every load verifies the artifact reference and validates row, shape, dtype, and
selection identity before returning a view or copy.

## Normalizer implementation contract

All existing normalization behavior must operate on compact arrays without
formula changes. Preserve float64 inputs, operation ordering, tolerances, sign
conventions, interval pairing, missing propagation, and native provenance.

Canonical grid messages must carry the same compact descriptor or its verified
reference. Do not reconstruct a crop independently from numeric bounds in the
normalizer.

For a canonical field whose values are already canonical and require no
numeric transformation:

- reference the parser matrix row directly through the versioned matrix-slice
  reference;
- do not copy the same bytes into a normalizer-owned array merely to express a
  new semantic field record;
- retain canonical field/unit/statistic metadata in the normalizer batch JSON.

For unit conversions, sign conversions, interval reconstruction, missing
materialization, or derived fields:

- calculate over compact matrices only;
- collect new rows in one deterministic
  `compact-canonical-derived-values.npy` matrix;
- reference each produced row by matrix-slice reference;
- retain every contributing selector, native message, raw artifact, method,
  and version exactly as the current contract requires.

Do not use filesystem hard links as a deduplication mechanism. Semantic reuse
must be visible in the immutable artifact reference graph and work across
platforms and copied artifact roots.

## Spatial-stage compatibility contract

Keep the accepted sampling definitions unchanged:

- strict four-node bilinear point sampling;
- no weight renormalization when a contributing node is missing;
- interpolate U/V components before deriving speed and direction;
- inclusive 50 km Haversine neighbourhood membership;
- exact model-orography and reviewed-site-elevation handling;
- the existing below-terrain pressure-level exclusion rule;
- existing global footprint node identities and definition hashes.

Replace full-global-array indexing with verified compact lookup:

1. Load the compact descriptor once.
2. Check its native geometry, site-config SHA, policy SHA, and selection SHA
   against the spatial stage inputs.
3. Translate every footprint's global row/column to compact row/column.
4. Fail closed if any required point or neighbourhood node is absent.
5. Retrieve values through the matrix-slice cache so each matrix artifact is
   hash-verified and loaded at most once per command execution.
6. Produce the existing canonical site samples and neighbourhood-node evidence
   without changing their domain values or global node identities.

The model-orography field must use the same compact descriptor and crop. It
must not retain a separate full-global elevation array.

## Compact-artifact hashing and immutability boundaries

This scaling change does not remove SHA-256 integrity checks. It reduces the
bytes and file count being hashed by changing artifact representation.

Required behavior:

- hash each newly published compact file according to the existing immutable
  artifact protocol;
- keep raw manifest/message provenance and hashes unchanged;
- include reused parser matrix references as normalizer inputs, not duplicated
  normalizer outputs;
- never rewrite an existing parser, normalizer, or spatial directory;
- publish compact boundaries under new component/schema versions;
- keep legacy full-grid artifacts readable for historical verification;
- do not delete legacy or raw artifacts during parser/normalizer execution.

Phase 1 owns repeated-hash elimination and the command-scoped verification
session. Compact readers/writers must use that session rather than introduce a
parallel cache. Do not weaken the ledger chain, skip effective-lineage
verification, or change raw-retention semantics.

## Backward compatibility and retained-run use

Introduce new artifact schema and producer versions; never reinterpret v5
parser or v7 normalizer payloads as compact artifacts.

The retained run may be used read-only as the parity oracle. Because it already
has historical and persistence state, do not append experimental compact
boundaries to it if doing so would violate terminal-run or replay rules.
Instead, the parity harness must use one of these isolated approaches:

- temporary artifact roots and a temporary run identity referencing copied or
  read-only retained raw evidence; or
- frozen compact test fixtures derived from the retained source under a new
  explicit offline replay identity.

Neither approach may alter, delete, supersede, or append state to the retained
source run. Any production formula or feature revision remains outside this
representation-only change.

## Losslessness and parity gates

### Numeric definition of equivalence

For the same raw messages, site configuration, and sampling policy:

- direct/native selected values must be bit-identical float64 values;
- `NaN` positions and selected sentinel masks must be identical;
- all transformed and derived canonical values must be bit-identical where the
  previous implementation is deterministic and uses the same operation order;
- signed zero must be preserved when semantically relevant;
- no new float32 conversion, rounding, quantization, compression loss, or
  tolerance-based value replacement is permitted;
- any unavoidable non-bit-exact result is a blocker, not an automatically
  accepted approximate match.

Artifact paths, hashes, schema versions, producer versions, crop metadata, and
timestamps are expected to differ. Those representation fields must be
excluded explicitly from business-value comparison; do not hide unexplained
domain differences behind a broad exclusion list.

### Required focused tests

Add tests for:

- deterministic crop planning from the seven reviewed site rows and policy;
- the expected current 77-node union and `8 x 24` bounds;
- exact global/local/global index round trips;
- north-to-south row order and west-to-east column order;
- longitude wrapping and invalid/unsupported scan layouts;
- a site exactly on a grid line or grid point;
- inclusive radius-boundary behavior;
- a required node at each crop edge and corner;
- missing values inside and outside the crop;
- compact packed-mask round trip and fixed bit order;
- full message-count/missing-count validation before crop persistence;
- deterministic message and matrix-row ordering;
- matrix-slice range, dtype, shape, and fingerprint failures;
- identity normalization reusing parser storage;
- transformed and interval-derived normalization using compact storage;
- model-orography crop and below-terrain behavior;
- absence of nearest-node fallback;
- immutable stage reuse and new-version publication;
- interrupted write leaving no completed boundary.

### Legacy-versus-compact retained-data parity

Create an ignored/manual offline parity fixture over the retained real GFS
evidence. It must make zero network calls and compare:

1. required point and neighbourhood footprint definitions;
2. every selected native value and sentinel position;
3. every canonical compact value and provenance identity;
4. all 77 site-hour canonical samples;
5. all neighbourhood-node samples;
6. validation dispositions, quality states, and reason codes;
7. hourly and daily feature values;
8. the prepared persistence business graph;
9. SQLite domain rows persisted independently to two freshly migrated
   temporary databases.

Database comparison must include every business value, null, unit, time,
statistic, quality state, missing reason, source identity, footprint/node
identity, and provenance relation. It may normalize only run-specific surrogate
keys, artifact paths/hashes, producer versions, and execution timestamps.
Row counts and natural-key sets must match exactly.

Any changed SQLite value, null state, field quality, footprint membership,
exclusion decision, feature value, or provider provenance blocks acceptance.

### Storage regression gate

Add a deterministic bounded-fixture assertion that prevents global arrays from
returning. At minimum verify:

- no parser or normalizer output array has global `721 x 1440` shape;
- no persisted parser missing mask has global cell count;
- the compact descriptor contains every required footprint node;
- normalizer identity fields do not create duplicate numeric outputs;
- the current reviewed configuration resolves to at most 192 persisted cells
  per field unless an explicitly reviewed policy/site change updates the
  fixture;
- parser plus normalizer numeric output for the bounded day remains below a
  conservative documented limit such as 32 MiB.

The size check must inspect artifact manifests and file lengths. It must not
rehash multi-gigabyte legacy directories merely to calculate the result.

## Expected storage result and raw-retention boundary

With compact parser/normalizer artifacts, approximately 1.09 GiB of compressed
raw GRIB becomes the main per-day cost. Allowing for current downstream JSON
artifacts, 100 days should be on the order of 110--115 GiB rather than 2.4 TiB.
Record the measured result from the first fresh compact run; do not present this
estimate as a completed benchmark.

Do not delete raw GRIB as part of this slice revision. Raw retention is what
permits parser corrections, new site/policy crops, and offline database
restoration without another provider request. Provider-side spatial subsetting,
regional GRIB re-encoding, cold archival, and whole-run pruning require a
separate reviewed retention/source decision.

Do not selectively remove files referenced by an existing state ledger or
stage manifest. Such a run is no longer replayable or hash-verifiable.

## Dependency decision

Add no dependency for this work.

- Continue using the pinned `eccodes==2.47.0` package for GRIB decoding.
- Continue using NumPy for little-endian float64 matrices, deterministic
  slicing, and packed compact masks.
- Do not add xarray, cfgrib, Zarr, Parquet/PyArrow, Dask, or MetPy.
- Do not add the external `wgrib2` executable solely to create a regional GRIB.
- Do not introduce lossy compression or float32 storage.

If implementation evidence later demonstrates that a new dependency is
necessary, stop for owner review and record the concrete need before adding it.

## Phase 3 orchestration hardening

### Shared execution context and service boundaries

The current pipeline invokes individual CLI `main()` functions, redirects
stdout, and parses their JSON. Replace that internal coupling with typed service
functions. CLI wrappers remain thin argument/result adapters.

Introduce a command-scoped context, for example `WeatherRunContext`, containing:

- one `WeatherArtifactStore`;
- one `ArtifactVerificationSession`;
- one `RunStateLedger` and current `RunStateSnapshot`;
- resolved project root;
- resolved database URL only for stages that need it;
- source-family identity and structured verification statistics.

Expose typed stage services for parse/normalize, spatial sampling, validation,
feature building, and persistence. Each service accepts the context/current
snapshot, returns a typed stage result plus updated snapshot, and performs no
stdout parsing. Standalone CLIs create one context, call the same service, and
serialize its result. Remove `_run_cli_stage` after all orchestration callers
use the service boundary.

Do not create another HTTP service, process manager, Airflow DAG, or scheduler.
The Python process remains the local batch owner.

### Effective-stage discovery and reuse

At the start of resume, load state once. For each stage:

1. select the effective immediate upstream event from the snapshot;
2. verify its effective lineage through the shared session;
3. reuse an existing current producer/fingerprint/upstream boundary;
4. otherwise create a new versioned derived boundary if the ledger permits it;
5. append through snapshot-aware append and carry the returned state forward;
6. stop on partial raw coverage or quarantine;
7. never select a directory merely because its version string sorts highest.

No stage may independently create another store/session and repeat verification
inside one `weather-ingest` call.

### Fresh contract

`weather-ingest fresh` must:

1. require explicit live-network acknowledgement and exactly one run-selection
   mode;
2. validate usage policy and the already migrated SQLite schema before payload
   GETs;
3. plan inventory and enforce an explicit reviewed byte cap;
4. bind the site-config SHA, sampling-policy SHA, and crop-selection version
   into the acquisition identity used by the duplicate gate;
5. run the duplicate-acquisition gate before payload GETs;
6. create one run UUID and immutable raw boundary;
7. stop terminally on partial coverage;
8. create one shared context/session after collection;
9. execute the same offline services used by resume;
10. persist the complete graph atomically;
11. return one structured result with stage dispositions, artifact references,
    database disposition, network status, and verification summary.

An exact succeeded acquisition may return `already_succeeded` after inventory
metadata checks and before payload GETs. Do not silently create another run.
An otherwise identical provider request with a different site/policy/crop
identity is not the same acquisition. It requires a new run or a separately
designed future raw-reuse workflow; S10 must not silently reuse the old compact
or persisted graph.

### Resume contract

`weather-ingest resume --run-key` must expose no live-network option and must
not instantiate or call a transport. Importing source contracts is acceptable;
constructing a network client or issuing inventory/payload requests is not.

Resume must support:

- continuation from a complete raw boundary;
- reuse of current matching derived boundaries;
- legal versioned supersession before terminal persistence;
- stop on partial raw coverage or validation quarantine;
- retry after persistence failure;
- exact persisted-run revalidation with unchanged rows/timestamps;
- restoration of the same immutable graph into another freshly migrated empty
  SQLite database without source access.

Restoring another database does not supersede or append another terminal ledger
event to the source run. The original terminal persistence evidence remains the
run boundary. A database-specific restoration receipt may be written/reused as
a small operation artifact or returned as structured output, but it must not
rewrite the original receipt, alter source facts, or create a second terminal
state event.

### Exit and failure semantics

Retain stable, machine-readable distinctions for:

- `inserted`;
- `revalidated_no_op`;
- `recovered_committed_write`;
- `already_succeeded`;
- `incomplete_coverage`;
- `quarantined`;
- immutable conflict;
- schema/configuration/integrity/operational failure.

Quarantine and incomplete coverage are not successful persistence. A conflict
never overwrites. A failed stage must not emit a complete ledger event.

## Phase 4 bounded live acceptance

No successful fresh current-catalogue run exists yet. Do not mark T-018 or S10
complete from unit/synthetic tests alone.

After Phases 0--3 are implemented:

1. inspect the chosen local date/cycle inventory without payload download;
2. record the exact planned fields, valid window, range count, expected bytes,
   catalogue identity, and reviewed `--maximum-total-mib` cap;
3. confirm adequate free disk space for raw plus compact outputs;
4. run one explicitly authorized `weather-ingest fresh` command;
5. record run key, cycle, target date, stage versions, durations, verification
   counters, artifact sizes, validation/quality counts, and SQLite table counts;
6. inspect that no parser/normalizer global arrays or duplicate identity arrays
   were written;
7. rerun `weather-ingest resume` against the same database and prove exact
   no-op, unchanged counts, and unchanged immutable timestamps;
8. migrate a second empty temporary SQLite database and resume into it with a
   transport-construction spy/disabled network, proving full graph restoration;
9. run `weather-artifacts audit --scope effective` successfully;
10. report all validation commands and any remaining limitation honestly.

The full-history audit of old superseded multi-GiB evidence is optional
maintenance and not part of the live completion gate. Do not delete the new
raw run after acceptance.

## Implementation sequence and planned commits

Keep commits ticket-prefixed, independently reviewable, and free of raw data,
local databases, generated retained artifacts, and unrelated user changes.
Inspect staged and unstaged diffs before every commit.

### Commit 1 — `T-018 defer ERA5 ingestion beyond T-018`

- add the DEC-032 supersession and preserve DEC-031 source roles;
- update tasks, handoff, architecture, and README claims;
- create the future T-038 ERA5 task;
- keep T-018 in progress and preserve future-compatible contracts/schema;
- include this completed owner-reviewed S10 plan if it is still uncommitted;
- do not include the current user-owned S07/S08 plan deletions unless the owner
  explicitly scopes them into the commit.

### Commit 2 — `T-018 separate ledger and artifact verification`

- add `RunStateSnapshot` and metadata-only ledger loading;
- hash event bytes once and remove implicit evidence traversal;
- implement effective-stage selection and snapshot-aware append;
- add explicit effective/all-history audit modes;
- cover chain tampering, supersession, terminal, concurrency, and audit tests.

### Commit 3 — `T-018 cache weather artifact verification`

- add the command-scoped `ArtifactVerificationSession`;
- cache verified references, parsed manifests, boundaries, and compact matrices;
- implement stat-based invalidation and complete-identity cache keys;
- eliminate repeated read/verify call sites and just-written rereads;
- add atomic temporary publication and verification counters;
- prove one raw/effective-file hash pass per top-level operation.

### Commit 4 — `T-018 define compact GFS grid artifacts`

- add versioned compact descriptor and matrix-slice contracts;
- centralize deterministic footprint/crop planning;
- add canonical selection fingerprinting;
- add consolidated matrix and packed-mask readers/writers;
- cover geometry, index translation, descriptor, and corruption cases;
- preserve legacy contract readers.

### Commit 5 — `T-018 crop GFS parser outputs`

- bump parser producer and artifact schema versions;
- retain full-message validation in transient memory;
- persist only compact native values and packed selected-node missing evidence;
- compact model-orography evidence;
- publish consolidated immutable parser artifacts;
- add parser parity, sentinel, interruption, and storage-bound tests.

### Commit 6 — `T-018 normalize and sample compact GFS grids`

- bump normalizer and spatial producer/artifact versions;
- reuse parser matrix slices for identity normalizations;
- consolidate only transformed/derived canonical rows;
- translate global footprint nodes to local crop indexes;
- retain existing point, radius, terrain, interval, and provenance semantics;
- add normalizer/spatial parity and missing-propagation tests.

### Commit 7 — `T-018 unify weather stage orchestration`

- introduce shared run context and typed stage service functions;
- make standalone CLIs thin adapters over those services;
- remove CLI stdout capture/JSON parsing from the pipeline;
- share one state snapshot and verification session across fresh/resume;
- preserve exit/disposition semantics and strict zero-network resume.

### Commit 8 — `T-018 verify bounded GFS ingestion`

- run the reviewed bounded current-catalogue fresh command;
- prove same-database no-op and second-database offline restoration;
- record measured storage, verification, duration, quality, and table counts;
- update tasks/handoff/README with only verified commands and results;
- mark T-018 complete only if every gate in this plan passes.

Smaller commits may split a mechanical boundary. Preserve the phase order and
do not mix artifact deletion, ERA5 implementation, Airflow, or unrelated
feature/model/schema work into these commits.

## Definition of done for S10 and T-018

S10 is complete only when:

- DEC-032 timing/ownership is superseded and every source-of-truth document
  consistently defers ERA5 to T-038 without weakening its separate reanalysis
  role;
- T-018 remains GFS-only in executable behavior while schema/contracts retain
  honest future ERA5 compatibility;
- operational ledger loading validates its event chain without opening every
  evidence boundary;
- only the effective lineage is verified during normal commands, while an
  explicit all-history audit remains available;
- one command-scoped session prevents repeated hashing/parsing/loading and
  detects changed files conservatively;
- full SHA-256 integrity remains mandatory for every trusted effective file;
- one compact top-level resume hashes raw payload bytes no more than once;
- no new GFS parser or normalizer boundary persists a full global numeric grid
  or full global missing mask;
- the crop is derived deterministically from reviewed configuration, policy,
  and verified native geometry;
- every required bilinear and radius node is present;
- compact native values and sentinel evidence are lossless;
- identity normalizations reuse immutable parser storage;
- transformed and derived values operate only on compact matrices;
- spatial sampling retains global node identities and unchanged mathematics;
- legacy artifacts remain readable and untouched;
- no new dependency or SQLite schema/column is introduced;
- the artifact size regression gate passes;
- actual storage measurements and limitations are documented honestly;
- stage CLIs and end-to-end orchestration call the same typed services and share
  one state/verification context;
- resume cannot construct or call transport;
- one new bounded current-catalogue GFS fresh run reaches SQLite successfully;
- exact same-database resume is a timestamp-preserving no-op;
- offline resume restores the graph into another freshly migrated empty
  database with zero source requests;
- the final diff contains no raw data, local database, generated run artifacts,
  unrelated feature/model work, or unapproved user changes;
- tasks, handoff, decisions, architecture, and command documentation reflect
  the verified end state;
- no ERA5 implementation, retention deletion, partial hashes, Airflow, or
  unrelated user change is included.

Only after all of these conditions and the validation commands pass may T-018
move from `In Progress` to `Done` or the repository's equivalent completed
status. ERA5 remains open as T-038 rather than hidden unfinished T-018 work.
