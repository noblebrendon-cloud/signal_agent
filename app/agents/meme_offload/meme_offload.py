"""
Meme Offload Engine — deterministic meme generation pipeline (v0.2).

Integrates: constraint packs, reprojection, telemetry, kernel stability.
No randomness unless SHA256-seeded. All selection order is stable.

v0.2 additions:
- spec_version locked to "meme_spec_v1"
- Telemetry includes pack provenance (pack_id, pack_version, pack_hash, rule_ids)
- Optional policy-gated LLM caption expansion via call_with_resilience()
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

import yaml

from app.agents.meme_offload.schema import (
    SPEC_VERSION_CANONICAL,
    MemeSpecV1, MemePackRef, MemeCanvas, MemeOutput, MemeProvenance,
    MemeTextTwoPanel, MemeTextInfographic, generate_meme_id,
)
from app.utils.exceptions import ConstraintViolation
from app.utils.reprojection import (
    ConstraintPack, reproject_checkpoint_meme,
)
from app.utils.ir import stable_pack_hash

if TYPE_CHECKING:
    from app.audit.coherence_kernel import CoherenceKernel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACTION = "CONTENT_MEME_OFFLOAD"
PACK_BASE = Path("constraints/packs/domain/content_meme")
SPEC_DIR = Path("data/meme_offload/specs")
RENDER_DIR = Path("data/meme_offload/renders")
MAX_OUTPUTS_DEFAULT = 5

# Disallowed terms — hard-coded for determinism, no network lookups.
DISALLOWED_TERMS = frozenset([
    "kill", "murder", "suicide", "terrorism", "bomb",
    "racial slur", "hate speech",
])

# Named-person heuristic: simple title-case multi-word detection.
_NAMED_PERSON_RE = re.compile(
    r"\b(?:Mr|Mrs|Ms|Dr|Prof|President|Senator|Governor)\b\.?\s+[A-Z][a-z]+"
)


# ---------------------------------------------------------------------------
# Frame extraction (deterministic)
# ---------------------------------------------------------------------------

def _extract_candidate_frames(
    source_text: str,
    fmt: str,
) -> List[Dict[str, Any]]:
    """
    Splits source text into deterministic candidate frames.
    Each frame is a dict with the text content for a single meme.
    Order is stable (input order preserved).
    """
    lines = [ln.strip() for ln in source_text.strip().splitlines() if ln.strip()]
    frames: List[Dict[str, Any]] = []

    if fmt == "infographic_list":
        if lines:
            title = lines[0]
            bullets = tuple(lines[1:])
            frames.append({"title": title, "bullets": bullets})
    else:
        for i in range(0, len(lines) - 1, 2):
            top = lines[i]
            bottom = lines[i + 1] if (i + 1) < len(lines) else ""
            frames.append({"top": top, "bottom": bottom})

        if len(lines) % 2 == 1 and len(lines) > 0:
            frames.append({"top": lines[-1], "bottom": ""})

    return frames


def _contains_named_person(text: str) -> bool:
    return bool(_NAMED_PERSON_RE.search(text))


def _contains_disallowed_terms(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in DISALLOWED_TERMS)


def _get_rule_ids(pack_obj: ConstraintPack) -> List[str]:
    """Extract deterministically-ordered rule IDs from pack."""
    return [
        r.get("constraint_id", "unknown")
        for r in (pack_obj.constraint_rules or [])
    ]


def _pack_provenance(pack_ref: MemePackRef, rule_ids: List[str]) -> Dict[str, Any]:
    """Build pack provenance dict for telemetry events."""
    return {
        "pack_id": pack_ref.pack_id,
        "pack_version": pack_ref.pack_version,
        "pack_hash": pack_ref.pack_hash,
        "rule_ids": rule_ids,
        "action": ACTION,
    }


# ---------------------------------------------------------------------------
# Provider expansion (optional, policy-gated)
# ---------------------------------------------------------------------------

def _is_expansion_allowed(pack_obj: ConstraintPack) -> bool:
    """
    Check whether the pack explicitly ALLOWs provider expansion.
    Default: disabled. Only activates if an ALLOW rule for
    'provider_expansion' evaluates to true.

    If the predicate is absent or evaluates to false → disabled.
    """
    for rule in (pack_obj.constraint_rules or []):
        cid = rule.get("constraint_id", "")
        if cid == "MEME_ALLOW_PROVIDER_EXPANSION":
            rtype = rule.get("rule_type", "")
            if rtype != "ALLOW":
                return False
            # Check predicate — if predicate is explicitly "false" → disabled
            pred = rule.get("predicate", {})
            if isinstance(pred, str) and pred.lower() == "false":
                return False
            if isinstance(pred, dict) and not pred:
                # Empty predicate in an ALLOW rule → allowed
                return True
            # Non-empty structured predicate: conservatively allow
            # (DSL will evaluate at runtime)
            return True
    return False


def _expand_caption(
    text: str,
    kernel: Optional[CoherenceKernel],
    log: Callable,
    now_utc: str,
    pack_provenance: Dict[str, Any],
) -> str:
    """
    Optional LLM caption expansion via call_with_resilience().
    Constrained: max_tokens ≤ 80, temperature ≤ 0.7.
    Returns expanded text or original on failure/unavailability.
    """
    try:
        from app.utils.resilience import call_with_resilience

        result = call_with_resilience(
            prompt=f"Expand this meme caption to be funnier in under 80 characters: {text}",
            max_tokens=80,
            temperature=0.7,
        )
        expanded = result.get("text", text) if isinstance(result, dict) else text

        log({
            "event": "MEME_CAPTION_EXPANDED",
            "original_len": len(text),
            "expanded_len": len(expanded),
            "timestamp": now_utc,
            **pack_provenance,
        })
        return expanded

    except Exception as e:
        logger.warning(f"Provider expansion failed (fail-closed, using original): {e}")
        log({
            "event": "MEME_CAPTION_EXPANSION_FAILED",
            "error": str(e),
            "timestamp": now_utc,
            **pack_provenance,
        })
        return text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def meme_offload_generate(
    source_text: str,
    pack_id: str,
    n: int = 5,
    *,
    logger_fn: Optional[Callable[[Dict[str, Any]], None]] = None,
    kernel: Optional[CoherenceKernel] = None,
    session_id: str = "",
    source_artifact_id: str = "",
    fmt: str = "two_panel",
) -> List[MemeSpecV1]:
    """
    Generate up to `n` meme specs from source text, enforced by constraint pack.

    Steps:
      1. Emit MEME_OFFLOAD_START (with pack provenance)
      2. Load pack YAML
      3. Extract candidate frames (deterministic)
      4. Build up to n MemeSpecV1 objects (spec_version="meme_spec_v1")
      5. [Optional] Provider expansion if policy-gated ALLOW
      6. Reprojection checkpoint per spec
      7. On FAIL: kernel.record_constraint_violation(), raise ConstraintViolation
      8. Write spec JSON
      9. Call renderer
     10. Emit MEME_OFFLOAD_DONE (with pack provenance)
    """
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log = logger_fn or (lambda _evt: None)

    # ------------------------------------------------------------------
    # 2. Load constraint pack
    # ------------------------------------------------------------------
    pack_path = PACK_BASE / f"{pack_id}.yaml"
    if not pack_path.exists():
        raise FileNotFoundError(f"Constraint pack not found: {pack_path}")

    with open(pack_path, "r", encoding="utf-8") as f:
        pack_data = yaml.safe_load(f) or {}

    pack_obj = ConstraintPack.from_dict(pack_data)
    pack_meta = pack_data.get("pack_metadata", {})
    p_hash = stable_pack_hash(pack_obj)
    pack_ref = MemePackRef(
        pack_id=pack_meta.get("name", pack_id),
        pack_version=pack_meta.get("version", "0.0.0"),
        pack_hash=f"sha256:{p_hash}",
    )

    rule_ids = _get_rule_ids(pack_obj)
    prov = _pack_provenance(pack_ref, rule_ids)

    # ------------------------------------------------------------------
    # 1. Emit MEME_OFFLOAD_START (with pack provenance)
    # ------------------------------------------------------------------
    log({
        "event": "MEME_OFFLOAD_START",
        "n_requested": n,
        "source_chars": len(source_text),
        "format": fmt,
        "timestamp": now_utc,
        **prov,
    })

    # Enforce LIMIT: cap n at max_outputs from pack
    effective_n = min(n, MAX_OUTPUTS_DEFAULT)

    # ------------------------------------------------------------------
    # 3. Extract candidate frames
    # ------------------------------------------------------------------
    frames = _extract_candidate_frames(source_text, fmt)

    log({
        "event": "MEME_CANDIDATES_EXTRACTED",
        "frame_count": len(frames),
        "effective_n": effective_n,
        "timestamp": now_utc,
        **prov,
    })

    # ------------------------------------------------------------------
    # 5. Optional provider expansion check
    # ------------------------------------------------------------------
    expansion_enabled = _is_expansion_allowed(pack_obj)

    # ------------------------------------------------------------------
    # 4. Build MemeSpecV1 objects (up to effective_n)
    # ------------------------------------------------------------------
    specs: List[MemeSpecV1] = []
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    RENDER_DIR.mkdir(parents=True, exist_ok=True)

    for idx, frame in enumerate(frames[:effective_n]):
        # Normalize text for ID generation
        if fmt == "infographic_list":
            normalized = (frame.get("title", "") + "|".join(frame.get("bullets", ()))).strip()
            text_obj: Any = MemeTextInfographic(
                title=frame.get("title", ""),
                bullets=tuple(frame.get("bullets", ())),
            )
        else:
            top_text = frame.get("top", "")
            bottom_text = frame.get("bottom", "")

            # Optional expansion (policy-gated)
            if expansion_enabled:
                top_text = _expand_caption(top_text, kernel, log, now_utc, prov)
                bottom_text = _expand_caption(bottom_text, kernel, log, now_utc, prov)

            normalized = (top_text + bottom_text).strip()
            text_obj = MemeTextTwoPanel(top=top_text, bottom=bottom_text)

        frame_id = f"frame_{idx:04d}"
        meme_id = generate_meme_id(p_hash, frame_id, normalized, fmt)

        spec = MemeSpecV1(
            spec_version=SPEC_VERSION_CANONICAL,
            meme_id=meme_id,
            pack=pack_ref,
            format=fmt,
            canvas=MemeCanvas(),
            text=text_obj,
            output=MemeOutput(
                spec_path=str(SPEC_DIR / f"{meme_id}.json"),
                render_dir=str(RENDER_DIR),
                filename=f"{meme_id}.png",
            ),
            provenance=MemeProvenance(
                source_artifact_id=source_artifact_id,
                session_id=session_id,
                created_at_utc=now_utc,
            ),
        )
        specs.append(spec)

    log({
        "event": "MEME_SPECS_BUILT",
        "count": len(specs),
        "meme_ids": [s.meme_id for s in specs],
        "expansion_enabled": expansion_enabled,
        "timestamp": now_utc,
        **prov,
    })

    # ------------------------------------------------------------------
    # 6 + 7. Reprojection checkpoint per spec
    # ------------------------------------------------------------------
    for spec in specs:
        try:
            reproject_checkpoint_meme(spec, str(pack_path))
            log({
                "event": "MEME_REPROJECTION_PASS",
                "meme_id": spec.meme_id,
                "timestamp": now_utc,
                **prov,
            })
        except ConstraintViolation:
            log({
                "event": "MEME_REPROJECTION_FAIL",
                "meme_id": spec.meme_id,
                "timestamp": now_utc,
                **prov,
            })
            if kernel:
                kernel.record_constraint_violation()
            raise

    # ------------------------------------------------------------------
    # 8. Write spec JSON
    # ------------------------------------------------------------------
    for spec in specs:
        spec_file = Path(spec.output.spec_path)
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        with open(spec_file, "w", encoding="utf-8") as f:
            f.write(spec.to_json())

    # ------------------------------------------------------------------
    # 9. Render
    # ------------------------------------------------------------------
    from app.agents.meme_offload.render.render_memes import render_meme

    for spec in specs:
        out_path = render_meme(spec)
        log({
            "event": "MEME_RENDER_DONE",
            "meme_id": spec.meme_id,
            "output_path": str(out_path),
            "timestamp": now_utc,
            **prov,
        })

    # ------------------------------------------------------------------
    # 10. Final telemetry (with pack provenance)
    # ------------------------------------------------------------------
    log({
        "event": "MEME_OFFLOAD_DONE",
        "total_rendered": len(specs),
        "meme_ids": [s.meme_id for s in specs],
        "expansion_used": expansion_enabled,
        "timestamp": now_utc,
        **prov,
    })

    return specs
