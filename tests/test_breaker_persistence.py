from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.utils.breaker_store import SqliteBreakerStore
from app.utils.resilience import CircuitBreaker


class TestBreakerPersistence(unittest.TestCase):
    def test_breaker_persistence_survives_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "breakers.sqlite"

            store_a = SqliteBreakerStore(db_path)
            breaker_a = CircuitBreaker()
            now = 1000.0
            breaker_a.record_failure(now, open_after=1, open_for_seconds=60)
            store_a.persist_breaker("google:gemini-3-pro", breaker_a, now=now)

            store_b = SqliteBreakerStore(db_path)
            breaker_b = CircuitBreaker()
            loaded = store_b.load_state_into_breaker("google:gemini-3-pro", breaker_b, now=1000.0)

            self.assertTrue(loaded)
            self.assertEqual(breaker_b.get_state(1000.0), "OPEN")
            self.assertFalse(breaker_b.allow_request(1000.0))
            self.assertEqual(breaker_b.get_state(1061.0), "HALF_OPEN")
            self.assertTrue(breaker_b.allow_request(1061.0))


if __name__ == "__main__":
    unittest.main()
