# T-020 XCContest sub-100 km ingestion implementation plan

## 1. Purpose

This plan covers only the XCContest flight-ingestion changes required inside
T-020 so the existing pipeline can collect, validate, reconcile, and persist
flights from `0` through `2000` scored kilometres for the seven configured
Bulgarian locations.

The immediate reason is downstream label evidence. A confirmed flight below
100 km can prove that pilots were active at a site on a date even when nobody
reached a 100/200/300 km threshold. This ingestion change supplies that
evidence. Building the joined weather dataset and calculating labels remain
separate T-020 implementation steps and are outside this plan.

This work belongs to T-020. It must not create a separate backlog ticket.

## 2. Existing behavior that must be preserved

The implemented collector is deliberately optimized for complete discovery of
100+ km records:

1. it opens the Bulgarian solo-paraglider (`FAI3`) season view ordered by
   distance descending;
2. if the first page can hide qualifying rows, it partitions by the exact
   `CCC`, `EN-D`, `EN-C`, `EN-B`, and `EN-A` classes;
3. if a class is still saturated, it partitions by source-offered date;
4. if a class/date view is still saturated, it records additional first-page
   views sorted by pilot, points, and duration in both directions;
5. it deduplicates by the stable XCContest source-flight identity;
6. parsing, validation, mapping review, reconciliation, and transactional
   SQLite persistence run from immutable artifacts.

After the initial source-default discovery capture, that threshold-first phase
runs unchanged and keeps its current meaning. The new activity phase supplements
it; it must not reduce 100+ recall or silently reinterpret old manifests.

The existing command already accepts one or more seasons:

```powershell
uv run --project services/ml xccontest-collect --season 2025
```

`--season` remains the public time-scope option. This plan does not add
`--date`, date-range, or all-dates command arguments.

## 3. Locked behavior

### 3.1 Distance domain

- Collector observations, parser records, validator records, and
  `flight_records.scored_distance_km` accept finite values in the inclusive
  range `0 <= distance_km <= 2000`.
- Negative values, non-finite values, missing values, and values above 2000 km
  remain invalid.
- Thresholds remain inclusive: `100+` means `>= 100`, and similarly for 200
  and 300 km.
- A stored `0 km` row is retained as source evidence but does not by itself
  prove meaningful flying activity. The later label builder must require a
  positive distance when it uses a flight as activity evidence.

### 3.2 Collection priorities

Each requested season is collected in this order:

1. capture the parent solo-PG season view in source-default order before any
   explicit sort;
2. run the existing threshold-first 100+ strategy, beginning with distance
   descending;
3. enumerate the dates offered by XCContest for that season;
4. collect all-distance activity views for every offered date, again capturing
   each default view before its explicit sorts;
5. deduplicate observations across season, default, category, date, and sorted
   views;
6. continue through the existing offline stages and persistence boundary.

The collector stays sequential and keeps the current source pacing and
fail-closed `--max-views` limit. Seasons supplied through repeated `--season`
arguments are also processed sequentially.

### 3.3 Source-default view comes first

For every date and category scope in the activity phase, capture the source's
default list view before applying any explicit sort. This can expose stable
flight IDs that are absent from the first page of another ordering.

"Default" has a strict technical meaning:

- navigate to a canonical list URL or reset the visible controls so no sort
  parameter or previous sort state is carried into the view;
- do not click a sortable column before capturing it;
- record the scope as `sort_mode = source_default`, with no invented sort key
  or direction;
- validate the resulting filters and page identity just like a sorted view.

The source-default order is a discovery aid. Because its order is not a stable
contract, it never proves that a saturated scope is complete.

### 3.4 Sorted views after the default view

After the source-default capture, collect explicit sort views in this order:

1. distance descending;
2. distance ascending;
3. pilot descending and ascending;
4. points descending and ascending;
5. duration descending and ascending.

Distance descending remains the authoritative saturation check. The other
sorts are rescue views that improve discovery when only page one is visible.
Repeated IDs are expected and are reconciled by the existing source-flight
identity rules.

### 3.5 Internal date traversal, unchanged CLI

Date traversal is an internal collector strategy, not a new command feature.
For every requested season, the browser adapter reads the dates exposed by the
XCContest date filter and processes them in deterministic chronological order.
The user continues to request a season only.

Why dates are still needed internally: a full season has far more rows than
one visible page. A daily scope is much more likely to expose all activity rows,
including short flights. Removing date partitioning would leave most sub-100
records permanently hidden behind the source's page-one limit.

The manifest stores the chosen source date value and normalized local date for
audit and offline replay. It does not expose new date-selection CLI options.

### 3.6 Category fallback

For one date:

1. capture solo-PG (`FAI3`) in source-default order;
2. capture its explicit sort sequence;
3. if distance-descending still has a next page, repeat the same
   default-then-sorted sequence for `CCC`, `EN-D`, `EN-C`, `EN-B`, and
   `EN-A`;
4. union all stable source-flight IDs.

Exact classes are a partitioning fallback. They do not change the accepted
product scope, which remains solo paraglider flights. If XCContest exposes an
unclassified solo-PG row that appears only in the parent `FAI3` view, retain it.

## 4. Completeness and partial results

The pipeline cannot guarantee that every sub-100 km flight was discovered when
an all-distance class/date view still has a next page after all reviewed sorts.
It must represent that limitation explicitly.

Per season/date/category, record:

- whether the source-default view was captured;
- every explicit sort attempted;
- whether distance-descending reported a next page;
- rows observed and distinct source-flight IDs;
- duplicate observations across views;
- `complete`, `partial_saturated`, `empty`, or `failed` status;
- the reason for a partial or failed status.

A partial scope may still persist the valid flights it found. It may not report
complete all-distance coverage. Later dataset logic may use an observed short
flight as positive activity evidence, but it must consult the completeness and
mapping evidence before treating an absent threshold flight as a known
negative.

Empty means a successfully loaded and verified view containing no rows. A
failed or unverified view is not empty.

## 5. Data-contract changes

### 5.1 Collector scope

Change `FlightListScope` so sort state is explicit:

- `sort_key` and `sort_direction` are both absent for `source_default`;
- both are present for an explicit sorted view;
- mixed states are rejected;
- artifact filenames and manifests use a stable `source-default` token.

Do not model the source-default view as distance order. That would fabricate a
provider guarantee and make saturation evidence incorrect.

### 5.2 Distance constants

Separate two concepts currently represented by `MIN_DISTANCE_KM = 100`:

- accepted storage/parser minimum: `0 km`;
- threshold-coverage distance: `100 km`.

The threshold-first saturation predicate continues to compare the last
distance with 100 km. The activity collector's saturation state depends on
`has_next_page`, not on whether the last row is above 100 km.

### 5.3 Manifest version

Publish a new manifest schema version because old manifests require a sort and
describe only 100+ qualifying observations. The new version must preserve:

- acquisition purpose (`threshold_100` or `all_distance_activity`);
- season, country, source date, and category;
- sort mode and optional sort key/direction;
- page-next evidence and scope completeness;
- total and distinct observation counts;
- count below 100 km and count at/above 100 km;
- immutable artifact path, hash, and retrieval time;
- unresolved/failed scope summaries.

Offline readers must reject an unknown version. Existing historical manifests
remain readable under their old 100+ contract; they are not retroactively
claimed to contain sub-100 flights.

### 5.4 Parser, validator, reconciliation, and mapping

- Parser: accept finite distances from 0 through 2000 km and keep existing
  source identity, URL, timestamp, route, and provenance validation.
- Validator: apply the same range and continue quarantining malformed records.
- Reconciliation: keep stable source-flight deduplication and conflict rules;
  the same flight seen in several views remains one canonical record.
- Mapping: keep the existing approved/provisional/rejected review workflow and
  seven configured site catchments. More short flights may produce more
  proposals or run-local rejections; no new mapping-exclusion table is added.
- Persistence: accept the wider distance domain without changing source IDs,
  mapping foreign keys, ingestion-run lineage, or transaction rules.

## 6. Database migration

Create one Drizzle-owned migration that changes only the existing check:

```sql
CHECK (scored_distance_km BETWEEN 0 AND 2000)
```

Update the matching Drizzle schema declaration and migration tests. No new
table, column, or index is required for this ingestion change. The existing
`source_site_mappings`, `flight_ingestion_runs`, and artifact/run reports retain
their current responsibilities.

Why no exclusion table: a durable exclusion registry could avoid repeatedly
reviewing known out-of-scope launches, but it is an optimization for mapping
operations rather than a requirement for collecting and storing sub-100
flights. The existing review and quarantine outputs are sufficient for T-020.

The migration must prove:

- `0`, a representative sub-100 value, `100`, and `2000` are accepted;
- a negative value and a value above `2000` are rejected;
- existing 100+ rows, foreign keys, unique source identity, and indexes remain
  valid;
- a fresh database and an already-migrated database both reach the same schema.

## 7. Pipeline and command behavior

### 7.1 Collector command

Keep the existing command shape and options. Do not add date arguments. Update
help text to say that a requested season performs threshold-first collection
and then internally scans source-offered dates for all-distance activity.

One invocation may contain several repeated `--season` arguments, as today.
The implementation processes them sequentially and emits one run manifest.

### 7.2 Long-run recovery

A season-level activity scan can require many paced views. Extend the existing
checkpoint artifact so a failed or interrupted run records the last completed
season/date/category/sort scope and all completed artifact hashes. Recovery
must reuse only verified artifacts and continue from the first unfinished
scope without fetching completed views again.

If the existing command architecture cannot safely resume the live collection,
add a collector resume command keyed by `run_key`. This command is allowed as a
recovery mechanism; it must not introduce user-selected dates or bypass source
pacing and view caps.

### 7.3 Downstream stages

The existing parse, validate, mapping-review, reconcile, and persist commands
must accept the new manifest version and sub-100 rows. Offline replay must not
construct a browser or perform network access.

Persistence remains atomic for canonical database changes. Valid records from
a collector run with partial saturated coverage may be inserted, while the run
and manifest must preserve that partial state.

## 8. Test plan

### 8.1 Collector fixtures

Add deterministic rendered-HTML fixtures for:

- source-default view with IDs absent from every explicit sorted first page;
- quiet date whose parent PG view has no next page;
- busy date that requires exact category partitioning;
- class/date scope still saturated after every sort;
- empty verified date;
- failed/unverified date;
- the same flight repeated across default, category, and sort views;
- 0 km, sub-100, exactly 100, and 2000 km boundary rows.

### 8.2 Collector tests

Prove:

- default view is captured before any sort action;
- the browser does not carry a previous sort into `source_default`;
- source-offered dates are traversed internally in deterministic order;
- no date/range CLI option is introduced;
- the season source-default capture occurs before threshold sorting, and the
  threshold phase finishes before daily activity collection starts;
- category fallback and rescue-sort order match this plan;
- view cap and 30-second default pacing still fail closed;
- partial saturation is explicit and never reported as complete;
- checkpoints resume without refetching verified completed views.

### 8.3 Offline-stage tests

Prove:

- parser and validator accept the inclusive 0..2000 domain;
- negative, non-finite, missing, and over-2000 distances are quarantined;
- deduplication keeps one canonical flight across all views;
- conflict detection still rejects materially different records with the same
  source ID;
- existing approved mappings work unchanged for sub-100 records;
- rejected/ambiguous mappings remain outside canonical persistence;
- offline replay performs zero network/browser operations;
- old manifest versions retain their old interpretation.

### 8.4 Database tests

Run the fresh-file, migration-idempotence, constraint, relationship, and
reconciliation suites with the new range boundaries. Add an end-to-end fixture
that persists one approved sub-100 record and proves its ingestion-run lineage.

### 8.5 Bounded live acceptance

After all fixture and offline checks pass, run one owner-authorized headed
collection for one recent season under normal 30-second pacing and an explicit
view cap. Verify:

- a source-default artifact exists before sorted artifacts for a sampled date;
- at least one sub-100 flight is parsed;
- an approved in-scope sub-100 flight can be persisted;
- the manifest honestly reports complete or partial per-date coverage;
- the existing 100+ results are not reduced.

Do not start a multi-season backfill as part of acceptance.

## 9. Implementation order

1. Add/adjust fixtures for default order, sub-100 distances, saturation, and
   duplication.
2. Split storage minimum from the 100 km threshold constant.
3. Add the explicit `source_default` scope and browser reset/navigation logic.
4. Preserve the current threshold-first strategy.
5. Add internal source-date traversal and the default-then-sorted activity
   phase, followed by category fallback.
6. Version the artifacts, manifest, checkpoints, and completeness reports.
7. Widen parser and validator distance checks.
8. Update reconciliation and mapping fixtures without changing their business
   rules.
9. Add the single Drizzle check-constraint migration and schema/test updates.
10. Update offline readers and persistence for the new manifest version.
11. Document the unchanged season-based command and recovery behavior in the
    ML README.
12. Run focused Python tests, database tests, repository checks, and then the
    bounded headed acceptance.
13. Record the verified result and any remaining saturated scopes in the
    handoff.

## 10. Definition of done

This ingestion prerequisite is complete when:

- the public collection scope remains season-based;
- one source-default season view is captured before threshold sorting;
- threshold-first 100+ coverage finishes before the daily activity phase;
- every source-offered season date is scanned internally for activity;
- source-default order is captured before explicit sorts;
- valid 0..2000 km rows pass every stage and can be stored;
- no new database table is introduced;
- saturated or failed scopes remain explicit;
- offline replay remains network-free and deterministic;
- old manifest meaning is preserved;
- required Python, database, repository, and bounded live checks pass;
- documentation states that stored zero-distance rows are not sufficient
  activity evidence for later labels.

## 11. Out of scope for this plan

- building the T-020 joined flight/weather dataset;
- calculating positive, negative, or unknown site-day labels;
- fetching GFS for newly discovered dates;
- training the T-023 XC model;
- implementing cloudbase or overdevelopment calculations;
- adding a source-site exclusion table;
- changing the seven sites or their catchments;
- parallel collection, direct/private APIs, page-two bypasses, or automated
  evasion of XCContest controls.

The only downstream contract recorded here is that the future dataset builder
may consume persisted positive-distance sub-100 flights as activity evidence,
along with the manifest's collection status. It must not treat missing rows as
proof of a bad flying day.
