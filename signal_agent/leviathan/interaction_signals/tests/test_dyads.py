"""Tests for core/dyads.py -- Dyadic working_pair_score tracking."""
import unittest
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent.parent.parent))

from signal_agent.leviathan.interaction_signals.core.types import (
    DyadState, Event, Features, Signal, ActorState, ThreadState
)
from signal_agent.leviathan.interaction_signals.core.dyads import update_dyad

class TestDyads(unittest.TestCase):
    def setUp(self):
        self.st = DyadState("self", "other")
        self.actor = ActorState("other", transaction_pressure=0.0)
        self.thread = ThreadState("t")

    def _ev(self, actor_id: str):
        return Event("e", actor_id, "t", "2026-01-01T00:00:00Z", "text")

    def test_asymmetry_penalty_increases_on_one_sided_contrib(self):
        ev = self._ev("self") # mine
        f = Features("e", {"novelty_injection": 1.0, "synthesis_quality": 1.0, "proof_move": True})
        s = Signal("e", "PERFORMANCE")
        
        # Self does all the work
        st2 = update_dyad(self.st, ev, f, s, self.actor, self.thread, alpha=1.0)
        self.assertGreater(st2.my_contrib, 0.0)
        self.assertEqual(st2.their_contrib, 0.0)
        self.assertAlmostEqual(st2.asymmetry_penalty, 1.0)

        # Other joins in
        ev_other = self._ev("other")
        st3 = update_dyad(st2, ev_other, f, s, self.actor, self.thread, alpha=1.0)
        # alpha=1.0 -> their EMA replaces old value -> their_contrib becomes equal to my_contrib
        self.assertAlmostEqual(st3.my_contrib, st3.their_contrib)
        self.assertAlmostEqual(st3.asymmetry_penalty, 0.0)

    def test_working_pair_score_increases_with_mutual_shipping(self):
        ev = self._ev("other")
        f = Features("e", {"synthesis_quality": 1.0, "proof_move": True})
        s = Signal("e", "PERFORMANCE")
        
        st2 = update_dyad(self.st, ev, f, s, self.actor, self.thread, alpha=1.0)
        self.assertGreater(st2.working_pair_score, 0.0)

    def test_extraction_penalty_lowers_w(self):
        ev = self._ev("other")
        f = Features("e", {"extraction_ratio": 1.0})
        s = Signal("e", "TRANSACTION")
        actor_tx = ActorState("other", transaction_pressure=1.0)
        
        st2 = update_dyad(self.st, ev, f, s, actor_tx, self.thread, alpha=1.0)
        self.assertAlmostEqual(st2.extraction_penalty, 1.0)
        self.assertEqual(st2.working_pair_score, 0.0)  # clamped at 0

if __name__ == "__main__":
    unittest.main()
