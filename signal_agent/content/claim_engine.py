"""
Claim Engine — zero-friction claim capture and anchoring.

Primary entry point: quick_capture(raw_text) → claim_dict

This module converts raw insight text into a timestamped, positioned claim
with an anchored markdown file and append-only ledger entry.
No draft state. No review gate. Capture → anchor immediately.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from signal_agent.formal_governance.hashing import stable_hash
from signal_agent.formal_governance.models import (
    DecisionOutcome,
    GateResult,
    GateStatus,
    PromotionDecision,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CLAIMS_DIR = REPO_ROOT / "data" / "claims"
INBOX_DIR = CLAIMS_DIR / "inbox"
ANCHORED_DIR = CLAIMS_DIR / "anchored"
DISTRIBUTED_DIR = CLAIMS_DIR / "distributed"
LEDGER_PATH = CLAIMS_DIR / "claims_ledger.jsonl"

# Claim evidence enforcement is integrated for the active claim runtime.
# This does not yet prove repo-wide promotion governance.
PROVISIONAL_CLAIM_STATUSES = {"provisional", "unverified"}
EVIDENCE_REQUIRED_ACTIONS = {"anchor", "promote", "export", "publication_ready"}
CLAIM_EVIDENCE_DECISION_SCHEMA = "claim_evidence_decision.v1"


class ClaimEvidenceError(ValueError):
    """Raised when a claim cannot advance because evidence governance failed."""

    def __init__(self, decision: PromotionDecision) -> None:
        super().__init__(decision.decision_reason)
        self.decision = decision

# --- Claim ID generation ---

def _hex4() -> str:
    """4-char hex suffix from current time + entropy."""
    return hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:4]


def _make_claim_id(ts: datetime) -> str:
    """CLM-YYYYMMDD-HHMMSS-xxxx"""
    date_part = ts.strftime("%Y%m%d")
    time_part = ts.strftime("%H%M%S")
    return f"CLM-{date_part}-{time_part}-{_hex4()}"


def _normalize_evidence_refs(evidence_refs: Optional[list[Any]]) -> list[str]:
    """Normalize evidence references into stable string references."""

    if not evidence_refs:
        return []

    normalized: list[str] = []
    for ref in evidence_refs:
        if isinstance(ref, str) and ref.strip():
            normalized.append(ref.strip())
        elif type(ref) is dict:
            evidence_id = ref.get("evidence_id")
            uri = ref.get("uri")
            if isinstance(evidence_id, str) and evidence_id.strip():
                normalized.append(evidence_id.strip())
            elif isinstance(uri, str) and uri.strip():
                normalized.append(uri.strip())
            else:
                normalized.append(json.dumps(ref, sort_keys=True, separators=(",", ":")))
        elif ref is not None:
            normalized.append(str(ref))
    return [ref for ref in normalized if ref]


def _evidence_self_certified(claim: Dict[str, Any]) -> bool:
    """Return true when evidence authority is supplied by the generator/model itself."""

    if claim.get("self_certified_evidence") is True:
        return True

    authority = claim.get("evidence_authority")
    if type(authority) is not dict:
        return False

    actor_type = authority.get("actor_type")
    self_certified = authority.get("self_certified")
    return actor_type in {"agent", "generator", "model"} or self_certified is True


def _claim_decision_id(claim: Dict[str, Any], action: str) -> str:
    return stable_hash(
        {
            "schema_version": CLAIM_EVIDENCE_DECISION_SCHEMA,
            "action": action,
            "claim_id": claim.get("claim_id", ""),
            "statement": claim.get("statement", ""),
            "core_assertion": claim.get("core_assertion", ""),
            "status": claim.get("status", ""),
            "evidence_refs": _normalize_evidence_refs(claim.get("evidence_refs", [])),
        }
    )


def _claim_gate_result(
    *,
    status: GateStatus,
    reason_code: str,
    message: str,
    outcome: DecisionOutcome | None = None,
) -> GateResult:
    return GateResult(
        gate_name="claim_evidence_gate",
        status=status,
        reason_code=reason_code,
        message=message,
        outcome=outcome,
    )


def evaluate_claim_evidence(
    claim: Dict[str, Any],
    *,
    action: str,
) -> PromotionDecision:
    """
    Evaluate whether a claim can advance for the requested claim action.

    The decision uses formal-governance promotion decision objects while staying
    scoped to claim evidence enforcement only.
    """

    status = str(claim.get("status", ""))
    evidence_refs = _normalize_evidence_refs(claim.get("evidence_refs", []))
    decision_id = _claim_decision_id(claim, action)

    if evidence_refs and _evidence_self_certified(claim):
        gate = _claim_gate_result(
            status=GateStatus.FAIL,
            reason_code="claim_evidence_self_certification",
            message="Generated or self-certified evidence cannot satisfy claim evidence authority.",
            outcome=DecisionOutcome.REJECT_SELF_CERTIFICATION,
        )
        return PromotionDecision(
            deterministic_decision_id=decision_id,
            decision=DecisionOutcome.REJECT_SELF_CERTIFICATION,
            decision_reason=gate.reason_code,
            gate_results=[gate],
            proposal_id=str(claim.get("claim_id", "")),
        )

    if not evidence_refs:
        if action == "draft" and status in PROVISIONAL_CLAIM_STATUSES:
            gate = _claim_gate_result(
                status=GateStatus.PASS,
                reason_code="provisional_unverified_claim_allowed",
                message="Draft claim without evidence is allowed only as provisional or unverified.",
            )
            return PromotionDecision(
                deterministic_decision_id=decision_id,
                decision=DecisionOutcome.CONSOLIDATE_ONLY,
                decision_reason=gate.reason_code,
                gate_results=[gate],
                proposal_id=str(claim.get("claim_id", "")),
            )

        if action in EVIDENCE_REQUIRED_ACTIONS or status not in PROVISIONAL_CLAIM_STATUSES:
            gate = _claim_gate_result(
                status=GateStatus.FAIL,
                reason_code="claim_missing_evidence",
                message="Anchored, promoted, exported, or publication-ready claims require evidence_refs.",
                outcome=DecisionOutcome.REJECT_MISSING_EVIDENCE,
            )
            return PromotionDecision(
                deterministic_decision_id=decision_id,
                decision=DecisionOutcome.REJECT_MISSING_EVIDENCE,
                decision_reason=gate.reason_code,
                gate_results=[gate],
                proposal_id=str(claim.get("claim_id", "")),
            )

    gate = _claim_gate_result(
        status=GateStatus.PASS,
        reason_code="claim_evidence_refs_present",
        message="Claim evidence references are present and not self-certified.",
    )
    return PromotionDecision(
        deterministic_decision_id=decision_id,
        decision=DecisionOutcome.PROMOTE_TO_STATE,
        decision_reason=gate.reason_code,
        gate_results=[gate],
        proposal_id=str(claim.get("claim_id", "")),
    )


def require_claim_evidence(claim: Dict[str, Any], *, action: str) -> PromotionDecision:
    """Return a decision or raise when evidence governance blocks the claim action."""

    decision = evaluate_claim_evidence(claim, action=action)
    if decision.decision in {
        DecisionOutcome.REJECT_MISSING_EVIDENCE,
        DecisionOutcome.REJECT_SELF_CERTIFICATION,
    }:
        raise ClaimEvidenceError(decision)
    return decision


# --- Core assertion extraction ---

def _extract_core_assertion(raw_text: str) -> str:
    """
    Extract the strongest single-sentence assertion from raw text.
    Heuristic: first sentence that is declarative (no '?'), > 20 chars.
    If nothing qualifies, use the first sentence.
    """
    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!])\s+', raw_text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return raw_text.strip()[:280]

    # Prefer declarative sentences > 20 chars
    for s in sentences:
        if '?' not in s and len(s) > 20:
            return s

    return sentences[0]


# --- Claim generation ---

def build_claim(
    raw_text: str,
    source_trigger: str = "manual",
    source_id: str = "manual",
    *,
    evidence_refs: Optional[list[Any]] = None,
    status: str = "provisional",
    evidence_authority: Optional[Dict[str, Any]] = None,
    self_certified_evidence: bool = False,
) -> Dict[str, Any]:
    """
    Build a structured claim without writing it.

    Draft claims without evidence are allowed only when explicitly marked
    provisional or unverified.
    """
    now = datetime.now(timezone.utc)
    claim_id = _make_claim_id(now)
    timestamp_utc = now.isoformat()

    core_assertion = _extract_core_assertion(raw_text)

    # Clean statement: use full raw text, trimmed
    statement = raw_text.strip()

    claim = {
        "claim_id": claim_id,
        "timestamp_utc": timestamp_utc,
        "statement": statement,
        "core_assertion": core_assertion,
        "evidence_refs": _normalize_evidence_refs(evidence_refs),
        "source_trigger": source_trigger,
        "source_id": source_id,
        "status": status,
    }
    if evidence_authority is not None:
        claim["evidence_authority"] = dict(evidence_authority)
    if self_certified_evidence:
        claim["self_certified_evidence"] = True

    if status in PROVISIONAL_CLAIM_STATUSES:
        require_claim_evidence(claim, action="draft")

    return claim


def generate_claim(
    raw_text: str,
    source_trigger: str = "manual",
    source_id: str = "manual",
    *,
    evidence_refs: Optional[list[Any]] = None,
    status: str = "anchored",
    evidence_authority: Optional[Dict[str, Any]] = None,
    self_certified_evidence: bool = False,
) -> Dict[str, Any]:
    """
    Generate a structured claim from raw insight text.

    Anchored claims require non-empty, non-self-certified evidence_refs before
    any ledger entry or anchored markdown is written.
    """
    claim = build_claim(
        raw_text=raw_text,
        source_trigger=source_trigger,
        source_id=source_id,
        evidence_refs=evidence_refs,
        status=status,
        evidence_authority=evidence_authority,
        self_certified_evidence=self_certified_evidence,
    )

    if status in PROVISIONAL_CLAIM_STATUSES:
        return claim

    require_claim_evidence(claim, action="anchor")

    # Ensure directories exist
    _ensure_dirs()

    # 1. Write ledger entry (append-only)
    _append_ledger(claim)

    # 2. Write anchored markdown
    _write_anchored_md(claim)

    return claim


def _ensure_dirs() -> None:
    """Create the claims directory tree if missing."""
    for d in (CLAIMS_DIR, INBOX_DIR, ANCHORED_DIR, DISTRIBUTED_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _append_ledger(claim: Dict[str, Any]) -> None:
    """Append claim to claims_ledger.jsonl."""
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_PATH, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(claim, sort_keys=False) + "\n")


def _write_anchored_md(claim: Dict[str, Any]) -> None:
    """Write Substack-ready anchored markdown."""
    md_path = ANCHORED_DIR / f"{claim['claim_id']}.md"
    evidence_refs = _normalize_evidence_refs(claim.get("evidence_refs", []))
    evidence_block = ""
    if evidence_refs:
        evidence_lines = "\n".join(f"- {ref}" for ref in evidence_refs)
        evidence_block = f"\n\n## Evidence\n{evidence_lines}"
    content = f"""---
claim_id: {claim['claim_id']}
timestamp_utc: {claim['timestamp_utc']}
source_trigger: {claim['source_trigger']}
source_id: {claim['source_id']}
status: anchored
---

# {claim['core_assertion']}

{claim['statement']}{evidence_block}
"""
    with open(md_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


# --- Quick Capture (zero friction) ---

def quick_capture(raw_text: str) -> Dict[str, Any]:
    """
    Zero-friction claim capture.

    Takes raw text, produces:
    - Ledger entry
    - Anchored markdown
    - Returns the claim dict

    This is the function to call when you recognize something.
    No structure required. Just text in, authority out.
    """
    return generate_claim(
        raw_text=raw_text,
        source_trigger="quick_capture",
        source_id="direct",
    )


# --- Inbox processing ---

def process_inbox() -> list[Dict[str, Any]]:
    """
    Process all .txt files in data/claims/inbox/.
    Each file becomes a claim. Files are removed after processing.
    Returns list of generated claims.
    """
    _ensure_dirs()
    claims = []

    for txt_file in sorted(INBOX_DIR.glob("*.txt")):
        try:
            raw_text = txt_file.read_text(encoding="utf-8").strip()
            if not raw_text:
                continue
            claim = generate_claim(
                raw_text=raw_text,
                source_trigger="inbox",
                source_id=txt_file.name,
            )
            claims.append(claim)
            # Remove consumed file
            txt_file.unlink()
        except Exception as e:
            print(f"[ERROR] inbox processing failed for {txt_file.name}: {e}")

    return claims


# --- Ledger queries ---

def read_ledger() -> list[Dict[str, Any]]:
    """Read all claims from the ledger."""
    if not LEDGER_PATH.exists():
        return []
    claims = []
    with open(LEDGER_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    claims.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return claims


def get_claim(claim_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific claim from the ledger by ID."""
    for claim in read_ledger():
        if claim.get("claim_id") == claim_id:
            return claim
    return None
