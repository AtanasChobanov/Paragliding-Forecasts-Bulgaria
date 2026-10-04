"""Immutable bounded GFS range collection after a resolved request plan."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from ..atmosphere.contracts import ArtifactReference, RawManifest, RequestPlan
from ..weather.artifacts import WeatherArtifactStore
from ..weather.serialization import canonical_json_bytes, sha256_file
from .models import (
    GFS_COLLECTOR_VERSION,
    GFS_SOURCE_ID,
    GfsArtifactEvidence,
    GfsCollectionRecord,
    GfsResolvedPlan,
)
from .transport import GfsTransportError, HttpTransport


class GfsCollectionError(RuntimeError):
    """A planned GFS object could not be collected safely."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class GfsCollector:
    """Downloads only hash-planned GFS indexes and exact GRIB byte ranges."""

    source_id = GFS_SOURCE_ID
    collector_version = GFS_COLLECTOR_VERSION

    def __init__(self, transport: HttpTransport, *, clock=_now_utc) -> None:
        self.transport = transport
        self.clock = clock

    def fetch(self, plan: RequestPlan, artifacts: WeatherArtifactStore) -> ArtifactReference:
        try:
            resolved = GfsResolvedPlan.model_validate_json(json.dumps(plan.adapter_request))
        except Exception as error:
            raise GfsCollectionError(
                "invalid_plan", "Request plan is not a strict GFS resolved plan."
            ) from error
        if plan.source_id != self.source_id or plan.run_key != artifacts.run_key:
            raise GfsCollectionError(
                "invalid_plan", "GFS plan and artifact store do not identify the same run."
            )
        plan_reference = artifacts.write_request_plan(plan)
        evidence: list[GfsArtifactEvidence] = []
        indexes: dict[str, object] = {}
        try:
            for item in resolved.ranges:
                if item.index_url in indexes:
                    continue
                response = self._get(item.index_url)
                if response.status == 404:
                    raise GfsCollectionError("absent_file", "GFS index disappeared after planning.")
                if (
                    response.status != 200
                    or hashlib.sha256(response.body).hexdigest() != item.index_sha256
                ):
                    raise GfsCollectionError(
                        "invalid_inventory", "GFS index changed after planning."
                    )
                reference = artifacts.write_raw_bytes(
                    f"gfs_idx_f{item.lead_hours:03d}",
                    f"gfs.t{resolved.resolved_run_at_utc[11:13]}z.pgrb2.0p25.f{item.lead_hours:03d}.idx",
                    response.body,
                    media_type="text/plain",
                )
                indexes[item.index_url] = reference
                evidence.append(
                    GfsArtifactEvidence(
                        artifact=reference,
                        source_url=item.index_url,
                        etag=response.header("ETag"),
                        last_modified_utc=(
                            item.index_last_modified_utc or item.object_last_modified_utc
                        ),
                    )
                )
            for ordinal, item in enumerate(resolved.ranges, start=1):
                response = self._get(
                    item.grib_url, headers={"Range": f"bytes={item.byte_start}-{item.byte_end}"}
                )
                expected = item.byte_end - item.byte_start + 1
                content_range = response.header("Content-Range")
                if response.status == 404:
                    raise GfsCollectionError(
                        "absent_file", "GFS GRIB object disappeared after planning."
                    )
                if (
                    response.status != 206
                    or content_range
                    != f"bytes {item.byte_start}-{item.byte_end}/{item.object_content_length}"
                ):
                    raise GfsCollectionError(
                        "range_protocol_failure", "GFS did not honour the planned byte range."
                    )
                if len(response.body) != expected:
                    raise GfsCollectionError(
                        "range_protocol_failure", "GFS range response is truncated or oversized."
                    )
                reference = artifacts.write_raw_bytes(
                    f"gfs_grib_f{item.lead_hours:03d}_r{ordinal:03d}",
                    f"gfs-f{item.lead_hours:03d}-r{ordinal:03d}.grib2",
                    response.body,
                    media_type="application/x-grib2",
                )
                evidence.append(
                    GfsArtifactEvidence(
                        artifact=reference,
                        source_url=item.grib_url,
                        byte_start=item.byte_start,
                        byte_end=item.byte_end,
                        lead_hours=item.lead_hours,
                        valid_at_utc=item.valid_at_utc,
                        message_numbers=item.message_numbers,
                        selector_keys=item.selector_keys,
                        forecast_descriptors=item.forecast_descriptors,
                        etag=item.object_etag,
                        last_modified_utc=item.object_last_modified_utc,
                    )
                )
        except (GfsTransportError, GfsCollectionError) as error:
            kind = error.kind if isinstance(error, GfsCollectionError) else "network_failure"
            return self._failed_manifest(
                plan, plan_reference, resolved, artifacts, tuple(evidence), kind, str(error)
            )
        record = GfsCollectionRecord(
            run_key=plan.run_key,
            source_product_key=resolved.source_product_key,
            run_at_utc=resolved.resolved_run_at_utc,
            available_at_utc=resolved.available_at_utc,
            retrieved_at_utc=self.clock(),
            licence_reference=resolved.licence_reference,
            attribution_text=resolved.attribution_text,
            outcome="complete",
            artifacts=tuple(evidence),
        )
        record_reference = artifacts.write_raw_model(
            "gfs_collection_record", "gfs-collection-record.json", record
        )
        return artifacts.write_raw_manifest(
            RawManifest(
                run_key=plan.run_key,
                source_id=self.source_id,
                source_kind="forecast",
                collector_version=self.collector_version,
                request_plan=plan_reference,
                source_product_key=resolved.source_product_key,
                source_url=resolved.ranges[0].grib_url,
                permission_basis="NOAA Open Data on AWS public data",
                permission_reference=resolved.licence_reference,
                attribution_text=resolved.attribution_text,
                reference_at_utc=resolved.resolved_run_at_utc,
                available_at_utc=resolved.available_at_utc,
                retrieved_at_utc=record.retrieved_at_utc,
                valid_from_utc=min(item.valid_at_utc for item in resolved.ranges),
                valid_to_utc=max(item.valid_at_utc for item in resolved.ranges),
                artifacts=tuple(item.artifact for item in evidence) + (record_reference,),
                status="complete",
                completed_at_utc=self.clock(),
            )
        )

    def fetch_resumable(
        self,
        plan: RequestPlan,
        artifacts: WeatherArtifactStore,
        *,
        progress: Callable[[int, int], None] | None = None,
    ) -> ArtifactReference:
        """Complete a pinned plan with immutable per-range checkpoints.

        An interrupted attempt has no final raw manifest. Existing payloads are
        reused only after a checkpoint hash and live source identity agree.
        """

        resolved = GfsResolvedPlan.model_validate_json(json.dumps(plan.adapter_request))
        if plan.source_id != self.source_id or plan.run_key != artifacts.run_key:
            raise GfsCollectionError("invalid_plan", "GFS plan and run key differ.")
        if (artifacts.raw_dir / "manifest.json").exists():
            raise GfsCollectionError("complete_run", "Raw manifest already exists.")
        plan_path = artifacts.raw_dir / "request-plan.json"
        plan_bytes = canonical_json_bytes(plan.model_dump(mode="json"))
        if plan_path.exists():
            existing = RequestPlan.model_validate_json(plan_path.read_bytes(), strict=True)
            if existing != plan:
                raise GfsCollectionError("changed_plan", "Saved GFS request plan changed.")
            plan_reference = self._existing_reference(
                artifacts, plan_path, "request_plan", "application/json"
            )
        else:
            plan_reference = artifacts.write_request_plan(plan)
        plan_sha = hashlib.sha256(plan_bytes).hexdigest()
        by_index: dict[str, GfsArtifactEvidence] = {}
        for item in resolved.ranges:
            if item.index_url in by_index:
                continue
            head = self.transport.request(item.grib_url, method="HEAD")
            if head.status != 200:
                raise GfsCollectionError("source_changed", "GFS GRIB HEAD is no longer 200.")
            modified = self._http_timestamp(head.header("Last-Modified"))
            if (
                head.header("Content-Length") != str(item.object_content_length)
                or head.header("ETag") != item.object_etag
                or modified != item.object_last_modified_utc
            ):
                raise GfsCollectionError("source_changed", "GFS GRIB identity changed.")
            response = self._get(item.index_url)
            if (
                response.status != 200
                or hashlib.sha256(response.body).hexdigest() != item.index_sha256
            ):
                raise GfsCollectionError("source_changed", "GFS index changed.")
            index_modified = self._http_timestamp(response.header("Last-Modified"))
            if (
                item.index_last_modified_utc is None
                or index_modified != item.index_last_modified_utc
            ):
                raise GfsCollectionError("source_changed", "GFS index timestamp changed.")
            path = (
                artifacts.raw_dir
                / "payloads"
                / (
                    f"gfs.t{resolved.resolved_run_at_utc[11:13]}z.pgrb2.0p25.f{item.lead_hours:03d}.idx"
                )
            )
            if path.exists():
                if sha256_file(path) != item.index_sha256:
                    raise GfsCollectionError("corrupt_checkpoint", "Saved GFS index hash differs.")
                reference = self._existing_reference(
                    artifacts, path, f"gfs_idx_f{item.lead_hours:03d}", "text/plain"
                )
            else:
                reference = artifacts.write_raw_bytes(
                    f"gfs_idx_f{item.lead_hours:03d}",
                    path.name,
                    response.body,
                    media_type="text/plain",
                )
            by_index[item.index_url] = GfsArtifactEvidence(
                artifact=reference,
                source_url=item.index_url,
                etag=None,
                last_modified_utc=index_modified,
            )
        evidence = list(by_index.values())
        for ordinal, item in enumerate(resolved.ranges, start=1):
            artifact_key = f"gfs_grib_f{item.lead_hours:03d}_r{ordinal:03d}"
            path = (
                artifacts.raw_dir / "payloads" / f"gfs-f{item.lead_hours:03d}-r{ordinal:03d}.grib2"
            )
            checkpoint = artifacts.raw_dir / "checkpoints" / f"{artifact_key}.json"
            expected = item.byte_end - item.byte_start + 1
            if checkpoint.exists():
                saved = json.loads(checkpoint.read_bytes())
                if saved.get("plan_sha256") != plan_sha or saved.get("ordinal") != ordinal:
                    raise GfsCollectionError(
                        "corrupt_checkpoint", "Range checkpoint belongs to another plan."
                    )
                item_evidence = GfsArtifactEvidence.model_validate_json(
                    json.dumps(saved["evidence"])
                )
                if (
                    item_evidence.artifact.artifact_key != artifact_key
                    or item_evidence.artifact.relative_path
                    != path.relative_to(artifacts.project_root).as_posix()
                    or item_evidence.byte_start != item.byte_start
                    or item_evidence.byte_end != item.byte_end
                    or item_evidence.source_url != item.grib_url
                    or item_evidence.etag != item.object_etag
                    or item_evidence.last_modified_utc != item.object_last_modified_utc
                    or item_evidence.message_numbers != item.message_numbers
                    or item_evidence.selector_keys != item.selector_keys
                    or item_evidence.forecast_descriptors != item.forecast_descriptors
                    or item_evidence.artifact.byte_count != expected
                ):
                    raise GfsCollectionError(
                        "corrupt_checkpoint", "Range checkpoint metadata differs."
                    )
                artifacts.verify_reference(
                    item_evidence.artifact,
                    expected_root=artifacts.raw_dir,
                    require_disk_hash=True,
                )
                evidence.append(item_evidence)
                if progress is not None and (ordinal % 50 == 0 or ordinal == len(resolved.ranges)):
                    progress(ordinal, len(resolved.ranges))
                continue
            request_headers = {"Range": f"bytes={item.byte_start}-{item.byte_end}"}
            if item.object_etag is not None:
                request_headers["If-Match"] = item.object_etag
            response = self._get(item.grib_url, headers=request_headers)
            if (
                response.status != 206
                or response.header("Content-Range")
                != f"bytes {item.byte_start}-{item.byte_end}/{item.object_content_length}"
                or len(response.body) != expected
            ):
                raise GfsCollectionError("range_protocol_failure", "GFS planned range differs.")
            if response.header("ETag") not in {None, item.object_etag}:
                raise GfsCollectionError("source_changed", "GFS range ETag changed.")
            response_modified = response.header("Last-Modified")
            if (
                response_modified is not None
                and self._http_timestamp(response_modified) != item.object_last_modified_utc
            ):
                raise GfsCollectionError("source_changed", "GFS range timestamp changed.")
            if path.exists():
                if sha256_file(path) != hashlib.sha256(response.body).hexdigest():
                    raise GfsCollectionError(
                        "corrupt_checkpoint", "Uncheckpointed range differs from source."
                    )
                reference = self._existing_reference(
                    artifacts, path, artifact_key, "application/x-grib2"
                )
            else:
                reference = artifacts.write_raw_bytes(
                    artifact_key, path.name, response.body, media_type="application/x-grib2"
                )
            item_evidence = GfsArtifactEvidence(
                artifact=reference,
                source_url=item.grib_url,
                byte_start=item.byte_start,
                byte_end=item.byte_end,
                lead_hours=item.lead_hours,
                valid_at_utc=item.valid_at_utc,
                message_numbers=item.message_numbers,
                selector_keys=item.selector_keys,
                forecast_descriptors=item.forecast_descriptors,
                etag=item.object_etag,
                last_modified_utc=item.object_last_modified_utc,
            )
            artifacts.write_raw_checkpoint(
                checkpoint.name,
                canonical_json_bytes(
                    {
                        "plan_sha256": plan_sha,
                        "ordinal": ordinal,
                        "evidence": item_evidence.model_dump(mode="json"),
                    }
                ),
            )
            evidence.append(item_evidence)
            if progress is not None and (ordinal % 50 == 0 or ordinal == len(resolved.ranges)):
                progress(ordinal, len(resolved.ranges))
        record_path = artifacts.raw_dir / "payloads" / "gfs-collection-record.json"
        if record_path.exists():
            record = GfsCollectionRecord.model_validate_json(record_path.read_bytes(), strict=True)
            if record.run_key != plan.run_key or record.artifacts != tuple(evidence):
                raise GfsCollectionError("corrupt_checkpoint", "Saved collection record differs.")
            record_reference = self._existing_reference(
                artifacts, record_path, "gfs_collection_record", "application/json"
            )
        else:
            record = GfsCollectionRecord(
                run_key=plan.run_key,
                source_product_key=resolved.source_product_key,
                run_at_utc=resolved.resolved_run_at_utc,
                available_at_utc=resolved.available_at_utc,
                retrieved_at_utc=self.clock(),
                licence_reference=resolved.licence_reference,
                attribution_text=resolved.attribution_text,
                outcome="complete",
                artifacts=tuple(evidence),
            )
            record_reference = artifacts.write_raw_model(
                "gfs_collection_record", "gfs-collection-record.json", record
            )
        return artifacts.write_raw_manifest(
            RawManifest(
                run_key=plan.run_key,
                source_id=self.source_id,
                source_kind="forecast",
                collector_version=self.collector_version,
                request_plan=plan_reference,
                source_product_key=resolved.source_product_key,
                source_url=resolved.ranges[0].grib_url,
                permission_basis="NOAA Open Data on AWS public data",
                permission_reference=resolved.licence_reference,
                attribution_text=resolved.attribution_text,
                reference_at_utc=resolved.resolved_run_at_utc,
                available_at_utc=resolved.available_at_utc,
                retrieved_at_utc=record.retrieved_at_utc,
                valid_from_utc=min(item.valid_at_utc for item in resolved.ranges),
                valid_to_utc=max(item.valid_at_utc for item in resolved.ranges),
                artifacts=tuple(item.artifact for item in evidence) + (record_reference,),
                status="complete",
                completed_at_utc=self.clock(),
            )
        )

    @staticmethod
    def _existing_reference(
        artifacts: WeatherArtifactStore, path: Path, key: str, media_type: str
    ) -> ArtifactReference:
        reference = ArtifactReference(
            artifact_key=key,
            relative_path=path.relative_to(artifacts.project_root).as_posix(),
            sha256=sha256_file(path),
            byte_count=path.stat().st_size,
            media_type=media_type,
        )
        artifacts.verify_reference(
            reference, expected_root=artifacts.raw_dir, require_disk_hash=True
        )
        return reference

    @staticmethod
    def _http_timestamp(value: str | None) -> str | None:
        if value is None:
            return None
        return parsedate_to_datetime(value).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _failed_manifest(
        self, plan, plan_reference, resolved, artifacts, evidence, kind, detail
    ) -> ArtifactReference:
        record = GfsCollectionRecord(
            run_key=plan.run_key,
            source_product_key=resolved.source_product_key,
            run_at_utc=resolved.resolved_run_at_utc,
            available_at_utc=resolved.available_at_utc,
            retrieved_at_utc=self.clock(),
            licence_reference=resolved.licence_reference,
            attribution_text=resolved.attribution_text,
            outcome="partial" if evidence else "failed",
            failure_kind=kind,
            artifacts=evidence
            or (
                GfsArtifactEvidence(
                    artifact=plan_reference, source_url=resolved.ranges[0].index_url
                ),
            ),
        )
        record_reference = artifacts.write_raw_model(
            "gfs_collection_record", "gfs-collection-record.json", record
        )
        return artifacts.write_raw_manifest(
            RawManifest(
                run_key=plan.run_key,
                source_id=self.source_id,
                source_kind="forecast",
                collector_version=self.collector_version,
                request_plan=plan_reference,
                source_product_key=resolved.source_product_key,
                source_url=resolved.ranges[0].grib_url,
                permission_basis="NOAA Open Data on AWS public data",
                permission_reference=resolved.licence_reference,
                attribution_text=resolved.attribution_text,
                reference_at_utc=resolved.resolved_run_at_utc,
                available_at_utc=resolved.available_at_utc,
                retrieved_at_utc=record.retrieved_at_utc,
                valid_from_utc=min(item.valid_at_utc for item in resolved.ranges),
                valid_to_utc=max(item.valid_at_utc for item in resolved.ranges),
                artifacts=tuple(item.artifact for item in evidence) + (record_reference,),
                status=record.outcome,
                completed_at_utc=self.clock(),
            )
        )

    def _get(self, url: str, *, headers=None):
        return self.transport.request(url, headers=headers)
