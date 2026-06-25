from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from signal_agent.transport.ledgers import AppendOnlyJsonlLedger, utc_now_iso


MEDIA_OPPORTUNITY_LEDGER_NAMES = (
    "opportunity_records",
    "state_transitions",
    "approval_records",
    "public_reference_exports",
)


def repo_root() -> Path:
    root = os.environ.get("SIGNAL_AGENT_ROOT")
    if root:
        return Path(root).resolve()
    return Path(__file__).resolve().parents[2]


def state_root(root: Path | None = None) -> Path:
    return (root or repo_root()) / "data" / "state" / "media_opportunities"


class MediaOpportunityLedgers:
    def __init__(self, root: str | Path | None = None, *, clock: Callable[[], str] = utc_now_iso) -> None:
        self.root = Path(root) if root is not None else state_root()
        self.clock = clock
        self._ledgers = {
            name: AppendOnlyJsonlLedger(
                self.root / f"{name}.jsonl",
                clock=clock,
                lock_on_ledger=True,
            )
            for name in MEDIA_OPPORTUNITY_LEDGER_NAMES
        }

    def append(self, name: str, record: dict) -> dict:
        return self.ledger(name).append(record)

    def read(self, name: str) -> list[dict]:
        return self.ledger(name).read()

    def ledger(self, name: str) -> AppendOnlyJsonlLedger:
        try:
            return self._ledgers[name]
        except KeyError as exc:
            raise KeyError(f"unknown_media_opportunity_ledger:{name}") from exc
