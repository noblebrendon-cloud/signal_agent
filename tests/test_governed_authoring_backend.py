from __future__ import annotations

import hashlib
import json
from pathlib import Path

from signal_agent.formal_governance.ledger import read_ledger_entries, verify_ledger
from signal_agent.governed_authoring import GovernedAuthoringRuntime, SourcePacket


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "governed_authoring"
SCHEMAS = ROOT / "schemas" / "governed_authoring"
LEDGER_SCHEMA = ROOT / "schemas" / "formal_governance" / "governed_transition_ledger_entry.v1.schema.json"
PROTOTYPE = ROOT / "products" / "governed_authoring_studio" / "prototype_v1a"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _run_fixture(name: str, *, canonical_ledger_path: Path | None = None):
    runtime = GovernedAuthoringRuntime(canonical_ledger_path=canonical_ledger_path)
    return runtime.run(_fixture(name))


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


def _assert_schema_fields(entry: dict) -> None:
    schema = json.loads(LEDGER_SCHEMA.read_text(encoding="utf-8"))
    assert set(schema["required"]) <= set(entry)
    assert set(entry) <= set(schema["properties"])
    assert entry["schema_version"] == "governed_transition_ledger_entry.v1"
    assert entry["content_hash"].startswith("sha256:")
    assert entry["record_hash"].startswith("sha256:")
    assert isinstance(entry["subsystem_refs"], list)


def _assert_ref(entry: dict, ref_type: str) -> None:
    assert any(
        ref.get("subsystem") == "governed_authoring" and ref.get("ref_type") == ref_type
        for ref in entry["subsystem_refs"]
    )


def test_governed_authoring_schema_files_are_present_and_parseable() -> None:
    expected = {
        "source_packet.v1.schema.json",
        "draft_candidate.v1.schema.json",
        "review_decision.v1.schema.json",
        "output_manifest.v1.schema.json",
    }

    assert expected == {path.name for path in SCHEMAS.glob("*.json")}
    for schema_name in expected:
        schema = json.loads((SCHEMAS / schema_name).read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["type"] == "object"
        assert schema["required"]


def test_valid_source_packet_materializes_typed_backend_models() -> None:
    packet = SourcePacket.from_dict(_fixture("valid_source_packet.json"))

    assert packet.source_packet_id == "ga.source.valid"
    assert packet.has_source_material() is True
    assert packet.claim_references()[0].claim_id == "claim.valid.source"
    assert packet.all_evidence_refs() == ["evidence:source.valid.001"]


def test_valid_source_packet_can_produce_provisional_governed_draft() -> None:
    result = _run_fixture("valid_provisional_output.json")

    assert result.output_manifest.output_status == "provisional"
    assert result.formal_decision.decision.value == "EMIT_PROVISIONAL_DRAFT"
    assert result.formal_decision.gate_results[0].outcome.value == "ADMIT_SOURCE_PACKET"
    assert result.draft_candidate is not None
    assert result.draft_candidate.status == "provisional"
    assert result.draft_candidate.evidence_refs == []
    assert result.canonical_ledger_entry is None


def test_valid_source_with_evidence_and_human_review_can_approve_output(tmp_path: Path) -> None:
    canonical_ledger = tmp_path / "canonical" / "governed_authoring.jsonl"

    result = _run_fixture("valid_approved_output.json", canonical_ledger_path=canonical_ledger)

    assert result.output_manifest.output_status == "approved"
    assert result.formal_decision.decision.value == "APPROVE_OUTPUT"
    assert result.output_manifest.canonical_ledger_entry_id
    entries = read_ledger_entries(canonical_ledger)
    assert len(entries) == 1
    entry = entries[0]
    _assert_schema_fields(entry)
    _assert_ref(entry, "authoring_trace")
    _assert_ref(entry, "source_packet")
    _assert_ref(entry, "draft_candidate")
    _assert_ref(entry, "review_decision")
    _assert_ref(entry, "output_manifest")
    _assert_ref(entry, "evidence_ref")
    _assert_ref(entry, "unresolved_tension")
    assert entry["decision"] == "APPROVE_OUTPUT"
    assert entry["human_authority_status"]["approved"] is True
    assert entry["unresolved_tensions"][0]["tension_id"] == "tension.nonblocking.style"
    assert verify_ledger(canonical_ledger)["clean"] is True


def test_missing_source_material_is_rejected() -> None:
    result = _run_fixture("missing_source_material.json")

    assert result.draft_candidate is None
    assert result.output_manifest.output_status == "rejected"
    assert result.formal_decision.decision.value == "REJECT_MISSING_SOURCE"
    assert result.formal_decision.gate_results[-1].reason_code == "missing_source_material"


def test_missing_evidence_prevents_publication_ready_output() -> None:
    result = _run_fixture("missing_evidence_refs.json")

    assert result.output_manifest.output_status == "rejected"
    assert result.formal_decision.decision.value == "REJECT_MISSING_EVIDENCE"
    assert result.output_manifest.evidence_refs == []
    assert result.formal_decision.gate_results[-1].reason_code == "missing_evidence_refs"


def test_blocking_unresolved_tension_defers_approval(tmp_path: Path) -> None:
    canonical_ledger = tmp_path / "canonical" / "deferred.jsonl"

    result = _run_fixture("blocking_unresolved_tension.json", canonical_ledger_path=canonical_ledger)

    assert result.output_manifest.output_status == "deferred"
    assert result.formal_decision.decision.value == "DEFER_UNRESOLVED_TENSION"
    assert result.output_manifest.unresolved_tensions[0].blocking is True
    entry = read_ledger_entries(canonical_ledger)[0]
    assert entry["decision"] == "DEFER_UNRESOLVED_TENSION"
    assert entry["unresolved_tensions"][0]["tension_id"] == "tension.blocking.lineage"


def test_nonblocking_unresolved_tension_is_recorded_without_blocking_approval(tmp_path: Path) -> None:
    canonical_ledger = tmp_path / "canonical" / "nonblocking.jsonl"

    result = _run_fixture("valid_approved_output.json", canonical_ledger_path=canonical_ledger)

    assert result.output_manifest.output_status == "approved"
    assert result.output_manifest.unresolved_tensions[0].blocking is False
    entry = read_ledger_entries(canonical_ledger)[0]
    assert entry["decision"] == "APPROVE_OUTPUT"
    assert entry["unresolved_tensions"][0]["blocking"] is False
    assert any(
        ref.get("ref_type") == "unresolved_tension"
        and ref.get("tension_id") == "tension.nonblocking.style"
        for ref in entry["subsystem_refs"]
    )


def test_missing_human_review_prevents_approval() -> None:
    result = _run_fixture("missing_human_review.json")

    assert result.output_manifest.output_status == "rejected"
    assert result.formal_decision.decision.value == "REJECT_MISSING_HUMAN_REVIEW"
    assert result.output_manifest.review_decision_id == ""
    assert result.formal_decision.gate_results[-1].reason_code == "missing_human_review"


def test_generator_or_model_self_approval_is_rejected() -> None:
    result = _run_fixture("generator_self_approved.json")

    assert result.output_manifest.output_status == "rejected"
    assert result.formal_decision.decision.value == "REJECT_SELF_APPROVAL"
    assert result.review_decision is not None
    assert result.review_decision.actor_type == "generator"
    assert result.formal_decision.gate_results[-1].reason_code == "generator_self_approval"


def test_canonical_ledger_entry_includes_authoring_subsystem_refs(tmp_path: Path) -> None:
    canonical_ledger = tmp_path / "canonical" / "refs.jsonl"

    result = _run_fixture("valid_approved_output.json", canonical_ledger_path=canonical_ledger)
    entry = read_ledger_entries(canonical_ledger)[0]
    trace = next(ref for ref in entry["subsystem_refs"] if ref.get("ref_type") == "authoring_trace")

    assert trace["source_packet_id"] == result.source_packet.source_packet_id
    assert trace["draft_candidate_id"] == result.draft_candidate.draft_candidate_id
    assert trace["review_decision_id"] == result.review_decision.review_decision_id
    assert trace["output_manifest_id"] == result.output_manifest.output_manifest_id
    assert trace["evidence_refs"] == ["evidence:source.approved.001"]
    assert trace["tension_ids"] == ["tension.nonblocking.style"]


def test_governed_authoring_tests_do_not_modify_production_jsonl_or_static_prototype(tmp_path: Path) -> None:
    before_jsonl = _production_jsonl_snapshot()
    before_prototype = _prototype_snapshot()
    canonical_ledger = tmp_path / "canonical" / "guard.jsonl"

    _run_fixture("valid_provisional_output.json")
    _run_fixture("valid_approved_output.json", canonical_ledger_path=canonical_ledger)
    _run_fixture("blocking_unresolved_tension.json", canonical_ledger_path=tmp_path / "canonical" / "defer.jsonl")
    _run_fixture("generator_self_approved.json")

    assert read_ledger_entries(canonical_ledger)
    assert _production_jsonl_snapshot() == before_jsonl
    assert _prototype_snapshot() == before_prototype
