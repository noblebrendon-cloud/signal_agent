import unittest
from unittest.mock import MagicMock, patch
import time
from app.agent import SignalAgent, AgentConfig, CircuitBreaker

class TestAgentResilience(unittest.TestCase):
    def test_deterministic_jitter(self):
        """Verify that same request_id yields same sleep pattern."""
        config = AgentConfig(
            models=("mock:model",),
            max_attempts_per_model=3,
            base_delay_s=1.0,
            max_delay_s=10.0,
            multiplier=2.0
        )
        agent = SignalAgent(config)
        agent._call_model = MagicMock(side_effect=RuntimeError("503 Unavailable"))
        
        # Mock time.sleep to capture delays
        with patch("time.sleep") as mock_sleep:
             # Force retry on RuntimeError for test

            # Run 1
            try:
                agent.generate("test", request_id="run_1")
            except Exception as e:
                print(f"DEBUG: Run 1 raised {e}")
            delays_1 = [call.args[0] for call in mock_sleep.call_args_list]
            print(f"DEBUG: Delays 1: {delays_1}")
            
            mock_sleep.reset_mock()
            
            # Run 2 (Same ID)
            agent2 = SignalAgent(config)
            agent2._call_model = MagicMock(side_effect=RuntimeError("503 Unavailable"))
            try:
                agent2.generate("test", request_id="run_1")
            except Exception as e:
                print(f"DEBUG: Run 2 raised {e}")
            delays_2 = [call.args[0] for call in mock_sleep.call_args_list]

            mock_sleep.reset_mock()

            # Run 3 (Different ID)
            agent3 = SignalAgent(config)
            agent3._call_model = MagicMock(side_effect=RuntimeError("503 Unavailable"))
            try:
                agent3.generate("test", request_id="run_2")
            except Exception as e:
                print(f"DEBUG: Run 3 raised {e}")
            delays_3 = [call.args[0] for call in mock_sleep.call_args_list]

        # Assertions
        self.assertEqual(delays_1, delays_2, "Same request_id should yield same jitter delays")
        self.assertNotEqual(delays_1, delays_3, "Different request_id should yield different jitter delays")

if __name__ == "__main__":
    unittest.main()
