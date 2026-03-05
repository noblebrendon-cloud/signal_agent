"""Tests for feature extraction -- self-contained path injection."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent.parent.parent))
import unittest
from signal_agent.leviathan.interaction_signals.core.types import Event
from signal_agent.leviathan.interaction_signals.core.features import compute_features


def _ev(text, eid="e1", meta=None):
    return Event(event_id=eid, actor_id="a", thread_id="t",
                 timestamp="2026-02-28T18:00:00Z", text=text, meta=meta or {})


class TestFeatureRatios(unittest.TestCase):
    RATIO_KEYS = [
        "q_ratio","certainty_ratio","hedge_ratio","authority_ref_ratio",
        "self_ref_ratio","extraction_ratio","causal_ratio","integration_ratio",
        "abstraction_ratio","adversarial_tone","promo_density","challenge_intensity",
        "novelty_injection","synthesis_quality","scope_control","time_to_concrete",
    ]

    def test_ratios_in_range(self):
        feat = compute_features(_ev("Perhaps this might work, possibly."))
        for k in self.RATIO_KEYS:
            v = feat.f[k]
            self.assertGreaterEqual(v, 0.0, f"{k} < 0")
            self.assertLessEqual(v, 1.0, f"{k} > 1")

    def test_empty_text_no_nan(self):
        feat = compute_features(_ev(""))
        for k, v in feat.f.items():
            if isinstance(v, float):
                self.assertEqual(v, v, f"NaN for {k}")

    def test_hedge_ratio_nonzero(self):
        feat = compute_features(_ev("Perhaps this might possibly work."))
        self.assertGreater(feat.f["hedge_ratio"], 0.0)

    def test_extraction_ratio_nonzero(self):
        feat = compute_features(_ev("DM me now! Sign up for my course. Book a call today."))
        self.assertGreater(feat.f["extraction_ratio"], 0.0)

    def test_example_given_from_code_fence(self):
        feat = compute_features(_ev("Here is code:\n```python\nprint(1)\n```"))
        self.assertTrue(feat.f["example_given"])

    def test_example_given_from_digits(self):
        feat = compute_features(_ev("We saw improvement of 42 percent."))
        self.assertTrue(feat.f["example_given"])

    def test_proof_move_from_url(self):
        feat = compute_features(_ev("See results at https://example.com/benchmark"))
        self.assertTrue(feat.f["proof_move"])

    def test_challenge_present(self):
        feat = compute_features(_ev("How do you know this? Prove it works."))
        self.assertTrue(feat.f["challenge_present"])

    def test_repair_attempt(self):
        feat = compute_features(_ev("Fair point. Let me clarify what I meant."))
        self.assertTrue(feat.f["repair_attempt"])

    def test_scope_control_with_reply_to(self):
        feat = compute_features(_ev("the payment system scales well",
                                    meta={"reply_to": "payment system"}))
        self.assertGreater(feat.f["scope_control"], 0.0)

    def test_scope_control_default(self):
        feat = compute_features(_ev("something unrelated"))
        self.assertEqual(feat.f["scope_control"], 0.5)

    def test_question_follow_through_false(self):
        feat = compute_features(_ev("prove it. source? edge case?"))
        self.assertFalse(feat.f["question_follow_through"])


if __name__ == "__main__":
    unittest.main()
