"""
shared/contract.py — Minimal bundle lifecycle contract resolver.

Resolution order (stops at first authoritative hit):
  1. Registry lookup  — checks state_registry; skips if artifact file is missing (stale guard)
  2. Frontmatter scan — looks for `lifecycle_state:` in first 30 lines of bundle text
  3. Member ref scan  — infers `promoted` if bundle references raw source files,
                        but this is informational only and not authoritative for routing
  4. Raise ContractResolutionError — no silent fallback

Public API:
    resolve_bundle_contract(bundle_path, bundle_text, registry_path=None) -> dict

Return shape:
    {
        "lifecycle_state": str,       # e.g. "promoted", "routed"
        "contract_source": str,       # "registry" | "frontmatter" | "member_inference"
        "routable": bool,              # True only for authoritative routing evidence
        "confidence": str,            # "high" | "medium" | "low"
    }

confidence semantics:
    high   — registry confirmed AND file exists on disk
    medium — frontmatter present in bundle text
    low    — inferred from member/source references only; not routing authority
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

class ContractResolutionError(RuntimeError):
    """Raised when a bundle contract cannot be resolved from available evidence."""

# States that qualify a bundle for routing
ROUTABLE_STATES = {"promoted", "routed"}

# Frontmatter lifecycle_state key
_FM_RE = re.compile(r"^\s*lifecycle_state\s*:\s*(\S+)", re.MULTILINE)

# Member reference patterns in bundle text (from _build_bundle_content)
_MEMBER_RE = re.compile(r"raw_\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}")


def resolve_bundle_contract(
    bundle_path: Path,
    bundle_text: str,
    registry_path: Optional[Path] = None,
) -> dict:
    """
    Resolve the lifecycle contract for a bundle.

    Args:
        bundle_path:    Path to the bundle file on disk (used for registry key + file-existence check)
        bundle_text:    Raw text content of the bundle (used for frontmatter + member scan)
        registry_path:  Override path to state registry (for tests)

    Returns:
        dict with keys: lifecycle_state, contract_source, routable, confidence

    Raises:
        ContractResolutionError if no source can resolve the contract
    """
    # -------------------------------------------------------------------------
    # Step 1: Registry lookup (with stale-file guard)
    # -------------------------------------------------------------------------
    try:
        from shared.state_registry import get_state
        entry = get_state(bundle_path.name, registry_path=registry_path)
        if entry and entry.get("state") in ROUTABLE_STATES:
            # Stale registry guard: only trust registry if the file still exists
            if bundle_path.exists():
                return {
                    "lifecycle_state": entry["state"],
                    "contract_source": "registry",
                    "routable": True,
                    "confidence": "high",
                }
            # File missing — registry is stale; fall through to next step
    except Exception:
        pass  # If registry is unavailable, try next resolution step

    # -------------------------------------------------------------------------
    # Step 2: Frontmatter scan (first 30 lines)
    # -------------------------------------------------------------------------
    head = "\n".join(bundle_text.splitlines()[:30])
    fm_match = _FM_RE.search(head)
    if fm_match:
        state = fm_match.group(1).strip().rstrip("\"'")
        return {
            "lifecycle_state": state,
            "contract_source": "frontmatter",
            "routable": state in ROUTABLE_STATES,
            "confidence": "medium",
        }

    # -------------------------------------------------------------------------
    # Step 3: Member reference inference
    # Bundles built by promote.py include raw_* filenames in their text.
    # Presence of these filenames is useful evidence the bundle was promoted,
    # but it is not authoritative enough to route the bundle.
    # -------------------------------------------------------------------------
    if _MEMBER_RE.search(bundle_text):
        return {
            "lifecycle_state": "promoted",
            "contract_source": "member_inference",
            "routable": False,
            "confidence": "low",
        }

    # -------------------------------------------------------------------------
    # Step 4: No resolvable contract
    # -------------------------------------------------------------------------
    raise ContractResolutionError(
        f"Bundle '{bundle_path.name}' has no resolvable lifecycle contract. "
        f"Checked: registry (stale or missing), frontmatter (no lifecycle_state), "
        f"member inference (no raw_ references found). "
        f"Run a contract backfill pass to stamp this bundle before routing."
    )
