"""Tests for Lyapunov scalar -- self-contained path injection."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent.parent.parent))
import unittest
from signal_agent.leviathan.interaction_signals.core.types import Event, ActorState, ThreadState
from signal_agent.leviathan.interaction_signals.core.features import compute_features
from signal_agent.leviathan.interaction_signals.core.classify import classify
from signal_agent.leviathan.interaction_signals.core.state_update import update_actor, update_thread
from signal_agent.leviathan.interaction_signals.core.lyapunov import compute_lyapunov, delta_v


def _full(text, actor=None, thread=None):
    ev = Event("e1","a","t","2026-02-28T18:00:00Z", text)
    a  = actor  or ActorState(actor_id="a")
    th = thread or ThreadState(thread_id="t")
    feat = compute_features(ev); sig = classify(feat)
    aa = update_actor(a, feat, sig); ta = update_thread(th, feat, sig)
    return compute_lyapunov(feat, sig, aa, ta) + (aa, ta)


class TestLyapunov(unittest.TestCase):

    def test_v_in_zero_one(self):
        for text in [
            "DM me now! Sign up. My course.",
            "Perhaps this might work. Fair point. Let me clarify.",
            "See benchmark at https://example.com (n=1200).",
            "",
        ]:
            V, _, _, _ = _full(text)
            self.assertGreaterEqual(V, 0.0, f"V<0 for {text!r}")
            self.assertLessEqual(V, 1.0, f"V>1 for {text!r}")

    def test_v_finite(self):
        V, cp, _, _ = _full("some neutral text here")
        self.assertEqual(V, V)
        self.assertEqual(cp["L_a"], cp["L_a"])

    def test_components_present(self):
        _, cp, _, _ = _full("test text")
        for key in ("L_a","L_tau","V_raw","V"):
            self.assertIn(key, cp)

    def test_delta_v_none_on_first(self):
        self.assertIsNone(delta_v(None, 0.5))

    def test_delta_v_correct(self):
        self.assertAlmostEqual(delta_v(0.4, 0.6), 0.2, places=5)

    def test_v_lower_for_evidence_rich(self):
        V_promo, _, _, _ = _full("DM me! Book a call. My clients. Sign up now.")
        V_proof, _, _, _ = _full(
            "Here are benchmark results at https://example.com\n"
            "Because integration of both approaches leads to convergence (n=1200)."
        )
        self.assertGreaterEqual(V_promo, V_proof)

    def test_transition_matrix_after_two_events(self):
        a0 = ActorState(actor_id="a")
        ev1 = Event("e1","a","t","2026-02-28T18:00:00Z","DM me! Sign up.")
        ev2 = Event("e2","a","t","2026-02-28T18:01:00Z","Perhaps I should clarify. Fair point.")
        f1=compute_features(ev1); s1=classify(f1); a1=update_actor(a0,f1,s1)
        f2=compute_features(ev2); s2=classify(f2); a2=update_actor(a1,f2,s2)
        self.assertGreater(len(a2.transition_matrix), 0)


if __name__ == "__main__":
    unittest.main()
