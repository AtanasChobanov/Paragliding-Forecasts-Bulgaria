"""Offline, immutable T-020 flight cohort and GFS request planning."""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from importlib import resources
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from paragliding_forecasts_ml.ingestion.gfs.models import sofia_window_instants
from paragliding_forecasts_ml.storage.sqlite import repository_root

VERSION = "weather-cohort-plan/2"
LABEL_VERSION = "site-day-flight-label-audit/2"
OUTPUT_NAMES = (
    "selected_site_days.jsonl",
    "unselected_development_site_days.jsonl",
    "acquisition_jobs.jsonl",
    "summary.json",
)


class CohortPlanError(RuntimeError):
    """The frozen audit or cohort policy cannot support a safe offline plan."""


def _encoded(value: Any) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_hash(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise CohortPlanError("Expected a lowercase SHA-256 identity.")
    return value


def _read_policy(path: Path | None) -> tuple[dict[str, Any], str]:
    content = (
        path.read_bytes()
        if path is not None
        else resources.files("paragliding_forecasts_ml.datasets")
        .joinpath("resources", "weather-cohort-policy.json")
        .read_bytes()
    )
    policy = json.loads(content)
    expected = {
        "schema_version",
        "policy_version",
        "source_audit_id",
        "development_seasons",
        "backtest_seasons",
        "development_positive_100_quota",
        "development_negative_100_quota",
        "mandatory_positive_threshold_km",
        "rare_site_positive_100_max",
        "selection_seed",
        "technical_sample_target_dates",
        "source_ready_time_local",
        "delivery_time_local",
        "cycle_hour_utc",
        "timezone",
        "flying_window_version",
        "horizons_days",
    }
    if not isinstance(policy, dict) or set(policy) != expected or policy["schema_version"] != 2:
        raise CohortPlanError("Unsupported weather-cohort policy schema.")
    _require_hash(policy["source_audit_id"])
    if any(
        not isinstance(policy[k], str) or not policy[k]
        for k in ("policy_version", "selection_seed")
    ):
        raise CohortPlanError("Policy version and selection seed are required.")
    development, backtest = policy["development_seasons"], policy["backtest_seasons"]
    if (
        any(
            not isinstance(years, list)
            or not years
            or any(type(y) is not int or not 2000 <= y <= 2100 for y in years)
            or len(set(years)) != len(years)
            for years in (development, backtest)
        )
        or set(development) & set(backtest)
        or max(development) >= min(backtest)
    ):
        raise CohortPlanError("Development and backtest seasons must be unique and chronological.")
    for key in ("development_positive_100_quota", "development_negative_100_quota"):
        if type(policy[key]) is not int or policy[key] < 1:
            raise CohortPlanError(f"Invalid cohort quota: {key}.")
    if policy["mandatory_positive_threshold_km"] not in (200, 300):
        raise CohortPlanError("Mandatory positive threshold must be 200 or 300 km.")
    if (
        type(policy["rare_site_positive_100_max"]) is not int
        or policy["rare_site_positive_100_max"] < 0
    ):
        raise CohortPlanError("Invalid rare-site threshold.")
    if (
        policy["source_ready_time_local"] != "16:00"
        or policy["delivery_time_local"] != "20:00"
        or type(policy["cycle_hour_utc"]) is not int
        or policy["cycle_hour_utc"] != 6
        or policy["timezone"] != "Europe/Sofia"
        or policy["flying_window_version"] != "sofia-flying-window/1"
        or policy["horizons_days"] != [1, 2, 3]
    ):
        raise CohortPlanError("This planner implements the fixed 06Z evening policy only.")
    sample_dates = policy["technical_sample_target_dates"]
    if (
        not isinstance(sample_dates, list)
        or not sample_dates
        or len(set(sample_dates)) != len(sample_dates)
    ):
        raise CohortPlanError("Technical sample dates must be nonempty and unique.")
    try:
        for value in sample_dates:
            if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                raise ValueError(value)
    except ValueError as error:
        raise CohortPlanError("Technical sample dates must be ISO local dates.") from error
    return policy, _sha(content)


def _load_audit(directory: Path, audit_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    manifest_bytes = (directory / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    recorded_id = manifest.pop("audit_id", None)
    if recorded_id != audit_id or _sha(_encoded(manifest)) != audit_id:
        raise CohortPlanError("Label-audit manifest identity does not verify.")
    if (
        manifest.get("schema_version") != LABEL_VERSION
        or manifest.get("timezone") != "Europe/Sofia"
    ):
        raise CohortPlanError("Unsupported label-audit schema or timezone.")
    seasons = manifest.get("source_seasons")
    if (
        not isinstance(seasons, list)
        or not seasons
        or any(type(season) is not int for season in seasons)
        or len(set(seasons)) != len(seasons)
    ):
        raise CohortPlanError("Label audit must declare unique source seasons.")
    label_path = directory / "known_site_day_labels.jsonl"
    content = label_path.read_bytes()
    expected = manifest["outputs"][label_path.name]
    if _sha(content) != expected["sha256"] or len(content) != expected["bytes"]:
        raise CohortPlanError("Known-label output disagrees with its audit manifest.")
    rows = [json.loads(line) for line in content.splitlines()]
    identities: set[tuple[int, str]] = set()
    for row in rows:
        try:
            day = date.fromisoformat(row["local_date"])
            identity = (row["site_id"], row["local_date"])
            labels = row["labels"]
            states = tuple(labels[str(t)]["state"] for t in (100, 200, 300))
            valid = (
                row["local_date"] == day.isoformat()
                and row["source_season"] == day.year + (day.month >= 10)
                and row["source_season"] in seasons
                and row["schema_version"] == LABEL_VERSION
                and row["timezone"] == "Europe/Sofia"
                and row["all_labels_known"] is True
                and all(state in ("positive", "negative") for state in states)
                and states
                in (
                    ("negative", "negative", "negative"),
                    ("positive", "negative", "negative"),
                    ("positive", "positive", "negative"),
                    ("positive", "positive", "positive"),
                )
                and type(row["site_id"]) is int
                and identity not in identities
            )
        except (KeyError, TypeError, ValueError) as error:
            raise CohortPlanError("Malformed known site-day row.") from error
        if not valid:
            raise CohortPlanError("Duplicate, unknown, or inconsistent known site-day row.")
        identities.add(identity)
    return manifest, rows, _sha(manifest_bytes)


def _row_key(row: dict[str, Any]) -> tuple[str, int]:
    return row["local_date"], row["site_id"]


def _stratum(row: dict[str, Any]) -> tuple[str, int, str, str]:
    pattern = "".join(
        str(int(row["labels"][str(t)]["state"] == "positive")) for t in (100, 200, 300)
    )
    return (
        str(row["site_id"]),
        row["source_season"],
        row["local_date"][5:7],
        pattern,
    )


def _stratified_fill(
    candidates: list[dict[str, Any]], mandatory: set[tuple[str, int]], quota: int, seed: str
) -> tuple[set[tuple[str, int]], dict[tuple[str, int], tuple[int, int]]]:
    if len(mandatory) > quota or len(candidates) < quota:
        raise CohortPlanError("Mandatory rows exceed the quota or too few eligible rows exist.")
    groups: dict[tuple[str, int, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        if _row_key(row) not in mandatory:
            groups[_stratum(row)].append(row)
    seats = quota - len(mandatory)
    if len(groups) > seats:
        raise CohortPlanError(
            "Quota cannot represent every nonmandatory site/season/month/label stratum."
        )
    allocations = {key: 1 for key in groups}
    additional = seats - len(groups)
    capacity = {key: len(rows) - 1 for key, rows in groups.items()}
    total_capacity = sum(capacity.values())
    if additional > total_capacity:
        raise CohortPlanError("Quota exceeds eligible nonmandatory rows.")
    if additional:
        for key, available in capacity.items():
            allocations[key] += additional * available // total_capacity
        remainder = seats - sum(allocations.values())
        order = sorted(
            groups,
            key=lambda key: (
                -(additional * capacity[key] % total_capacity),
                _sha(f"{seed}|stratum|{key}".encode()),
            ),
        )
        for key in order[:remainder]:
            allocations[key] += 1
    selected = set(mandatory)
    inclusion = {key: (1, 1) for key in mandatory}
    for key, rows in sorted(groups.items()):
        ordered = sorted(
            rows,
            key=lambda row: (
                _sha(f"{seed}|{row['site_id']}|{row['local_date']}".encode()),
                _row_key(row),
            ),
        )
        selected.update(_row_key(row) for row in ordered[: allocations[key]])
        inclusion.update({_row_key(row): (allocations[key], len(rows)) for row in rows})
    if len(selected) != quota or len(inclusion) != len(candidates):
        raise CohortPlanError("Stratified selection did not reconcile.")
    return selected, inclusion


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fixed_cycle(issue: date, valid_times: tuple[str, ...]) -> list[dict[str, Any]]:
    cycle = datetime.combine(issue, time(6), tzinfo=UTC)
    leads = [
        int((datetime.fromisoformat(value) - cycle).total_seconds() // 3600)
        for value in valid_times
    ]
    if min(leads) < 0 or max(leads) > 120:
        raise CohortPlanError("The fixed 06Z cycle cannot cover the flying window.")
    return [{"cycle_reference_utc": _utc(cycle), "lead_hours": leads}]


def plan_weather_cohort(
    *,
    audit_id: str | None = None,
    audit_directory: Path | None = None,
    policy_file: Path | None = None,
    output_directory: Path | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Verify a frozen label audit, select site-days, and emit offline GFS requests."""
    root = (project_root or repository_root()).resolve()
    policy, policy_sha = _read_policy(policy_file)
    selected_audit_id = _require_hash(audit_id or policy["source_audit_id"])
    if selected_audit_id != policy["source_audit_id"]:
        raise CohortPlanError("Requested audit ID disagrees with cohort policy.")
    directory = (
        audit_directory or root / "data/processed/flight-label-audits" / selected_audit_id
    ).resolve()
    audit, rows, audit_manifest_sha = _load_audit(directory, selected_audit_id)
    if set(policy["development_seasons"] + policy["backtest_seasons"]) != set(
        audit["source_seasons"]
    ):
        raise CohortPlanError("Cohort policy must classify every audited source season.")
    development = [r for r in rows if r["source_season"] in policy["development_seasons"]]
    backtest = [r for r in rows if r["source_season"] in policy["backtest_seasons"]]
    positives = [r for r in development if r["labels"]["100"]["state"] == "positive"]
    negatives = [r for r in development if r["labels"]["100"]["state"] == "negative"]
    site_positives = Counter(r["site_id"] for r in positives)
    sample_dates = set(policy["technical_sample_target_dates"])
    available_dates = {r["local_date"] for r in rows}
    if not sample_dates <= available_dates:
        raise CohortPlanError("A technical sample date has no complete known label row.")
    mandatory_positive: set[tuple[str, int]] = set()
    mandatory_negative: set[tuple[str, int]] = set()
    reasons: dict[tuple[str, int], list[str]] = defaultdict(list)
    for row in development:
        key = _row_key(row)
        positive = row["labels"]["100"]["state"] == "positive"
        if row["local_date"] in sample_dates:
            (mandatory_positive if positive else mandatory_negative).add(key)
            reasons[key].append("technical_sample_date")
        if (
            positive
            and row["labels"][str(policy["mandatory_positive_threshold_km"])]["state"] == "positive"
        ):
            mandatory_positive.add(key)
            reasons[key].append("mandatory_high_threshold_positive")
        if positive and site_positives[row["site_id"]] <= policy["rare_site_positive_100_max"]:
            mandatory_positive.add(key)
            reasons[key].append("rare_site_positive")
    chosen_positive, positive_inclusion = _stratified_fill(
        positives,
        mandatory_positive,
        policy["development_positive_100_quota"],
        policy["selection_seed"] + "|positive",
    )
    chosen_negative, negative_inclusion = _stratified_fill(
        negatives,
        mandatory_negative,
        policy["development_negative_100_quota"],
        policy["selection_seed"] + "|negative",
    )
    chosen = chosen_positive | chosen_negative
    inclusion = positive_inclusion | negative_inclusion
    selected_rows = sorted(
        [r for r in development if _row_key(r) in chosen] + backtest, key=_row_key
    )
    unselected_rows = sorted((r for r in development if _row_key(r) not in chosen), key=_row_key)

    def entry(row: dict[str, Any], split: str) -> dict[str, Any]:
        key = _row_key(row)
        numerator, denominator = inclusion[key] if split != "backtest" else (1, 1)
        return {
            "site_id": row["site_id"],
            "site_slug": row["site_slug"],
            "target_local_date": row["local_date"],
            "source_season": row["source_season"],
            "split": split,
            "labels": {str(t): row["labels"][str(t)]["state"] for t in (100, 200, 300)},
            "label_row_sha256": _sha(_encoded(row)),
            "inclusion_probability": {"numerator": numerator, "denominator": denominator},
            "sampling_weight": denominator / numerator
            if split != "unselected_development"
            else None,
            "sampling_stratum": list(_stratum(row)),
            "selection_reasons": sorted(set(reasons[key]))
            if split == "development"
            else ["whole_2025_backtest"],
        }

    selected = [
        entry(r, "backtest" if r["source_season"] in policy["backtest_seasons"] else "development")
        for r in selected_rows
    ]
    unselected = [entry(r, "unselected_development") for r in unselected_rows]
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in selected:
        by_date[row["target_local_date"]].append(row)
    jobs = []
    for target in sorted(by_date):
        day = date.fromisoformat(target)
        split = by_date[target][0]["split"]
        if any(r["split"] != split for r in by_date[target]):
            raise CohortPlanError("One target date crosses development/backtest splits.")
        valid_times = sofia_window_instants(target)
        for horizon in policy["horizons_days"]:
            issue = day - timedelta(days=horizon)
            cutoff = datetime.combine(issue, time(16), tzinfo=ZoneInfo("Europe/Sofia"))
            jobs.append(
                {
                    "target_local_date": target,
                    "source_season": by_date[target][0]["source_season"],
                    "split": split,
                    "horizon_days": horizon,
                    "issue_local_date": issue.isoformat(),
                    "issue_cutoff_utc": _utc(cutoff),
                    "delivery_deadline_utc": _utc(
                        datetime.combine(issue, time(20), tzinfo=ZoneInfo("Europe/Sofia"))
                    ),
                    "site_ids": sorted(r["site_id"] for r in by_date[target]),
                    "valid_times_utc": list(valid_times),
                    "flying_window_version": policy["flying_window_version"],
                    "cycle_selection_status": "unresolved_metadata_probe",
                    "candidate_cycles": _fixed_cycle(issue, valid_times),
                }
            )
    summary = {
        "known_site_days": len(rows),
        "development_eligible_site_days": len(development),
        "development_selected_site_days": len(chosen),
        "development_selected_target_dates": len(
            {r["local_date"] for r in development if _row_key(r) in chosen}
        ),
        "development_selected_positive_100": len(chosen_positive),
        "development_selected_negative_100": len(chosen_negative),
        "development_unselected_site_days": len(unselected),
        "backtest_site_days": len(backtest),
        "backtest_target_dates": len({r["local_date"] for r in backtest}),
        "selected_target_dates": len(by_date),
        "acquisition_jobs": len(jobs),
        "jobs_by_split": dict(sorted(Counter(j["split"] for j in jobs).items())),
        "technical_sample_target_dates": sorted(sample_dates),
        "selection_method": "mandatory high-threshold/rare-site/sample rows, then at least one seeded hash-ranked row per nonmandatory site/season/month/label stratum with proportional largest-remainder allocation",
        "development_selection_fraction_by_100_class": {
            "positive": {"selected": len(chosen_positive), "eligible": len(positives)},
            "negative": {"selected": len(chosen_negative), "eligible": len(negatives)},
        },
        "selected_by_site_and_split": {
            split: dict(
                sorted(Counter(r["site_slug"] for r in selected if r["split"] == split).items())
            )
            for split in ("development", "backtest")
        },
        "selected_by_season": dict(
            sorted(Counter(str(r["source_season"]) for r in selected).items())
        ),
        "selected_by_calendar_month": dict(
            sorted(Counter(r["target_local_date"][5:7] for r in selected).items())
        ),
        "limitations": [
            "No GFS metadata or payload was requested; the fixed 06Z cycle is unverified.",
            "Selection probabilities are conditional on this frozen policy and audited eligible population; downstream calibration must define its target population and account for mandatory rows.",
            "Three horizons reuse one site-day flight outcome; they are not independent events.",
        ],
    }
    files = {
        "selected_site_days.jsonl": b"".join(_encoded(r) for r in selected),
        "unselected_development_site_days.jsonl": b"".join(_encoded(r) for r in unselected),
        "acquisition_jobs.jsonl": b"".join(_encoded(r) for r in jobs),
        "summary.json": _encoded(summary),
    }
    manifest = {
        "schema_version": VERSION,
        "source_audit_id": selected_audit_id,
        "source_audit_manifest_sha256": audit_manifest_sha,
        "source_known_labels_sha256": audit["outputs"]["known_site_day_labels.jsonl"]["sha256"],
        "policy": policy,
        "policy_sha256": policy_sha,
        "outputs": {
            name: {"bytes": len(data), "sha256": _sha(data)} for name, data in sorted(files.items())
        },
    }
    plan_id = _sha(_encoded(manifest))
    files["manifest.json"] = _encoded({**manifest, "plan_id": plan_id})
    destination = (output_directory or root / "data/processed/weather-cohorts" / plan_id).resolve()
    try:
        destination.relative_to((root / "data/processed").resolve())
    except ValueError as error:
        raise CohortPlanError("Cohort outputs must stay below ignored data/processed/.") from error
    if destination.exists():
        if (
            not destination.is_dir()
            or {p.name for p in destination.iterdir()} != set(files)
            or any((destination / name).read_bytes() != content for name, content in files.items())
        ):
            raise CohortPlanError("Existing cohort plan differs; refusing to overwrite it.")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".weather-cohort-build-", dir=destination.parent
        ) as temporary:
            staging = Path(temporary) / "plan"
            staging.mkdir()
            for name, content in files.items():
                (staging / name).write_bytes(content)
            staging.rename(destination)
    return {"plan_id": plan_id, "output_directory": str(destination), "summary": summary}
