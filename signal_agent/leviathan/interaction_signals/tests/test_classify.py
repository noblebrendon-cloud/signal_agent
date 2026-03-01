"""Tests for classifier -- self-contained path injection."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent.parent.parent))
import unittest
from signal_agent.leviathan.interaction_signals.core.types import Event, Features
from signal_agent.leviathan.interaction_signals.core.features import compute_features
from signal_agent.leviathan.interaction_signals.core.classify import classify


def _feat(text):
    ev = Event("e1","a","t","2026-02-28T18:00:00Z", text)
    return compute_features(ev)


class TestClassifier(unittest.TestCase):

    def test_prob_sums_to_one(self):
        sig = classify(_feat("Perhaps this might work because the evidence shows it."))
        self.assertAlmostEqual(sum(sig.p.values()), 1.0, places=5)

    def test_confidence_in_range(self):
        sig = classify(_feat("Book a call! DM me now. My clients love my program."))
        self.assertGreaterEqual(sig.confidence, 0.0)
        self.assertLessEqual(sig.confidence, 1.0)

    def test_transaction_on_promo_text(self):
        sig = classify(_feat("DM me now! Sign up. Book a call. My course. Link in bio."))
        self.assertEqual(sig.mode, "TRANSACTION")

    def test_performance_on_benchmark_text(self):
        sig = classify(_feat(
            "Here are the benchmark results at https://example.com (n=1200). "
            "Because of the integration with the pipeline, synthesis of both approaches works."
        ))
        self.assertEqual(sig.mode, "PERFORMANCE")

    def test_cognitive_honesty_on_hedge_challenge(self):
        sig = classify(_feat(
            "Perhaps we might be wrong. How do you know this works? "
            "Prove it. Let me clarify what I meant. Fair point."
        ))
        self.assertEqual(sig.mode, "COGNITIVE_HONESTY")

    def test_mode_in_valid_set(self):
        valid = {"PERFORMANCE","TRANSACTION","COGNITIVE_HONESTY","MIXED"}
        for text in ["hello", "Book a call!", "maybe", "with code example"]:
            sig = classify(_feat(text))
            self.assertIn(sig.mode, valid)

    def test_reasons_nonempty(self):
        sig = classify(_feat("Perhaps this might be correct. How do you know?"))
        self.assertGreater(len(sig.reasons), 0)

    def test_all_probs_positive(self):
        sig = classify(_feat("neutral text with no strong signal"))
        for v in sig.p.values():
            self.assertGreater(v, 0.0)


if __name__ == "__main__":
    unittest.main()
