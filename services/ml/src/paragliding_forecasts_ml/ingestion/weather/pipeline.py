"""GFS fresh and strictly offline-resume weather-ingestion orchestration."""

from __future__ import annotations

from dataclasses import dataclass
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
from ..gfs.collector import GfsCollectionError
from ..gfs.compact import COMPACT_SELECTION_VERSION
from ..gfs.models import (
    GFS_COLLECTOR_VERSION,
    SOFIA_FLYING_WINDOW_VERSION,
    GfsRequest,
    sofia_window_instants,
)
from ..gfs.parser import GfsParserError
from ..gfs.planner import GfsPlanningError
from .artifacts import ArtifactError, WeatherArtifactStore
from .feature_stage import WeatherFeatureBuildError
from .grid import site_config_fingerprint, snapshot_site_configs
from .persistence import WeatherPersistenceError, _require_schema
from .persistence_models import load_weather_usage_policy
from .sampling_policy import load_sampling_policy
from .serialization import canonical_json_bytes, sha256_bytes, sha256_file
from .services import (
    WeatherRunContext,
    build_features,
    parse_and_normalize,
    persist_run,
    sample_sites,
    validate_run,
)
from .sites import SiteSamplingConfigError, load_site_sampling_configs
from .spatial import SpatialSamplingError
from .state import StateError
from .validation import WeatherValidationError


class WeatherPipelineError(RuntimeError):
    """A weather orchestration precondition or offline stage did not complete."""


@dataclass(frozen=True, slots=True)
class WeatherPreflight:
    database_url: str
    site_config_sha256: str
    sampling_policy_sha256: str
    compact_selection_version: str


def _preflight(policy_path: Path | None, database_url: str | None, root: Path) -> WeatherPreflight:
    """Verify the explicit policy and existing migrated SQLite before fresh network use."""

    try:
        load_weather_usage_policy(policy_path, source_family="gfs", project_root=root)
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
    try:
        sites = load_site_sampling_configs(resolved_url, root, require_elevation=True)
        _sampling_policy, sampling_policy_sha256 = load_sampling_policy()
        site_config_sha256 = site_config_fingerprint(snapshot_site_configs(sites))
    except (DatabaseConfigurationError, SiteSamplingConfigError, ValueError) as error:
        raise WeatherPipelineError(
            f"Weather pipeline compact-selection preflight failed: {error}"
        ) from error
    return WeatherPreflight(
        database_url=resolved_url,
        site_config_sha256=site_config_sha256,
        sampling_policy_sha256=sampling_policy_sha256,
        compact_selection_version=COMPACT_SELECTION_VERSION,
    )


def _offline_services(
    context: WeatherRunContext,
    policy_path: Path | None,
) -> dict[str, Any]:
    """Run the common strictly offline service sequence through one shared context."""

    raw_event = context.snapshot.effective_event("raw_complete")
    if raw_event is None or raw_event.evidence is None:
        raise WeatherPipelineError("Weather resume requires a raw coverage state event.")
    context.store.verify_raw_manifest(raw_event.evidence)
    if raw_event.disposition != "complete":
        return {
            "status": "incomplete_coverage",
            "run_key": context.run_key,
            "raw_disposition": raw_event.disposition,
            "network_access": False,
            "verification_summary": context.verification_summary(),
            "next_step": "Start a new fresh GFS collection; partial raw coverage cannot resume.",
        }

    parser, context.snapshot = parse_and_normalize(context)
    sampling, context.snapshot = sample_sites(context)
    validation, context.snapshot = validate_run(context)
    if validation.disposition == "quarantined":
        return {
            "status": "quarantined",
            "run_key": context.run_key,
            "parser": parser.as_dict(),
            "sampling": sampling.as_dict(),
            "validation": validation.as_dict(),
            "network_access": False,
            "verification_summary": context.verification_summary(),
            "next_step": "Review the immutable validation quarantine before persistence.",
        }
    features, context.snapshot = build_features(context)
    persistence, context.snapshot = persist_run(context, policy_path)
    return {
        "status": persistence.report["status"],
        "run_key": context.run_key,
        "parser": parser.as_dict(),
        "sampling": sampling.as_dict(),
        "validation": validation.as_dict(),
        "features": features.as_dict(),
        "persistence": persistence.as_dict(),
        "network_access": False,
        "verification_summary": context.verification_summary(),
    }


def resume_run(
    run_key: str,
    policy_path: Path | None,
    *,
    database_url: str | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Complete all remaining stages from durable local evidence with no GFS transport path."""

    root = (project_root or Path.cwd()).resolve()
    try:
        preflight = _preflight(policy_path, database_url, root)
        context = WeatherRunContext.open(
            run_key,
            project_root=root,
            database_url=preflight.database_url,
        )
        return _offline_services(context, policy_path)
    except (
        ArtifactError,
        GfsParserError,
        OSError,
        SiteSamplingConfigError,
        SpatialSamplingError,
        StateError,
        ValueError,
        WeatherFeatureBuildError,
        WeatherPersistenceError,
        WeatherValidationError,
    ) as error:
        raise WeatherPipelineError(f"Weather offline stages did not complete: {error}") from error


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
                "expected_artifact_keys": list(plan.expected_artifact_keys),
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
    preflight = _preflight(policy_path, database_url, root)
    try:
        request = GfsRequest(
            run_key=str(uuid4()),
            request_purpose=purpose,
            valid_at_utc=sofia_window_instants(local_date),
            explicit_run_at_utc=explicit_run_at,
            newest_complete_before_utc=newest_complete_before,
            maximum_total_bytes=maximum_total_mib * 1024 * 1024,
            target_local_date=local_date,
            flying_window_version=SOFIA_FLYING_WINDOW_VERSION,
            site_config_sha256=preflight.site_config_sha256,
            sampling_policy_sha256=preflight.sampling_policy_sha256,
            compact_selection_version=preflight.compact_selection_version,
        )
        collector = collect_gfs_run(
            request,
            project_root=root,
            duplicate_run_key=lambda plan: _existing_successful_acquisition(
                plan, preflight.database_url, root
            ),
        )
    except (GfsCollectionError, GfsPlanningError, OSError, StateError, ValueError) as error:
        raise WeatherPipelineError(f"Weather fresh collection did not complete: {error}") from error
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
    try:
        context = WeatherRunContext.open(
            run_key,
            project_root=root,
            database_url=preflight.database_url,
        )
        result = _offline_services(context, policy_path)
    except (
        ArtifactError,
        GfsParserError,
        OSError,
        SiteSamplingConfigError,
        SpatialSamplingError,
        StateError,
        ValueError,
        WeatherFeatureBuildError,
        WeatherPersistenceError,
        WeatherValidationError,
    ) as error:
        raise WeatherPipelineError(f"Weather offline stages did not complete: {error}") from error
    return {"collector": collector, **result}
