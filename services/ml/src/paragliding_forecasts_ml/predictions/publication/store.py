"""Validate one GFS date's batches and publish its complete SQLite graph."""

from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from sqlite3 import Connection, Row

from ...ingestion.gfs.models import GFS_SOURCE_ID
from ...storage.sqlite import open_writable_database, resolve_database_path
from ..cloudbase.calculation import aggregate_day, conditional_base
from ..cloudbase.service import CloudbaseBatch
from ..cloudbase.service import load_prediction as load_cloudbase
from ..overdevelopment.artifacts import Manifest as OdManifest
from ..overdevelopment.artifacts import read_prediction as load_od
from ..xc_probability.models import AvailableMetric
from ..xc_probability.policy import load_policy
from ..xc_probability.prediction import PredictionBatch
from ..xc_probability.prediction import load_prediction as load_xc
from .drivers import Provenance, cloud_drivers, od_drivers, primary_cloud_reason, xc_drivers
from .weather import SITE_COUNT, ForecastWeather, read_weather, utc_text

TABLES = {
    "prediction_runs",
    "predictions",
    "prediction_cloudbase_hours",
    "prediction_metric_details",
    "prediction_drivers",
    "prediction_driver_inputs",
}


@dataclass(frozen=True)
class BundleIds:
    xc: str
    cloudbase: str
    overdevelopment: str


@dataclass(frozen=True)
class Batches:
    xc: PredictionBatch
    cloudbase: CloudbaseBatch
    od_manifest: OdManifest
    od_rows: list[dict]


@dataclass(frozen=True)
class Publication:
    id: int
    created_at_utc: str
    reused: bool


def require_schema(connection: Connection) -> None:
    strict_tables = {
        row[1]
        for row in connection.execute("PRAGMA main.table_list")
        if row[2] == "table" and row[5] == 1
    }
    if not TABLES <= strict_tables:
        raise ValueError(
            "Forecast publication requires the create_prediction_publications migration."
        )


def _snapshots(connection: Connection, weather: ForecastWeather) -> dict[int, Row]:
    sites = dict(connection.execute("SELECT id, slug FROM sites WHERE is_active = 1").fetchall())
    rows = connection.execute(
        """SELECT d.id AS snapshot_id, f.site_id, s.slug
           FROM weather_daily_feature_snapshots AS d
           JOIN weather_sampling_footprints AS f ON f.id = d.point_footprint_id
           JOIN sites AS s ON s.id = f.site_id
           WHERE d.ingestion_run_id = ? AND f.purpose = 'point'
           ORDER BY f.site_id""",
        (weather.id,),
    ).fetchall()
    if len(rows) != SITE_COUNT or {row["site_id"]: row["slug"] for row in rows} != sites:
        raise ValueError(
            "Forecast requires one weather snapshot for each of the seven active sites."
        )
    return {row["site_id"]: row for row in rows}


def existing_publication(
    connection: Connection, weather: ForecastWeather, model_id: str
) -> Publication | None:
    """Return an already committed date after checking its relational coverage."""
    parent = connection.execute(
        """SELECT id, created_at_utc FROM prediction_runs
           WHERE weather_ingestion_run_id = ? AND xc_model_id = ?""",
        (weather.id, model_id),
    ).fetchone()
    if parent is None:
        return None

    expected = {row["snapshot_id"] for row in _snapshots(connection, weather).values()}
    rows = connection.execute(
        "SELECT * FROM predictions WHERE prediction_run_id = ?", (parent["id"],)
    ).fetchall()
    if {row["daily_feature_snapshot_id"] for row in rows} != expected:
        raise ValueError("Existing forecast publication has incomplete site coverage.")
    for row in rows:
        hours = connection.execute(
            """SELECT valid_at_utc, regime, estimated_cloudbase_msl_m
               FROM prediction_cloudbase_hours WHERE prediction_id = ? ORDER BY valid_at_utc""",
            (row["id"],),
        ).fetchall()
        details = dict(
            connection.execute(
                """SELECT metric_code, data_status FROM prediction_metric_details
                   WHERE prediction_id = ?""",
                (row["id"],),
            ).fetchall()
        )
        expected_statuses = {
            key: "missing" if row[column] is None else "baseline"
            for key, column in (
                ("p100", "p_100km"),
                ("p200", "p_200km"),
                ("p300", "p_300km"),
                ("overdevelopment", "overdevelopment_risk"),
            )
        }
        expected_statuses["cloudbase"] = (
            "missing" if row["cloudbase_summary_state"] == "missing" else "baseline"
        )
        if (
            tuple(hour[0] for hour in hours) != weather.horizon.hours
            or details != expected_statuses
        ):
            raise ValueError(
                "Existing forecast publication has incomplete hourly or metric coverage."
            )
        for regime, column in (
            ("cumulus", "cloudbase_max_at_utc"),
            ("indeterminate", "conditional_lcl_max_at_utc"),
        ):
            candidates = [h for h in hours if h[1] == regime and h[2] is not None]
            at = min(candidates, key=lambda h: (-h[2], h[0]))[0] if candidates else None
            if row[column] != at:
                raise ValueError("Existing forecast publication has inconsistent cloudbase maxima.")
    return Publication(parent["id"], parent["created_at_utc"], True)


def _read_batches(ids: BundleIds, root: Path) -> Batches:
    od, od_rows = load_od(ids.overdevelopment, project_root=root)
    return Batches(
        load_xc(prediction_id=ids.xc, project_root=root),
        load_cloudbase(ids.cloudbase, project_root=root),
        od,
        od_rows,
    )


def _check_refs(references: list[dict], weather: ForecastWeather) -> None:
    refs = {(ref["relative_path"], ref["sha256"]) for ref in references}
    if weather.raw_manifest not in refs or weather.feature_manifest not in refs:
        raise ValueError(
            "Prediction artifact source manifests differ from the persisted weather run."
        )


def _check_batch_identity(
    batches: Batches, weather: ForecastWeather, model_id: str, database_identity: str
) -> None:
    key = weather.run_key
    if (
        batches.xc.metadata.model_id != model_id
        or batches.xc.metadata.run_keys != (key,)
        or batches.od_manifest.run_keys != (key,)
        or len(batches.cloudbase.sources) != 1
    ):
        raise ValueError(
            "Prediction batches do not identify the selected weather run and XC model."
        )
    cloud_source = batches.cloudbase.sources[0]
    (od_source,) = batches.od_manifest.sources
    if (
        cloud_source["run_key"] != key
        or cloud_source["source_id"] != GFS_SOURCE_ID
        or cloud_source["reference_at_utc"] != weather.horizon.cycle
        or cloud_source["target_local_date"] != weather.horizon.target_date.isoformat()
        or od_source.run_key != key
        or od_source.persistence_input_sha256 != weather.persistence_input_sha256
        or od_source.database_identity != database_identity
    ):
        raise ValueError("Prediction artifact source identity differs from the publication.")
    _check_refs(cloud_source["references"], weather)
    _check_refs([ref.model_dump(mode="json") for ref in od_source.references], weather)
    for row in batches.xc.inputs:
        lineage = row.source_lineage
        if (
            row.run_key != key
            or row.source_ready_at_utc != max(weather.ready_times.values())
            or lineage["persistence_input_sha256"] != weather.persistence_input_sha256
            or lineage["source_product_key"] != weather.source_product_key
            or tuple(lineage["hourly_source_ready_at_utc"]) != tuple(weather.ready_times.values())
        ):
            raise ValueError("XC source identity or readiness differs from the publication.")
        _check_refs(lineage["references"], weather)


def _insert_metric(
    connection: Connection,
    prediction_id: int,
    code: str,
    *,
    confidence: str | None,
    reason: str | None = None,
    note: str | None = None,
    limitations: str | None = None,
) -> None:
    connection.execute(
        """INSERT INTO prediction_metric_details (
               prediction_id, metric_code, data_status, confidence_level,
               confidence_note, missing_reason_code, limitations_note
           ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            prediction_id,
            code,
            "missing" if reason else "baseline",
            confidence,
            note,
            reason,
            limitations,
        ),
    )


def _insert_drivers(connection: Connection, prediction_id: int, drivers) -> None:
    ranks = defaultdict(int)
    for driver in drivers:
        ranks[driver.metric] += 1
        driver_id = connection.execute(
            """INSERT INTO prediction_drivers (
                   prediction_id, metric_code, rank, kind, code, message, xc_stage, direction,
                   contribution_logit, score_points, support_successes, support_total
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                prediction_id,
                driver.metric,
                ranks[driver.metric],
                driver.kind,
                driver.code,
                driver.message,
                driver.stage,
                driver.direction,
                driver.contribution,
                driver.points,
                driver.successes,
                driver.total,
            ),
        ).lastrowid
        connection.executemany(
            """INSERT INTO prediction_driver_inputs (
                   prediction_driver_id, input_ordinal, input_key, valid_at_utc,
                   interval_end_utc, weather_field_provenance_id
               ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                (driver_id, ordinal, item.key, item.valid, item.end, item.provenance_id)
                for ordinal, item in enumerate(driver.inputs, start=1)
            ),
        )


def _insert_site(
    connection: Connection,
    run_id: int,
    snapshot_id: int,
    xc,
    od,
    day,
    hours,
    inputs,
    conversion,
    policy,
) -> None:
    if aggregate_day(hours) != day:
        raise ValueError("Daily cloudbase does not match the hourly maxima and regimes.")
    probabilities = xc.probabilities
    prediction_id = connection.execute(
        """INSERT INTO predictions (
               prediction_run_id, daily_feature_snapshot_id, p_100km, p_200km, p_300km,
               overdevelopment_risk, overdevelopment_score, cloudbase_summary_state,
               cloudbase_max_at_utc, conditional_lcl_max_at_utc
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            run_id,
            snapshot_id,
            probabilities.p100.value,
            probabilities.p200.value,
            probabilities.p300.value,
            od["risk_level"],
            od["score"],
            day.summary_state,
            day.max_at_utc,
            day.potential_max_at_utc,
        ),
    ).lastrowid
    for hour in hours:
        height = hour.estimated_cloudbase or conditional_base(hour)
        values = (height.msl_m, height.model_agl_m, height.site_agl_m) if height else (None,) * 3
        connection.execute(
            """INSERT INTO prediction_cloudbase_hours (
                   prediction_id, valid_at_utc, regime, estimated_cloudbase_msl_m,
                   estimated_cloudbase_model_agl_m, estimated_cloudbase_site_agl_m,
                   confidence_level, reason_code, note
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                prediction_id,
                hour.valid_at_utc,
                hour.regime,
                *values,
                hour.confidence,
                primary_cloud_reason(hour),
                "; ".join(hour.limitations) or None,
            ),
        )
    for code in ("p100", "p200", "p300"):
        metric = getattr(probabilities, code)
        message = xc.threshold_explanations[code].message
        available = isinstance(metric, AvailableMetric)
        _insert_metric(
            connection,
            prediction_id,
            code,
            confidence=metric.confidence.level if available else None,
            reason=None if available else metric.missing_reason,
            note=metric.confidence.note if available else (message.text if message else None),
            limitations=xc.limitation.text,
        )
    _insert_metric(
        connection,
        prediction_id,
        "overdevelopment",
        confidence=od["confidence"],
        reason=od["reasons"][0]["code"] if od["data_status"] == "missing" else None,
        limitations=od["validation_status"]
        + ("" if od["coverage"]["complete"] else "; incomplete_weather_evidence"),
    )
    _insert_metric(
        connection,
        prediction_id,
        "cloudbase",
        confidence=day.confidence,
        reason=primary_cloud_reason(hours[0]) if day.summary_state == "missing" else None,
        limitations="; ".join(day.limitations) or None,
    )
    evidence = Provenance(connection, snapshot_id)
    _insert_drivers(
        connection,
        prediction_id,
        [
            *xc_drivers(xc, conversion, policy, evidence),
            *od_drivers(od, evidence),
            *cloud_drivers(day, hours, inputs, evidence),
        ],
    )


def _by_site(records, identity):
    keyed = {}
    for record in records:
        site_id, *key = identity(record)
        if site_id in keyed:
            raise ValueError(f"Prediction batch repeats site {site_id}.")
        keyed[site_id] = (tuple(key), record)
    return keyed


def _write_date(
    connection: Connection,
    weather: ForecastWeather,
    model_id: str,
    batches: Batches,
    created_at_utc: str,
) -> Publication:
    snapshots = _snapshots(connection, weather)
    horizon = weather.horizon
    xc = _by_site(
        batches.xc.rows,
        lambda r: (
            r.site_id,
            r.run_key,
            r.site_slug,
            r.target_local_date,
            r.cycle_reference_utc,
            r.horizon_days,
        ),
    )
    od = _by_site(
        batches.od_rows,
        lambda r: tuple(
            r[key]
            for key in (
                "site_id",
                "run_key",
                "site_slug",
                "target_local_date",
                "cycle_reference_utc",
                "horizon_days",
            )
        ),
    )
    cloud = _by_site(
        batches.cloudbase.daily,
        lambda r: (
            r.site_id,
            r.run_key,
            r.site_slug,
            r.target_local_date,
            r.reference_at_utc,
            r.horizon_days,
        ),
    )
    hourly = defaultdict(list)
    source = defaultdict(dict)
    for row in batches.cloudbase.hourly:
        hourly[row.site_id].append(row)
    for row in batches.cloudbase.inputs:
        if (
            row.run_key != weather.run_key
            or row.source_ready_at_utc != weather.ready_times.get(row.valid_at_utc)
            or row.valid_at_utc in source[row.site_id]
        ):
            raise ValueError("Cloudbase input hours or source readiness differ from SQLite.")
        source[row.site_id][row.valid_at_utc] = row
    if any(set(index) != snapshots.keys() for index in (xc, od, cloud, hourly, source)):
        raise ValueError("Prediction batches do not cover the seven persisted site snapshots.")

    policy, _ = load_policy()
    run_id = connection.execute(
        """INSERT INTO prediction_runs (
               weather_ingestion_run_id, created_at_utc, xc_model_id,
               cloudbase_method_version, overdevelopment_policy_version
           ) VALUES (?, ?, ?, ?, ?)""",
        (
            weather.id,
            created_at_utc,
            model_id,
            batches.cloudbase.method_version,
            batches.od_manifest.policy_version,
        ),
    ).lastrowid
    for site_id, snapshot in snapshots.items():
        expected = (
            weather.run_key,
            snapshot["slug"],
            horizon.target_date.isoformat(),
            horizon.cycle,
            horizon.days,
        )
        if any(index[site_id][0] != expected for index in (xc, od, cloud)):
            raise ValueError("XC, cloudbase and OD must match the same persisted site and date.")
        if set(source[site_id]) != set(horizon.hours):
            raise ValueError("Publication requires eleven exact hourly inputs for each site.")
        _insert_site(
            connection,
            run_id,
            snapshot["snapshot_id"],
            xc[site_id][1],
            od[site_id][1],
            cloud[site_id][1],
            sorted(hourly[site_id], key=lambda hour: hour.valid_at_utc),
            source[site_id],
            batches.xc.metadata.conversion,
            policy,
        )
    existing_publication(connection, weather, model_id)
    return Publication(run_id, created_at_utc, False)


def publish_date(
    *,
    project_root: Path,
    database_url: str,
    run_key: str,
    model_id: str,
    ids: BundleIds,
    clock=lambda: datetime.now(UTC),
) -> Publication:
    """Commit all six tables for one date or leave the database unchanged."""
    database_identity = resolve_database_path(database_url, project_root).relative_to(project_root)
    with closing(open_writable_database(database_url, project_root)) as connection, connection:
        connection.row_factory = Row
        connection.execute("BEGIN IMMEDIATE")
        weather = read_weather(connection, run_key)
        published = existing_publication(connection, weather, model_id)
        if published is not None:
            return published
        batches = _read_batches(ids, project_root)
        _check_batch_identity(batches, weather, model_id, database_identity.as_posix())
        return _write_date(connection, weather, model_id, batches, utc_text(clock()))
