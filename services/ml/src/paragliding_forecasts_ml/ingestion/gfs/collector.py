"""Immutable bounded GFS range collection after a resolved request plan."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from ..atmosphere.contracts import ArtifactReference, RawManifest, RequestPlan
from ..weather.artifacts import WeatherArtifactStore
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
                        last_modified_utc=item.object_last_modified_utc,
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
