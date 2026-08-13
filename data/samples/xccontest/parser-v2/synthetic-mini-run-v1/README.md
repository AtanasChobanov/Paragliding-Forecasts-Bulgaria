# XCContest parser-v2 synthetic mini-run v1

This is a small, deterministic fixture for the offline XCContest parser. It is
not an XCContest download, a seasonal dataset, an export, or a record of a real
pilot or flight.

## Origin, permission, and sanitation

All HTML, flight IDs, pilot placeholders, launch names, coordinates, dates,
distances, URLs, and manifest timestamps in this directory were authored for
this repository on 2026-08-13. The XCContest domain and rendered-DOM shape are
used only to exercise the accepted parser contract. The detail and search URL
paths are synthetic and must not be fetched.

No content was copied from a live page or local raw run. The fixture contains no
real pilot name, account data, cookies, headers, track files, private data, or
source-collected page. `SYNTHETIC PILOT — OMIT FROM OUTPUT` is a redaction
sentinel: the regression test proves that list-row pilot text never reaches the
normalized output.

Because the content is project-authored synthetic data, it is safe to commit and
redistribute under the repository's eventual licence. It does not grant a right
to retrieve, retain, or redistribute XCContest data. Live/raw data remains
ignored under `data/raw`.

## Layout and use

- `input/` is a complete immutable manifest-v3 raw-run layout. Its artifact
  paths intentionally refer to `data/raw/xccontest/t015-synthetic-mini-run-v1/`
  so the test can copy it unchanged into an isolated temporary project root.
- `expected/` contains reviewed golden parser-v2 outputs. Do not regenerate
  them automatically from a changed parser; review every intentional parser
  contract change and update the fixture version or goldens explicitly.
- `services/ml/tests/ingestion/xccontest/test_parser_fixtures.py` copies the
  input, invokes the real `parse_run`, and compares normalized JSONL,
  rejections, and the report with these goldens.

Run only this fixture-based integration/regression test from the repository
root:

```powershell
uv run --project services/ml pytest `
  services/ml/tests/ingestion/xccontest/test_parser_fixtures.py -vv
```

The test makes no browser or network request and does not access SQLite.

## Coverage matrix

| Case | Fixture evidence | Expected parser behaviour |
| --- | --- | --- |
| Manifest-v3 contract | Complete two-season manifest, SHA-256s, counters, source pacing | Validates immutable inputs before parsing |
| Legacy/current URL shapes | 2024 year-prefixed and 2026 current detail paths | Retains canonical HTTPS source URL |
| 100/200/300 km thresholds | IDs `150001`, `150002`, `150003`, `150004`, `150005` | Preserves 100.00, 199.99, 200.00, 299.99, and 300.00 km exactly |
| Points are not kilometres | ID `150001` has `999.99` points and `100.00` km | Reads the `td.km` score, not points |
| Decimal separators | ID `150009` uses `150,50` km | Normalizes to `150.5` km |
| Route values | Five supported route titles; absent route; `race to goal` | Produces supported values, `unknown`, and `other` with raw evidence |
| Timezone/season boundary | 2024 starts 2023-10-01 and ends 2024-09-30 | Emits correct UTC timestamps within the season |
| Launch evidence | With point, without point, and empty point token | Preserves name/search URL and handles optional coordinates deliberately |
| Exact overlap duplicate | `150001` occurs identically in two artifacts | Produces one normalized record with both artifact references |
| Conflicting overlap duplicate | `150002` has two distance values | Produces one conflicted candidate without choosing a value |
| Threshold/malformed rows | `150006`, `150007`, `150008` | Records an under-threshold rejection, bad duration rejection, and unavailable detail rejection |
| Pilot sanitation | Every row includes the sentinel pilot text | Does not serialize pilot text in any parser output |

The fixture intentionally does not test browser navigation, authentication or
HTTP responses, no-results screens, pagination/saturation, rate limiting, or
collector retries. Those are collector/browser concerns and remain covered by
their separate fake-driver tests; they are not part of the offline parser
boundary.
