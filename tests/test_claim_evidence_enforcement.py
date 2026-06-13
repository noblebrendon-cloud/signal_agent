from __future__ import annotations

import json
from pathlib import Path

import pytest

from signal_agent.content import claim_distributor, claim_engine
from signal_agent.content.claim_engine import (
    ClaimEvidenceError,
    build_claim,
    evaluate_claim_evidence,
    generate_claim,
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


def _raw_text() -> str:
    return "Evidence-bearing claims must cite their source before anchoring."


def _evidence_authority() -> dict:
    return {
        "actor_type": "human",
        "actor_id": "curator.test",
        "self_certified": False,
    }


def _production_claim_ledger_bytes() -> bytes | None:
    path = Path(__file__).resolve().parents[1] / "data" / "claims" / "claims_ledger.jsonl"
    if not path.exists():
        return None
    return path.read_bytes()


def test_claim_with_evidence_refs_passes_anchoring(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claims_dir = _redirect_claim_paths(monkeypatch, tmp_path)

    claim = generate_claim(
        _raw_text(),
        evidence_refs=["evidence:test-source"],
        evidence_authority=_evidence_authority(),
    )

    ledger_rows = [
        json.loads(line)
        for line in (claims_dir / "claims_ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert claim["status"] == "anchored"
    assert claim["evidence_refs"] == ["evidence:test-source"]
    assert ledger_rows[-1]["claim_id"] == claim["claim_id"]
    assert (claims_dir / "anchored" / f"{claim['claim_id']}.md").exists()


def test_claim_without_evidence_refs_is_rejected_before_anchor_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claims_dir = _redirect_claim_paths(monkeypatch, tmp_path)

    with pytest.raises(ClaimEvidenceError) as exc:
        generate_claim(_raw_text())

    assert exc.value.decision.decision.value == "REJECT_MISSING_EVIDENCE"
    assert not (claims_dir / "claims_ledger.jsonl").exists()
    assert not (claims_dir / "anchored").exists()


def test_provisional_draft_claim_without_evidence_is_allowed_only_as_provisional() -> None:
    draft = build_claim(_raw_text(), status="provisional", evidence_refs=[])
    decision = evaluate_claim_evidence(draft, action="draft")

    assert draft["status"] == "provisional"
    assert decision.decision.value == "CONSOLIDATE_ONLY"

    anchored_shape = dict(draft)
    anchored_shape["status"] = "anchored"
    with pytest.raises(ClaimEvidenceError):
        claim_engine.require_claim_evidence(anchored_shape, action="anchor")


def test_publication_ready_claim_without_evidence_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claims_dir = _redirect_claim_paths(monkeypatch, tmp_path)
    claim = build_claim(_raw_text(), status="provisional", evidence_refs=[])
    claim["status"] = "anchored"

    with pytest.raises(ClaimEvidenceError) as exc:
        claim_distributor.distribute_claim(claim)

    assert exc.value.decision.decision.value == "REJECT_MISSING_EVIDENCE"
    assert not (claims_dir / "distributed").exists()
    assert not (claims_dir / "distribution_log.jsonl").exists()


def test_generated_claim_cannot_self_certify_its_own_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claims_dir = _redirect_claim_paths(monkeypatch, tmp_path)

    with pytest.raises(ClaimEvidenceError) as exc:
        generate_claim(
            _raw_text(),
            evidence_refs=["evidence:self-certified"],
            evidence_authority={
                "actor_type": "generator",
                "actor_id": "codex.generator",
                "self_certified": True,
            },
        )

    assert exc.value.decision.decision.value == "REJECT_SELF_CERTIFICATION"
    assert not (claims_dir / "claims_ledger.jsonl").exists()


def test_publication_ready_claim_with_evidence_can_be_distributed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claims_dir = _redirect_claim_paths(monkeypatch, tmp_path)
    claim = generate_claim(
        _raw_text(),
        evidence_refs=["evidence:test-source"],
        evidence_authority=_evidence_authority(),
    )

    result = claim_distributor.distribute_claim(claim)

    assert result["status"] == "complete"
    assert sorted(result["platforms_ok"]) == ["facebook", "linkedin", "substack", "x"]
    assert (claims_dir / "distribution_log.jsonl").exists()


def test_production_claims_ledger_is_not_modified_by_temp_path_tests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _production_claim_ledger_bytes()
    _redirect_claim_paths(monkeypatch, tmp_path)

    generate_claim(
        _raw_text(),
        evidence_refs=["evidence:test-source"],
        evidence_authority=_evidence_authority(),
    )

    after = _production_claim_ledger_bytes()
    assert after == before
