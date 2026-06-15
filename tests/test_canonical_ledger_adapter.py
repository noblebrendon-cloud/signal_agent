from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import app.hq.governance as governance
from app.hq.capture import promote
from signal_agent.content import claim_distributor, claim_engine
from signal_agent.content.claim_engine import (
    ClaimEvidenceError,
    evaluate_claim_evidence,
    generate_claim,
)
from signal_agent.formal_governance.adapters import append_claim_evidence_entry
from signal_agent.formal_governance.ledger import read_ledger_entries, verify_ledger


SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "schemas"
    / "formal_governance"
    / "governed_transition_ledger_entry.v1.schema.json"
)


def _redirect_claim_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    claims_dir = tmp_path / "claims"
    monkeypatch.setattr(claim_engine, "CLAIMS_DIR", claims_dir)
    monkeypatch.setattr(claim_engine, "INBOX_DIR", claims_dir / "inbox")
    monkeypatch.setattr(claim_engine, "ANCHORED_DIR", claims_dir / "anchored")
    monkeypatch.setattr(claim_engine, "DISTRIBUTED_DIR", claims_dir / "distributed")
    monkeypatch.setattr(claim_engine, "LEDGER_PATH", claims_dir / "claims_ledger.jsonl")
    monkeypatch.setattr(claim_distributor, "CLAIMS_DIR", claims_dir)
    monkeypatch.setattr(claim_distributor, "DISTRIBUTED_DIR", claims_dir / "distributed")
    monkeypatch.setattr(claim_distributor, "DISTRIBUTION_LOG", claims_dir / "distribution_log.jsonl")
    return claims_dir


def _raw_claim_text() -> str:
    return "Canonical claim evidence decisions must link to their subsystem evidence."


def _evidence_authority() -> dict:
    return {
        "actor_type": "human",
        "actor_id": "curator.test",
        "self_certified": False,
    }


def _make_capture_dir(tmp_path: Path) -> Path:
    capture_dir = tmp_path / "capture"
    for name in ("raw", "promoted", "archive"):
        (capture_dir / name).mkdir(parents=True, exist_ok=True)
    return capture_dir


def _create_raw_pair(capture_dir: Path) -> None:
    raw_dir = capture_dir / "raw"
    for idx, body in enumerate(
        (
            "Canonical HQ promotion decisions should precede promoted artifact writes.",
            "Governed HQ promotion proof entries should link subsystem evidence.",
        ),
        start=1,
    ):
        (raw_dir / f"raw_2026-06-14T00-00-0{idx}_00{idx}Z.md").write_text(
            "---\n"
            "timestamp_utc: 2026-06-14T00:00:00Z\n"
            "input_type: text\n"
            "source: null\n"
            "---\n\n"
            f"{body}\n",
            encoding="utf-8",
        )


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _state_registry_path(capture_dir: Path) -> Path:
    return capture_dir.parent / "data" / "state" / "artifact_registry.jsonl"


def _transition_ledger_path(capture_dir: Path) -> Path:
    return capture_dir.parent / "data" / "state" / "transition_gate_events.jsonl"


def _promotion_log_path(capture_dir: Path) -> Path:
    return capture_dir / "promotion_log.jsonl"


def _rejected_validation(failure: str) -> dict:
    return {
        "allowed": False,
        "current_state": None,
        "next_state": "promoted",
        "lane_id": "volatile_capture",
        "state_source": "missing",
        "gate": "promotion_policy",
        "policy_id": "promotion_policy",
        "policy_result": {
            "allowed": False,
            "failures": [failure],
        },
        "reason": failure,
    }


def _production_jsonl_snapshot() -> dict[str, tuple[int, str]]:
    data_dir = Path(__file__).resolve().parents[1] / "data"
    snapshot: dict[str, tuple[int, str]] = {}
    if not data_dir.exists():
        return snapshot
    for path in sorted(data_dir.rglob("*.jsonl")):
        payload = path.read_bytes()
        snapshot[str(path)] = (len(payload), hashlib.sha256(payload).hexdigest())
    return snapshot


def _assert_schema_fields(entry: dict) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert set(schema["required"]) <= set(entry)
    assert set(entry) <= set(schema["properties"])
    assert entry["schema_version"] == "governed_transition_ledger_entry.v1"
    assert entry["content_hash"].startswith("sha256:")
    assert entry["record_hash"].startswith("sha256:")
    assert isinstance(entry["subsystem_refs"], list)


def _assert_ref(entry: dict, subsystem: str, ref_type: str) -> None:
    assert any(
        ref.get("subsystem") == subsystem and ref.get("ref_type") == ref_type
        for ref in entry["subsystem_refs"]
    )


def test_valid_claim_evidence_decision_writes_canonical_ledger_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claims_dir = _redirect_claim_paths(monkeypatch, tmp_path)
    canonical_ledger = tmp_path / "canonical" / "governed_transition_ledger.jsonl"

    claim = generate_claim(
        _raw_claim_text(),
        evidence_refs=["evidence:test-source"],
        evidence_authority=_evidence_authority(),
        canonical_ledger_path=canonical_ledger,
    )

    entries = read_ledger_entries(canonical_ledger)
    assert len(entries) == 1
    entry = entries[0]
    _assert_schema_fields(entry)
    _assert_ref(entry, "claim_runtime", "claim")
    _assert_ref(entry, "claim_engine", "claims_ledger")
    assert entry["decision"] == "PROMOTE_TO_STATE"
    assert entry["evidence_references"]
    assert _read_jsonl(claims_dir / "claims_ledger.jsonl")[-1]["claim_id"] == claim["claim_id"]
    assert verify_ledger(canonical_ledger)["clean"] is True


def test_rejected_claim_evidence_decision_writes_canonical_ledger_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claims_dir = _redirect_claim_paths(monkeypatch, tmp_path)
    canonical_ledger = tmp_path / "canonical" / "governed_transition_ledger.jsonl"

    with pytest.raises(ClaimEvidenceError):
        generate_claim(
            _raw_claim_text(),
            canonical_ledger_path=canonical_ledger,
        )

    entries = read_ledger_entries(canonical_ledger)
    assert len(entries) == 1
    entry = entries[0]
    _assert_schema_fields(entry)
    _assert_ref(entry, "claim_runtime", "claim")
    assert entry["decision"] == "REJECT_MISSING_EVIDENCE"
    assert entry["decision_reason"] == "claim_missing_evidence"
    assert not (claims_dir / "claims_ledger.jsonl").exists()
    assert not (claims_dir / "anchored").exists()


def test_valid_hq_promotion_decision_writes_canonical_ledger_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_dir = _make_capture_dir(tmp_path)
    _create_raw_pair(capture_dir)
    canonical_ledger = tmp_path / "canonical" / "governed_transition_ledger.jsonl"
    monkeypatch.setattr(promote, "_try_route", lambda bundle_path: {"spine": "test_spine"})
    monkeypatch.setattr(promote, "_try_instability", lambda capture_dir: [])
    monkeypatch.setattr("shared.events.emit_event", lambda *args, **kwargs: None)

    result = promote.promote_run(
        capture_dir=capture_dir,
        min_cluster_size=2,
        threshold=0.10,
        canonical_ledger_path=canonical_ledger,
    )

    promoted = list((capture_dir / "promoted").glob("bundle_*.md"))
    entries = read_ledger_entries(canonical_ledger)
    assert result["status"] == "ok"
    assert len(promoted) == 1
    assert len(entries) == 1
    entry = entries[0]
    _assert_schema_fields(entry)
    _assert_ref(entry, "hq_capture", "promotion_bundle")
    _assert_ref(entry, "hq_capture", "promotion_log")
    _assert_ref(entry, "hq_governance", "transition_gate_event")
    _assert_ref(entry, "state_registry", "artifact_registry")
    assert entry["decision"] == "PROMOTE_TO_STATE"
    assert _read_jsonl(_state_registry_path(capture_dir))
    assert _read_jsonl(_promotion_log_path(capture_dir))
    assert _read_jsonl(_transition_ledger_path(capture_dir))


def test_rejected_hq_promotion_decision_writes_canonical_ledger_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_dir = _make_capture_dir(tmp_path)
    _create_raw_pair(capture_dir)
    canonical_ledger = tmp_path / "canonical" / "governed_transition_ledger.jsonl"

    monkeypatch.setattr(
        governance,
        "validate_transition",
        lambda *args, **kwargs: _rejected_validation("candidate_cluster_members_present"),
    )

    with pytest.raises(RuntimeError, match="Canonical gate rejected promotion"):
        promote.promote_run(
            capture_dir=capture_dir,
            min_cluster_size=2,
            threshold=0.10,
            canonical_ledger_path=canonical_ledger,
        )

    entries = read_ledger_entries(canonical_ledger)
    assert len(entries) == 1
    entry = entries[0]
    _assert_schema_fields(entry)
    _assert_ref(entry, "hq_capture", "promotion_bundle")
    _assert_ref(entry, "hq_governance", "transition_gate_event")
    assert entry["decision"] == "MANUAL_REVIEW_REQUIRED"
    assert entry["decision_reason"] == "candidate_cluster_members_present"
    assert not list((capture_dir / "promoted").glob("bundle_*.md"))
    assert _read_jsonl(_state_registry_path(capture_dir)) == []
    assert not any(
        row.get("status") in {"ok", "partial"}
        for row in _read_jsonl(_promotion_log_path(capture_dir))
    )


def test_deterministic_decision_id_is_stable_while_ledger_entry_id_varies(
    tmp_path: Path,
) -> None:
    claim = {
        "claim_id": "CLM-STABLE-001",
        "timestamp_utc": "2026-06-14T00:00:00Z",
        "statement": _raw_claim_text(),
        "core_assertion": _raw_claim_text(),
        "evidence_refs": ["evidence:test-source"],
        "source_trigger": "manual",
        "source_id": "manual",
        "status": "anchored",
        "evidence_authority": _evidence_authority(),
    }
    decision_a = evaluate_claim_evidence(claim, action="anchor")
    decision_b = evaluate_claim_evidence(claim, action="anchor")

    entry_a = append_claim_evidence_entry(
        tmp_path / "a.jsonl",
        claim=claim,
        action="anchor",
        decision=decision_a,
        timestamp="2026-06-14T00:00:00Z",
    )
    entry_b = append_claim_evidence_entry(
        tmp_path / "b.jsonl",
        claim=claim,
        action="anchor",
        decision=decision_b,
        timestamp="2026-06-14T00:00:01Z",
    )

    assert entry_a["deterministic_decision_id"] == entry_b["deterministic_decision_id"]
    assert entry_a["ledger_entry_id"] != entry_b["ledger_entry_id"]


def test_temp_canonical_adapter_tests_do_not_modify_production_jsonl_ledgers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _production_jsonl_snapshot()
    claims_dir = _redirect_claim_paths(monkeypatch, tmp_path)
    claim_ledger = tmp_path / "canonical" / "claim_ledger.jsonl"
    hq_ledger = tmp_path / "canonical" / "hq_ledger.jsonl"

    generate_claim(
        _raw_claim_text(),
        evidence_refs=["evidence:test-source"],
        evidence_authority=_evidence_authority(),
        canonical_ledger_path=claim_ledger,
    )
    assert (claims_dir / "claims_ledger.jsonl").exists()

    capture_dir = _make_capture_dir(tmp_path)
    _create_raw_pair(capture_dir)
    monkeypatch.setattr(promote, "_try_route", lambda bundle_path: {"spine": "test_spine"})
    monkeypatch.setattr(promote, "_try_instability", lambda capture_dir: [])
    monkeypatch.setattr("shared.events.emit_event", lambda *args, **kwargs: None)
    promote.promote_run(
        capture_dir=capture_dir,
        min_cluster_size=2,
        threshold=0.10,
        canonical_ledger_path=hq_ledger,
    )

    after = _production_jsonl_snapshot()
    assert after == before
