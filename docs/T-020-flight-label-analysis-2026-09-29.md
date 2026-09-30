# T-020 flight evidence review — 29 September 2026

## Operational supersession — 30 September 2026

This is a historical, pre-2025-repair exploratory snapshot. The 2025 source run
named below was superseded by repaired run
`89841b61-c681-4008-b833-031d4aee636e`, which copied 219 views, recollected 31,
passed a zero-issue raw audit, and persisted 1,336 accepted flights. The exact
flight, site-day, label, and proposed-split counts in this report must therefore
not select a current weather or evaluation cohort. Retain the report for its
negative-policy sensitivity and methodology; the planned deterministic offline
label audit must recompute all current counts from repaired evidence.

## Outcome and scope

The local database contains enough recorded site-days to begin a pooled,
regularized **100+ km baseline**, and a cautious **200+ km baseline** after the
weather join. It does **not** contain enough independent 300+ events for a
credible learned/calibrated 300+ probability model, or enough evidence for
separate models at every location. Collection completeness and statistical
sufficiency are different questions.

At the time of this analysis, the 2022–2024 repair was completed and
persisted, while the integrity review found **31 stale dated views in the 2025
run**. Its recorded positive flights remained evidence on their actual takeoff
dates, but its affected negative labels and activity counts could not be
accepted solely from the manifest's `complete` status. The later completed
repair is recorded in the operational-supersession note above; this review did
not contact XCContest or acquire GFS.

This is an exploratory, read-only analysis supporting T-020. It does not
implement the production label builder, freeze a weather cohort, train a
model, change DEC-056, or complete T-020. Activity thresholds and evaluation
splits below are recommendations, not accepted decisions.

## Inputs, integrity checks, and counting method

Read `AGENTS.md`, `handoff.md`, the two T-020 implementation plans, T-020 and
downstream tickets in `tasks.md`, DEC-023–030 and DEC-054–062, and focused
flight/weather/model-validation sections of the brief and architecture.

SQLite was opened with URI `mode=ro` and `PRAGMA query_only=ON`. `quick_check`
returned `ok`; foreign-key checking found no violations. Database SHA-256 was
unchanged across the analysis. There are **4,887 unique canonical flights**,
all attached to approved mappings, and **zero zero-distance flights**.

| Evidence run | Seasons | Accepted flights | Saved views | Date-integrity findings |
| --- | --- | ---: | ---: | --- |
| `9c70c7a0-89f2-4a56-8b8e-a608eb3dde6e` | 2022, 2023, 2024 | 3,753 | 1,487 | 0 inconsistent views |
| `d577156f-7f73-4e62-81ad-eb6881715739` | 2025 | 1,052 | 250 | 31 inconsistent dated views |

The repaired run retains provenance for **85 replacement views and 1,402
verified copied views**, originating from
`724845c1-7b75-4900-a74c-d61e9de83157`. Its manifest hash is
`44118e8d9fb177122d0d0bbfe273cc2364f92c06962bf216aaecdb2c0156c7dd`.
The 2025 manifest hash is
`545e91018c56370457b7a95d733ea114ec2374cc72903fe23b017933d2764c8c`.

Effective accepted-file, validation-report, normalized-parser, parser-report,
and quarantine hashes were verified against persistence/validation provenance.
Every accepted flight in the two effective all-distance runs matches SQLite's
site, takeoff timestamp, and distance. Both have **zero unresolved actionable
mapping quarantines**, checked with the existing offline pipeline logic:

- 2022–2024: 2,222 persisted reviewed exclusions and 374 coordinate-based
  out-of-scope rejections; these are terminal exclusions, not missing in-scope
  flights or negative training labels.
- 2025: 865 run-local reviewed rejections and 128 coordinate-based rejections.
  Its historical validation file still calls those 865 rows `review_required`;
  the matching reviewed decision file resolves them. They must not be counted
  as unresolved merely from that old report field.
- Six parser-rejected rows have invalid duration. Their observed scored
  distances are 0.02–1.38 km, so they cannot hide a 100/200/300+ positive.
  They are excluded from the accepted-activity counts, as required.

The 2025 audit finds **14 nonempty and 17 empty stale views**. Requested and
serialized dates together identify **47 potentially affected dates**. For
this conservative exploratory review, a negative requires a complete,
untainted all-distance daily capture plus terminal mapping evidence. Both
requested and serialized dates of an inconsistent view are excluded from
negative eligibility. A more exact production builder could recover some
negatives from independent complete threshold evidence; this review does not
assume that recovery. Confirmed positives require no inference from absence.

Group flights by **canonical site and takeoff date in `Europe/Sofia`**. A
training outcome is a site-day, not an individual flight. Inclusive maximum
distances determine nested observed outcomes: `000`, `100`, `110`, or `111`.
Source season is **1 October of the preceding year through 30 September**,
not the calendar year. Daily activity collection covers the source-offered
dates satisfying 15 February–15 October; preceding October dates are therefore
part of the following source season. The four runs expose 973 daily scopes.

## Inventory and label eligibility

The main four-season cohort contains **4,806 flights, 972 active site-days,
and 521 distinct calendar dates**. One additional older canonical 2024-season
flight was not in the new run: Shumen, 17 October 2023, 107.88 km. It remains
positive evidence for 100+, but lacks an all-distance daily scope.

The remaining **81 flights / 37 site-days** in SQLite belong to legacy
threshold-only season 2026. They contribute 37/16/1 observed positive site-days
for 100/200/300+, but cannot supply general negative examples. Keep this partial
cohort separate; it is not a fifth complete season.

| Source season | Flights | Active site-days | All below 100 (`000`) | 100–199 (`100`) | 200–299 (`110`) | 300+ (`111`) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2022 | 998 | 202 | 153 | 39 | 10 | 0 |
| 2023 | 1,373 | 242 | 168 | 61 | 11 | 2 |
| 2024 | 1,383 | 294 | 204 | 71 | 18 | 1 |
| 2025 | 1,052 | 234 | 154 | 57 | 18 | 5 |
| **Total** | **4,806** | **972** | **679** | **228** | **57** | **8** |

These are observed bands, not a claim that every below-threshold row is a
known negative. The accepted individual-flight bands are 4,139 below 100 km,
546 at 100–199, 108 at 200–299, and 13 at 300+. Those 13 long flights collapse
to eight 300+ site-days on seven distinct dates.

| Threshold | Confirmed positive site-days | Below threshold with activity | Conservative known negatives | Active rows with unknown absence |
| --- | ---: | ---: | ---: | ---: |
| 100+ | 293 | 679 | 651 | 28 |
| 200+ | 65 | 907 | 860 | 47 |
| 300+ | 8 | 964 | 911 | 53 |

The site/date audit includes **5,846 no-accepted-activity combinations** over
the enumerated dates. They remain unknown; they are not bad-weather examples.
This is not an enumeration of every calendar day outside the scan policy.

For a dataset requiring all three labels to be known, the conservative current
cohort is **919 site-days on 488 dates**, with bands **651 / 209 / 51 / 8**.
It has 268/59/8 positives for 100/200/300+. The difference from 293/65/8 is
confirmed low-threshold positives whose higher-threshold absences cannot yet
be used. Preserve their positive evidence in the audit rather than deleting
it; a future threshold-specific masked fitting approach would need an explicit
implementation/design choice.

Seven active site-days are outside daily activity scopes, including six short
days incidentally discovered from parent-season views. Another 46 active
site-days have an unknown absence because of conservative date-integrity
exclusion. Together they explain the 53 rows lacking a complete label vector.

## Distribution across locations

Positive columns below are cumulative thresholds; below-100 is the observed
`000` band. All counts refer to source seasons 2022–2025.

| Location | Flights | Active days | Below 100 | 100+ | 200+ | 300+ | Fully known vectors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Sofia / Vitosha | 728 | 200 | 168 | 32 | 0 | 0 | 188 |
| Zlatitsa | 282 | 95 | 83 | 12 | 1 | 0 | 95 |
| Sopot | 2,427 | 325 | 227 | 98 | 8 | 0 | 306 |
| Nevsha | 349 | 80 | 28 | 52 | 32 | 1 | 73 |
| Shumen | 806 | 217 | 137 | 80 | 14 | 1 | 204 |
| Pastrina | 155 | 34 | 20 | 14 | 5 | 1 | 33 |
| Dobrich region | 59 | 21 | 16 | 5 | 5 | 5 | 20 |

- **100+:** pooled MVP fitting is justified by the label inventory, subject to
  GFS availability and actual validation. Sopot and Shumen have the strongest
  site-specific support. Vitosha has useful 100+ evidence. Zlatitsa has few
  positives; Nevsha has fewer negatives. Pastrina and especially Dobrich need
  pooled learning and explicit uncertainty rather than separate local models.
- **200+:** 65 positives exceed the handoff's rough pooled planning target of
  50. This is uneven: Nevsha alone contributes 32. Vitosha has none, Zlatitsa
  one, Sopot eight. A per-site 200+ classifier/calibration is not justified.
  Reserving 2025 leaves only 42 currently eligible development positives, so
  this is enough to start a cautious experiment, not to claim robust training
  and evaluation support simultaneously.
  Zero recorded positives do not prove physical impossibility or a true 0%
  probability.
- **300+:** eight site-days fall far below the planning minimum of 30.
  Development seasons 2022–2024 contain only three, and 2022 adds none.
  Dobrich contributes five of eight. More negatives, flights from the same
  event, or three forecast horizons cannot compensate for missing positive
  events. Treat this output as exploratory/conservative, not validated precise
  percentages.
- Every location has some activity in each of the four source seasons, but
  Dobrich has only **1 / 11 / 4 / 5 days**, and Pastrina **12 / 12 / 4 / 6**.
  Multi-season presence is not full seasonal/weather-regime coverage.
- Site-level activity selection is substantial. There are 100+ outcomes on
  52/80 observed Nevsha days and only 12/95 Zlatitsa days. These are conditional
  source-recording rates, not estimated unconditional forecast probabilities.

## Negative activity threshold sensitivity

Among the 679 observed below-100 site-days:

| Accepted positive-distance flights per site-day | Days | Share |
| --- | ---: | ---: |
| Exactly 1 | 247 | 36.4% |
| Exactly 2 | 141 | 20.8% |
| Exactly 3 | 72 | 10.6% |
| At least 4 | 219 | 32.3% |

Thus **213 days have exactly two or three short flights**; **460 have at most
three**. Of the 651 conservative known 100+ negatives, 229/136/71/215 have
one/two/three/at-least-four flights respectively. The verified two-or-three
subset is **207 days**.

Distance also helps describe how much flying actually occurred:

| Daily maximum scored km | 1 flight | 2 flights | 3 flights | 4+ flights | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| >0, below 10 | 122 | 40 | 13 | 10 | 185 |
| 10, below 30 | 65 | 42 | 17 | 53 | 177 |
| 30, below 50 | 27 | 35 | 14 | 47 | 123 |
| 50, below 100 | 33 | 24 | 28 | 109 | 194 |

Almost half of the singleton days have a maximum below 10 km. At the other
extreme, 33 singleton days reach 50–99 km. Three short flights can still all
be short local flights, while one 90 km flight can contain substantial XC
effort. Counts alone do not prove attempts to reach a threshold or the weather
cause of failure. Pilot skill, intentions, launches/towing, source participation,
and unrecorded flights remain unobserved.

The following sensitivity applies a minimum **accepted positive-distance
flight count at that same site/date** to each negative threshold independently.
Confirmed positives are always retained. It never converts an unknown into a
negative. These are threshold-specific audit counts, not necessarily counts
of complete three-label vectors.

| Minimum count for negatives | Known 100+ negatives | Moved to unknown | Known 200+ negatives | Known 300+ negatives |
| --- | ---: | ---: | ---: | ---: |
| 1 (accepted DEC-056 baseline) | 651 | 0 | 860 | 911 |
| 2 | 422 | 229 | 612 | 658 |
| 3 | 286 | 365 | 451 | 492 |
| 4 | 215 | 436 | 362 | 399 |
| 5 | 145 | 506 | 274 | 306 |
| 10 | 37 | 614 | 104 | 121 |

| Location | Known 100+ negatives: count ≥1 | ≥2 | ≥3 | ≥5 |
| --- | ---: | ---: | ---: | ---: |
| Sofia / Vitosha | 159 | 93 | 62 | 27 |
| Zlatitsa | 83 | 51 | 34 | 12 |
| Sopot | 217 | 164 | 132 | 78 |
| Nevsha | 26 | 13 | 9 | 5 |
| Shumen | 131 | 80 | 41 | 22 |
| Pastrina | 20 | 12 | 6 | 1 |
| Dobrich region | 15 | 9 | 2 | 0 |

**Recommendation:** retain the accepted one-flight audit policy and compare
count ≥1/≥2/≥3 in chronological development validation before selecting a
different label policy. Count ≥2 is a reasonable first stricter experiment;
≥3 should be a sensitivity cohort, not an unquestioned universal rule.
Count ≥5 removes 77.7% of currently known 100+ negatives and erases Dobrich's
negative support. Global planning minima conceal that local damage.

A stricter count changes the sampled population, not just label quality.
Keeping all 293 confirmed 100+ positives while retaining only 145 negatives
raises the selected positive share from 31.0% to 66.9%. That is selection
bias, not evidence that the real opportunity probability doubled. Do not
calibrate operational probabilities from a balanced or activity-filtered cohort
without stating its population and accounting for the selection.

Observed counts belong to **label provenance and audit filters**, not weather
predictor inputs: tomorrow's realised flight count, maximum distance, or total
distance are unavailable at forecast issue time. Feeding them to the predictor
would leak the target. Weather-only models remain conditional on the observed
source/activity process; this dataset cannot independently validate the
unconditional chance on no-flight days.

## Training, tuning, calibration, and historical backtesting

Reserve complete **joined examples**, not only GFS files. Flights provide the
outcome `y`; historical pre-issue GFS provides the inputs `X`. A held-out target
day's flight labels must not fit the predictor, feature selection, scaling,
imputation, calibration, or alert threshold. Loading all raw evidence into
SQLite and calculating its labels is compatible with this reservation.

Recommended initial protocol, subject to acceptance and a recomputed repaired
2025 label audit:

1. **Development: source seasons 2022–2024.** Use expanding chronological
   folds, such as 2022 → 2023 and 2022–2023 → 2024, for baseline selection,
   regularization, feature choices, and negative-policy sensitivity. No fold
   may train on a later season to predict an earlier one.
2. **Final historical test: source season 2025.** Fix model, cohort policy,
   calibration approach, and alert thresholds before evaluating it. Use the
   completed repaired evidence, and do not choose only its famous record days.
   Evaluate all known eligible positives and negatives, preserving the site's
   and season's natural selected prevalence, plus a separate unknown-day
   demonstration cohort without binary scoring.
3. **Calibration:** use genuinely out-of-time development predictions, or a
   separate temporal calibration block, from models that did not fit those
   target outcomes. Keep final 2025 test labels out of calibration. There are
   too few 300+ development events for credible fitted 300+ calibration.
   Avoid splitting the already tiny rare-event cohort into four arbitrary
   random sets just to give each use a name.
4. **Grouping:** all sites for one target calendar date, and that site's
   D+1/D+2/D+3 rows, must follow the same date split. Flights within one
   site-day never become independent rows. Weather episodes can correlate
   adjacent dates; report by season and consider calendar gaps at boundaries
   that prevent shared issue/run windows spanning train and test. Exact gap
   semantics belong to the versioned split manifest, not a silent default.
5. **After evaluation:** a production refit may use all then-eligible seasons,
   including 2025. Retain the frozen pre-refit model and its out-of-sample
   predictions/report. A model trained on 2025 can show a historical replay,
   but cannot claim that replay as unseen historical performance; its next
   independent evaluation needs later untouched data or proper rolling-origin
   predictions.

Current counts for the strict all-three-known cohort, before GFS missingness
or any proposed boundary gap:

| Role | Site-days | 100+ positive | 200+ positive | 300+ positive |
| --- | ---: | ---: | ---: | ---: |
| 2022–2023, earlier development | 444 | 123 | 23 | 2 |
| 2024, later development validation | 292 | 89 | 19 | 1 |
| 2022–2024, combined development | 736 | 212 | 42 | 3 |
| 2025, provisional final test eligibility | 183 | 56 | 17 | 5 |

The 183 figure is a conservative historical subset, not a current cohort.
The completed repair changed flights, dates, and activity counts. Merely
reserving the eight 300+ dates is not an adequate test:
false positives and calibration require held-out negatives too. Three horizons
would produce up to 2,757 rows from today's 919 complete vectors, but still
only 919 site-day outcomes, and fewer independent weather events.

For T-026 report per horizon, threshold, site, and season: event counts,
precision/recall and false-positive/false-negative examples, ranking performance,
probability calibration and Brier/log loss where supported, with uncertainty
estimated in date/episode groups. Overall accuracy is misleading for 300+:
predicting negative everywhere is already correct on 911/919 complete vectors
(99.1%). T-025 confidence must reflect rare events, absent local classes,
out-of-season or missing data, and weather/model uncertainty; it is not the
same quantity as `p_100`, `p_200`, or `p_300`.

This methodology follows the official guidance on
[time-dependent/grouped validation](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-of-time-series-data),
[training/test leakage](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage),
and [separate calibration evidence](https://scikit-learn.org/stable/modules/calibration.html).
It does not select or install a modeling library.

## Weather readiness and next steps

SQLite has **28 daily feature snapshots from four weather runs**, seven site
snapshots per run. Only two target dates are historical: **2 August 2025** and
**3 October 2023**; the other dates are operational September 2026 samples.
This is technical pipeline evidence, not a weather-backed training dataset.
The existing explicit 00Z historical runs are not yet proven to be the newest
complete pre-20:00 cycle for their horizons under DEC-055. Do not automatically
count those snapshots as compliant joined training rows.

Before broad weather acquisition, T-020 should:

1. Use the completed repaired 2025 run and recompute the flight inventory
   through the deterministic production audit.
2. Implement its deterministic production tri-state audit with full provenance,
   mature coverage, out-of-window states, and declared negative-policy version.
   Keep all confirmed positives and unknown reasons in the evidence outputs.
3. Record an accepted split/cohort plan and generate the bounded GFS acquisition
   manifest for both development and held-out test dates, using each horizon's
   exact issue cutoff. Do not download a different kind of GFS forecast for
   test dates. Sampling, if storage requires it, must preserve scarce positive
   events and record sampling probabilities; calibration/test distributions
   cannot silently become balanced case-control samples.
4. Verify a bounded multi-season/site/horizon technical sample and actual
   compact storage size before approving the main batch.

Additional flight collection is most valuable for sparse locations and truly
new 300+ event dates, not more flights from an existing record day. The four
seasons exceed rough pooled 100+ and 200+ inventory checkpoints; they do not
meet the 300+ checkpoint. More collection should be a deliberate next scope,
not an implied continuation of this analysis. T-022/T-024 baselines and T-039
GFS/IGRA validation have separate evidence requirements; flight-distance labels
do not become cloudbase or overdevelopment ground truth. T-038 ERA5 remains
deferred and cannot replace pre-cutoff GFS.

## Reproduction and limitations

Local generated outputs are ignored and contain no pilot fields:

- `data/processed/flight-label-review-2026-09-29/analyze.py`
- `data/processed/flight-label-review-2026-09-29/summary.json`
- `data/processed/flight-label-review-2026-09-29/site-days.jsonl`
- Two `raw-audit-<run-key>.json` evidence files.

Run locally against the same database and artifact tree:

```powershell
uv run --no-sync --project services/ml python data/processed/flight-label-review-2026-09-29/analyze.py
```

The scratch script is deliberately not a supported clean-checkout command or
the future production dataset builder. It verifies SQLite integrity, unique
identities, positive-distance/approved-mapping constraints, manifest/stage
hashes, terminal mapping review, accepted-file equality, nested labels,
count reconciliation, and unchanged database bytes. Production reproducibility
must be implemented and tested in T-020, including its complete audit manifest.

Verification completed: two final executions produced byte-identical
`summary.json` and `site-days.jsonl`; scratch-script Ruff lint and format checks
passed; `npm.cmd run repo:check` and `git diff --check` passed. No product code
changed, so product build/test suites were not rerun for this analysis.

Recorded flight achievement is not weather-only potential, a safety label, or
proof of guaranteed flyability. These are observed source cohorts and planning
inferences; sufficiency for useful forecasts can only be established after
the weather join and honest out-of-time evaluation.
