import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile

from app.agent import SignalAgent, AgentConfig

class TestAgentResilience(unittest.TestCase):
    def test_deterministic_jitter(self):
        """Verify that same request_id yields same sleep pattern."""
        # Keep this test hermetic: no shared repo DB/log state.
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)

            def _make_agent(db_name: str, log_name: str) -> SignalAgent:
                cfg = AgentConfig(
                    models=("mock:model",),
                    max_attempts_per_model=3,
                    base_delay_s=1.0,
                    max_delay_s=10.0,
                    multiplier=2.0,
                    breaker_db_path=tmp / db_name,
                    analytics_log=tmp / log_name,
                )
                ag = SignalAgent(cfg)
                ag._call_model = MagicMock(side_effect=RuntimeError("503 Unavailable"))
                return ag

            # Mock time.sleep to capture delays
            with patch("time.sleep") as mock_sleep:
                # Run 1
                try:
                    _make_agent("breakers_1.sqlite", "events_1.jsonl").generate("test", request_id="run_1")
                except Exception:
                    pass
                delays_1 = [call.args[0] for call in mock_sleep.call_args_list]

                mock_sleep.reset_mock()

                # Run 2 (Same ID)
                try:
                    _make_agent("breakers_2.sqlite", "events_2.jsonl").generate("test", request_id="run_1")
                except Exception:
                    pass
                delays_2 = [call.args[0] for call in mock_sleep.call_args_list]

                mock_sleep.reset_mock()

                # Run 3 (Different ID)
                try:
                    _make_agent("breakers_3.sqlite", "events_3.jsonl").generate("test", request_id="run_2")
                except Exception:
                    pass
                delays_3 = [call.args[0] for call in mock_sleep.call_args_list]

        # Assertions
        self.assertEqual(delays_1, delays_2, "Same request_id should yield same jitter delays")
        self.assertNotEqual(delays_1, delays_3, "Different request_id should yield different jitter delays")

if __name__ == "__main__":
    unittest.main()
