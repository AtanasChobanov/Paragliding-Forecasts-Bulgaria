# T-020 repaired flight evidence and negative-activity sensitivity — 30 September 2026

## Scope and result

This read-only exploratory review repeats the flight-label inventory after both
XCContest repairs. It compares requiring at least **one, two, or three accepted
positive-distance flights at the same site/date** before calling an otherwise
eligible below-threshold day negative. Confirmed threshold positives remain
positive at every minimum; a day failing the activity minimum becomes
`unknown`. The accepted DEC-056 policy remains one flight. These counts are
flight-label candidates, before any GFS availability, cutoff check, sampling,
model fitting, or calibrated performance claim.

The local SQLite database has **5,171 canonical positive-distance flights**.
Seasons 2022–2025 have **5,090 flights on 985 active site-days and 525 dates**;
81 older, threshold-only 2026 flights remain outside the negative cohort. The
repaired 2022–2024 run has 3,753 accepted flights, while the development
inventory includes one additional earlier canonical flight outside that run's
all-distance daily scope. The repaired 2025 run has 1,336 accepted flights.
The two repaired raw audits report zero inconsistent views (1,487 and 250
artifacts), and parser v3 replay accepted their dated artifacts. The preceding
[29 September report](T-020-flight-label-analysis-2026-09-29.md) remains a
pre-repair historical snapshot; use the figures here for the present comparison.

## Method and denominator

The local analysis reads SQLite in read-only/query-only mode and verifies its
integrity, artifact/stage hashes, accepted-file equality, terminal mapping
review, nested labels, and unchanged database bytes. It groups accepted
flights by canonical site and `Europe/Sofia` takeoff date; source seasons run
from 1 October through 30 September. A negative additionally requires a
complete daily all-distance scope and terminal mapping evidence. No-activity
days remain `unknown`, however many empty saved views exist. There is no
inference that missing XCContest flights mean poor weather.

Development here means **source seasons 2022–2024**; the repaired 2025 season
is the proposed, still unaccepted final historical test period. Counts refer
to site-days, not individual flights or independent weather events. At 100+,
the activity minimum applies to days whose maximum accepted distance is below
100 km. At 200+ and 300+, an accepted flight above 100 km but below that
threshold can likewise establish activity. Complete vectors are site-days
with all three threshold labels known under the tested minimum.

## All four source seasons after repair, 2022–2025

The complete current inventory has **985 active site-days / 5,090 flights /
525 distinct dates**. Including 2025 gives the following label counts:

| Minimum flights for a negative | 100+ positive | 100+ negative | 200+ positive | 200+ negative | 300+ positive | 300+ negative | Complete vectors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 (DEC-056) | 293 | 686 | 65 | 913 | 8 | 970 | 978 |
| 2 | 293 | 445 | 65 | 651 | 8 | 702 | 710 |
| 3 | 293 | 301 | 65 | 482 | 8 | 528 | 536 |

For **100+ pooled over all four seasons**, ≥3 produces a nearly balanced
**293 positive / 301 negative** candidate set. It is a numerically viable
experiment; class balance alone is not a reason to reject it. For honest
historical evaluation, however, fitting all four seasons would leave no
untouched 2025 season. The development/test rows below show what remains
under that proposed split. Of the 985 active site-days, **391** have an
unknown 100+ label under ≥3, compared with **6** under ≥1.

| Location | 100+ positive | Negative ≥1 | Negative ≥2 | Negative ≥3 |
| --- | ---: | ---: | ---: | ---: |
| Sofia / Vitosha | 32 | 172 | 102 | 69 |
| Zlatitsa | 12 | 83 | 51 | 34 |
| Sopot | 98 | 227 | 172 | 138 |
| Nevsha | 52 | 29 | 14 | 9 |
| Shumen | 80 | 139 | 84 | 43 |
| Pastrina | 14 | 20 | 12 | 6 |
| Dobrich region | 5 | 16 | 10 | 2 |
| **All seven** | **293** | **686** | **445** | **301** |

Even with repaired 2025 included, ≥3 leaves only **two** 100+ negative
site-days for Dobrich, **six** for Pastrina, and **nine** for Nevsha. This
limits site-level fitting and error analysis despite the good pooled balance.

## Development cohort, seasons 2022–2024

There are **738 active site-days / 3,754 flights / 389 distinct dates**. The
observed maximum-distance bands are below 100 / 100–199 / 200–299 / 300+ =
**525 / 171 / 39 / 3**. The below-100 days have exactly one/two/three flights
on **187 / 112 / 52** days; 174 have at least four. One below-100 day lacks
the complete daily evidence needed for a known negative. Another 100+ day is
confirmed positive but lacks sufficient coverage to make its higher-threshold
absences known.

| Minimum flights for a negative | 100+ positive | 100+ negative | 200+ positive | 200+ negative | 300+ positive | 300+ negative | Complete vectors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 (DEC-056) | 213 | 524 | 42 | 694 | 3 | 733 | 736 |
| 2 | 213 | 338 | 42 | 492 | 3 | 526 | 529 |
| 3 | 213 | 226 | 42 | 364 | 3 | 396 | 399 |

Against the one-flight policy, minimum two removes **186 (35.5%)** known
100+ negatives and **207 (28.1%)** complete vectors. Minimum three removes
**298 (56.9%)** known 100+ negatives and **337 (45.8%)** complete vectors.
Those rows become unknown, not positive. The selected 100+ positive share
among known examples rises from **28.9%** at one flight to **38.7%** at two
and **48.5%** at three. This shift is selection, not evidence that good XC
weather has become more common.

No classifier needs more negative rows than positive rows as a general rule.
The requirement is enough representative evidence for both outcomes in the
intended sites, seasons, and evaluation folds. A near-50/50 training ratio can
be useful computationally, but it does not itself improve label truth or
calibration. In the four-season inventory, ≥3 keeps all **293** confirmed
100+ positives, including **29** one-flight and **30** two-flight positive
days, while converting **385** low-activity known negatives to `unknown`.
The observed positive share of the remaining known 100+ rows moves from
**29.9%** (≥1) to **49.3%** (≥3). That asymmetry selects examples using
future flight activity, which is unavailable at forecast time; probabilities
fitted or calibrated on the restricted cohort may overstate the frequency of
100+ days in the broader recorded-activity cohort. A training sampler or
class weighting can adjust optimization without changing the audited label
policy; evaluation and calibration must still state their target cohort.

### 100+ examples by location

Each cell in the three negative columns is a count of known negative
site-days in the full 2022–2024 development period. Positive counts are
unchanged by the tested minimum.

| Location | 100+ positive | Negative ≥1 | Negative ≥2 | Negative ≥3 |
| --- | ---: | ---: | ---: | ---: |
| Sofia / Vitosha | 20 | 127 | 76 | 50 |
| Zlatitsa | 6 | 59 | 34 | 22 |
| Sopot | 75 | 181 | 140 | 114 |
| Nevsha | 41 | 19 | 8 | 5 |
| Shumen | 59 | 106 | 62 | 29 |
| Pastrina | 10 | 18 | 10 | 4 |
| Dobrich region | 2 | 14 | 8 | 2 |
| **All seven** | **213** | **524** | **338** | **226** |

The concern about losing local negative support is well founded. At ≥2,
Dobrich and Nevsha each have only eight 100+ negatives; Pastrina has ten.
At ≥3, Dobrich has two, Pastrina four, and Nevsha five. Even ≥1 leaves those
sites thin for independent site-specific estimates, but preserves substantially
more examples for pooled modeling and for checking site-level errors. The
positive side is also sparse: Zlatitsa has six and Dobrich only two 100+
development days. Retaining negatives alone cannot make a local classifier
reliable at those sites.

Seasonal validation makes the scarcity sharper. Dobrich's 2022/2023/2024
100+ negative counts are **1/9/4** at ≥1, **0/5/3** at ≥2, and **0/2/0** at
≥3. Nevsha's are **8/6/5**, then **4/2/2**, then **1/2/2**. Pastrina's are
**6/8/4**, then **5/3/2**, then **1/1/2**. Both Dobrich and Pastrina have
zero 100+ positives in 2024, so no activity threshold can support a
meaningful 2024 per-site positive-class evaluation there. Across all sites,
2024 known 100+ negatives fall from **203** at ≥1 to **139** at ≥2 and
**100** at ≥3; the 90 confirmed positives remain.

For 200+, the full development cohort has 42 confirmed positive site-days,
but only 23 are from Nevsha; Sofia/Vitosha and Zlatitsa have none. For 300+,
there are only three development positive site-days. More negative rows do not
resolve these positive-class limitations; the current evidence supports only
cautious pooled experiments for 100+ and 200+, and exploratory treatment of
300+.

## Repaired 2025 and all-season context

The repaired 2025 season contributes **1,336 flights on 247 active site-days**. Its observed
bands are **167 / 57 / 18 / 5**, so its confirmed 100+/200+/300+ positives
are **80 / 23 / 5**. Under minima 1/2/3, its known 100+ negatives are
**162 / 107 / 75**, and complete vectors are **242 / 181 / 137**. A stricter
policy would therefore shrink the proposed final historical test as well as
development, while leaving the confirmed positives fixed.

Across source seasons 2022–2025, the observed bands are **692 / 228 / 57 / 8**;
confirmed 100+/200+/300+ positives are **293 / 65 / 8**. The repair added
short-flight activity and repaired absence evidence; it did not add 100+
positive site-days. The 300+ count remains eight site-days on seven calendar
dates, far below the planning checkpoint of 30 independent events.

## Recommendation for T-020

Keep DEC-056's **one accepted positive-distance flight** as the default
audited negative minimum for now, provided the daily source and mapping
coverage checks pass. The stronger justification is representativeness and
local support, not a need for more negatives than positives: ≥3 is a viable
**pooled 100+ experiment** by count, but its local negatives are sparse and
its asymmetric selection changes the cohort that the learned probability
describes. ≥2 is also a reasonable sensitivity policy. Preserve flight
count, maximum distance, coverage, and reason fields in the production offline
audit; compare ≥1/≥2/≥3 in chronological development folds for ranking,
false positives/negatives, site coverage, and calibration. Only then choose
whether the extra activity evidence improves the outcome enough to justify
the narrower population, recording any change to DEC-056 explicitly before
using the reserved 2025 season for final testing. This analysis alone cannot
rank the three policies by predictive performance.

This comparison cannot prove that a singleton short flight represents an
attempt to fly 100 km, or that the absence of a longer recorded flight was
caused by weather. Nor does it establish model quality: historical GFS rows
still need an issue-time-valid join, and training, calibration, and final
testing must keep whole target dates and their outcomes separated.

## Reproduction and verification

Ignored local files under `data/processed/flight-label-review-2026-09-30/`
contain the scratch `analyze.py`, `compare_thresholds.py`, `summary.json`,
`site-days.jsonl`, `threshold-comparison.json`, and raw-audit JSON. They use
the repaired run keys `9c70c7a0-89f2-4a56-8b8e-a608eb3dde6e` and
`89841b61-c681-4008-b833-031d4aee636e`; the original 2025 run is not a
candidate input. The scripts are local analysis aids, not the T-020 offline
labeling command. The replay asserted unchanged SQLite bytes and produced
byte-identical summary, site-day, and comparison files twice. Both scratch
scripts pass Ruff check and format validation. This report records their
results so a later production audit can reconcile or correct them.
