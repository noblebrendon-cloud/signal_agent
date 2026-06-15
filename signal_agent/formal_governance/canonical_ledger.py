from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ledger import append_ledger_entry
from .models import PromotionDecision, TransitionProposal


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def append_canonical_ledger_entry(
    path: Path,
    *,
    proposal: TransitionProposal,
    decision: PromotionDecision,
    subsystem_refs: list[dict[str, Any]] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """
    Append one normalized governed-transition proof entry.

    This helper preserves subsystem ledgers by linking to their evidence through
    subsystem_refs instead of replacing or rewriting those ledgers.
    """

    return append_ledger_entry(
        Path(path),
        proposal=proposal,
        decision=decision,
        timestamp=timestamp or utc_timestamp(),
        subsystem_refs=[dict(item) for item in subsystem_refs or []],
    )
