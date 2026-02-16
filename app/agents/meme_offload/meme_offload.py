"""
Meme Offload Engine — deterministic meme generation pipeline.

Integrates: constraint packs, reprojection, telemetry, kernel stability.
No randomness unless SHA256-seeded. All selection order is stable.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

import yaml

from app.agents.meme_offload.schema import (
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
import re
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
        # Title = first line, bullets = subsequent lines
        if lines:
            title = lines[0]
            bullets = tuple(lines[1:])
            frames.append({"title": title, "bullets": bullets})
    else:
        # two_panel: pair consecutive lines as top/bottom
        for i in range(0, len(lines) - 1, 2):
            top = lines[i]
            bottom = lines[i + 1] if (i + 1) < len(lines) else ""
            frames.append({"top": top, "bottom": bottom})

        # If odd number of lines, last line becomes a single-panel
        if len(lines) % 2 == 1 and len(lines) > 0:
            frames.append({"top": lines[-1], "bottom": ""})

    return frames


def _contains_named_person(text: str) -> bool:
    return bool(_NAMED_PERSON_RE.search(text))


def _contains_disallowed_terms(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in DISALLOWED_TERMS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def meme_offload_generate(
    source_text: str,
    pack_id: str,
    n: int = 5,
    *,
    logger: Optional[Callable[[Dict[str, Any]], None]] = None,
    kernel: Optional[CoherenceKernel] = None,
    session_id: str = "",
    source_artifact_id: str = "",
    fmt: str = "two_panel",
) -> List[MemeSpecV1]:
    """
    Generate up to `n` meme specs from source text, enforced by constraint pack.

    Steps:
      1. Emit MEME_OFFLOAD_START
      2. Load pack YAML
      3. Extract candidate frames (deterministic)
      4. Build up to n MemeSpecV1 objects
      5. Reprojection checkpoint per spec
      6. On FAIL: kernel.record_constraint_violation(), raise ConstraintViolation
      7. Write spec JSON
      8. Call renderer
      9. Emit MEME_RENDER_DONE per output
     10. Emit MEME_OFFLOAD_DONE
    """
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log = logger or (lambda _evt: None)

    # ------------------------------------------------------------------
    # 1. Emit MEME_OFFLOAD_START
    # ------------------------------------------------------------------
    log({
        "event": "MEME_OFFLOAD_START",
        "action": ACTION,
        "pack_id": pack_id,
        "n_requested": n,
        "source_chars": len(source_text),
        "format": fmt,
        "timestamp": now_utc,
    })

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

    # Enforce LIMIT: cap n at max_outputs from pack
    effective_n = min(n, MAX_OUTPUTS_DEFAULT)

    log({
        "event": "MEME_CANDIDATES_EXTRACTED",
        "pack_hash": p_hash,
        "effective_n": effective_n,
        "timestamp": now_utc,
    })

    # ------------------------------------------------------------------
    # 3. Extract candidate frames
    # ------------------------------------------------------------------
    frames = _extract_candidate_frames(source_text, fmt)

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
            normalized = (frame.get("top", "") + frame.get("bottom", "")).strip()
            text_obj = MemeTextTwoPanel(
                top=frame.get("top", ""),
                bottom=frame.get("bottom", ""),
            )

        frame_id = f"frame_{idx:04d}"
        meme_id = generate_meme_id(p_hash, frame_id, normalized, fmt)

        spec = MemeSpecV1(
            spec_version="1.0.0",
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
        "timestamp": now_utc,
    })

    # ------------------------------------------------------------------
    # 5 + 6. Reprojection checkpoint per spec
    # ------------------------------------------------------------------
    for spec in specs:
        try:
            reproject_checkpoint_meme(spec, str(pack_path))
            log({
                "event": "MEME_REPROJECTION_PASS",
                "meme_id": spec.meme_id,
                "timestamp": now_utc,
            })
        except ConstraintViolation:
            log({
                "event": "MEME_REPROJECTION_FAIL",
                "meme_id": spec.meme_id,
                "timestamp": now_utc,
            })
            if kernel:
                kernel.record_constraint_violation()
            raise

    # ------------------------------------------------------------------
    # 7. Write spec JSON
    # ------------------------------------------------------------------
    for spec in specs:
        spec_file = Path(spec.output.spec_path)
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        with open(spec_file, "w", encoding="utf-8") as f:
            f.write(spec.to_json())

    # ------------------------------------------------------------------
    # 8 + 9. Render
    # ------------------------------------------------------------------
    from app.agents.meme_offload.render.render_memes import render_meme

    for spec in specs:
        out_path = render_meme(spec)
        log({
            "event": "MEME_RENDER_DONE",
            "meme_id": spec.meme_id,
            "output_path": str(out_path),
            "timestamp": now_utc,
        })

    # ------------------------------------------------------------------
    # 10. Final telemetry
    # ------------------------------------------------------------------
    log({
        "event": "MEME_OFFLOAD_DONE",
        "action": ACTION,
        "total_rendered": len(specs),
        "meme_ids": [s.meme_id for s in specs],
        "pack_hash": p_hash,
        "timestamp": now_utc,
    })

    return specs
