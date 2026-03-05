from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class SqliteBreakerStore:
    db_path: Path

    def __post_init__(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as cx:
            cx.execute(
                """
                CREATE TABLE IF NOT EXISTS breakers (
                    name TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    updated_utc TEXT
                )
                """
            )
            cx.commit()

    def set_state(self, name: str, state: str) -> None:
        with sqlite3.connect(str(self.db_path)) as cx:
            cx.execute(
                "INSERT INTO breakers(name, state, updated_utc) VALUES(?, ?, datetime('now')) "
                "ON CONFLICT(name) DO UPDATE SET state=excluded.state, updated_utc=excluded.updated_utc",
                (name, state.upper()),
            )
            cx.commit()

    def get_state(self, name: str) -> str:
        with sqlite3.connect(str(self.db_path)) as cx:
            row = cx.execute("SELECT state FROM breakers WHERE name = ?", (name,)).fetchone()
            if not row:
                return "CLOSED"
            return str(row[0]).upper()

    def required_breakers(self) -> List[str]:
        # Minimal default: one breaker controlling the loop.
        return ["default"]
