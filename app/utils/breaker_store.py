from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BreakerRecord:
    provider: str
    fail_count: int
    last_fail_ts: float
    state: str
    cooldown_until: float


class SqliteBreakerStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS breaker_state (
                    provider TEXT PRIMARY KEY,
                    fail_count INTEGER NOT NULL,
                    last_fail_ts REAL NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('open', 'half_open', 'closed')),
                    cooldown_until REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.commit()

    def load_record(self, provider: str) -> BreakerRecord | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT provider, fail_count, last_fail_ts, state, cooldown_until
                FROM breaker_state
                WHERE provider = ?
                """,
                (provider,),
            ).fetchone()
        if row is None:
            return None
        return BreakerRecord(
            provider=str(row["provider"]),
            fail_count=int(row["fail_count"]),
            last_fail_ts=float(row["last_fail_ts"]),
            state=str(row["state"]),
            cooldown_until=float(row["cooldown_until"]),
        )

    def save_record(self, record: BreakerRecord) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO breaker_state (provider, fail_count, last_fail_ts, state, cooldown_until, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider) DO UPDATE SET
                    fail_count = excluded.fail_count,
                    last_fail_ts = excluded.last_fail_ts,
                    state = excluded.state,
                    cooldown_until = excluded.cooldown_until,
                    updated_at = excluded.updated_at
                """,
                (
                    record.provider,
                    int(record.fail_count),
                    float(record.last_fail_ts),
                    str(record.state),
                    float(record.cooldown_until),
                    float(time.time()),
                ),
            )
            conn.commit()

    def load_state_into_breaker(self, provider: str, breaker: Any, *, now: float | None = None) -> bool:
        record = self.load_record(provider)
        if record is None:
            return False
        breaker.apply_persisted_state(
            fail_count=record.fail_count,
            last_fail_ts=record.last_fail_ts,
            state=record.state,
            cooldown_until=record.cooldown_until,
            now=now if now is not None else time.time(),
        )
        return True

    def persist_breaker(self, provider: str, breaker: Any, *, now: float | None = None) -> None:
        now_ts = now if now is not None else time.time()
        state = breaker.get_state(now_ts).lower()
        record = BreakerRecord(
            provider=provider,
            fail_count=int(getattr(breaker, "failures", 0)),
            last_fail_ts=float(getattr(breaker, "last_fail_ts", 0.0)),
            state=state,
            cooldown_until=float(getattr(breaker, "open_until", 0.0)),
        )
        self.save_record(record)
