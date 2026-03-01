"""Tests for actor/thread state update -- self-contained path injection."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent.parent.parent))
import unittest
from signal_agent.leviathan.interaction_signals.core.types import Event, ActorState, ThreadState
from signal_agent.leviathan.interaction_signals.core.features import compute_features
from signal_agent.leviathan.interaction_signals.core.classify import classify
from signal_agent.leviathan.interaction_signals.core.state_update import update_actor, update_thread


def _run(text, actor=None, thread=None):
    ev = Event("e1","a","t","2026-02-28T18:00:00Z", text)
    a  = actor  or ActorState(actor_id="a")
    th = thread or ThreadState(thread_id="t")
    feat = compute_features(ev); sig = classify(feat)
    return update_actor(a, feat, sig), update_thread(th, feat, sig), feat, sig


class TestActorStateUpdate(unittest.TestCase):

    def test_transaction_pressure_increases_on_promo(self):
        a0 = ActorState(actor_id="a")
        a1, _, _, _ = _run("DM me! Book a call. My course. Sign up now.", actor=a0)
        self.assertGreater(a1.transaction_pressure, a0.transaction_pressure)

    def test_trust_decreases_with_transaction(self):
        a0 = ActorState(actor_id="a", trust_score=0.7)
        a1, _, _, sig = _run("DM me! Sign up. My clients. Book a call.", actor=a0)
        if sig.mode == "TRANSACTION":
            self.assertLess(a1.trust_score, a0.trust_score)

    def test_evasion_increases_on_transaction_no_proof(self):
        a0 = ActorState(actor_id="a")
        a1, _, feat, sig = _run("DM me! Sign up. My clients. Book a call.", actor=a0)
        if sig.mode == "TRANSACTION" and not feat.f.get("proof_move") and not feat.f.get("example_given"):
            self.assertGreater(a1.evasion_rate_30, a0.evasion_rate_30)

    def test_shipping_increases_on_evidence(self):
        a0 = ActorState(actor_id="a")
        a1, _, _, _ = _run("Here is proof at https://example.com (n=1200 test set).", actor=a0)
        self.assertGreater(a1.shipping_rate_30, a0.shipping_rate_30)

    def test_mode_histogram_keys_correct(self):
        a, _, _, _ = _run("neutral text")
        self.assertIn("PERFORMANCE", a.mode_histogram_30)
        self.assertIn("TRANSACTION", a.mode_histogram_30)

    def test_last_n_modes_bounded(self):
        a = ActorState(actor_id="a")
        for _ in range(15):
            a, _, _, _ = _run("DM me! Sign up.", actor=a)
        self.assertLessEqual(len(a.last_n_modes), 10)

    def test_all_actor_floats_in_range(self):
        a, _, _, _ = _run("perhaps maybe build on evidence because integration")
        for field in ("trust_score","collab_readiness","integrity_index",
                      "transaction_pressure","mode_volatility_30",
                      "evasion_rate_30","shipping_rate_30"):
            v = getattr(a, field)
            self.assertGreaterEqual(v, 0.0, field)
            self.assertLessEqual(v, 1.0, field)


class TestThreadStateUpdate(unittest.TestCase):

    def test_shipping_evidence_increases_on_proof(self):
        th0 = ThreadState(thread_id="t")
        _, th1, _, _ = _run("See the results at https://example.com (n=1200)", thread=th0)
        self.assertGreater(th1.shipping_evidence_score, th0.shipping_evidence_score)

    def test_drift_increases_on_promo(self):
        th0 = ThreadState(thread_id="t")
        _, th1, _, _ = _run("DM me! My course. Sign up. Book a call.", thread=th0)
        self.assertGreater(th1.drift_score, th0.drift_score)

    def test_all_thread_floats_in_range(self):
        _, th, _, _ = _run("perhaps we might integrate these results furthermore")
        for field in ("working_node_score","shipping_evidence_score","drift_score",
                      "leverage_score","artifact_probability","coordination_cost",
                      "convergence_rate","disagreement_productivity"):
            v = getattr(th, field)
            self.assertGreaterEqual(v, 0.0, field)
            self.assertLessEqual(v, 1.0, field)


if __name__ == "__main__":
    unittest.main()
