from __future__ import annotations

import hashlib
from typing import Any

from signal_agent.evidence_sources.canonical import canonical_json
from signal_agent.evidence_sources.models import NormalizedRelationshipBatch
from signal_agent.transport.schemas import derive_id


RUN_MANIFEST_SCHEMA_VERSION = "signal_agent.relationship_signal_run_manifest.v1"


class DetachedRunManifestBuilder:
    """Build the v1 detached run manifest from neutral prior outputs."""

    def build(
        self,
        *,
        created_at: str,
        batch: NormalizedRelationshipBatch,
        source_receipt_file_sha256: str,
        analysis: dict[str, Any],
        artifacts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        receipt = batch.preserved.source_receipt
        taxonomy = analysis["taxonomy"]
        protection = receipt.protection_dict()
        run_id = derive_id(
            "lrr",
            RUN_MANIFEST_SCHEMA_VERSION,
            batch.preserved.source_sha256,
            taxonomy["taxonomy_id"],
            taxonomy["taxonomy_version"],
            taxonomy["file_sha256"].removeprefix("sha256:"),
            protection["key_id"],
            length=20,
        )
        manifest = {
            "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
            "run_id": run_id,
            "created_at": created_at,
            "completion_state": "completed",
            "source": {
                "source_sha256": f"sha256:{batch.preserved.source_sha256}",
                "source_receipt_id": receipt.receipt_id,
                "source_receipt_hash": receipt.receipt_hash,
                "source_receipt_file_sha256": f"sha256:{source_receipt_file_sha256}",
                "source_receipt_path": receipt.persisted_relative_path,
            },
            "taxonomy": {
                "taxonomy_id": taxonomy["taxonomy_id"],
                "taxonomy_version": taxonomy["taxonomy_version"],
                "file_sha256": taxonomy["file_sha256"],
            },
            "identifier_protection": {
                "key_id": protection["key_id"],
                "algorithm": protection["algorithm"],
                "version": protection["version"],
            },
            "artifacts": artifacts,
            "canonicalization": {
                "encoding": "UTF-8",
                "ensure_ascii": False,
                "object_keys": "sorted",
                "json_separators": [",", ":"],
                "json_final_newline_count": 1,
                "jsonl_record_format": "one_canonical_object_plus_newline",
                "artifact_hash_boundary": "exact_persisted_bytes_including_final_newline",
                "packet_hash_boundary": "canonical_packet_content_excluding_only_packet_hash_without_final_newline",
                "manifest_hash_boundary": "canonical_manifest_content_excluding_only_manifest_hash_without_final_newline",
            },
            "safety_flags": {
                "campaign_authorized": False,
                "contact_authorized": False,
                "content_library_mutated": False,
                "external_action_authorized": False,
                "message_authorized": False,
                "network_authorized": False,
                "publication_authorized": False,
                "retention_mutated": False,
                "routing_authorized": False,
                "social_orchestration_mutated": False,
            },
        }
        manifest["manifest_hash"] = "sha256:" + hashlib.sha256(
            canonical_json(manifest).encode("utf-8")
        ).hexdigest()
        return manifest
