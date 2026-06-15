from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "products" / "governed_authoring_studio" / "prototype_v1a"
STATIC_BRIDGE = PROTOTYPE / "prototype_bridge_static.js"


def _production_jsonl_snapshot() -> dict[str, tuple[int, str]]:
    data_dir = ROOT / "data"
    snapshot: dict[str, tuple[int, str]] = {}
    if not data_dir.exists():
        return snapshot
    for path in sorted(data_dir.rglob("*.jsonl")):
        payload = path.read_bytes()
        snapshot[str(path)] = (len(payload), hashlib.sha256(payload).hexdigest())
    return snapshot


def _run_node(expression: str, payload: dict[str, Any]) -> Any:
    script = f"""
const bridge = require({json.dumps(STATIC_BRIDGE.as_posix())});
const fs = require("fs");
const inputText = fs.readFileSync(0, "utf8");
const input = inputText ? JSON.parse(inputText) : {{}};
const fn = {expression};
const result = fn(bridge, input);
process.stdout.write(JSON.stringify(result));
"""
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def _sample_state(
    *,
    status: str = "provisional",
    evidence_refs: list[str] | None = None,
    unresolved_tensions: list[dict[str, Any]] | None = None,
    review_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "sourcePacketId": "prototype.packet.static.001",
        "participant": {"id": "P01", "displayName": "Example participant"},
        "governance": {
            "requestedOutputStatus": status,
            "draftMode": "publication_ready" if status == "approved" else "provisional",
            "unresolvedTensions": unresolved_tensions or [],
        },
        "intake": {
            "projectTitle": "Static bridge packet",
            "artifactType": "essay series",
            "sourceNotes": "Source text remains separate while a backend-compatible packet is exported.",
            "importantFragments": "Evidence refs and unresolved tensions must survive.",
            "existingStructure": "Intake -> review -> output.",
            "desiredOutput": "Create a governed authoring output packet.",
            "audience": "system reviewers",
            "privacyAck": True,
        },
        "review": {"status": "Ready to continue", "confidence": "Medium"},
        "evidence": {"status": "in production"},
        "evidenceRefs": evidence_refs or [],
        "reviewDecision": review_decision,
    }


def _approved_review(*, actor_type: str = "human", self_certified: bool = False) -> dict[str, Any]:
    return {
        "reviewDecisionId": "prototype.review.static.001",
        "actorId": f"prototype.{actor_type}.001",
        "actorType": actor_type,
        "role": "authoring_reviewer",
        "scope": "governed_authoring_output",
        "decision": "approved",
        "timestamp": "2026-06-15T15:00:00Z",
        "selfCertified": self_certified,
    }


def _issue_codes(packet: dict[str, Any]) -> set[str]:
    return {issue["code"] for issue in packet["bridge_issues"]}


def test_static_export_packet_shape_matches_bridge_contract() -> None:
    packet = _run_node("(bridge, input) => bridge.buildBridgePacket(input)", _sample_state())

    assert packet["schema_version"] == "governed_authoring.prototype_bridge.v1"
    assert packet["source_packet"]["schema_version"] == "governed_authoring.source_packet.v1"
    assert packet["source_packet"]["source_packet_id"] == "prototype.packet.static.001"
    assert packet["source_packet"]["requested_output_status"] == "provisional"
    assert packet["source_packet"]["draft_mode"] == "provisional"
    assert packet["source_packet"]["source_material"][0]["text"]
    assert packet["source_packet"]["claims"][0]["statement"] == "Create a governed authoring output packet."


def test_static_export_preserves_evidence_tensions_review_and_approved_status() -> None:
    state = _sample_state(
        status="approved",
        evidence_refs=["evidence:prototype.source.001", "evidence:operator.review.001"],
        unresolved_tensions=[
            {
                "id": "prototype.tension.lineage",
                "description": "Lineage should remain visible.",
                "blocking": True,
                "severity": "high",
            }
        ],
        review_decision=_approved_review(),
    )

    packet = _run_node("(bridge, input) => bridge.buildBridgePacket(input)", state)
    source_packet = packet["source_packet"]

    assert packet["bridge_issues"] == []
    assert source_packet["requested_output_status"] == "approved"
    assert source_packet["draft_mode"] == "publication_ready"
    assert source_packet["evidence_refs"] == ["evidence:prototype.source.001", "evidence:operator.review.001"]
    assert source_packet["unresolved_tensions"][0]["tension_id"] == "prototype.tension.lineage"
    assert source_packet["review_decision"]["decision"] == "approved"
    assert source_packet["review_decision"]["actor_type"] == "human"


@pytest.mark.parametrize("status", ["provisional", "rejected", "deferred", "approved"])
def test_output_status_survives_static_export_and_backend_result_import(status: str) -> None:
    evidence_refs = ["evidence:prototype.source.001"] if status == "approved" else []
    review = _approved_review() if status == "approved" else None
    exported = _run_node(
        "(bridge, input) => bridge.buildBridgePacket(input)",
        _sample_state(status=status, evidence_refs=evidence_refs, review_decision=review),
    )
    imported = _run_node(
        "(bridge, input) => bridge.importBackendResultPacket(input)",
        {
            "schema_version": "governed_authoring.output_manifest.v1",
            "output_manifest_id": f"output_manifest.{status}",
            "source_packet_id": "prototype.packet.static.001",
            "draft_candidate_id": "draft.static.001",
            "review_decision_id": "review.static.001",
            "output_status": status,
            "decision": status.upper(),
            "decision_reason": f"{status}_result",
            "evidence_refs": ["evidence:prototype.source.001"],
            "unresolved_tensions": [
                {
                    "tension_id": "prototype.tension.imported",
                    "description": "Imported tension survives.",
                    "blocking": status == "deferred",
                    "severity": "medium",
                }
            ],
            "messages": ["Imported result parsed locally."],
            "canonical_ledger_entry_id": "",
        },
    )

    assert exported["source_packet"]["requested_output_status"] == status
    assert imported["output_status"] == status
    assert imported["review_status"]
    assert imported["evidence_refs"] == ["evidence:prototype.source.001"]
    assert imported["unresolved_tensions"][0]["tension_id"] == "prototype.tension.imported"


def test_publication_ready_static_export_without_evidence_is_flagged() -> None:
    packet = _run_node(
        "(bridge, input) => bridge.buildBridgePacket(input)",
        _sample_state(status="approved", review_decision=_approved_review()),
    )

    assert "missing_evidence_refs" in _issue_codes(packet)


def test_generator_self_approval_is_flagged_in_static_export() -> None:
    packet = _run_node(
        "(bridge, input) => bridge.buildBridgePacket(input)",
        _sample_state(
            status="approved",
            evidence_refs=["evidence:prototype.source.001"],
            review_decision=_approved_review(actor_type="generator", self_certified=True),
        ),
    )

    assert "generator_self_approval" in _issue_codes(packet)
    assert packet["source_packet"]["review_decision"]["actor_type"] == "generator"


def test_static_ui_declares_non_production_boundary_and_no_network_surface() -> None:
    app_js = (PROTOTYPE / "app.js").read_text(encoding="utf-8")
    bridge_js = STATIC_BRIDGE.read_text(encoding="utf-8")
    index_html = (PROTOTYPE / "index.html").read_text(encoding="utf-8")
    readme = (PROTOTYPE / "README.md").read_text(encoding="utf-8")

    assert '<script src="prototype_bridge_static.js"></script>' in index_html
    for text in (app_js, readme):
        assert "Static prototype packet export/import only." in text
        assert "No backend submission occurs from this UI." in text
        assert "No production writes occur from this UI." in text

    combined_runtime = "\n".join([app_js, bridge_js, index_html])
    forbidden_tokens = [
        "fetch(",
        "XMLHttpRequest",
        "sendBeacon",
        "WebSocket",
        "EventSource",
        "http.createServer",
        "express(",
        "listen(",
        "pyodide",
        "python",
    ]
    for token in forbidden_tokens:
        assert token not in combined_runtime


def test_static_export_import_does_not_modify_production_jsonl_ledgers() -> None:
    before = _production_jsonl_snapshot()

    _run_node(
        "(bridge, input) => bridge.buildBridgePacket(input)",
        _sample_state(
            status="approved",
            evidence_refs=["evidence:prototype.source.001"],
            review_decision=_approved_review(),
        ),
    )
    _run_node(
        "(bridge, input) => bridge.importBackendResultPacket(input)",
        {
            "backend_result": {
                "output_manifest": {
                    "output_manifest_id": "output_manifest.static.import",
                    "source_packet_id": "prototype.packet.static.001",
                    "output_status": "approved",
                    "decision": "APPROVE_OUTPUT",
                    "decision_reason": "approved_output_ready",
                    "evidence_refs": ["evidence:prototype.source.001"],
                    "unresolved_tensions": [],
                    "messages": [],
                    "canonical_ledger_entry_id": "",
                }
            }
        },
    )

    assert _production_jsonl_snapshot() == before
