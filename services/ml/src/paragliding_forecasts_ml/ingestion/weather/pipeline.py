"""GFS fresh and strictly offline-resume weather-ingestion orchestration."""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from ...storage.sqlite import (
    DatabaseConfigurationError,
    configured_database_url,
    open_read_only_database,
)
from ..atmosphere.contracts import RawManifest, RequestPlan
from ..gfs.cli import collect_gfs_run
from ..gfs.models import (
    GFS_COLLECTOR_VERSION,
    SOFIA_FLYING_WINDOW_VERSION,
    GfsRequest,
    sofia_window_instants,
)
from ..gfs.parser_cli import main as gfs_parse_cli
from .artifacts import ArtifactError, WeatherArtifactStore
from .feature_cli import main as weather_features_cli
from .persistence import WeatherPersistenceError, _require_schema, persist_weather_run
from .persistence_models import load_weather_usage_policy
from .serialization import canonical_json_bytes, sha256_bytes, sha256_file
from .spatial_cli import main as gfs_sample_cli
from .state import RunStateLedger, StateError
from .validation_cli import main as weather_validate_cli


class WeatherPipelineError(RuntimeError):
    """A weather orchestration precondition or offline stage did not complete."""


def _run_cli_stage(
    command: Callable[[list[str]], int],
    arguments: list[str],
    label: str,
    *,
    allowed_exit_codes: frozenset[int] = frozenset({0}),
) -> dict[str, Any]:
    """Call an individual command boundary without spawning a subprocess."""

    output = StringIO()
    with redirect_stdout(output):
        exit_code = command(arguments)
    if exit_code not in allowed_exit_codes:
        raise WeatherPipelineError(f"{label} did not complete (exit {exit_code}).")
    try:
        payload = json.loads(output.getvalue())
    except json.JSONDecodeError as error:
        raise WeatherPipelineError(f"{label} did not emit a JSON result.") from error
    if not isinstance(payload, dict):
        raise WeatherPipelineError(f"{label} did not emit a JSON object.")
    return payload


def _preflight(policy_path: Path | None, database_url: str | None, root: Path) -> str:
    """Verify the explicit policy and existing migrated SQLite before fresh network use."""

    try:
        load_weather_usage_policy(policy_path, expected_source_id="gfs", project_root=root)
        resolved_url = configured_database_url(database_url)
        connection = open_read_only_database(resolved_url, root)
    except (DatabaseConfigurationError, ValueError) as error:
        raise WeatherPipelineError(
            f"Weather pipeline preflight failed before collection: {error}"
        ) from error
    try:
        _require_schema(connection)
    except WeatherPersistenceError as error:
        raise WeatherPipelineError(
            f"Weather pipeline requires the current migrated SQLite schema: {error}"
        ) from error
    except Exception as error:
        raise WeatherPipelineError("Weather pipeline could not inspect SQLite schema.") from error
    finally:
        connection.close()
    return resolved_url


def _raw_state(run_key: str, root: Path) -> str:
    """Verify the ledger and return the current raw coverage disposition."""

    try:
        store = WeatherArtifactStore(run_key, project_root=root)
        ledger = RunStateLedger(store)
        events = ledger.load_events()
    except (ArtifactError, StateError, OSError) as error:
        raise WeatherPipelineError("Weather resume cannot verify its state ledger.") from error
    raw_events = [
        event for event in events if event.stage == "raw_complete" and event.evidence is not None
    ]
    if not raw_events:
        raise WeatherPipelineError("Weather resume requires a raw coverage state event.")
    return raw_events[-1].disposition


def resume_run(
    run_key: str,
    policy_path: Path | None,
    *,
    database_url: str | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Complete all remaining stages from durable local evidence with no GFS transport path."""

    root = (project_root or Path.cwd()).resolve()
    resolved_url = _preflight(policy_path, database_url, root)
    raw_disposition = _raw_state(run_key, root)
    if raw_disposition != "complete":
        return {
            "status": "incomplete_coverage",
            "run_key": run_key,
            "raw_disposition": raw_disposition,
            "network_access": False,
            "next_step": "Start a new fresh GFS collection; partial raw coverage cannot resume.",
        }

    parser = _run_cli_stage(
        gfs_parse_cli,
        ["--run-key", run_key, "--project-root", str(root)],
        "Offline GFS parse/normalize",
    )
    sampling = _run_cli_stage(
        gfs_sample_cli,
        [
            "--run-key",
            run_key,
            "--database-url",
            resolved_url,
            "--project-root",
            str(root),
        ],
        "Offline GFS sampling",
    )
    validation = _run_cli_stage(
        weather_validate_cli,
        [
            "--run-key",
            run_key,
            "--database-url",
            resolved_url,
            "--project-root",
            str(root),
        ],
        "Offline weather validation",
        allowed_exit_codes=frozenset({0, 2}),
    )
    if validation.get("disposition") == "quarantined":
        return {
            "status": "quarantined",
            "run_key": run_key,
            "parser": parser,
            "sampling": sampling,
            "validation": validation,
            "network_access": False,
            "next_step": "Review the immutable validation quarantine before any persistence attempt.",
        }
    features = _run_cli_stage(
        weather_features_cli,
        ["--run-key", run_key, "--project-root", str(root)],
        "Offline weather feature build",
    )
    try:
        persistence = persist_weather_run(
            run_key,
            policy_path,
            database_url=resolved_url,
            project_root=root,
        )
    except WeatherPersistenceError as error:
        raise WeatherPipelineError(f"Weather persistence did not complete: {error}") from error
    return {
        "status": persistence["status"],
        "run_key": run_key,
        "parser": parser,
        "sampling": sampling,
        "validation": validation,
        "features": features,
        "persistence": persistence,
        "network_access": False,
    }


def _acquisition_identity(plan: RequestPlan) -> str:
    """Identity checked after inventory planning and before any GFS payload GET."""

    return sha256_bytes(
        canonical_json_bytes(
            {
                "schema_version": 1,
                "collector_version": GFS_COLLECTOR_VERSION,
                "source_id": plan.source_id,
                "source_kind": plan.source_kind,
                "ingestion_method": plan.ingestion_method,
                "request_purpose": plan.request_purpose,
                "catalogue_version": plan.catalogue_version,
                "catalogue_sha256": plan.catalogue_sha256,
                "adapter_request_schema_version": plan.adapter_request_schema_version,
                "adapter_request": plan.adapter_request,
                "expected_artifact_keys": plan.expected_artifact_keys,
            }
        )
    )


def _candidate_request_plan(
    root: Path, run_key: str, manifest_path: str, manifest_sha256: str
) -> RequestPlan:
    """Hash-verify compact raw metadata without opening candidate GRIB payloads."""

    try:
        store = WeatherArtifactStore(run_key, project_root=root)
        candidate_path = (root / manifest_path).resolve()
        candidate_path.relative_to(store.raw_dir.resolve())
        if not candidate_path.is_file() or sha256_file(candidate_path) != manifest_sha256:
            raise WeatherPipelineError(
                "Existing acquisition raw manifest no longer matches SQLite."
            )
        raw_manifest = RawManifest.model_validate_json(candidate_path.read_bytes(), strict=True)
        request_path = store.verify_reference(
            raw_manifest.request_plan, expected_root=store.raw_dir
        )
        return RequestPlan.model_validate_json(request_path.read_bytes(), strict=True)
    except (ArtifactError, OSError, ValueError) as error:
        raise WeatherPipelineError(
            "Existing successful acquisition evidence cannot be hash-verified."
        ) from error


def _existing_successful_acquisition(
    plan: RequestPlan, database_url: str, root: Path
) -> str | None:
    """Return an exact completed acquisition before collector payload requests begin."""

    resolved = plan.adapter_request
    source_product_key = resolved.get("source_product_key")
    target_local_date = resolved.get("target_local_date")
    if not isinstance(source_product_key, str) or not isinstance(target_local_date, str):
        raise WeatherPipelineError("Planned GFS acquisition lacks product/date identity.")
    try:
        connection = open_read_only_database(database_url, root)
    except DatabaseConfigurationError as error:
        raise WeatherPipelineError(
            "Duplicate-acquisition gate cannot open SQLite read-only."
        ) from error
    try:
        rows = connection.execute(
            """SELECT run.run_key, run.raw_manifest_path, run.raw_manifest_sha256
               FROM weather_ingestion_runs AS run
               INNER JOIN weather_product_runs AS product ON product.id = run.product_run_id
               INNER JOIN weather_sources AS source ON source.id = product.source_id
               WHERE source.code = ? AND product.source_product_key = ?
                 AND run.target_local_date = ? AND run.request_purpose = ?
                 AND run.status = 'succeeded'
               ORDER BY run.id""",
            (plan.source_id, source_product_key, target_local_date, plan.request_purpose),
        ).fetchall()
    except Exception as error:
        raise WeatherPipelineError(
            "Duplicate-acquisition gate could not inspect SQLite runs."
        ) from error
    finally:
        connection.close()
    identity = _acquisition_identity(plan)
    for row in rows:
        candidate = _candidate_request_plan(root, str(row[0]), str(row[1]), str(row[2]))
        if _acquisition_identity(candidate) == identity:
            return str(row[0])
    return None


def fresh_run(
    *,
    local_date: str,
    purpose: str,
    policy_path: Path | None,
    explicit_run_at: str | None = None,
    newest_complete_before: str | None = None,
    maximum_total_mib: int,
    allow_live_network: bool,
    database_url: str | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Collect one explicitly approved GFS scope, then use the same offline stage boundaries."""

    if not allow_live_network:
        raise WeatherPipelineError(
            "Weather fresh ingestion refuses network access without --allow-live-network."
        )
    if (explicit_run_at is None) == (newest_complete_before is None):
        raise WeatherPipelineError(
            "Weather fresh ingestion requires exactly one GFS run selection mode."
        )
    root = (project_root or Path.cwd()).resolve()
    resolved_url = _preflight(policy_path, database_url, root)
    request = GfsRequest(
        run_key=str(uuid4()),
        request_purpose=purpose,
        valid_at_utc=sofia_window_instants(local_date),
        explicit_run_at_utc=explicit_run_at,
        newest_complete_before_utc=newest_complete_before,
        maximum_total_bytes=maximum_total_mib * 1024 * 1024,
        target_local_date=local_date,
        flying_window_version=SOFIA_FLYING_WINDOW_VERSION,
    )
    collector = collect_gfs_run(
        request,
        project_root=root,
        duplicate_run_key=lambda plan: _existing_successful_acquisition(plan, resolved_url, root),
    )
    run_key = collector["run_key"]
    if collector["status"] == "already_succeeded":
        return {
            "status": "already_succeeded",
            "run_key": run_key,
            "collector": collector,
            "network_access": "inventory_only",
        }
    if collector["status"] != "complete":
        return {
            "status": "incomplete_coverage",
            "run_key": run_key,
            "collector": collector,
            "next_step": "Review the immutable raw manifest and start a new fresh collection.",
        }
    result = resume_run(
        run_key,
        policy_path,
        database_url=resolved_url,
        project_root=root,
    )
    return {"collector": collector, **result}
