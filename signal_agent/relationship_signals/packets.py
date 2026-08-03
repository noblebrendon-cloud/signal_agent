from __future__ import annotations

from copy import deepcopy
from typing import Any

from signal_agent.evidence_sources.canonical import sha256_canonical_json
from signal_agent.evidence_sources.models import NormalizedRelationshipBatch
from signal_agent.transport.schemas import derive_id


SIGNAL_PACKET_SCHEMA_VERSION = "signal_agent.relationship_signal_packet.v1"
CAMPAIGN_PACKET_SCHEMA_VERSION = "signal_agent.campaign_context_packet.v1"


def _seal_packet(packet: dict[str, Any]) -> dict[str, Any]:
    sealed = deepcopy(packet)
    sealed.pop("packet_hash", None)
    sealed["packet_hash"] = "sha256:" + sha256_canonical_json(sealed)
    return sealed


def build_signal_packet(
    *,
    created_at: str,
    source_receipt: dict[str, Any],
    source_sha256: str,
    normalized_artifact: dict[str, Any],
    unresolved_artifact: dict[str, Any],
    topic_cluster_artifact: dict[str, Any],
    related_work_artifact: dict[str, Any],
    topic_cluster: dict[str, Any],
    related_work: dict[str, Any],
) -> dict[str, Any]:
    taxonomy = deepcopy(topic_cluster["taxonomy"])
    cluster = deepcopy(topic_cluster["inferred_cluster"])
    cluster["analysis_status"] = topic_cluster["analysis_status"]
    stable_inputs = {
        "schema_version": SIGNAL_PACKET_SCHEMA_VERSION,
        "source_sha256": source_sha256,
        "source_receipt_id": source_receipt["receipt_id"],
        "normalized_sha256": normalized_artifact["sha256"],
        "unresolved_sha256": unresolved_artifact["sha256"],
        "topic_cluster_sha256": topic_cluster_artifact["sha256"],
        "related_work_sha256": related_work_artifact["sha256"],
        "taxonomy": taxonomy,
    }
    packet = {
        "schema_version": SIGNAL_PACKET_SCHEMA_VERSION,
        "packet_id": derive_id("rsp", sha256_canonical_json(stable_inputs), length=20),
        "created_at": created_at,
        "status": "pending_human_approval",
        "source": {
            "source_receipt_id": source_receipt["receipt_id"],
            "source_receipt_hash": source_receipt["receipt_hash"],
            "source_sha256": f"sha256:{source_sha256}",
        },
        "artifact_references": {
            "normalized_relationships": deepcopy(normalized_artifact),
            "unresolved_matches": deepcopy(unresolved_artifact),
            "topic_cluster": deepcopy(topic_cluster_artifact),
            "related_work": deepcopy(related_work_artifact),
        },
        "taxonomy": taxonomy,
        "deterministic_classification": {
            "method": topic_cluster["analysis_method"],
            "matches": deepcopy(topic_cluster["deterministic_matches"]),
            "ambiguous_matches": deepcopy(topic_cluster["ambiguous_matches"]),
            "unclassified_record_ids": deepcopy(topic_cluster["unclassified_record_ids"]),
        },
        "inferred_results": {
            "topic_cluster": cluster,
            "related_work": {
                "confidence_state": related_work["confidence_state"],
                "evidence_refs": deepcopy(related_work["evidence_refs"]),
            },
        },
        "related_work": {
            "search_scope": related_work["search_scope"],
            "scope_complete": related_work["scope_complete"],
            "result_characterization": related_work["result_characterization"],
            "results": deepcopy(related_work["results"]),
        },
        "privacy": {
            "clear_email_embedded": False,
            "email_hmac_token_embedded": False,
            "linkedin_url_embedded": False,
            "contact_target_embedded": False,
        },
        "routing": {
            "content_library": {"state": "pending", "performed": False},
            "campaign": {"state": "pending", "performed": False},
        },
        "safety_flags": {
            "contact_authorized": False,
            "external_action_authorized": False,
            "message_authorized": False,
            "network_authorized": False,
            "publication_authorized": False,
            "routing_authorized": False,
        },
    }
    return _seal_packet(packet)


def build_campaign_context_packet(
    *,
    created_at: str,
    signal_packet: dict[str, Any],
    signal_packet_path: str,
    signal_packet_file_sha256: str,
) -> dict[str, Any]:
    # This builder's sole semantic input is the already-built signal packet. It
    # intentionally cannot inspect normalized records or source CSV data.
    signal_cluster = signal_packet["inferred_results"]["topic_cluster"]
    signal_related = signal_packet["related_work"]
    cluster_context = {
        "cluster_id": signal_cluster["cluster_id"],
        "label": signal_cluster["label"],
        "status": signal_cluster["analysis_status"],
        "confidence_state": signal_cluster["confidence_state"],
        "rule_groups": deepcopy(signal_cluster["rule_groups"]),
        "supporting_record_count": signal_cluster["supporting_record_count"],
        "evidence_refs": deepcopy(signal_cluster["evidence_refs"]),
        "inference_method": signal_cluster["inference_method"],
        "inference_basis": signal_cluster["inference_basis"],
    }
    relationship_count = signal_packet["artifact_references"]["normalized_relationships"][
        "record_count"
    ]
    unresolved_count = signal_packet["artifact_references"]["unresolved_matches"][
        "record_count"
    ]
    packet = {
        "schema_version": CAMPAIGN_PACKET_SCHEMA_VERSION,
        "packet_id": derive_id(
            "ccp",
            CAMPAIGN_PACKET_SCHEMA_VERSION,
            signal_packet["packet_id"],
            length=20,
        ),
        "created_at": created_at,
        "status": "pending_human_approval",
        "source_signal_packet": {
            "packet_id": signal_packet["packet_id"],
            "packet_hash": signal_packet["packet_hash"],
            "path": signal_packet_path,
            "file_sha256": f"sha256:{signal_packet_file_sha256}",
        },
        "context_readiness": (
            "insufficient_evidence"
            if signal_cluster["confidence_state"] == "insufficient"
            else "pending_human_review"
        ),
        "aggregate_cluster": cluster_context,
        "related_work": {
            "search_scope": signal_related["search_scope"],
            "scope_complete": signal_related["scope_complete"],
            "result_characterization": signal_related["result_characterization"],
            "references": [
                {
                    "atom_id": result["atom_id"],
                    "atom_path": result["atom_path"],
                    "originating_event_ids": deepcopy(result["originating_event_ids"]),
                    "confidence_state": result["confidence_state"],
                    "evidence_refs": deepcopy(result["evidence_refs"]),
                }
                for result in signal_related["results"]
            ],
        },
        "counts": {
            "relationship_records": relationship_count,
            "unresolved_candidate_groups": unresolved_count,
        },
        "authorization": {
            "authorized": False,
            "authorization_scope": "none",
            "approval_id": None,
            "human_approval_required": True,
        },
        "routing": {
            "social_orchestration": {"state": "pending", "performed": False},
            "content_library": {"state": "pending", "performed": False},
        },
        "privacy": {
            "relationship_names_embedded": False,
            "contact_identifiers_embedded": False,
            "contact_targets_embedded": False,
            "audience_embedded": False,
            "platforms_embedded": False,
            "campaign_copy_embedded": False,
            "schedule_embedded": False,
            "outreach_instructions_embedded": False,
        },
        "safety_flags": {
            "campaign_authorized": False,
            "contact_authorized": False,
            "external_action_authorized": False,
            "message_authorized": False,
            "network_authorized": False,
            "publication_authorized": False,
            "routing_authorized": False,
        },
    }
    return _seal_packet(packet)


class GovernedRelationshipPacketBuilder:
    """PacketBuilder wrapper preserving the v1 packet functions unchanged."""

    def build_signal_packet(
        self,
        *,
        created_at: str,
        batch: NormalizedRelationshipBatch,
        normalized_artifact: dict[str, Any],
        unresolved_artifact: dict[str, Any],
        analysis_artifact: dict[str, Any],
        context_artifact: dict[str, Any],
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        receipt = batch.preserved.source_receipt
        return build_signal_packet(
            created_at=created_at,
            source_receipt={
                "receipt_id": receipt.receipt_id,
                "receipt_hash": receipt.receipt_hash,
            },
            source_sha256=batch.preserved.source_sha256,
            normalized_artifact=normalized_artifact,
            unresolved_artifact=unresolved_artifact,
            topic_cluster_artifact=analysis_artifact,
            related_work_artifact=context_artifact,
            topic_cluster=analysis,
            related_work=context,
        )

    def build_campaign_context_packet(
        self,
        *,
        created_at: str,
        signal_packet: dict[str, Any],
        signal_packet_path: str,
        signal_packet_file_sha256: str,
    ) -> dict[str, Any]:
        return build_campaign_context_packet(
            created_at=created_at,
            signal_packet=signal_packet,
            signal_packet_path=signal_packet_path,
            signal_packet_file_sha256=signal_packet_file_sha256,
        )
