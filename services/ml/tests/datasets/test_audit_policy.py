from __future__ import annotations

import json

import pytest

from paragliding_forecasts_ml.datasets.audit_policy import load_policy
from paragliding_forecasts_ml.datasets.flight_labels import LabelAuditError


def document():
    return {
        "schema_version": 1,
        "policy_version": "synthetic-reviewed-snapshot/1",
        "coverage_runs": [
            {"run_key": "11111111-1111-4111-8111-111111111111", "seasons": [2027], "mature": True}
        ],
    }


def test_new_season_and_run_are_configuration_not_python(tmp_path):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(document()))
    policy = load_policy(path)
    assert policy.seasons == (2027,)
    assert policy.runs["11111111-1111-4111-8111-111111111111"]["mature"] is True
    assert policy.sha256 == load_policy(path).sha256


@pytest.mark.parametrize(
    "change", ["version", "uuid", "mature", "duplicate", "overlap", "season", "keys"]
)
def test_invalid_or_ambiguous_policy_is_rejected(tmp_path, change):
    value = document()
    entry = value["coverage_runs"][0]
    if change == "version":
        value["schema_version"] = 99
    elif change == "uuid":
        entry["run_key"] = "../unsafe"
    elif change == "mature":
        entry["mature"] = "true"
    elif change == "duplicate":
        entry["seasons"] = [2027, 2027]
    elif change == "overlap":
        value["coverage_runs"].append({**entry, "run_key": "22222222-2222-4222-8222-222222222222"})
    elif change == "season":
        entry["seasons"] = [True]
    else:
        value["guessed_policy"] = True
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(value))
    with pytest.raises(LabelAuditError):
        load_policy(path)
