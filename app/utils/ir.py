import hashlib
import json
from typing import Any, Dict, List
from app.utils.reprojection import ConstraintPack, extract_artifact_state, ArtifactState

def stable_pack_hash(pack: ConstraintPack) -> str:
    """
    Computes a deterministic SHA256 hash of the ConstraintPack.
    """
    data = {
        "scope": pack.scope,
        "required_invariants": sorted([json.dumps(x, sort_keys=True) for x in pack.required_invariants]),
        "disallowed_phrases": sorted(pack.disallowed_phrases),
        "allowed_output_classes": sorted(pack.allowed_output_classes),
        "boundary_conditions": {k: v for k, v in sorted(pack.boundary_conditions.items())}
    }
    dump = json.dumps(data, sort_keys=True).encode("utf-8")
    return hashlib.sha256(dump).hexdigest()

def validate_leaves(ir: Dict[str, Any]) -> bool:
    """
    Validates that all leaf nodes in the IR (sections) are strings.
    """
    sections = ir.get("sections", {})
    if not isinstance(sections, dict):
        return False
    for k, v in sections.items():
        if not isinstance(k, str):
            return False
        if not isinstance(v, str):
            return False
    return True

def parse_text_to_ir(text: str, pack: ConstraintPack = None) -> Dict[str, Any]:
    """
    Parses text into a structured Intermediate Representation (IR).
    The IR is the single source of truth.
    """
    state = extract_artifact_state(text)
    
    # Pack hash for traceability
    pack_hash = stable_pack_hash(pack) if pack else "no_pack"

    return {
        "meta": {
            "version": "1.0",
            "pack_hash": pack_hash,
            "word_count": state.word_count,
            "claims_count": len(state.claims)
        },
        "sections": state.sections,  #Dict[str, str]
        # We store full_text only if we want perfect fidelity, but axiom says text is render target.
        # But for stability, regenerating from sections is preferred if deterministic.
        # Sections parsing in extract_artifact_state is lossy regarding exact whitespace between sections?
        # It joins content with \n.
        # Let's rely on sections as the primary data.
    }

def render_ir_to_text(ir: Dict[str, Any]) -> str:
    """
    Renders the IR back into text.
    """
    sections = ir.get("sections", {})
    lines = []
    
    # Preamble first
    if "preamble" in sections:
        lines.append(sections["preamble"])
        
    # Then other sections in order
    for head, content in sections.items():
        if head == "preamble":
            continue
        lines.append(f"\n# {head}")  # Axiom: Render logic determines formatting
        lines.append(content)
        
    return "\n".join(lines).strip()
