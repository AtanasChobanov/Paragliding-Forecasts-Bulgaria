"""Offline batch composition and immutable, atomic publication of cloudbase outputs."""

from __future__ import annotations

import json
import platform
import tempfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from statistics import mean

from ...ingestion.weather.serialization import canonical_json_bytes, pretty_json_bytes, sha256_bytes
from .calculation import aggregate_day, calculate_hour
from .inputs import read_inputs
from .policy import METHOD_VERSION, POLICY, SCHEMA_VERSION


def _jsonl(records) -> bytes:
    return b"".join(canonical_json_bytes(record) for record in records)


def _report(hourly, daily) -> str:
    regimes = Counter(hour.regime for hour in hourly)
    warnings = Counter(flag for hour in hourly for flag in hour.limitations)
    reasons = Counter(reason for hour in hourly for reason in hour.reason_codes)
    lines = [
        "# Cloudbase baseline report",
        "",
        f"Method: `{METHOD_VERSION}`.",
        "",
        "This is an uncalibrated forecast of locally generated cumulus, not observed cloud base,",
        "a cloud-top prediction, a clear-sky guarantee or a usable-thermal-height forecast.",
        "MSL is model-ground anchored; site AGL is height relative to the archived site elevation.",
        "Negative site AGL is preserved. Terrain mismatch is not physically corrected.",
        "",
        f"Hourly records: {len(hourly)}. Site/date/horizon summaries: {len(daily)}.",
        "",
        "## Hourly regimes",
        "",
        *[
            f"- {key}: {regimes[key]}"
            for key in ("cumulus", "blue", "other_cloud", "indeterminate", "missing")
        ],
        "",
        "## Limitations",
        "",
        *[f"- {key}: {value}" for key, value in sorted(warnings.items())],
        "",
        "## Reasons",
        "",
        *[f"- {key}: {value}" for key, value in sorted(reasons.items())],
        "",
        "## Full-model versus stored LCL",
        "",
        "Differences below compare computations, not accuracy against observations.",
        "",
        "| Site | Paired hours | Mean absolute difference, m | Maximum absolute difference, m |",
        "| --- | ---: | ---: | ---: |",
    ]
    pairs = defaultdict(list)
    for hour in hourly:
        value = hour.diagnostics.get("stored_lcl_difference_m")
        if value is not None:
            pairs[hour.site_slug].append(abs(value))
    for site, values in sorted(pairs.items()):
        lines.append(f"| {site} | {len(values)} | {mean(values):.2f} | {max(values):.2f} |")
    lines += [
        "",
        "## Daily maxima",
        "",
        "Expected maxima use estimated cumulus hours; potential maxima use indeterminate hours only.",
        "Expected values take display priority. A potential LCL is conditional, not the base of existing cloud.",
        "Coverage complete describes regime classification, not input availability or height accuracy.",
        "A partial maximum does not establish the maximum for an unresolved full day.",
        "",
        *[
            f"- {state}: {count}"
            for state, count in sorted(Counter(d.summary_state for d in daily).items())
        ],
        "",
        "| Date | Site | Horizon | State / displayed quantity | Max MSL, m | Above site, m | Time UTC | Coverage complete | Significant cloud times (local) |",
        "| --- | --- | ---: | --- | ---: | ---: | --- | --- | --- |",
    ]
    for day in daily:
        height = day.max_cloudbase or day.max_potential_base
        timestamp = (day.max_at_utc if day.max_cloudbase else day.potential_max_at_utc) or "-"
        cloudy = ", ".join(h.valid_at_local[11:16] for h in day.significant_cloud_hours) or "-"
        z = "-" if height is None else f"{height.msl_m:.2f}"
        agl = "-" if height is None else f"{height.site_agl_m:.2f}"
        lines.append(
            f"| {day.target_local_date} | {day.site_slug} | {day.horizon_days} | {day.summary_state} | {z} | {agl} | {timestamp} | {day.coverage_complete} | {cloudy} |"
        )
    return "\n".join(lines) + "\n"


def _publish(directory: Path, files: dict[str, bytes], identity: dict) -> None:
    def verify_existing():
        expected_names = {*files, "manifest.json"}
        if {path.name for path in directory.iterdir()} != expected_names:
            raise ValueError("Existing cloudbase artifact has unexpected or missing files.")
        existing = json.loads((directory / "manifest.json").read_bytes())
        timestamp = existing.pop("created_at_utc", None)
        if not isinstance(timestamp, str) or datetime.fromisoformat(
            timestamp
        ).utcoffset() != UTC.utcoffset(None):
            raise ValueError("Existing artifact has invalid creation metadata.")
        if existing != identity or any(
            (directory / name).read_bytes() != value for name, value in files.items()
        ):
            raise ValueError("Existing immutable cloudbase artifact differs from its identity.")

    if directory.exists():
        verify_existing()
        return
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".cloudbase-", dir=directory.parent) as temporary:
        staging = Path(temporary) / "artifact"
        staging.mkdir()
        for name, value in files.items():
            (staging / name).write_bytes(value)
        manifest = {**identity, "created_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
        (staging / "manifest.json").write_bytes(pretty_json_bytes(manifest))
        try:
            staging.rename(directory)
        except FileExistsError:
            verify_existing()


def build_predictions(
    run_keys: list[str], *, project_root: Path, database_url: str | None = None
) -> dict:
    """Compute only explicitly selected retained forecasts; never fetch or train."""
    if not run_keys:
        raise ValueError("At least one run-key is required.")
    inputs, evidence = [], []
    for key in sorted(set(run_keys)):
        rows, source = read_inputs(key, project_root=project_root, database_url=database_url)
        if not rows or any(row.run_key != key for row in rows):
            raise ValueError("Input reader returned an empty or mismatched run.")
        inputs.extend(rows)
        evidence.append(source)
    inputs.sort(key=lambda row: (row.run_key, row.site_id, row.valid_at_utc))
    if len({(row.run_key, row.site_id, row.valid_at_utc) for row in inputs}) != len(inputs):
        raise ValueError("Duplicate prediction input identity.")
    hourly = [calculate_hour(hour) for hour in inputs]
    grouped = defaultdict(list)
    for hour in hourly:
        grouped[(hour.run_key, hour.site_id)].append(hour)
    daily = [aggregate_day(grouped[key]) for key in sorted(grouped)]
    files = {
        "policy.json": pretty_json_bytes(POLICY.as_dict()),
        "inputs.jsonl": _jsonl(inputs),
        "hourly.jsonl": _jsonl(hourly),
        "daily.jsonl": _jsonl(daily),
        "report.md": _report(hourly, daily).encode("utf-8"),
    }
    contents = {
        "schema_version": SCHEMA_VERSION,
        "method_version": METHOD_VERSION,
        "policy_version": POLICY.version,
        "validation_status": POLICY.validation_status,
        "numerical_versions": {name: version(name) for name in ("metpy", "numpy", "scipy", "pint")},
        "python_version": platform.python_version(),
        "sources": evidence,
        "run_keys": sorted(set(run_keys)),
        "hourly_count": len(hourly),
        "daily_count": len(daily),
        "daily_state_counts": dict(sorted(Counter(day.summary_state for day in daily).items())),
        "regime_counts": dict(sorted(Counter(hour.regime for hour in hourly).items())),
        "files": {
            name: {"sha256": sha256_bytes(value), "byte_count": len(value)}
            for name, value in sorted(files.items())
        },
    }
    artifact_id = sha256_bytes(canonical_json_bytes(contents))
    identity = {**contents, "artifact_id": artifact_id}
    directory = project_root / "data" / "processed" / "cloudbase" / artifact_id
    _publish(directory, files, identity)
    return {
        "artifact_id": artifact_id,
        "output_directory": str(directory.resolve()),
        "hourly_count": len(hourly),
        "daily_count": len(daily),
        "regime_counts": contents["regime_counts"],
        "daily_state_counts": contents["daily_state_counts"],
        "network_access": False,
        "database_access": "read_only",
        "validation_status": POLICY.validation_status,
    }
