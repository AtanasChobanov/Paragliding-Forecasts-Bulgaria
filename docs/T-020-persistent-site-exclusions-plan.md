# T-020 persistent XCContest site-exclusion implementation plan

## 1. Status and objective

**Status:** Implemented in the current T-020 working tree and pending the ticket commit. The migration, runtime behavior, CLI, and tests described here are present; this document remains the durable implementation contract.

The objective is to persist one reviewed negative decision for a stable
XCContest launch identity and reuse it in later runs. A previously reviewed
out-of-scope `source_site_token` or `source_takeoff_id` should be rejected
automatically instead of creating the same mapping proposal every season.

This is an operational optimization of the T-020 site-mapping prerequisite. It
does not create negative flight labels, map an excluded identity to a canonical
site, or change the seven-site product scope.

## 2. Current behavior and concrete migration input

`source_site_mappings` stores only positive `provisional`, `approved`, or
`retired` relations to a canonical `sites` row. A human `rejected` decision is
currently counted and retained only in the ignored run-local JSONL file. Later
runs therefore propose the same unknown identity again.

The current run
`d577156f-7f73-4e62-81ad-eb6881715739` has 26 reviewed rejected decisions. All
26 use `key_type = source_site_token` and retain their immutable proposal
identity and context. They already have the only reviewer input required for a
durable exclusion: `decision = rejected`. No reference, reviewer identity, or
review timestamp is added to the decisions JSONL; applying it records the
technical insertion time and may retain optional existing `notes`.

## 3. Scope policy

### 3.1 Eligible persistent exclusions

Persist only exact, manually verified stable source identities:

- `source_site_token`;
- `source_takeoff_id`.

The decision must affirm that the exact source identity was checked and is
outside the currently supported canonical site scope. One decision excludes
only its exact `(source_id, key_type, key_value)` identity. Do not decode tokens,
infer related identifiers, or fan one decision out to another token/ID.

When a candidate exposes both a token and a takeoff ID, proposal generation
should emit independently reviewable stable-key evidence. Rejecting one key
must not silently reject the other.

### 3.2 Cases that must not become reusable exclusions

| Review case | Persistent auto-rejection? | Reason |
| --- | --- | --- |
| Exact source token verified as another location | Yes | Stable opaque identity and explicit human evidence. |
| Exact source takeoff ID verified as another location | Yes | Stable source identity with the same safety properties as a token. |
| `normalized_name` only | No | Names are reused, renamed, translated, and too weak for a durable negative identity. |
| Point outside all configured catchments | No new row | Already deterministically auto-rejected; a database row adds no benefit and can become stale when sites change. |
| Point inside more than one catchment | No | This is unresolved geometry, not proof that the launch is out of scope. |
| Point inside one catchment but country conflicts | No | Contradictory evidence requires review; it is not a stable negative identity. |
| Approved token/ID contradicted by coordinates | No | Resolve or retire the positive mapping explicitly; do not create a competing exclusion. |
| Unknown token/ID with no independent verification | No | Absence of evidence is not evidence that the launch is outside the supported sites. |

### 3.3 Applicability and new evidence

An exclusion is automatically applicable only when all of these hold:

1. source, key type, and key value match exactly;
2. no active approved/provisional mapping matches any candidate evidence;
3. the candidate has no new valid coordinate resolving inside or ambiguously
   across the current catchments;
4. no other stable candidate identity points to an active mapping.

If fresh evidence conflicts with an exclusion, produce `review_required` with a
specific `mapping_exclusion_conflict` reason. Never let an old negative decision
override stronger new coordinate or approved-mapping evidence.

## 4. Database design

Add one Drizzle-owned SQLite `STRICT` table named `source_site_exclusions`.

| Column | SQLite type | Null | Meaning |
| --- | --- | --- | --- |
| `id` | `INTEGER PRIMARY KEY` | No | Internal exclusion identity. |
| `source_id` | `INTEGER` | No | FK to `flight_sources.id`, `ON DELETE RESTRICT`. |
| `key_type` | `TEXT` | No | `source_site_token` or `source_takeoff_id`. |
| `key_value` | `TEXT` | No | Exact opaque source value; trimmed non-empty string. |
| `origin_run_key` | `TEXT` | No | Run whose immutable proposal was reviewed; intentionally not an FK because mapping review precedes ingestion-run persistence. |
| `origin_proposal_id` | `TEXT` | No | Exact proposal identity from the reviewed artifact. |
| `notes` | `TEXT` | Yes | Optional rationale without pilot-identifying or secret data. |
| `status` | `TEXT` | No | `active` or `retired`; default `active`. |
| `created_at_utc` | `TEXT` | No | Explicit insertion timestamp. |
| `retired_at_utc` | `TEXT` | Yes | Required only for retired rows. |
| `retirement_reason` | `TEXT` | Yes | Required short audit reason for retirement. |

Do not add `site_id`: an exclusion asserts that the identity maps to none of the
sites in the reviewed scope. It must not pretend to be a negative relationship
to one particular site. Do not link `origin_run_key` to
`flight_ingestion_runs`: the rejection is applied before that canonical run row
exists.

### 4.1 Constraints and indexes

Add database checks for:

- allowed key types and status values;
- non-empty trimmed key value, run key, proposal ID, and retirement reason;
- UTC timestamp shape matching the repository timestamp convention;
- `active` rows having all retirement fields null;
- `retired` rows having both retirement fields non-null.

Add:

- a partial unique index on `(source_id, key_type, key_value)` where
  `status = 'active'`;
- a lookup index on `(source_id, key_type, key_value, status)`;
- an audit index on `(origin_run_key, origin_proposal_id)`.

SQLite cannot express the cross-table conflict as a `CHECK`. Both the positive
mapping apply path and exclusion apply path must check within their write
transaction that an active positive mapping and applicable active exclusion do
not coexist for the same stable identity. Migration and command tests must
prove both directions fail closed.

## 5. Canonical site-scope changes

Do not add a new site-scope hash just for this table. The pipeline already
creates `mapping_snapshot_sha256` values for artifact reuse; extend that existing
snapshot to include canonical site/catchment fields and active exclusions so
validation cannot reuse an output after either changes.

Changing canonical sites, coordinates, country, radius, or active state is a
separate deliberate configuration change. Its operator workflow must list all
active exclusions for review and explicitly retire any identity that could now
belong to the changed scope. A stale exclusion is never silently rewritten or
deleted. Fresh in-scope/ambiguous coordinate evidence still wins immediately and
creates a human-review conflict even before that audit occurs.

## 6. Decision artifact contract

Bump the mapping artifact contract from v3 to v4. A rejected decision is
eligible for persistence only when it:

- matches one immutable proposal by `proposal_id`;
- repeats the proposal's `source`, `key_type`, exact key value/point shape, and
  relevant evidence unchanged;
- has `decision = rejected`;
- uses an eligible stable key type;

No additional JSONL fields are required for an eligible rejection: the exact
proposal identity plus `decision = rejected` remains the human workflow. The
apply command records `created_at_utc`; copied `notes` remain optional.

Rejected non-eligible proposals remain run-local decisions and continue to
unblock only their matching run. Report them as `rejected_not_persisted`; do not
silently coerce them into database exclusions.

Proposal generation should expose every distinct stable token/takeoff ID as an
independent review identity while retaining linked sample-flight and display
context. This avoids the current priority rule hiding a token whenever a
takeoff ID is present.

## 7. Code integration

### 7.1 Catalog and snapshots

- Add `SourceSiteExclusion` to the Python mapping catalog.
- Load all exclusions read-only with sites and positive mappings.
- Extend the existing `mapping_snapshot_sha256` payload to cover positive
  mappings, exclusions, and current site/catchment fields; do not introduce a
  second snapshot or persist any hash in `source_site_exclusions`.
- Bump output versions/directories so old validation output is never reused
  under the new semantics.

### 7.2 Applying reviewed decisions

Extend `xccontest-site-mappings apply` in its existing `BEGIN IMMEDIATE`
transaction:

1. load the sibling immutable proposals and verify every decision against it;
2. validate the whole decision file before writing;
3. apply approved/provisional decisions as today, after checking for an active
   applicable exclusion conflict;
4. for an eligible rejected decision, insert or idempotently reuse the exact
   `source_site_exclusions` row with its proposal/run lineage and optional notes;
5. retain non-eligible rejections only in the run artifact;
6. roll back the entire file on conflicting duplicate decisions, positive/
   negative identity conflict, or database failure;
7. report `exclusions_inserted`, `exclusions_unchanged`,
   `rejected_not_persisted`, and ordinary mapping counts separately.

Add an explicit retirement command. It must update only one active exclusion by
ID, require a short `retirement_reason`, record `retired_at_utc`, and refuse a
no-op or already-retired target. Do not instruct operators to edit SQLite
manually.

### 7.3 Proposal and validation behavior

Before writing a residual proposal:

- resolve positive mappings and fresh coordinate evidence first;
- apply an exact active exclusion only when the applicability rules in section
  3.3 pass;
- omit safely excluded identities from human proposals;
- keep configuration-change audit findings and evidence conflicts visible with
  explicit review reasons.

Validation writes safely excluded candidates to quarantine with:

- `reason = known_source_site_exclusion`;
- `mapping_disposition = persisted_rejection`;
- `source_site_exclusion_id` and snapshot lineage.

These records create no canonical flight and do not pause persistence. Add
separate report counts for persisted exclusions, run-local reviewed rejections,
outside-catchment automatic rejections, and unresolved human review.

The pipeline review gate must treat `persisted_rejection` as non-actionable,
but `mapping_exclusion_conflict`, ambiguity, country mismatch, and coordinate
conflict remain actionable.

## 8. Existing 26-token review batch

Do not run the current file through the old apply path if the goal is durable
reuse: the existing implementation merely increments `rejected` and writes no
database state.

After this plan is implemented:

1. keep the 26 exact proposal IDs, tokens, and copied evidence unchanged;
2. run the upgraded apply command once without changing their minimal rejected
   decision fields;
3. verify 26 inserted/unchanged active exclusions;
4. rerun `xccontest-ingest resume` so validation is rebuilt under the extended
   existing mapping snapshot;
5. prove a fixture/new run containing one of those tokens produces no residual
   mapping proposal and is nonblockingly rejected.

Do not automatically backfill older v2 point/name rejections. They lack the new
exact proposal identity and include key types that are deliberately ineligible.

## 9. Migration and implementation sequence

1. Add failing schema/migration tests for the exact table, constraints,
   indexes, fresh migration, repeated migration, and conflict rules.
2. Add the Drizzle schema declaration and one generated, reviewed migration;
   update database snapshots and package documentation.
3. Add exclusion catalog models and extend the existing mapping snapshot tests.
4. Upgrade proposal/decision artifacts to v4 without adding new rejection input
   fields.
5. Persist eligible rejected decisions transactionally and add audited
   retirement behavior.
6. Integrate known exclusions into proposal generation, validation, pipeline
   gating, and versioned reports.
7. Add an acceptance fixture based on a sanitized token; do not commit the real
   26-token decision file or source evidence.
8. Update `services/ml/README.md`'s mapping-proposal/review workflow with the
   v4 behavior: `rejected` remains minimal, eligible token/takeoff-ID rejections
   become persistent exclusions, and all other rejection types stay run-local.
   Update decisions, handoff, and command help at the same time.
9. Only then apply the owner's local 26-token review batch unchanged.

## 10. Test matrix

Cover at minimum:

- exact token and takeoff-ID exclusion insertion and idempotent replay;
- identical key under another source does not match;
- normalized-name and source-point rejection stays run-local;
- unchanged scope reuses an exclusion;
- changed site/radius/coordinate changes the existing mapping snapshot and
  requires an explicit exclusion-scope audit;
- excluded key with no coordinates is nonblockingly rejected;
- excluded key plus unique/ambiguous coordinate is review-required;
- excluded key plus another approved stable key is review-required;
- approved/provisional mapping conflicts with exclusion in both apply orders;
- decision/proposal evidence mismatch rolls back all writes;
- retirement disables future matching without deleting audit history;
- composite snapshot change prevents stale validator reuse;
- fresh and already-migrated databases converge on the same schema;
- pipeline resume remains network-free.

Run the database tests, focused XCContest tests, complete ML suite, TypeScript
typecheck/lint/format/build/test checks affected by the schema, `db:check`, and
`repo:check`. No live collection is required to implement this optimization.

## 11. Planned commits

1. `T-020 add persistent site exclusion schema`
2. `T-020 persist reviewed stable-key rejections`
3. `T-020 apply known exclusions during site resolution`
4. `T-020 document persistent site exclusion workflow` — update
   `services/ml/README.md`, decisions, handoff, and command help with the v4
   proposal/review behavior.

Do not combine the schema migration with unrelated ingestion or joined-dataset
work. Do not commit local decisions, raw XCContest data, or reviewer evidence.

## 12. Definition of done

- a reviewed stable token/takeoff-ID rejection is stored once and reused;
- repeated known exclusions create no human proposal and do not block approved
  records from the same run;
- weak, geographic, stale, and contradictory evidence still reaches human
  review;
- site-scope changes invalidate validation reuse and require an explicit
  exclusion-scope audit;
- positive mappings and exclusions cannot coexist silently;
- decisions retain proposal/run lineage and optional reviewer notes without
  requiring new review fields;
- retirement is explicit and audited;
- old artifacts remain readable under their old run-local semantics;
- the current 26-token batch can be applied with its existing rejected
  decisions;
- all relevant local checks pass and no live source call is required.

## 13. Out of scope

- inferring or decoding opaque XCContest tokens;
- treating a rejected site identity as a negative training label;
- automatically excluding normalized names or ambiguous/conflicting points;
- changing canonical sites or catchment radii;
- importing historical local decisions without an exact current token/ID
  proposal identity;
- running the live collector.
