"""Tests for ensuring pipeline precedence (v0.5 hardening)."""
import unittest
import sys
import pathlib
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent.parent.parent))

from signal_agent.leviathan.interaction_signals.core.types import Event
from signal_agent.leviathan.interaction_signals.core.engine import StateStore, process_event
from signal_agent.leviathan.interaction_signals.core.policy import PolicyAction

class TestPipelinePrecedence(unittest.TestCase):
    @patch("signal_agent.leviathan.interaction_signals.core.engine.decide_actions")
    def test_decide_actions_called_after_phase_space_and_dyads(self, mock_decide):
        # Setup mock to just return a dummy PolicyAction
        # But we capture the `result` argument passed to it
        captured_result = None
        
        def fake_decide_actions(result):
            nonlocal captured_result
            captured_result = result
            return PolicyAction(
                reply_depth="medium",
                dm_gate=False,
                off_platform_gate=False,
                ask_for_artifact=False,
                pressure_protocol=False,
                notes=["mocked"]
            )
            
        mock_decide.side_effect = fake_decide_actions

        store = StateStore(self_actor_id="self")
        # Ensure we satisfy dyad creation condition
        store.set_last_actor_in_thread("t1", "other")
        
        ev = Event("e1", "self", "t1", "2026-02-28T21:00:00Z", "hello")
        
        final_result = process_event(ev, store)
        
        self.assertTrue(mock_decide.called)
        self.assertIsNotNone(captured_result)
        
        # Verify the pipeline precedence lock
        self.assertIsNotNone(captured_result.phase_point, "phase_point must be computed before decide_actions")
        self.assertIsNotNone(captured_result.dyad_after, "dyad_after must be computed before decide_actions")

if __name__ == "__main__":
    unittest.main()
