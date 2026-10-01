# T-020 phase 2 — offline flight-label audit

## Scope and accepted policy

Implemented on 1 October 2026. The supported command is:

```powershell
uv run --project services/ml flight-label-audit
```

The command produces deterministic, local JSONL evidence for source seasons
2022–2025. One example is **one canonical location and one local flying date**,
not a flight and not a date shared across all locations. A Shumen 100+ flight
cannot label Nevsha positive. `Europe/Sofia` determines the flying date; source
season 2025 spans 2024-10-01 through 2025-09-30. All seven sites and every
calendar date are enumerated, including leap day and no-activity dates.

DEC-056 defines the inclusive 100/200/300 km thresholds and minimum one accepted
positive-distance flight for negative activity. Confirmed threshold evidence
gives a positive. A negative also requires complete mature coverage and terminal
mapping. All other cases are unknown; stored 0 km records do not prove activity.
DEC-063 records the owner's explicit maturity acceptance of the two repaired
runs. Future seasons do not acquire a maturity rule implicitly.

The implemented negative gate is conservative: require an integrity-verified,
non-paginated source-default daily parent view and complete/empty scope. It does
not recover absence from threshold-only or exact-category fallback evidence.
Unknowns retain positive evidence and all coverage reasons. The threshold states
remain nested wherever known.

## Verification boundary

The reader opens SQLite in read-only/query-only mode with a stable read
transaction and checks integrity/foreign keys. It verifies source-flight
uniqueness, approved site mappings, effective persisted accepted snapshots,
canonical site/timestamp/distance agreement, training-use authority, raw/stage
hashes, dated HTML selection and row dates, IDs/counts, parser normalization,
parser rejection evidence, and terminal mapping review. It recomputes the
persistence-event fingerprint using the existing contract.

Malformed or changed input fails before publication. Genuine partial/missing
coverage remains unknown. A lost threshold candidate or parser conflict blocks
run-wide absence for the affected thresholds; an unresolved mapping blocks
run-wide negatives. Short rejected parser rows do not count as accepted activity
and cannot conceal 100+ positives. Reviewed out-of-scope exclusions never create
flight labels. New outputs publish atomically; different existing outputs are
never overwritten. Identical inputs and replay produce identical bytes.

The verified evidence runs are:

- repaired 2022–2024 `9c70c7a0-89f2-4a56-8b8e-a608eb3dde6e`;
- repaired 2025 `89841b61-c681-4008-b833-031d4aee636e`;
- supplemental accepted positive provenance
  `8d809838-3ff8-42ce-9977-3997cd2536bc`, for Shumen on 2023-10-17
  (107.88 km), outside daily activity coverage. It does not establish negatives.

The repaired raw sets are independently reverified with the current dated-view
guard. Their effective persisted validation reports retain parser v2; the audit
does not rewrite them or require database revalidation merely to audit labels.
The existing parser v3 replays remain separate historical evidence.

## Owner-data results

There are **10,227 site-day rows**, **5,090 accepted positive-distance flights**,
**985 active site-days**, and **525 distinct active dates**. Of those rows,
**978** have all three labels known; **9,249** contain at least one unknown.
No accepted activity exists on 9,242 rows. Seven active rows lack complete
daily activity coverage outside the activity window; one still has a confirmed
100+ positive. All these unknown vectors stay out of the complete-vector output.

| Threshold | Positive | Negative | Unknown | Distinct positive dates |
| --- | ---: | ---: | ---: | ---: |
| 100+ km | 293 | 686 | 9,248 | 222 |
| 200+ km | 65 | 913 | 9,249 | 60 |
| 300+ km | 8 | 970 | 9,249 | 7 |

The complete-vector subset has 292/65/8 positives for 100/200/300+, respectively.
It differs from the threshold-specific audit because the supplemental Shumen
100+ positive has unknown higher-threshold labels.

| Source season | Flights | Active site-days | 100+ positives | 100+ negatives |
| --- | ---: | ---: | ---: | ---: |
| 2022 | 998 | 202 | 49 | 153 |
| 2023 | 1,373 | 242 | 74 | 168 |
| 2024 | 1,383 | 294 | 90 | 203 |
| 2025 | 1,336 | 247 | 80 | 162 |

Minimum 1/2/3 flights for an otherwise known 100+ negative gives **686/445/301**
negatives, with **293** positives unchanged. These numbers reproduce the repaired
exploratory report; the accepted production policy remains minimum one flight.
The report includes counts by site, season, and site/season, activity counts,
maximum-distance bands, unknown reasons, and independent positive dates.

The full-calendar denominator intentionally differs from the earlier exploratory
script's collected-date denominator. Unknown counts are therefore larger; no
new negatives are inferred from the additional dates.

## Local artifacts and replay

Verified audit identity:
`cd6c8b99b6898ec41cb631a2ee9913cd6b76df377b1046d777a8fadc91c92a38`.

All generated files remain ignored under
`data/processed/flight-label-audits/<audit-id>/`:

- `site_day_label_audit.jsonl` — every row;
- `known_site_day_labels.jsonl` — all-three-known vectors;
- `unknown_site_day_labels.jsonl` — any-unknown vectors;
- `summary.json` — recomputed inventories and sensitivity;
- `manifest.json` — input/output hashes, source/stage/mapping provenance,
  database snapshot identity, policy/schema/query versions, and limitations.

Two supported-command replays on unchanged evidence return the same audit ID
and verify every existing output byte. Outputs contain source identity and
provenance, with no pilot fields. For a subset use repeated `--season`; the
command only accepts 2022–2025 and requires the corresponding repaired run.
The service README documents all options and failure behavior.

## Validation and remaining work

Verification includes 36 synthetic offline tests covering site isolation,
inclusive thresholds, timezone/season boundaries, leap day, zero and invalid
distances, unknowns, partial/maturity/mapping gates, reviewed rejection, lost
threshold candidates, stale HTML dates, hash mismatch, SQLite reconciliation,
training permission, immutable output, deterministic replay, and CLI failures.
The full ML suite, Ruff lint/format, repository structure check, and Git diff
check must pass before the phase is reported complete. See the handoff for the
final execution results.

T-020 remains In Progress. Phase 3 must review the cohort, chronological split,
exact evening-cutoff/horizon acquisition manifest, and bounded storage plan.
Phase 4 owns the weather join. This phase collects no GFS, builds no model, and
selects no train/test split. Eight 300+ site-days across seven dates remain far
below the planning checkpoint of 30 independent positive site-days. Recorded
achievement is conditional source evidence, not a safety guarantee or a direct
measurement of weather-only potential. Flight counts and realised distances
must never become forecast predictors.
