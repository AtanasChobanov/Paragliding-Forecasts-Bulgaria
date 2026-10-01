"""Deterministic site-day labels; realised flight evidence is never a predictor."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

VERSION = "site-day-flight-label-audit/2"
POLICY = "DEC-056-positive-distance-minimum-1/1"
THRESHOLDS = (100, 200, 300)
TIMEZONE = ZoneInfo("Europe/Sofia")


class LabelAuditError(RuntimeError):
    """The evidence cannot support a reproducible audit."""


def flying_date(timestamp: str) -> date:
    value = datetime.fromisoformat(timestamp)
    if value.tzinfo is None:
        raise LabelAuditError("Flight timestamp must include a timezone.")
    return value.astimezone(TIMEZONE).date()


def source_season(day: date) -> int:
    return day.year + int(day.month >= 10)


def season_dates(season: int):
    day = date(season - 1, 10, 1)
    while day < date(season, 10, 1):
        yield day
        day += timedelta(days=1)


def build_rows(
    sites: list[dict[str, Any]],
    flights: list[dict[str, Any]],
    coverage: dict[tuple[int, str, str], dict[str, Any]],
    seasons: tuple[int, ...],
) -> list[dict[str, Any]]:
    """Enumerate the database site catalog, grouping only by site and local date."""
    site_ids = {s["id"] for s in sites}
    if not sites or len(site_ids) != len(sites) or len({s["slug"] for s in sites}) != len(sites):
        raise LabelAuditError("The canonical site catalog must be nonempty with unique IDs/slugs.")
    groups = defaultdict(list)
    identities = set()
    for flight in flights:
        if flight["site_id"] not in site_ids:
            raise LabelAuditError("Flight maps outside the canonical site catalog.")
        identity = (flight["source_id"], flight["source_flight_id"])
        if identity in identities:
            raise LabelAuditError("Duplicate canonical source flight.")
        identities.add(identity)
        distance = flight["scored_distance_km"]
        if not math.isfinite(distance) or not 0 <= distance <= 2000:
            raise LabelAuditError("Invalid accepted distance.")
        day = flying_date(flight["takeoff_at_utc"])
        if source_season(day) in seasons and distance > 0:
            groups[(flight["site_id"], day.isoformat())].append(flight)
    rows = []
    for season in sorted(seasons):
        for day in season_dates(season):
            for site in sorted(sites, key=lambda s: s["id"]):
                records = groups.get((site["id"], day.isoformat()), [])
                maximum = max((r["scored_distance_km"] for r in records), default=None)
                evidence = coverage.get((season, day.isoformat(), site["country_code_iso2"]))
                if evidence is None:
                    raise LabelAuditError("Coverage must explicitly enumerate every date/country.")
                labels = {}
                for threshold in THRESHOLDS:
                    positive_ids = sorted(
                        r["source_flight_id"]
                        for r in records
                        if r["scored_distance_km"] >= threshold
                    )
                    if positive_ids:
                        state, reason = "positive", "accepted_threshold_flight"
                    elif not records:
                        state, reason = "unknown", "no_accepted_positive_distance_activity"
                    else:
                        blockers = [
                            reason
                            for ok, reason in (
                                (evidence["mature"], "evidence_not_mature"),
                                (
                                    evidence["activity_state"] in {"complete", "empty"},
                                    evidence["activity_reason"],
                                ),
                                (evidence["mapping_complete"], "unresolved_mapping"),
                                (
                                    evidence["threshold_complete"][str(threshold)],
                                    "incomplete_threshold_evidence",
                                ),
                            )
                            if not ok
                        ]
                        state = "unknown" if blockers else "negative"
                        reason = (
                            blockers[0]
                            if blockers
                            else "accepted_activity_and_complete_mature_coverage"
                        )
                    labels[str(threshold)] = {
                        "state": state,
                        "reason": reason,
                        "positive_source_flight_ids": positive_ids,
                    }
                for low, high in ((100, 200), (200, 300)):
                    if (
                        labels[str(high)]["state"] == "positive"
                        and labels[str(low)]["state"] != "positive"
                    ):
                        raise LabelAuditError("Non-nested positive labels.")
                    if (
                        labels[str(low)]["state"] == "negative"
                        and labels[str(high)]["state"] != "negative"
                    ):
                        raise LabelAuditError("Non-nested negative labels.")
                rows.append(
                    {
                        "schema_version": VERSION,
                        "negative_policy_version": POLICY,
                        "data_state": "real" if records else "missing",
                        "site_id": site["id"],
                        "site_slug": site["slug"],
                        "local_date": day.isoformat(),
                        "source_season": season,
                        "timezone": "Europe/Sofia",
                        "flight_count": len(records),
                        "max_distance_km": maximum,
                        "total_distance_km": round(
                            math.fsum(r["scored_distance_km"] for r in records), 2
                        ),
                        "labels": labels,
                        "coverage": evidence,
                        "flights": [
                            {
                                key: r[key]
                                for key in (
                                    "id",
                                    "source_id",
                                    "source_flight_id",
                                    "source_site_mapping_id",
                                    "takeoff_at_utc",
                                    "scored_distance_km",
                                    "evidence_run_key",
                                )
                            }
                            for r in sorted(
                                records, key=lambda r: (r["source_id"], r["source_flight_id"])
                            )
                        ],
                        "all_labels_known": all(v["state"] != "unknown" for v in labels.values()),
                    }
                )
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "site_days": len(rows),
        "active_site_days": sum(r["flight_count"] > 0 for r in rows),
        "accepted_positive_distance_flights": sum(r["flight_count"] for r in rows),
        "active_dates": len({r["local_date"] for r in rows if r["flight_count"]}),
        "all_labels_known": sum(r["all_labels_known"] for r in rows),
        "observed_maximum_patterns": dict(
            sorted(
                Counter(
                    "".join(str(int(r["max_distance_km"] >= t)) for t in THRESHOLDS)
                    for r in rows
                    if r["flight_count"]
                ).items()
            )
        ),
        "below_100_activity_counts": dict(
            sorted(
                Counter(
                    str(r["flight_count"])
                    for r in rows
                    if r["flight_count"] and r["max_distance_km"] < 100
                ).items()
            )
        ),
        "negative_activity_sensitivity": {
            str(minimum): {
                str(t): {
                    "positive": sum(r["labels"][str(t)]["state"] == "positive" for r in rows),
                    "negative": sum(
                        r["labels"][str(t)]["state"] == "negative" and r["flight_count"] >= minimum
                        for r in rows
                    ),
                    "negative_to_unknown": sum(
                        r["labels"][str(t)]["state"] == "negative" and r["flight_count"] < minimum
                        for r in rows
                    ),
                }
                for t in THRESHOLDS
            }
            for minimum in (1, 2, 3)
        },
        "thresholds": {
            str(t): {
                **{
                    state: sum(r["labels"][str(t)]["state"] == state for r in rows)
                    for state in ("positive", "negative", "unknown")
                },
                "positive_dates": len(
                    {r["local_date"] for r in rows if r["labels"][str(t)]["state"] == "positive"}
                ),
                "unknown_reasons": dict(
                    sorted(
                        Counter(
                            r["labels"][str(t)]["reason"]
                            for r in rows
                            if r["labels"][str(t)]["state"] == "unknown"
                        ).items()
                    )
                ),
            }
            for t in THRESHOLDS
        },
    }
