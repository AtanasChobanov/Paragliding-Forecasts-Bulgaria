# T-020 XCContest Activity Ingestion Implementation Plan

Status: **implementation-ready plan; documentation only**

Date: 2026-09-23

Owners: T-040 expands XCContest ingestion; T-020 consumes the accepted flight
records and coverage evidence.

Durable decisions: DEC-023 through DEC-030, DEC-055, and DEC-056.

## 1. Goal

Extend the XCContest pipeline so it can discover, normalize, review, and persist
positive-distance PG flights below 100 km for the seven canonical Bulgarian
locations. These records prove that some recorded flying activity occurred on a
site-day even when no 100/200/300 km threshold was reached.

The current 100+ strategy remains intact. Long-flight coverage and short-flight
activity have different purposes and must be separate collection profiles.

The later dataset must distinguish three states per site, local date, and
threshold:

- `positive`: an accepted mapped flight reached the threshold;
- `negative`: accepted activity exists and complete evidence proves that no
  in-scope flight reached the threshold;
- `unknown`: the evidence is insufficient.

A day without a published accepted flight is never a negative by itself.

## 2. Current constraints

The implementation must preserve these boundaries:

- `MIN_DISTANCE_KM = 100.0` currently controls saturation, manifest counters,
  parser validation, and the SQLite `flight_records` constraint.
- The collector never clicks pagination or constructs an undocumented offset
  URL.
- It starts with PG all classes, partitions saturated views through CCC, EN D,
  EN C, EN B, and EN A, and uses alternate visible sorts only as rescue views.
- Rescue views may find more IDs but cannot prove complete coverage.
- Source-changing UI operations are sequential and wait 30 seconds by default.
  There are no parallel tabs or automatic source retries.
- Raw fragments and manifests are immutable parser evidence.
- Only approved source-site mappings may create canonical flight records.
- XCContest source flight ID reconciles overlap between views and runs.
- Drizzle owns SQLite DDL and migrations; Python never migrates the database.
- Live work remains inside the approved low-volume rendered-UI authority.

## 3. Terms

- **Threshold profile:** existing collection whose completeness claim is
  limited to flights at or above 100 km.
- **Activity profile:** date-scoped collection that retains every observed
  positive-distance flight.
- **Saturated view:** XCContest reports a next page for the selected filter.
- **Complete coverage:** visible filters prove no matching row is hidden on a
  later page.
- **Best-effort evidence:** observed rows are valid, but saturation means other
  rows may be missing.
- **Activity evidence:** at least one accepted, approved-mapping,
  positive-distance flight for the site and `Europe/Sofia` local date.
- **Mapping-complete:** every threshold-capable source candidate that could
  belong to a target site has an approved mapping or reviewed out-of-scope
  decision.
- **Mature date:** collection occurred at least 16 local calendar days after
  the flight date. An earlier collection may prove a positive but not an
  absence, because uploads may arrive late.

## 4. Locked label contract

The collector records flights and coverage; it does not assign model labels.
T-020 derives them later.

Thresholds are inclusive:

| Target | Positive condition |
| --- | --- |
| 100+ km | maximum accepted site-day distance `>= 100` km |
| 200+ km | maximum accepted site-day distance `>= 200` km |
| 300+ km | maximum accepted site-day distance `>= 300` km |

For threshold T:

1. If an accepted mapped flight is `>= T`, the label is `positive`.
2. Otherwise the label is `negative` only when:
   - an accepted mapped flight with distance `> 0` exists for the same site and
     local date;
   - a finalized threshold or activity manifest proves complete coverage for
     source rows `>= T` on that date;
   - the coverage was collected after the 16-day maturity boundary;
   - all relevant mapping evidence is terminal.
3. Otherwise the label is `unknown`.

One accepted positive-distance flight is the MVP activity minimum. T-020 also
retains flight count, maximum distance, total distance, coverage state, and
mapping state so a later analysis can require two or more flights without
another source collection.

| Accepted site-day evidence | 100 | 200 | 300 |
| --- | ---: | ---: | ---: |
| max 78 km, mature complete coverage | 0 | 0 | 0 |
| max 157 km, mature complete coverage | 1 | 0 | 0 |
| max 240 km, mature complete coverage | 1 | 1 | 0 |
| max 330 km | 1 | 1 | 1 |
| no accepted mapped flight | unknown | unknown | unknown |
| max 78 km, unresolved threshold coverage | unknown | unknown | unknown |
| max 157 km, unresolved 200+ mapping | 1 | unknown | unknown |

Incomplete activity coverage can reduce the number of discovered site-days. It
cannot manufacture a negative.

## 5. Collection profiles

### 5.1 `threshold-100`

Keep the current behavior and name its purpose explicitly:

1. Select season, country, PG all classes, distance descending.
2. If no next page exists, or the last distance is below 100 km, 100+ coverage
   is complete.
3. Otherwise partition through the five exact PG classes.
4. Partition a saturated exact class through all source-offered dates.
5. Capture rescue sorts for any saturated class/date.
6. Record every unresolved class/date.

This profile runs first for a season. It protects positive recall and supplies
the threshold-absence proof.

The new parser may recover incidental sub-100 rows already stored in old raw
threshold fragments. They are valid activity observations but do not expand the
old manifest's 100+ coverage claim.

### 5.2 `all-distance-activity`

For each requested source date:

1. Select PG all classes, exact date, distance descending.
2. Record the page and `has_next_page` even if it has zero rows.
3. If no next page exists, mark `complete_primary` and continue.
4. Otherwise select the same date for CCC, EN D, EN C, EN B, and EN A,
   each distance descending.
5. If all exact-category pages have no next page, mark
   `complete_partitioned`. Their union is complete for supported solo PG.
6. For each still-saturated exact category:
   - mark `saturated_unresolved`;
   - capture distance ascending;
   - capture pilot, points, and duration in both directions;
   - union all observed source IDs;
   - keep the date `partial_best_effort`.

The original distance-descending view is not repeated. Seven rescue views are
added for a saturated category/date: distance ascending plus three other sorts
in both directions.

Rescue views improve recall at the list edges. They never make a partial date
complete because multiple first pages do not prove that all middle rows were
seen.

The collector never activates page 2, constructs pagination URLs, opens
parallel tabs, calls undocumented endpoints, or guesses completeness from row
count.

### 5.3 Date selection

The activity profile accepts exactly one selection mode:

- repeatable `--date YYYY-MM-DD`;
- `--date-from YYYY-MM-DD --date-to YYYY-MM-DD`; or
- `--all-available-dates`.

A season covers 1 October of the previous calendar year through 30 September of
the named year. Dates outside requested seasons fail before browser creation.

A range is intersected with rendered source dates. The manifest records
requested, offered, selected, and non-offered dates. A non-offered date is
`no_source_date` and remains unknown.

One command may process several dates, always sequentially. At 30-second pacing,
365 unsaturated dates require at least about three hours before category
splits. The CLI reports selected date count and minimum one-view workload before
collection.

### 5.4 Live collection resume

Add:

```powershell
uv run --env-file .env --project services/ml xccontest-ingest collect-resume --run-key <uuid> --policy-file data/local/xccontest-usage-policy.json
```

This differs from existing offline `xccontest-ingest resume`.

After each view and date, checkpoint:

- run key and immutable configuration;
- profile, seasons, countries, ordered dates, pacing, and view cap;
- captured views and hashes;
- date statuses and unresolved scopes;
- next date/view position;
- observation and distinct-ID counters;
- observed source control values.

`collect-resume` verifies the checkpoint and all artifacts, restores the exact
scope, and continues from the first unfinished view. It does not recapture or
overwrite completed views. Any configuration change is rejected. Source
challenge, navigation failure, or control drift remains a manual stop.

The final manifest is written once. A finalized partial run is parseable. A
failed run without a final manifest is not an offline parser input.

## 6. Command contract

Existing behavior remains the backward-compatible default, while operational
examples pass the profile explicitly:

```powershell
uv run --env-file .env --project services/ml xccontest-ingest fresh --season 2025 --collection-profile threshold-100 --policy-file data/local/xccontest-usage-policy.json
```

Activity example:

```powershell
uv run --env-file .env --project services/ml xccontest-ingest fresh --season 2025 --collection-profile all-distance-activity --date-from 2025-06-01 --date-to 2025-06-30 --policy-file data/local/xccontest-usage-policy.json
```

`xccontest-collect` gets the same profile/date arguments. The one-command
pipeline continues to parser, mapping proposal, validation, and persistence
after finalization.

Validation:

- date arguments are invalid for `threshold-100`;
- activity requires exactly one date mode;
- mutually exclusive modes fail before browser creation;
- `--max-views` remains a total fail-closed cap;
- faster-than-recommended pacing needs the existing acknowledgement;
- country scope still comes from all canonical sites;
- policy and authority gates remain mandatory.

## 7. Manifest and coverage contract

Create raw manifest schema v4 and keep v1-v3 readers.

V4 separates lifecycle from coverage:

- `lifecycle_status: finalized`;
- `coverage_status: complete|partial`;
- `collection_profile: threshold-100|all-distance-activity`;
- record range `0 < distance_km <= 2000`;
- threshold profile floor `100`;
- requested/offered/selected/completed/non-offered dates;
- per-date status and unresolved category scopes;
- per-view `has_next_page`, row count, first/last ID and distance, selected
  controls, sort, retrieval time, and artifact path/hash or explicit empty-view
  evidence;
- total, distinct, repeated, below-100, and at-or-above-100 counts;
- existing pacing and permission provenance.

Do not overload v2/v3 `qualifying_row_observation_count`. V4 uses explicit
`below_100_row_observation_count` and
`at_or_above_100_row_observation_count`. Compatibility readers retain the old
meaning.

Coverage remains immutable artifact evidence. Do not add a duplicate coverage
table. `flight_ingestion_runs` already stores manifest path and SHA-256; T-020
verifies that reference. Mapping completeness additionally uses the hashed
parser, mapping-review, validation, quarantine, and persistence-receipt
artifacts for the same run; the joined manifest records those paths and hashes.

A finalized partial v4 run may persist observed records while its gaps remain
explicit. The new reader may also parse rows from a finalized old v3
`incomplete` manifest after verifying unresolved scopes. No partial scope may
prove absence.

T-020 resolves threshold coverage deterministically:

1. Convert the Sofia local date to its XCContest season.
2. Load only finalized manifests whose database run row matches the stored path
   and SHA-256.
3. A complete activity date covers all three thresholds.
4. A complete `threshold-100` season/country target covers all three thresholds
   for its dates.
5. For a partial threshold manifest, a date is covered only when none of its
   unresolved category/date scopes can contain that date. An unresolved
   season-wide category covers every date and therefore blocks all of them.
6. A complete proof from one manifest wins over partial evidence from another;
   partial manifests can never erase a complete proof.
7. The proof is eligible for a negative only after the maturity boundary.

The label audit records every manifest/run ID used for that decision.

## 8. Parser changes

Create a new parser output version; do not overwrite parser-v2.

1. Separate coverage threshold from record validity.
2. Accept finite `0 < distance <= 2000` km.
3. Reject zero, negative, non-finite, and over-2000 values explicitly.
4. Parse all valid rows from both profiles, including incidental old sub-100
   rows.
5. Preserve artifact references and collection profile.
6. Derive `takeoff_local_date` in `Europe/Sofia` while retaining
   `takeoff_at_utc`.
7. Compare derived date to a date-scoped artifact's request. Mismatch is
   quarantined and invalidates that date's coverage.
8. Keep source-ID deduplication and conflicting-variant output.
9. Replace `threshold_exclusions` with explicit invalid-distance counters.

A headed source check must confirm that the XCContest date control matches the
displayed Bulgarian flight date. Until it passes, date collection is inspectable
but cannot certify negatives.

## 9. Site mapping

Sub-100 collection exposes many Bulgarian launches outside the seven sites. Do
not force them into a target and do not review the same exclusion every run.

Add Drizzle table `source_site_mapping_exclusions` with source ID, the existing
mapping evidence key shapes, normalized key/rounded point, optional display
name, reason, verification reference, reviewed time, and canonical site-scope
hash.

An exclusion only means the evidence is outside the current seven-site scope.
It cannot create a flight. If site aliases, coordinates, or catchments change,
old-scope exclusions do not apply automatically.

Review flow:

1. Resolve approved mappings first.
2. A current-scope exclusion becomes terminal
   `reviewed_out_of_scope` quarantine.
3. Group unknown proposals by evidence key and include affected flight IDs,
   dates, count, and distance range.
4. Keep approved and provisional behavior.
5. Persist reviewed out-of-scope decisions in the exclusion table in the same
   transaction.
6. Leave ambiguous/unreviewed evidence actionable.
7. `--persist-approved-only` may persist known records but cannot declare
   mapping coverage complete.

For a negative, every raw candidate at/above the threshold that could affect
the site must be approved or excluded. An unresolved candidate blocks sites
suggested by its coordinates/catchment. Without usable location evidence, it
blocks all canonical sites in the same country/date.

Unknown sub-100 candidates neither create site activity nor block a 100/200/300
absence, because they are below every target threshold.

## 10. SQLite and persistence

Create one named T-040 Drizzle migration.

Change:

```sql
scored_distance_km BETWEEN 100 AND 2000
```

to:

```sql
scored_distance_km > 0 AND scored_distance_km <= 2000
```

Review the required SQLite table rebuild. Preserve all rows, keys, constraints,
indexes, timestamps, and ingestion-run relationships. Do not store a distance
band; labels are derived from numeric distance.

Create the mapping-exclusion table and only the indexes needed for validator
lookups.

Keep unique identity `(source_id, source_flight_id)`. Threshold/activity
overlap must insert once, recognize equivalent replays, apply only current
reconciliation upgrades, and surface conflicts instead of overwriting them.

Persistence accepts finalized complete or partial runs for observed accepted
records. It records profile and coverage status in run notes and retains the
manifest path/hash. Persistence never upgrades a partial coverage claim.

## 11. Replay existing raw evidence

After migration/parser acceptance:

1. inventory ignored XCContest manifests;
2. verify each manifest and artifact hash;
3. parse with the new version offline;
4. review new short-flight mapping proposals;
5. persist approved records through reconciliation;
6. record which old manifests yielded short flights.

Do not recollect a page already present in immutable raw HTML. Do not modify old
manifests or parser-v2 output.

## 12. T-020 dataset impact

### 12.1 Site-day population

The label audit contains canonical site/local-date pairs with at least one
accepted positive-distance flight. Short-flight ingestion adds candidate
negative days missing from the current database.

No accepted flight means `unknown_no_activity_evidence`, never zero.

### 12.2 Forecast row grain

Derive one label record per site-day, then up to three forecast examples for
D+1, D+2, and D+3. For target date D and horizon h:

- issue date is `D - h local calendar days`;
- cutoff is 20:00 `Europe/Sofia` on issue date;
- select the newest complete GFS cycle available by cutoff;
- use features valid for D and the accepted flying window;
- retain run, availability, cutoff, valid times, lead hours, snapshot identity,
  versions, and hashes.

One new activity day can add three joined rows per site. One weather ingestion
already samples all seven sites, so deduplicate acquisition by target date,
issue cutoff, and selected cycle rather than fetching per site.

Missing eligible GFS or feature snapshot creates an excluded row. Never
substitute a later cycle, same-day analysis, reanalysis, or IGRA observation.

### 12.3 Output files

T-020 writes ignored deterministic artifacts:

- `examples.jsonl`: model-eligible site/date/horizon rows;
- `label-audit.jsonl`: positive, negative, and unknown label evidence;
- `excluded-examples.jsonl`: explicit weather/coverage/mapping/maturity gaps;
- `manifest.json`: schema/policy/feature versions, source run IDs and hashes,
  counts, and output hashes.

JSONL is the MVP format: inspectable, streaming, language-neutral, and no new
dataframe dependency. Parquet may be a later derived export if scale justifies
it.

Label fields include site/date, activity count, max/total distance, tri-state
100/200/300 values, nullable binary values, coverage and mapping states,
maturity, contributing flight/run IDs, manifest hashes, and policy version.

Joined fields add horizon, issue date, local/UTC cutoff, GFS product/run and
availability, feature snapshot/version/columns, join status, and exclusion
reason.

Known labels must satisfy
`label_300 <= label_200 <= label_100`. Unknown is null, never zero. T-023 must
also enforce `P(300) <= P(200) <= P(100)`.

### 12.4 Weather acquisition plan

Do not fetch GFS immediately for every new short-flight day. Current retained
weather artifacts make an unbounded multi-year backfill too large.

T-020 first emits a deterministic, deduplicated missing-weather plan with
target date, cutoff, horizon, and byte estimate. The owner runs bounded batches.
Broad collection waits for the compact site-footprint weather design in the
handoff or an explicitly approved smaller cohort. Flight labels remain
independent of weather availability.

## 13. Implementation phases

### A. Source contract and fixtures

- Run one supervised headed activity date.
- Confirm date semantics, exact categories, next-page state, sorts, and
  sub-100 row shape.
- Update sanitized synthetic fixtures only; commit no live or pilot data.

### B. Database

- Update `packages/database/src/schema.ts`.
- Generate `expand_xccontest_activity_records`.
- Review rebuild/exclusion DDL.
- Extend fresh, upgrade, constraint, FK, index, and idempotence tests.

### C. Collector

Update:

- `models.py` for profiles, dates, generic saturation, statuses, and views;
- `browser.py` for ISO dates and supported sorts;
- `collector.py` for separate profile strategies;
- `artifacts.py` for checkpoint/resume and v4;
- `manifest.py` for v1-v4 and partial coverage;
- `cli.py`/`pipeline_cli.py` for profile/date/live-resume options;
- `collection_runner.py`/`pipeline.py` for resume and partial flow;
- `versions.py` for all changed boundaries.

Keep threshold logic isolated so activity work cannot alter 100+ behavior.

### D. Offline pipeline

- update parser distance/date rules;
- add grouped mappings and durable exclusions;
- distinguish actionable and reviewed-out-of-scope quarantine;
- update persistence/reconciliation;
- prove offline resume never contacts the source.

### E. T-020 builder

- verify ingestion manifest hashes;
- aggregate site-day flights;
- resolve coverage, mapping, and maturity by threshold;
- emit tri-state audit;
- join horizon-matched GFS using DEC-055;
- emit examples, exclusions, manifest, and weather plan;
- prove deterministic hashes.

### F. Documentation and rollout

- update `services/ml/README.md` commands and meanings;
- update handoff with live evidence;
- keep T-040 open until code, migration, offline replay, and bounded live
  verification pass;
- keep T-020 open until joined artifacts validate.

## 14. Required tests

### Collector/manifest

- all existing threshold saturation regressions;
- unsaturated activity date;
- saturated PG completed by five exact categories;
- unresolved exact category with seven rescue views;
- rescue discovers IDs without claiming completeness;
- empty/non-offered dates stay unknown;
- multiple dates remain sequential;
- view cap stops before an extra operation;
- checkpoint verifies hashes and skips completed views;
- changed resume config fails;
- challenge/control drift fails;
- v4 complete/partial validation and v1-v3 compatibility.

### Parser/mapping

- accept `0.01`, `99.99`, `100`, and `2000`;
- reject zero, negative, non-finite, and over-2000;
- recover incidental short rows from old artifacts;
- quarantine source/local-date mismatch;
- deduplicate identical views and retain conflicts;
- accept an approved short flight;
- exclude reviewed out-of-scope evidence from canonical records;
- invalidate exclusions after site-scope changes;
- keep unresolved mappings actionable.

### Database/persistence

- upgrade existing 100+ rows without loss;
- accept positive sub-100 and reject zero/negative;
- preserve all FKs, unique checks, and indexes;
- insert overlap once and leave equivalent replay unchanged;
- surface conflict;
- persist observed partial-run records with partial provenance;
- roll back atomically.

### Labels/join

- 78/157/240/330 examples produce nested states;
- no flight stays unknown;
- unresolved coverage/mapping blocks negatives;
- reviewed exclusion removes the correct blocker;
- immature collection cannot prove absence;
- one short flight establishes MVP activity;
- later count sensitivity needs no recollection;
- summer/winter Sofia cutoffs convert correctly;
- exactly-at-cutoff run is eligible and after-cutoff run is not;
- D+1/D+2/D+3 use matching issue dates;
- no fallback to later/reanalysis/IGRA inputs;
- missing weather is explicit;
- output is stable under input ordering;
- labels and predictions obey `300 <= 200 <= 100`.

Automated tests make no XCContest or NOAA requests. Live checks are separate
bounded evidence.

## 15. Operational rollout

1. Implement against fake driver and sanitized fixtures.
2. Test fresh and upgrade database migrations.
3. Replay existing XCContest raw artifacts offline.
4. Review/persist exposed short flights.
5. Confirm the current source authority covers all-distance multi-date rendered
   collection; otherwise stop live work and update authority.
6. Run one headed activity date at 30-second pacing.
7. Manually compare row IDs, date semantics, coverage, parser, mapping, and DB.
8. Run a small bounded range.
9. Review load, saturation, duration, mapping work, and negative-label yield.
10. Expand seasons in bounded resumable batches.
11. Build label audit before requesting GFS.
12. Run only an approved size-bounded weather plan.

Never run years/countries in parallel or reduce pacing just for speed.

## 16. Acceptance criteria

T-040 is ready for review only when:

- threshold commands retain tested 100+ behavior;
- activity handles multiple dates sequentially and resumes;
- every observed valid positive-distance flight can reach reviewed persistence;
- SQLite stores sub-100 safely;
- profile overlap does not duplicate source flights;
- complete/partial coverage is explicit and hash-verifiable;
- rescue sorts improve recall without overstating completeness;
- mappings and current-scope exclusions are durable;
- no absent-flight day becomes negative;
- label fixtures prove nested and unknown states;
- T-020 maps every new site-day to D+1/D+2/D+3 join candidates;
- commands, limitations, evidence, and tests are documented;
- no raw data, local DB, policy, pilot data, or generated dataset is committed.

## 17. Limitations

XCContest labels describe recorded public achievement, not physical potential
or safety. Participation, privacy, late upload, route choice, and site
popularity remain selection biases.

A partial activity scan may miss short-flight site-days. They remain unknown.
Even complete rendered coverage cannot reveal private or never-uploaded flights.

All-distance workload is much larger than 100+ collection. Date partitioning is
necessary, and a saturated category/date cannot be proven complete under the
first-page restriction. The manifest must expose this limit.
