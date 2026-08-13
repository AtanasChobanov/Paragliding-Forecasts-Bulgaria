# Committed samples

Only small, sanitized, redistributable fixtures used by automated tests belong
here. Each fixture should identify its source or synthetic origin, expected
schema, and the test that consumes it.

The first committed parser fixture is
[xccontest/parser-v2/synthetic-mini-run-v1](xccontest/parser-v2/synthetic-mini-run-v1/).
It is fully synthetic and is replayed by
services/ml/tests/ingestion/xccontest/test_parser_fixtures.py; see its README
for provenance, safety rules, and the coverage matrix.
