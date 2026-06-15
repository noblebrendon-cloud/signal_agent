from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from signal_agent.formal_governance.ledger import read_ledger_entries
from signal_agent.governed_authoring.offline_harness import (
    OFFLINE_VERIFICATION_SCHEMA_VERSION,
    load_static_export_packet,
    run_offline_verification_file,
    write_static_import_packet,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "governed_authoring"
HARNESS = ROOT / "signal_agent" / "governed_authoring" / "offline_harness.py"


def _fixture_path(name: str) -> Path:
    return FIXTURES / name


def _run(name: str, *, canonical_ledger_path: Path | None = None) -> dict[str, Any]:
    return run_offline_verification_file(_fixture_path(name), canonical_ledger_path=canonical_ledger_path)


def _production_jsonl_snapshot() -> dict[str, tuple[int, str]]:
    data_dir = ROOT / "data"
    snapshot: dict[str, tuple[int, str]] = {}
    if not data_dir.exists():
        return snapshot
    for path in sorted(data_dir.rglob("*.jsonl")):
        payload = path.read_bytes()
        snapshot[str(path)] = (len(payload), hashlib.sha256(payload).hexdigest())
    return snapshot


def _assert_static_import_packet(result: dict[str, Any], status: str) -> dict[str, Any]:
    packet = result["static_import_packet"]
    assert packet["schema_version"] == "governed_authoring.prototype_result.v1"
    assert packet["output_status"] == status
    assert packet["review_status"]
    assert packet["source_packet_id"] == result["source_packet"]["source_packet_id"]
    assert packet["backend_output_manifest_id"] == result["output_manifest"]["output_manifest_id"]
    return packet


def test_valid_static_provisional_export_produces_import_compatible_provisional_result() -> None:
    result = _run("static_export_valid_provisional.json")
    packet = _assert_static_import_packet(result, "provisional")

    assert result["schema_version"] == OFFLINE_VERIFICATION_SCHEMA_VERSION
    assert result["backend_result"]["formal_decision"]["decision"] == "EMIT_PROVISIONAL_DRAFT"
    assert packet["review_status"] == "Provisional backend draft"
    assert packet["evidence_refs"] == []
    assert packet["unresolved_tensions"] == []


def test_valid_static_approved_export_produces_import_compatible_approved_result() -> None:
    result = _run("static_export_valid_approved.json")
    packet = _assert_static_import_packet(result, "approved")

    assert result["backend_result"]["formal_decision"]["decision"] == "APPROVE_OUTPUT"
    assert packet["review_status"] == "Approved by backend review"
    assert packet["evidence_refs"] == ["evidence:prototype.source.offline.001"]
    assert packet["unresolved_tensions"][0]["tension_id"] == "prototype.tension.offline.nonblocking"
    assert result["backend_result"]["review_decision"]["decision"] == "approved"


def test_missing_evidence_static_export_rejects_publication_ready_approval() -> None:
    result = _run("static_export_missing_evidence.json")
    packet = _assert_static_import_packet(result, "rejected")

    assert "missing_evidence_refs" in {issue["code"] for issue in result["bridge_issues"]}
    assert result["backend_result"]["formal_decision"]["decision"] == "REJECT_MISSING_EVIDENCE"
    assert result["output_manifest"]["decision_reason"] == "missing_evidence_refs"
    assert packet["review_status"] == "Rejected by backend review"
    assert packet["evidence_refs"] == []


def test_blocking_unresolved_tension_static_export_defers_approval() -> None:
    result = _run("static_export_blocking_tension.json")
    packet = _assert_static_import_packet(result, "deferred")

    assert result["backend_result"]["formal_decision"]["decision"] == "DEFER_UNRESOLVED_TENSION"
    assert result["output_manifest"]["decision_reason"] == "blocking_unresolved_tension"
    assert packet["review_status"] == "Deferred by backend review"
    assert packet["evidence_refs"] == ["evidence:prototype.source.offline.002"]
    assert packet["unresolved_tensions"][0]["tension_id"] == "prototype.tension.offline.lineage"
    assert packet["unresolved_tensions"][0]["blocking"] is True


def test_generator_self_approval_static_export_rejects_approval() -> None:
    result = _run("static_export_generator_self_approval.json")
    packet = _assert_static_import_packet(result, "rejected")

    assert "generator_self_approval" in {issue["code"] for issue in result["bridge_issues"]}
    assert result["backend_result"]["formal_decision"]["decision"] == "REJECT_SELF_APPROVAL"
    assert result["backend_result"]["review_decision"]["actor_type"] == "generator"
    assert packet["review_status"] == "Rejected by backend review"
    assert packet["evidence_refs"] == ["evidence:prototype.source.offline.003"]


def test_optional_canonical_ledger_write_uses_temp_path_only(tmp_path: Path) -> None:
    before = _production_jsonl_snapshot()
    canonical_ledger_path = tmp_path / "canonical" / "governed_authoring.jsonl"

    result = _run("static_export_valid_approved.json", canonical_ledger_path=canonical_ledger_path)
    packet = _assert_static_import_packet(result, "approved")
    entries = read_ledger_entries(canonical_ledger_path)

    assert len(entries) == 1
    assert entries[0]["decision"] == "APPROVE_OUTPUT"
    assert result["backend_result"]["canonical_ledger_entry"]["ledger_entry_id"] == entries[0]["ledger_entry_id"]
    assert packet["canonical_ledger_entry_id"] == entries[0]["ledger_entry_id"]
    assert _production_jsonl_snapshot() == before


def test_static_import_packet_can_be_written_to_temp_fixture_path(tmp_path: Path) -> None:
    result = _run("static_export_blocking_tension.json")
    target = tmp_path / "static_import" / "blocking_tension_result.json"

    write_static_import_packet(target, result)
    payload = json.loads(target.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "governed_authoring.prototype_result.v1"
    assert payload["output_status"] == "deferred"
    assert payload["unresolved_tensions"][0]["tension_id"] == "prototype.tension.offline.lineage"


def test_offline_harness_loads_static_export_fixtures_without_modifying_production_jsonl() -> None:
    before = _production_jsonl_snapshot()

    for name in [
        "static_export_valid_provisional.json",
        "static_export_valid_approved.json",
        "static_export_missing_evidence.json",
        "static_export_blocking_tension.json",
        "static_export_generator_self_approval.json",
    ]:
        fixture = load_static_export_packet(_fixture_path(name))
        assert fixture["schema_version"] == "governed_authoring.prototype_bridge.v1"
        result = _run(name)
        assert result["static_import_packet"]["schema_version"] == "governed_authoring.prototype_result.v1"

    assert _production_jsonl_snapshot() == before


def test_offline_harness_introduces_no_network_or_server_surface() -> None:
    harness_text = HARNESS.read_text(encoding="utf-8")
    forbidden_tokens = [
        "fetch(",
        "XMLHttpRequest",
        "sendBeacon",
        "WebSocket",
        "EventSource",
        "http.server",
        "socket",
        "requests",
        "urllib",
        "FastAPI",
        "Flask",
        "listen(",
    ]

    for token in forbidden_tokens:
        assert token not in harness_text
