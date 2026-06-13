"""
Claim Distributor — deterministic platform transformations.

Takes a single anchored claim and produces platform-native outputs
for Substack, LinkedIn, Facebook, and X.

No rethinking. Only transformation.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from signal_agent.content.claim_engine import require_claim_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAIMS_DIR = REPO_ROOT / "data" / "claims"
DISTRIBUTED_DIR = CLAIMS_DIR / "distributed"
DISTRIBUTION_LOG = CLAIMS_DIR / "distribution_log.jsonl"

# Max length for X (Twitter) posts
X_MAX_CHARS = 280


def distribute_claim(claim: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate all platform outputs from a single claim.

    Writes:
    - data/claims/distributed/{claim_id}/substack.md
    - data/claims/distributed/{claim_id}/linkedin.txt
    - data/claims/distributed/{claim_id}/facebook.txt
    - data/claims/distributed/{claim_id}/x.txt
    - Appends to distribution_log.jsonl

    Returns distribution result dict.
    """
    claim_id = claim["claim_id"]
    core = claim["core_assertion"]
    statement = claim["statement"]
    evidence = claim.get("evidence_refs", [])
    require_claim_evidence(claim, action="publication_ready")

    # Create output directory
    out_dir = DISTRIBUTED_DIR / claim_id
    out_dir.mkdir(parents=True, exist_ok=True)

    outputs: Dict[str, str] = {}
    platforms_ok: List[str] = []
    platforms_failed: List[str] = []

    # --- Substack (full claim, newsletter format) ---
    try:
        substack = _render_substack(core, statement, evidence)
        _write(out_dir / "substack.md", substack)
        outputs["substack"] = substack
        platforms_ok.append("substack")
    except Exception as e:
        platforms_failed.append(f"substack:{e}")

    # --- LinkedIn (authority framing) ---
    try:
        linkedin = _render_linkedin(core, statement, evidence)
        _write(out_dir / "linkedin.txt", linkedin)
        outputs["linkedin"] = linkedin
        platforms_ok.append("linkedin")
    except Exception as e:
        platforms_failed.append(f"linkedin:{e}")

    # --- Facebook (narrative framing) ---
    try:
        facebook = _render_facebook(core, statement, evidence)
        _write(out_dir / "facebook.txt", facebook)
        outputs["facebook"] = facebook
        platforms_ok.append("facebook")
    except Exception as e:
        platforms_failed.append(f"facebook:{e}")

    # --- X (compressed insight) ---
    try:
        x_post = _render_x(core)
        _write(out_dir / "x.txt", x_post)
        outputs["x"] = x_post
        platforms_ok.append("x")
    except Exception as e:
        platforms_failed.append(f"x:{e}")

    # --- Log ---
    status = "complete" if len(platforms_ok) == 4 else "partial"
    log_entry = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "claim_id": claim_id,
        "platforms_ok": platforms_ok,
        "platforms_failed": platforms_failed,
        "status": status,
    }
    _append_log(log_entry)

    return {
        "claim_id": claim_id,
        "output_dir": str(out_dir),
        "platforms_ok": platforms_ok,
        "platforms_failed": platforms_failed,
        "status": status,
        "outputs": outputs,
    }


# --- Platform renderers (no Jinja dependency, deterministic string transforms) ---

def _render_substack(core: str, statement: str, evidence: List[str]) -> str:
    """Substack: newsletter-ready markdown. Copy-paste into editor."""
    lines = [
        f"# {core}",
        "",
        statement,
    ]
    if evidence:
        lines.append("")
        lines.append("## Key Evidence")
        for ref in evidence:
            lines.append(f"* {ref}")
    return "\n".join(lines) + "\n"


def _render_linkedin(core: str, statement: str, evidence: List[str]) -> str:
    """LinkedIn: authority framing. Hook + body + evidence bullets."""
    lines = [
        core,
        "",
        statement,
    ]
    if evidence:
        lines.append("")
        for ref in evidence:
            lines.append(f"→ {ref}")
    return "\n".join(lines) + "\n"


def _render_facebook(core: str, statement: str, evidence: List[str]) -> str:
    """Facebook: narrative framing. Observation + expansion."""
    lines = [
        core,
        "",
        statement,
    ]
    if evidence:
        lines.append("")
        for ref in evidence:
            lines.append(f"- {ref}")
    return "\n".join(lines) + "\n"


def _render_x(core: str) -> str:
    """X: compressed insight. Core assertion only, max 280 chars."""
    if len(core) <= X_MAX_CHARS:
        return core
    # Truncate at last word boundary before limit
    truncated = core[:X_MAX_CHARS - 1]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated + "…"


# --- Helpers ---

def _write(path: Path, content: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def _append_log(entry: Dict[str, Any]) -> None:
    DISTRIBUTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(DISTRIBUTION_LOG, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, sort_keys=False) + "\n")
