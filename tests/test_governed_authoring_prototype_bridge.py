from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from signal_agent.governed_authoring.prototype_bridge import (
    PrototypeBridgeError,
    bridge_prototype_packet,
    output_manifest_to_prototype_result,
    prototype_to_source_packet,
    run_prototype_bridge,
)
from signal_agent.governed_authoring.runtime import GovernedAuthoringRuntime


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "products" / "governed_authoring_studio" / "prototype_v1a"


def _production_jsonl_snapshot() -> dict[str, tuple[int, str]]:
    data_dir = ROOT / "data"
    snapshot: dict[str, tuple[int, str]] = {}
    if not data_dir.exists():
        return snapshot
    for path in sorted(data_dir.rglob("*.jsonl")):
        payload = path.read_bytes()
        snapshot[str(path)] = (len(payload), hashlib.sha256(payload).hexdigest())
    return snapshot


def _prototype_snapshot() -> dict[str, str]:
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(PROTOTYPE.glob("*"))
        if path.is_file()
    }


def _base_prototype_packet() -> dict:
    return {
        "sourcePacketId": "prototype.packet.001",
        "participant": {
            "id": "P01",
            "displayName": "Example participant",
        },
        "governance": {
            "requestedOutputStatus": "provisional",
            "draftMode": "provisional",
        },
        "intake": {
            "projectTitle": "Prototype bridge packet",
            "artifactType": "essay series",
            "sourceNotes": (
                "The static prototype should keep source and generated output separate while "
                "exporting packet data that a governed backend can evaluate."
            ),
            "importantFragments": "Source remains private by default.",
            "existingStructure": "Intake -> review -> output.",
            "desiredOutput": "Create a governed first draft path.",
            "audience": "careful system reviewers",
            "privacyAck": True,
        },
        "review": {
            "status": "Ready to continue",
            "confidence": "Medium",
        },
        "evidence": {
            "status": "in production",
        },
    }


def _approved_review() -> dict:
    return {
        "reviewDecisionId": "prototype.review.approved",
        "actorId": "reviewer.human.001",
        "actorType": "human",
        "role": "authoring_reviewer",
        "scope": "governed_authoring_output",
        "decision": "approved",
        "timestamp": "2026-06-15T15:00:00Z",
        "selfCertified": False,
    }


def _run(packet: dict):
    return GovernedAuthoringRuntime().run(prototype_to_source_packet(packet))


def _issue_codes(bridge_packet: dict) -> set[str]:
    return {issue["code"] for issue in bridge_packet["bridge_issues"]}


def test_prototype_packet_converts_to_backend_source_packet_for_provisional_draft() -> None:
    packet = _base_prototype_packet()

    bridge_packet = bridge_prototype_packet(packet)
    source_packet = bridge_packet["source_packet"]
    result = _run(packet)
    prototype_result = output_manifest_to_prototype_result(result.output_manifest)

    assert bridge_packet["schema_version"] == "governed_authoring.prototype_bridge.v1"
    assert source_packet["schema_version"] == "governed_authoring.source_packet.v1"
    assert source_packet["source_packet_id"] == "prototype.packet.001"
    assert source_packet["requested_output_status"] == "provisional"
    assert source_packet["draft_mode"] == "provisional"
    assert source_packet["source_material"][0]["text"]
    assert source_packet["claims"][0]["statement"] == "Create a governed first draft path."
    assert result.output_manifest.output_status == "provisional"
    assert prototype_result["output_status"] == "provisional"
    assert prototype_result["review_status"] == "Provisional backend draft"


def test_approved_prototype_packet_preserves_evidence_review_and_output_status() -> None:
    packet = _base_prototype_packet()
    packet["governance"] = {
        "requestedOutputStatus": "approved",
        "draftMode": "publication_ready",
    }
    packet["evidenceRefs"] = ["evidence:prototype.source.001", "evidence:operator.review.001"]
    packet["reviewDecision"] = _approved_review()

    bridge_packet = bridge_prototype_packet(packet)
    source_packet = bridge_packet["source_packet"]
    result = _run(packet)
    prototype_result = output_manifest_to_prototype_result(result.output_manifest)

    assert bridge_packet["bridge_issues"] == []
    assert source_packet["evidence_refs"] == ["evidence:prototype.source.001", "evidence:operator.review.001"]
    assert source_packet["review_decision"]["decision"] == "approved"
    assert source_packet["review_decision"]["actor_type"] == "human"
    assert result.output_manifest.output_status == "approved"
    assert prototype_result["output_status"] == "approved"
    assert prototype_result["review_status"] == "Approved by backend review"
    assert prototype_result["evidence_refs"] == ["evidence:prototype.source.001", "evidence:operator.review.001"]


def test_publication_ready_prototype_packet_without_evidence_is_flagged_and_rejected() -> None:
    packet = _base_prototype_packet()
    packet["governance"] = {
        "requestedOutputStatus": "approved",
        "draftMode": "publication_ready",
    }
    packet["reviewDecision"] = _approved_review()

    bridge_packet = bridge_prototype_packet(packet)
    result = _run(packet)

    assert "missing_evidence_refs" in _issue_codes(bridge_packet)
    assert result.output_manifest.output_status == "rejected"
    assert result.formal_decision.decision.value == "REJECT_MISSING_EVIDENCE"
    with pytest.raises(PrototypeBridgeError):
        bridge_prototype_packet(packet, strict=True)


def test_blocking_unresolved_tension_survives_conversion_and_defers_backend_approval() -> None:
    packet = _base_prototype_packet()
    packet["governance"] = {
        "requestedOutputStatus": "approved",
        "draftMode": "publication_ready",
        "unresolvedTensions": [
            {
                "id": "prototype.tension.lineage",
                "description": "Source lineage must be clarified before approval.",
                "blocking": True,
                "severity": "high",
            }
        ],
    }
    packet["evidenceRefs"] = ["evidence:prototype.source.001"]
    packet["reviewDecision"] = _approved_review()

    source_packet = prototype_to_source_packet(packet)
    result = _run(packet)
    prototype_result = output_manifest_to_prototype_result(result.output_manifest)

    assert source_packet["unresolved_tensions"][0]["tension_id"] == "prototype.tension.lineage"
    assert source_packet["unresolved_tensions"][0]["blocking"] is True
    assert result.output_manifest.output_status == "deferred"
    assert result.formal_decision.decision.value == "DEFER_UNRESOLVED_TENSION"
    assert prototype_result["unresolved_tensions"][0]["tension_id"] == "prototype.tension.lineage"
    assert prototype_result["output_status"] == "deferred"


def test_generator_self_approval_survives_conversion_and_is_rejected() -> None:
    packet = _base_prototype_packet()
    packet["governance"] = {
        "requestedOutputStatus": "approved",
        "draftMode": "publication_ready",
    }
    packet["evidenceRefs"] = ["evidence:prototype.source.001"]
    packet["reviewDecision"] = {
        "reviewDecisionId": "prototype.review.self_approved",
        "actorId": "prototype.generator",
        "actorType": "generator",
        "role": "authoring_reviewer",
        "scope": "governed_authoring_output",
        "decision": "approved",
        "timestamp": "2026-06-15T15:05:00Z",
        "selfCertified": True,
    }

    bridge_packet = bridge_prototype_packet(packet)
    result = _run(packet)
    prototype_result = output_manifest_to_prototype_result(result.output_manifest)

    assert "generator_self_approval" in _issue_codes(bridge_packet)
    assert bridge_packet["source_packet"]["review_decision"]["actor_type"] == "generator"
    assert result.output_manifest.output_status == "rejected"
    assert result.formal_decision.decision.value == "REJECT_SELF_APPROVAL"
    assert prototype_result["output_status"] == "rejected"


def test_run_prototype_bridge_returns_backend_and_prototype_result_without_required_ledger() -> None:
    packet = _base_prototype_packet()

    result = run_prototype_bridge(packet)

    assert result["source_packet"]["source_packet_id"] == "prototype.packet.001"
    assert result["backend_result"]["output_manifest"]["output_status"] == "provisional"
    assert result["prototype_result"]["output_status"] == "provisional"
    assert result["backend_result"]["canonical_ledger_entry"] is None


def test_bridge_does_not_modify_production_jsonl_or_static_prototype_files() -> None:
    before_jsonl = _production_jsonl_snapshot()
    before_prototype = _prototype_snapshot()
    approved = _base_prototype_packet()
    approved["governance"] = {
        "requestedOutputStatus": "approved",
        "draftMode": "publication_ready",
    }
    approved["evidenceRefs"] = ["evidence:prototype.source.001"]
    approved["reviewDecision"] = _approved_review()

    run_prototype_bridge(_base_prototype_packet())
    run_prototype_bridge(approved)

    assert _production_jsonl_snapshot() == before_jsonl
    assert _prototype_snapshot() == before_prototype
