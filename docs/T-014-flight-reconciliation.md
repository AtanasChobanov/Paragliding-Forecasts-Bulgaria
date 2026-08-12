# T-014 Flight reconciliation and review workflow

## Purpose and boundary

T-014 makes persistence of an already validated XCContest flight snapshot
repeatable and auditable.  It is an **offline** boundary: it reads the existing
`parser-v2` and `validation-v2` artifacts, verifies their hashes, and reconciles
accepted records with migrated SQLite.  It does not collect, open a browser, or
contact XCContest.

The source identity of a canonical flight is the database constraint
`(source_id, source_flight_id)`.  A second observation of that identity is not
silently inserted or overwritten.  It is classified before any database write.

T-014 deliberately keeps the mapping-review gate introduced by DEC-029:

1. `xccontest-ingest fresh` creates mapping proposals and stops with
   `awaiting_mapping_review` if mapping-actionable quarantines are still
   unresolved.
2. A human applies mapping decisions, then runs `xccontest-ingest resume`.
   `resume` is offline and revalidates against the current approved mapping
   snapshot.
3. Only then does persistence reconcile the accepted flights.  A reconciliation
   conflict creates another explicit review pause rather than a partial write.

`--persist-approved-only` remains an explicit, exceptional path.  It may persist
currently accepted records while unresolved mapping quarantines remain.  When
mapping review later permits the remaining records, `resume` reuses the same
`ingestion_runs` row and reconciles the earlier subset instead of failing on
duplicates.  It is not the normal `fresh` workflow and never bypasses the
mapping-review requirement for a quarantined record.

## What is compared

Every accepted validation record is normalized to these canonical values before
comparison.  Distances use an exact normalized decimal representation, so JSON
`150`, `150.0`, and `150.00` are equal; there is intentionally no arbitrary
numeric tolerance.

| Field | Reconciliation rule |
| --- | --- |
| `source_flight_url` | Different non-empty URL is a human-review conflict. |
| `source_site_mapping_id` | Different approved mapping is a human-review conflict. |
| `takeoff_at_utc` | Different timestamp is a human-review conflict. |
| `scored_distance_km` | Different normalized decimal is a human-review conflict. |
| `duration_seconds` | `null` to a concrete value enriches; concrete to `null` preserves the existing value; two different concrete values conflict. |
| `route_type` | `unknown` to known enriches; known to `unknown` preserves the existing value; two different known values conflict. |
| `track_url` | `null` to a URL enriches; URL to `null` preserves the existing value; two distinct URLs conflict. |
| `validation_level` | `metadata` to `track` enriches automatically; the reverse preserves the existing level. |

The resulting outcome is one of the following:

| Outcome | Effect on `flight_records` |
| --- | --- |
| `inserted` | Create a new canonical flight. |
| `revalidated_unchanged` | Keep canonical values and refresh validation/provenance metadata. |
| `enriched` | Fill only the allowed missing or lower-quality values. |
| `preserved_existing` | Keep a better existing value when the incoming value is missing, unknown, or lower validation level. |
| `reviewed_keep_existing` | A human chose the entire existing canonical value set for a conflict. |
| `reviewed_accept_incoming` | A human chose the entire incoming canonical value set for a conflict. |

There is no implicit field-by-field merge for a conflict.  `accept_incoming`
means the incoming canonical record wins; `keep_existing` means the existing
canonical record wins.  The proposal exposes both complete values so a reviewer
can make that choice deliberately.

## Normal reconciliation flow

```text
validated accepted JSONL + current SQLite
                |
                v
       classify each source identity
         |       |          |
         |       |          +-- conflict --> write immutable proposal --> pause
         |       |
         |       +-- existing --> revalidate / enrich / preserve
         |
         +-- absent --> insert
                |
                v
       one BEGIN IMMEDIATE transaction
                |
                v
  update run event + canonical flights + quality notes
```

The transaction first verifies all raw/parser/validation SHA-256 evidence, the
current mapping snapshot, and that every selected mapping is still approved for
XCContest.  If any comparison needs reconciliation review, it rolls back before
creating or changing an `ingestion_runs` or `flight_records` row.  Therefore a
batch containing one conflict and several new flights cannot partially persist.

For a successful reconciliation:

- The first persistence of a run creates its `ingestion_runs` row.  A later
  partial-run resume updates that same row and appends a new event in its
  versioned `notes` JSON.
- A cross-run duplicate creates a new `ingestion_runs` row, but never a second
  `flight_records` row for the same source identity.
- `created_by_ingestion_run_id` is never changed.  Every successful observation
  updates `last_validated_by_ingestion_run_id`, `validated_at_utc`,
  `validation_notes`, and `updated_at_utc` on the canonical flight.
- Repeating the exact already-applied validation evidence for the same run is a
  successful no-op.  It reports `reconciliation.status: "no_op"` and writes no
  additional database event or flight update.

This is intentionally a compare-and-reconcile policy rather than SQLite
`INSERT OR REPLACE`: replacement would lose provenance and could silently choose
the wrong distance, launch mapping, or takeoff time.

## Resolving a reconciliation conflict

When persistence returns `status: "awaiting_reconciliation_review"`, its JSON
report contains `reconciliation.proposals_path`, `report_path`, and
`decisions_path`.  The files are local and ignored by Git:

```text
data/interim/xccontest/<run-key>/
  reconciliation-v1/
    <plan-sha256>/
      reconciliation-proposals.jsonl  # generated immutable evidence
      reconciliation-report.json       # generated hash/count summary
      reconciliation-decisions.jsonl   # reviewer-created decision file
```

The `<plan-sha256>` includes the run key, validation snapshot, accepted JSONL
hash, and the comparison results.  Do not guess the directory name; copy the
paths returned by the pause report.  If validation evidence or the database
state changes, a new plan is generated and an old decisions file is deliberately
not reused.

### Reviewer procedure

1. Read `reconciliation-report.json` and inspect each line in
   `reconciliation-proposals.jsonl`.  It contains `existing`, `incoming`, and
   `conflicting_fields`; it contains no pilot identity fields.
2. Copy the proposal file next to itself.  Never edit the proposal file.

   ```powershell
   $reconciliationDir = 'data/interim/xccontest/<run-key>/reconciliation-v1/<plan-sha256>'
   Copy-Item "$reconciliationDir/reconciliation-proposals.jsonl" `
     "$reconciliationDir/reconciliation-decisions.jsonl"
   ```

3. Keep every copied immutable field exactly as generated.  Add the decision
   fields below to every JSONL line.  A decision file must contain exactly one
   decision for every proposal; it cannot resolve only a subset.
4. Run the usual offline resume command.  It uses the already existing raw and
   interim artifacts and does not launch the collector.

   ```powershell
   uv run --env-file .env --project services/ml xccontest-ingest resume `
     --run-key <uuid> `
     --policy-file data/local/xccontest-import-policy.json
   ```

`xccontest-persist` can be used for a focused stage replay instead.  Supply the
same `--run-key`, exact validation snapshot, and policy file.  Both commands
return exit code `2` while review is pending; malformed evidence returns an
error and exit code `1`.

### Required decision fields

The following values are copied from the proposal and are immutable evidence:

- `proposal_id`
- `reconciliation_schema_version`
- `run_key`
- `source`
- `source_flight_id`
- `validation_snapshot_sha256`
- `accepted_flights_sha256`
- `existing_fingerprint`
- `incoming_fingerprint`

The reviewer adds these fields:

| Field | Required value |
| --- | --- |
| `decision` | Exactly `keep_existing` or `accept_incoming`. |
| `verification_reference` | Non-empty auditable evidence reference. Prefer a stable source artifact/detail URL plus review context, for example `raw-artifact:data/raw/xccontest/<run>/views/…; detail-url:https://www.xcontest.org/…`. |
| `reviewed_by` | Non-empty reviewer identifier or initials. |
| `reviewed_at_utc` | UTC timestamp exactly `YYYY-MM-DDTHH:MM:SSZ`. |
| `notes` | Non-empty concise rationale for the selected canonical record. Do not add credentials or pilot-identifying data. |

Example decision line (the placeholders must be replaced by the unchanged values
copied from the generated proposal):

```json
{"proposal_id":"<copied>","reconciliation_schema_version":1,"run_key":"<copied>","source":"xccontest","source_flight_id":"12345","validation_snapshot_sha256":"<copied-sha>","accepted_flights_sha256":"<copied-sha>","existing_fingerprint":"<copied-sha>","incoming_fingerprint":"<copied-sha>","decision":"keep_existing","verification_reference":"raw-artifact:data/raw/xccontest/<run-key>/…; reviewed-source-detail:https://www.xcontest.org/world/en/flights/detail:12345","reviewed_by":"AB","reviewed_at_utc":"2026-08-12T12:00:00Z","notes":"The retained source artifact confirms the previously stored scored distance."}
```

The validator rejects a missing, duplicate, stale, incomplete, or edited
immutable record.  It also rejects a decision that does not cover every
proposal.  Nothing is written until the entire decisions file is valid.

## Quality and traceability notes

`flight_records.source_flight_url` remains the canonical link for the chosen
record.  T-014 writes a compact, machine-verifiable JSON object to
`flight_records.validation_notes` whenever it inserts, revalidates, enriches,
preserves, or resolves a record.  Its current `schema_version` is `1`:

```json
{
  "schema_version": 1,
  "evidence_level": "metadata",
  "parser_version": "xccontest-parser/2",
  "validator_version": "xccontest-validator/2",
  "persistence_version": "xccontest-persistence/3",
  "mapping_key_type": "source_site_token",
  "mapping_snapshot_sha256": "<sha256>",
  "accepted_flights_sha256": "<sha256>",
  "artifact_reference_count": 2,
  "artifact_references_sha256": "<sha256>",
  "quality_flags": ["track_not_verified"],
  "reconciliation": {
    "outcome": "revalidated_unchanged",
    "event_sha256": "<sha256>",
    "decision_reference": null
  }
}
```

`quality_flags` are derived from the chosen canonical value, not from an
operator free-text judgement:

- `track_not_verified` for metadata-level evidence;
- `route_type_unknown` when the route type is `unknown`;
- `duration_missing` when duration is null;
- `incoming_missing_value_preserved` when a lower-quality incoming value was
  deliberately not allowed to erase a known value; and
- `manual_reconciliation` for either reviewed conflict outcome.

The reconciliation object carries the outcome, deterministic persistence event
hash, and (for manual decisions) the reviewer-supplied verification reference.
The full per-artifact references stay in the verified parser/validation
artifacts; the database retains their count and deterministic hash to avoid
duplicating raw evidence or personal data.

Old T-013 plain-text `validation_notes` remain readable.  T-014 does not perform
a destructive database backfill.  A legacy row receives schema-v1 notes only
when a later valid reconciliation actually updates or revalidates it.

Run-level history is append-only within the versioned JSON held in
`ingestion_runs.notes`.  Each applied event records its validation report and
accepted JSONL paths/hashes, reconciliation plan hash, optional decisions hash,
mapping-review completeness, outcome counts, and timestamp.

## Operational outcomes and troubleshooting

| Result | Meaning | Next action |
| --- | --- | --- |
| `awaiting_mapping_review` | Unknown/ambiguous/provisional mapping evidence remains. | Review site mappings; do not create reconciliation decisions yet. |
| `awaiting_reconciliation_review` | A mapped accepted flight conflicts with an existing canonical record. No database writes occurred. | Create the complete reconciliation decisions JSONL, then use `resume`. |
| `succeeded` + `reconciliation.status: applied` | All records were inserted, revalidated, enriched, preserved, or manually resolved in one transaction. | Retain the output JSON and ignored local artifacts for audit. |
| `succeeded` + `reconciliation.status: no_op` | The same run/evidence was already applied. | No action; there was no duplicate write. |
| Error about mapping snapshot or mapping approval | Approved mappings changed after validation. | Re-run validation, then resume using its new snapshot. |
| Error about decision evidence | The decisions file is malformed, stale, or was edited beyond permitted fields. | Regenerate/read the current proposal plan and produce a complete matching decisions file. |

## Verification approach

T-014 has deterministic unit tests for exact comparison, allowed enrichment,
preservation, conflict classification, decision-evidence validation, and
quality-note semantics.  Its integration tests run the committed migrations into
a temporary local SQLite file and create only synthetic raw/parser/validation
artifacts.  They cover partial-run resume, same-run no-op replay, cross-run
duplicate revalidation, conflict atomicity, and a reviewed resolution.  No
Docker instance is required: the project uses SQLite, and no test sends a
request to XCContest.
