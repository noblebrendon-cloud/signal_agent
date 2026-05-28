from __future__ import annotations

from pathlib import Path
from typing import Callable

from signal_agent.transport.ledgers.jsonl import AppendOnlyJsonlLedger, utc_now_iso


LEDGER_NAMES = (
    "post_attempts",
    "execution_results",
    "retries",
    "provider_failures",
    "analytics_snapshots",
    "approvals",
    "transformations",
    "policy_decisions",
    "queue_transitions",
)


class TransportLedgers:
    def __init__(
        self,
        root: str | Path,
        *,
        clock: Callable[[], str] = utc_now_iso,
        lock_on_ledger: bool = False,
    ) -> None:
        self.root = Path(root)
        self.clock = clock
        self._ledgers = {
            name: AppendOnlyJsonlLedger(
                self.root / f"{name}.jsonl",
                clock=clock,
                lock_on_ledger=lock_on_ledger,
            )
            for name in LEDGER_NAMES
        }

    def ledger(self, name: str) -> AppendOnlyJsonlLedger:
        try:
            return self._ledgers[name]
        except KeyError as exc:
            raise KeyError(f"unknown_transport_ledger:{name}") from exc

    def append(self, name: str, record: dict) -> dict:
        return self.ledger(name).append(record)

    def read(self, name: str) -> list[dict]:
        return self.ledger(name).read()
