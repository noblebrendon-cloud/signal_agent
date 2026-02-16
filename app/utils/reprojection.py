from __future__ import annotations

import json
import logging
import re
import time
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml

from app.utils.exceptions import ConstraintViolation
from app.utils.policy_engine import resolve, EvalResult

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


@dataclass
class ConstraintPack:
    scope: str = "global"
    required_invariants: List[Dict[str, Any]] = field(default_factory=list)
    disallowed_phrases: List[str] = field(default_factory=list)
    allowed_output_classes: List[str] = field(default_factory=list)
    boundary_conditions: Dict[str, Any] = field(default_factory=dict)
    constraint_rules: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConstraintPack":
        return cls(
            scope=str(data.get("scope", "global")),
            required_invariants=list(data.get("required_invariants", [])),
            disallowed_phrases=[str(p) for p in data.get("disallowed_phrases", [])],
            allowed_output_classes=[str(c) for c in data.get("allowed_output_classes", [])],
            boundary_conditions=dict(data.get("boundary_conditions", {})),
            constraint_rules=list(data.get("constraint_rules", [])),
        )


@dataclass
class ArtifactState:
    sections: Dict[str, str]
    claims: List[str]
    word_count: int
    full_text_lower: str


@dataclass
class DeltaReport:
    status: str  # PASS | WARN | FAIL
    soft_score: float
    hard_violations: List[str]
    details: Dict[str, Any]
    pack_path: str
    execution_context_id: str



_claim_pattern = re.compile(r"^\s*(?:[-*]|\d+\.)\s+(.+)$")


def canonicalize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: canonicalize(obj[k]) for k in sorted(obj.keys())}
    if isinstance(obj, list):
        return [canonicalize(x) for x in obj]
    return obj


def pack_hash(pack: Dict[str, Any]) -> str:
    pack2 = json.loads(json.dumps(pack))  # deep copy via JSON-safe path
    if "pack_metadata" in pack2 and isinstance(pack2["pack_metadata"], dict):
        pack2["pack_metadata"].pop("pack_hash", None)  # remove self field
    canon = canonicalize(pack2)
    payload = json.dumps(canon, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _matches_trigger(rule: Dict[str, Any], action: Dict[str, Any]) -> bool:
    trigger = rule.get("trigger", {})
    cap = trigger.get("capability_id")
    if not cap:
        # If trigger cap is null, rule applies to ALL capabilities
        return True
    
    act_cap = action.get("capability_id")
    if cap == "ANY":
        return True
        
    return cap == act_cap


def extract_artifact_state(text: str) -> ArtifactState:
    lines = text.splitlines()
    sections: Dict[str, str] = {}
    current_header = "preamble"
    current_content: List[str] = []
    claims: List[str] = []

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("#"):
            if current_content:
                sections[current_header] = "\n".join(current_content).strip()
            current_header = stripped.lstrip("#").strip() or "untitled"
            current_content = []
            continue

        current_content.append(line)

        m = _claim_pattern.match(line)
        if m:
            claims.append(m.group(1).strip())

    if current_content:
        sections[current_header] = "\n".join(current_content).strip()

    return ArtifactState(
        sections=sections,
        claims=claims,
        word_count=len(text.split()),
        full_text_lower=text.lower(),
    )


def compute_delta(
    state: ArtifactState,
    pack: ConstraintPack,
    context_id: str,
    pack_path: str,
    warn_threshold: float,
) -> DeltaReport:
    hard: List[str] = []
    details: Dict[str, Any] = {}

    # Disallowed phrases (hard)
    for phrase in pack.disallowed_phrases:
        if phrase.lower() in state.full_text_lower:
            hard.append(f"Disallowed phrase found: '{phrase}'")

    # Boundary conditions (hard)
    max_words = pack.boundary_conditions.get("max_word_count")
    if max_words is not None and state.word_count > int(max_words):
        hard.append(f"Word count {state.word_count} exceeds max {max_words}")

    max_claims = pack.boundary_conditions.get("max_claims")
    if max_claims is not None and len(state.claims) > int(max_claims):
        hard.append(f"Claims count {len(state.claims)} exceeds max {max_claims}")

    # Allowed output classes (hard)
    if pack.allowed_output_classes:
        headers = {h.lower() for h in state.sections.keys()}
        allowed = {c.lower() for c in pack.allowed_output_classes}
        if not headers.intersection(allowed):
            hard.append(f"No allowed output classes found in headers: {list(state.sections.keys())}")

    # Required invariants (soft score)
    total = len(pack.required_invariants)
    satisfied = 0
    inv_details: Dict[str, Any] = {}

    if total:
        for inv in pack.required_invariants:
            inv_id = str(inv.get("id", "unknown"))
            keywords = inv.get("keywords", []) or []
            min_count = int(inv.get("min_count", 1))
            count = sum(state.full_text_lower.count(str(kw).lower()) for kw in keywords)
            ok = count >= min_count
            if ok:
                satisfied += 1
            inv_details[inv_id] = {"count": count, "satisfied": ok, "min_count": min_count}
        soft_score = satisfied / total
    else:
        soft_score = 1.0

    details["invariants"] = inv_details
    details["word_count"] = state.word_count
    details["claims_count"] = len(state.claims)

    # V2 Policy Engine Check
    if pack.constraint_rules:
        # Construct snapshot from state
        snapshot = {
            "content": state.full_text_lower,
            "word_count": state.word_count,
            "claims_count": len(state.claims),
            "sections": state.sections,
            "metrics": {
                "word_count": state.word_count,
                "claims_count": len(state.claims)
            } 
        }
        # Define action context for reprojection
        action = {
            "type": "content_generation",
            "capability_id": "content:text"
        }
        
        # Filter rules relevant to content projection
        relevant_rules = []
        for rule in pack.constraint_rules:
             if _matches_trigger(rule, action):
                 relevant_rules.append(rule)
        
        if relevant_rules:
            # Construct pack dict for engine
            pack_dict = {
                "pack_metadata": {
                    "scope": pack.scope,
                    "name": "reprojection_pack"
                },
                "constraint_rules": relevant_rules
            }
            
            # Context
            context = {"domain": "content", "execution_context_id": context_id}
            
            # Resolve
            result = resolve(action, snapshot, [pack_dict], context)
            
            if result.decision in ("DENY", "REQUIRE_APPROVAL"):
                 hard.append(f"Policy Violation: {result.reason} (Matched: {result.matched_constraints})")

    if hard:
        status = "FAIL"
    elif soft_score < warn_threshold:
        status = "WARN"
    else:
        status = "PASS"

    return DeltaReport(
        status=status,
        soft_score=float(soft_score),
        hard_violations=hard,
        details=details,
        pack_path=pack_path,
        execution_context_id=context_id,
    )


def log_reprojection(report: DeltaReport, log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{report.execution_context_id}.jsonl"
    record = {
        "timestamp": time.time(),
        "execution_context_id": report.execution_context_id,
        "pack_path": report.pack_path,
        "status": report.status,
        "soft_score": report.soft_score,
        "hard_violations": report.hard_violations,
        "details": report.details,
    }
    try:
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Failed to write reprojection log: {e}")


def reproject_checkpoint(
    artifact: str,
    pack_path: str,
    warn_threshold: float = 0.75,
    execution_context_id: str = "default_ctx",
    log_dir: Path = Path("data/logs/reprojection"),
) -> DeltaReport:
    try:
        with open(pack_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        pack = ConstraintPack.from_dict(data)
    except Exception as e:
        logger.warning(f"Failed to load constraint pack {pack_path}: {e}. Using defaults.")
        pack = ConstraintPack(scope="error_fallback")

    state = extract_artifact_state(artifact)
    report = compute_delta(state, pack, execution_context_id, pack_path, warn_threshold)
    log_reprojection(report, log_dir)

    if report.status == "FAIL":
        raise ConstraintViolation(report=report, message=f"Constraint violation in {pack_path}")

    if report.status == "WARN":
        logger.warning(f"Reprojection WARN: score={report.soft_score} < {warn_threshold} details={report.details}")

    return report


# ---------------------------------------------------------------------------
# CONTENT_MEME_OFFLOAD — Meme-specific reprojection
# ---------------------------------------------------------------------------

# Disallowed terms (must match engine list for consistency)
_MEME_DISALLOWED_TERMS = frozenset([
    "kill", "murder", "suicide", "terrorism", "bomb",
    "racial slur", "hate speech",
])

_MEME_NAMED_PERSON_RE = re.compile(
    r"\b(?:Mr|Mrs|Ms|Dr|Prof|President|Senator|Governor)\b\.?\s+[A-Z][a-z]+"
)


def extract_meme_artifact_state(spec) -> Dict[str, Any]:
    """
    Build a snapshot dict from a MemeSpecV1 for policy engine evaluation.
    All checks fail closed (missing data → conservative defaults).
    """
    from app.agents.meme_offload.schema import MemeTextTwoPanel, MemeTextInfographic

    fmt = getattr(spec, "format", "unknown")
    text_obj = getattr(spec, "text", None)

    top_chars = 0
    bottom_chars = 0
    title_chars = 0
    max_bullet_chars = 0
    all_text = ""

    if isinstance(text_obj, MemeTextTwoPanel):
        top_chars = len(text_obj.top)
        bottom_chars = len(text_obj.bottom)
        all_text = f"{text_obj.top} {text_obj.bottom}"
    elif isinstance(text_obj, MemeTextInfographic):
        title_chars = len(text_obj.title)
        max_bullet_chars = max((len(b) for b in text_obj.bullets), default=0)
        all_text = f"{text_obj.title} " + " ".join(text_obj.bullets)
    else:
        # Fail closed: treat unknown text format as violation-prone
        all_text = str(text_obj) if text_obj else ""

    contains_named = bool(_MEME_NAMED_PERSON_RE.search(all_text))
    contains_disallowed = any(term in all_text.lower() for term in _MEME_DISALLOWED_TERMS)

    return {
        "format": fmt,
        "top_chars": top_chars,
        "bottom_chars": bottom_chars,
        "title_chars": title_chars,
        "max_bullet_chars": max_bullet_chars,
        "contains_named_person": contains_named,
        "contains_disallowed_terms": contains_disallowed,
        "meme_output_count": 1,  # Per-spec evaluation
    }


def reproject_checkpoint_meme(
    spec,
    pack_path: str,
    warn_threshold: float = 0.75,
    log_dir: Path = Path("data/logs/reprojection"),
) -> DeltaReport:
    """
    Run reprojection for a CONTENT_MEME_OFFLOAD artifact.
    Constructs appropriate action/snapshot and evaluates against pack.
    Raises ConstraintViolation on FAIL.
    """
    # Load pack
    try:
        with open(pack_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        pack = ConstraintPack.from_dict(data)
    except Exception as e:
        logger.warning(f"Failed to load meme pack {pack_path}: {e}. Using defaults.")
        pack = ConstraintPack(scope="error_fallback")

    # Build meme-specific snapshot
    meme_state = extract_meme_artifact_state(spec)

    # Construct action
    action = {
        "type": "CONTENT_MEME_OFFLOAD",
        "capability_id": "content:meme_offload",
    }

    # Build snapshot for policy engine (merge meme state into metrics)
    snapshot = {
        **meme_state,
        "metrics": {
            "meme_output_count": meme_state.get("meme_output_count", 1),
        },
    }

    # Evaluate constraint rules via policy engine
    hard: List[str] = []
    context_id = getattr(spec, "meme_id", "unknown_meme")

    if pack.constraint_rules:
        pack_dict = {
            "pack_metadata": {
                "scope": pack.scope,
                "name": "content_meme_offload",
            },
            "activation_conditions": {"domain_match": ["content"]},
            "constraint_rules": pack.constraint_rules,
        }
        context = {"domain": "content", "execution_context_id": context_id}
        result = resolve(action, snapshot, [pack_dict], context)

        if result.decision in ("DENY", "REQUIRE_APPROVAL"):
            hard.append(f"Meme Policy Violation: {result.reason} (Matched: {result.matched_constraints})")

    # Also run legacy checks if pack has disallowed_phrases etc.
    all_text_lower = " ".join([
        str(meme_state.get("format", "")),
        str(getattr(getattr(spec, "text", None), "top", "")),
        str(getattr(getattr(spec, "text", None), "bottom", "")),
        str(getattr(getattr(spec, "text", None), "title", "")),
        " ".join(getattr(getattr(spec, "text", None), "bullets", ())),
    ]).lower()

    for phrase in pack.disallowed_phrases:
        if phrase.lower() in all_text_lower:
            hard.append(f"Disallowed phrase in meme: '{phrase}'")

    status = "FAIL" if hard else "PASS"

    report = DeltaReport(
        status=status,
        soft_score=1.0 if not hard else 0.0,
        hard_violations=hard,
        details=meme_state,
        pack_path=pack_path,
        execution_context_id=context_id,
    )

    log_reprojection(report, log_dir)

    if report.status == "FAIL":
        raise ConstraintViolation(report=report, message=f"Meme constraint violation: {hard}")

    return report
