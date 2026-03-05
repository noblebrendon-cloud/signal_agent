"""Tests for ensuring the controller escalation invariants (v0.5 hardening)."""
import unittest
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent.parent.parent))

from signal_agent.leviathan.interaction_signals.core.types import Event, Features, Signal, ActorState, ThreadState
from signal_agent.leviathan.interaction_signals.core.engine import ProcessResult
from signal_agent.leviathan.interaction_signals.core.policy import decide_actions

class TestControllerInvariant(unittest.TestCase):
    def _make_result(self, dV: float) -> ProcessResult:
        ev = Event("e", "a", "t", "2026-02-28T21:00:00Z", "hello")
        feats = Features(ev.event_id, {"challenge_present": False, "adversarial_tone": 0.0})
        sig = Signal(event_id=ev.event_id, mode="COGNITIVE_HONESTY", confidence=0.9)
        actor = ActorState(
            actor_id="a",
            collab_readiness=0.8,
            integrity_index=0.8,
            transaction_pressure=0.1,
            extraction_after_trust=0.1,
            shipping_rate_30=0.5,
            evasion_rate_30=0.1,
            mode_histogram_30={"COGNITIVE_HONESTY": 1.0}
        )
        thread = ThreadState(
            thread_id="t", 
            leverage_score=0.8,
            coordination_cost=0.0,
            convergence_rate=1.0,
            disagreement_productivity=1.0,
            artifact_probability=1.0
        )
        return ProcessResult(
            event=ev,
            features=feats,
            signal=sig,
            actor_before=actor,
            actor_after=actor,
            thread_before=thread,
            thread_after=thread,
            V=0.35,
            dV=dV,
            lyapunov_components={}
        )

    def test_escalation_blocked_on_divergence(self):
        # 1. dV <= 0 allows DM and OFF gates
        res1 = self._make_result(dV=-0.1)
        action1 = decide_actions(res1)
        
        self.assertTrue(action1.dm_gate)
        self.assertTrue(action1.off_platform_gate)
        
        # 2. dV > 0 forcibly blocks escalation
        res2 = self._make_result(dV=0.05)
        action2 = decide_actions(res2)
        
        self.assertFalse(action2.dm_gate)
        self.assertFalse(action2.off_platform_gate)
        
        notes = list(action2.notes)
        self.assertTrue(any("escalation blocked: dV=" in note for note in notes))

if __name__ == "__main__":
    unittest.main()
