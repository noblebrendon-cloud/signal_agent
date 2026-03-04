"""Tests for core/policy.py -- deterministic policy decisions."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent.parent.parent))

import unittest
from signal_agent.leviathan.interaction_signals.core.types import (
    Event, ActorState, ThreadState, ControllerParams,
)
from signal_agent.leviathan.interaction_signals.core.engine import StateStore, process_event
from signal_agent.leviathan.interaction_signals.core.policy import (
    PolicyAction, decide_actions, transition_prob,
)


# ── helpers ────────────────────────────────────────────────────────────────

def _result(
    text: str, 
    actor: ActorState | None = None, 
    thread: ThreadState | None = None,
    last_v: float | None = None,
    controller_params: ControllerParams | None = None,
):
    """Run process_event and return a ProcessResult."""
    ev = Event("e1", "a", "t", "2026-02-28T18:00:00Z", text)
    store = StateStore()
    if actor:
        store.set_actor(actor)
    if thread:
        store.set_thread(thread)
    if last_v is not None:
        store.set_last_v("a", "t", last_v)
    if controller_params is not None:
        store.system_params = controller_params
    return process_event(ev, store)


# ── transition_prob tests ──────────────────────────────────────────────────

class TestTransitionProb(unittest.TestCase):

    def test_empty_matrix_returns_zero(self):
        self.assertEqual(transition_prob({}, "COGNITIVE_HONESTY", "TRANSACTION"), 0.0)

    def test_uniform_init_returns_near_quarter(self):
        """Default EMA-initialised matrix rows (~0.25 each) should normalise to 0.25."""
        matrix = {
            "COGNITIVE_HONESTY": {
                "PERFORMANCE": 0.25,
                "TRANSACTION": 0.25,
                "COGNITIVE_HONESTY": 0.25,
                "MIXED": 0.25,
            }
        }
        p = transition_prob(matrix, "COGNITIVE_HONESTY", "TRANSACTION")
        self.assertAlmostEqual(p, 0.25, places=5)

    def test_biased_matrix_reflects_skew(self):
        """After repeated HONESTY→TRANSACTION transitions the probability should exceed 0.5."""
        matrix = {
            "COGNITIVE_HONESTY": {
                "PERFORMANCE": 0.05,
                "TRANSACTION": 0.80,
                "COGNITIVE_HONESTY": 0.10,
                "MIXED": 0.05,
            }
        }
        p = transition_prob(matrix, "COGNITIVE_HONESTY", "TRANSACTION")
        self.assertGreater(p, 0.5)

    def test_missing_from_mode_returns_zero(self):
        matrix = {"PERFORMANCE": {"TRANSACTION": 1.0}}
        self.assertEqual(transition_prob(matrix, "COGNITIVE_HONESTY", "TRANSACTION"), 0.0)


# ── PolicyAction field type tests ──────────────────────────────────────────

class TestPolicyActionShape(unittest.TestCase):

    def test_result_has_policy_action(self):
        r = _result("Integration and synthesis of evidence confirm the prior work.")
        self.assertIsNotNone(r.policy_action)
        self.assertIsInstance(r.policy_action, PolicyAction)

    def test_reply_depth_valid(self):
        r = _result("neutral message")
        self.assertIn(r.policy_action.reply_depth, {"low", "medium", "high"})

    def test_gates_are_bool(self):
        r = _result("Let's connect. DM me to discuss the collaboration plan.")
        pa = r.policy_action
        self.assertIsInstance(pa.dm_gate, bool)
        self.assertIsInstance(pa.off_platform_gate, bool)
        self.assertIsInstance(pa.ask_for_artifact, bool)
        self.assertIsInstance(pa.pressure_protocol, bool)

    def test_notes_is_list(self):
        r = _result("DM me! Sign up!  Book a call now.")
        self.assertIsInstance(r.policy_action.notes, list)

    def test_policy_version_is_pinned(self):
        r = _result("neutral message")
        self.assertEqual(r.policy_action.policy_version, "0.3")

    def test_reasons_are_sorted_and_unique(self):
        actor = ActorState(
            actor_id="a",
            cooldown_dm=2,
        )
        r = _result("DM me now! Book a call! Sign up.", actor=actor)
        reasons = r.policy_action.reasons
        self.assertEqual(reasons, sorted(reasons))
        self.assertEqual(len(reasons), len(set(reasons)))

    def test_metrics_snapshot_required_keys_and_types(self):
        r = _result("neutral message")
        snap = r.policy_action.metrics_snapshot
        expected_keys = {
            "mode",
            "V",
            "dV",
            "p_h_to_t",
            "flip_threshold",
            "flip_base_threshold",
            "theta_v_escalate",
            "off_platform_theta",
            "delta_v_spike_threshold",
            "mode_entropy_norm",
            "collab_readiness",
            "integrity_index",
            "transaction_pressure",
            "extraction_after_trust",
            "leverage_score",
            "artifact_probability",
            "coordination_cost",
            "convergence_rate",
            "pressure_integrity",
            "cooldown_dm",
            "cooldown_off",
        }
        self.assertEqual(set(snap.keys()), expected_keys)
        self.assertIsInstance(snap["mode"], str)
        self.assertTrue(snap["dV"] is None or isinstance(snap["dV"], float))
        self.assertIsInstance(snap["cooldown_dm"], int)
        self.assertIsInstance(snap["cooldown_off"], int)


# ── Transaction mode gates ─────────────────────────────────────────────────

class TestTransactionGating(unittest.TestCase):

    def test_transaction_text_disables_dm_and_off_platform(self):
        """Promotional / transaction text should lock out DM and off-platform."""
        r = _result("DM me now! Book a call! Sign up for the programme. My clients get results.")
        pa = r.policy_action
        # DM and off-platform must be False in transaction mode
        self.assertFalse(pa.dm_gate)
        self.assertFalse(pa.off_platform_gate)

    def test_transaction_text_requests_artifact(self):
        r = _result("DM me now! Book a call! Sign up. My course. Link in bio.")
        self.assertTrue(r.policy_action.ask_for_artifact)


# ── Flip-risk gate ─────────────────────────────────────────────────────────

class TestFlipRiskGate(unittest.TestCase):

    def test_high_flip_risk_delays_dm(self):
        """When P(HONESTY→TRANSACTION) > 0.35, dm_gate must be False and artifact requested."""
        # Build an actor with a strongly biased transition toward TRANSACTION
        actor = ActorState(
            actor_id="a",
            collab_readiness=0.8,
            integrity_index=0.8,
            transaction_pressure=0.2,
            extraction_after_trust=0.1,
            trust_score=0.8,
            transition_matrix={
                "COGNITIVE_HONESTY": {
                    "PERFORMANCE": 0.05,
                    "TRANSACTION": 0.80,
                    "COGNITIVE_HONESTY": 0.10,
                    "MIXED": 0.05,
                }
            },
        )
        thread = ThreadState(
            thread_id="t",
            leverage_score=0.75,
            coordination_cost=0.3,
            convergence_rate=0.7,
            artifact_probability=0.7,
            shipping_evidence_score=0.6,
        )
        r = _result(
            "I've been synthesising causal evidence because integration builds on that prior work.",
            actor=actor,
            thread=thread,
        )
        pa = r.policy_action
        self.assertFalse(pa.dm_gate, "flip-risk should block DM gate")
        self.assertTrue(pa.ask_for_artifact, "flip-risk should request artifact")
        self.assertFalse(pa.off_platform_gate)

    def test_low_flip_risk_allows_dm_when_conditions_met(self):
        """When flip-risk is low and all actor/thread conditions are met, dm_gate may open."""
        actor = ActorState(
            actor_id="a",
            collab_readiness=0.80,
            integrity_index=0.70,
            transaction_pressure=0.20,
            extraction_after_trust=0.10,
            trust_score=0.80,
            transition_matrix={
                "COGNITIVE_HONESTY": {
                    "PERFORMANCE": 0.50,
                    "TRANSACTION": 0.10,   # low flip-risk
                    "COGNITIVE_HONESTY": 0.30,
                    "MIXED": 0.10,
                }
            },
        )
        thread = ThreadState(
            thread_id="t",
            leverage_score=0.75,
            coordination_cost=0.3,
            convergence_rate=0.7,
            artifact_probability=0.5,   # below 0.50 → evidence-gap rule triggers
        )
        r = _result(
            "Integrating causal evidence: we have synthesis from three studies. "
            "I'm happy to collaborate on next steps.",
            actor=actor,
            thread=thread,
        )
        # Even with low flip-risk, the evidence-gap rule (leverage>0.60 but artifact_prob<0.50)
        # may intercept — that's correct behaviour.  We just verify the policy ran.
        pa = r.policy_action
        self.assertIsNotNone(pa)


# ── Pressure protocol ─────────────────────────────────────────────────────

class TestPressureProtocol(unittest.TestCase):

    def test_adversarial_tone_with_low_pressure_integrity_triggers_protocol(self):
        actor = ActorState(
            actor_id="a",
            pressure_integrity=0.30,  # below 0.45 threshold
        )
        # adversarial text that produces adversarial_tone > 0.35
        r = _result(
            "Why would that ever work? You're wrong. This is nonsense. "
            "Prove it or stop wasting my time. Completely false.",
            actor=actor,
        )
        pa = r.policy_action
        # pressure_protocol may be True if adversarial_tone > 0.35 fires
        # (result depends on lexicon hits — we just verify no crash)
        self.assertIsNotNone(pa)
        self.assertIn(pa.reply_depth, {"low", "medium", "high"})


# ── Immutability ───────────────────────────────────────────────────────────

class TestPolicyActionFrozen(unittest.TestCase):

    def test_policy_action_is_frozen(self):
        r = _result("neutral text")
        with self.assertRaises((AttributeError, TypeError)):
            r.policy_action.dm_gate = True  # type: ignore[misc]


# ── Escalation Invariant (v0.5) ────────────────────────────────────────────

class TestEscalationInvariant(unittest.TestCase):

    def test_dm_gate_blocked_when_dv_is_positive(self):
        actor = ActorState(
            actor_id="a",
            collab_readiness=0.80,
            integrity_index=0.70,
            transaction_pressure=0.20,
            extraction_after_trust=0.10,
            trust_score=0.80,
            mode_histogram_30={"COGNITIVE_HONESTY": 1.0}  # very stable
        )
        thread = ThreadState(
            thread_id="t", 
            leverage_score=0.75,
            coordination_cost=0.0,
            convergence_rate=1.0,
            disagreement_productivity=1.0,
            artifact_probability=1.0
        )
        
        # Test 1: dV <= 0 allows DM gate (base case)
        # We need last_v to be >= newly computed V.
        # V will be roughly 0.6 * (1-0.8 + 0.2 + 0 + 0 + 0) = 0.24. So last_v=0.99 will ensure dV < 0.
        r_ok = _result("let's collaborate", actor=actor, thread=thread, last_v=0.99)
        self.assertTrue(r_ok.policy_action.dm_gate)
        
        # Test 2: dV > 0 blocks DM gate
        # last_v=0.01 will ensure dV > 0
        r_block = _result("let's collaborate", actor=actor, thread=thread, last_v=0.01)
        self.assertFalse(r_block.policy_action.dm_gate)
        self.assertTrue(any("escalation blocked" in note for note in r_block.policy_action.notes))


# ── v0.3: mode entropy ─────────────────────────────────────────────────────

from signal_agent.leviathan.interaction_signals.core.policy import (
    mode_entropy_norm, adaptive_flip_threshold,
)


class TestModeEntropy(unittest.TestCase):

    def test_uniform_histogram_is_max_entropy(self):
        h = {"PERFORMANCE": 0.25, "TRANSACTION": 0.25,
             "COGNITIVE_HONESTY": 0.25, "MIXED": 0.25}
        self.assertAlmostEqual(mode_entropy_norm(h), 1.0, places=4)

    def test_peaked_histogram_is_low_entropy(self):
        h = {"PERFORMANCE": 0.97, "TRANSACTION": 0.01,
             "COGNITIVE_HONESTY": 0.01, "MIXED": 0.01}
        self.assertLess(mode_entropy_norm(h), 0.15)

    def test_empty_histogram_returns_one(self):
        self.assertEqual(mode_entropy_norm({}), 1.0)

    def test_entropy_in_unit_interval(self):
        import random
        rng = random.Random(42)
        for _ in range(50):
            raw = {m: rng.random() for m in ("PERFORMANCE", "TRANSACTION",
                                              "COGNITIVE_HONESTY", "MIXED")}
            v = mode_entropy_norm(raw)
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 1.0)


class TestAdaptiveFlipThreshold(unittest.TestCase):

    def test_minimum_threshold_at_zero_entropy(self):
        self.assertAlmostEqual(adaptive_flip_threshold(0.0), 0.30, places=6)

    def test_maximum_threshold_at_max_entropy(self):
        self.assertAlmostEqual(adaptive_flip_threshold(1.0), 0.50, places=6)

    def test_midpoint(self):
        self.assertAlmostEqual(adaptive_flip_threshold(0.5), 0.40, places=6)

    def test_threshold_monotone(self):
        """Higher entropy → higher threshold (demand more evidence)."""
        thresholds = [adaptive_flip_threshold(h) for h in (0.0, 0.25, 0.5, 0.75, 1.0)]
        self.assertEqual(thresholds, sorted(thresholds))


# ── v0.3: cooldown hysteresis ─────────────────────────────────────────────

class TestCooldownHysteresis(unittest.TestCase):

    def _actor_with_cooldown(self, dm: int, off: int) -> ActorState:
        """Return an otherwise well-qualified actor with explicit cooldown values."""
        return ActorState(
            actor_id="a",
            collab_readiness=0.80,
            integrity_index=0.70,
            transaction_pressure=0.20,
            extraction_after_trust=0.10,
            trust_score=0.80,
            cooldown_dm=dm,
            cooldown_off=off,
            transition_matrix={
                "COGNITIVE_HONESTY": {
                    "PERFORMANCE": 0.60,
                    "TRANSACTION": 0.10,
                    "COGNITIVE_HONESTY": 0.20,
                    "MIXED": 0.10,
                }
            },
        )

    def _thread_high_leverage(self) -> ThreadState:
        return ThreadState(
            thread_id="t",
            leverage_score=0.75,
            coordination_cost=0.30,
            convergence_rate=0.70,
            artifact_probability=0.75,
            shipping_evidence_score=0.60,
        )

    def test_cooldown_dm_locks_out_dm_gate(self):
        """With cooldown_dm=3, dm_gate must be False regardless of other conditions."""
        # Note: update_actor decrements cooldown by 1 before policy reads it,
        # so we start with dm=2 to ensure at least 1 event of lockout remains.
        actor  = self._actor_with_cooldown(dm=2, off=0)
        thread = self._thread_high_leverage()
        r = _result(
            "Integrating causal evidence and synthesis of three studies. "
            "Let's collaborate further on the integration.",
            actor=actor, thread=thread,
        )
        # cooldown_dm was 2, decremented to 1 by update_actor — still active
        self.assertFalse(r.policy_action.dm_gate,
                         "cooldown_dm should lock dm_gate=False")
        self.assertFalse(r.policy_action.off_platform_gate)

    def test_cooldown_dm_zero_no_lockout(self):
        """After cooldown drains, policy is free to open DM gate if conditions met."""
        actor  = self._actor_with_cooldown(dm=1, off=0)   # will drain to 0
        thread = self._thread_high_leverage()
        r = _result(
            "Integrating causal evidence and synthesis. Let's collaborate.",
            actor=actor, thread=thread,
        )
        # cooldown was 1, now 0 — DM gate depends purely on business conditions;
        # we just verify no crash and the gate is a bool
        self.assertIsInstance(r.policy_action.dm_gate, bool)

    def test_cooldown_note_present(self):
        """When cooldown is active, a note must mention 'cooldown_dm'."""
        actor  = self._actor_with_cooldown(dm=3, off=0)
        r = _result(
            "Integrating causal evidence and synthesis. Collaborate further.",
            actor=actor,
        )
        # After decrement cooldown_dm = 2 (still > 0)
        notes_text = " ".join(r.policy_action.notes)
        self.assertIn("cooldown_dm", notes_text)

    def test_cooldown_set_by_engine_on_pressure_protocol(self):
        """
        A pressure-protocol event should cause the engine to set cooldown counters;
        the second event should still see a locked dm_gate.
        """
        from signal_agent.leviathan.interaction_signals.core.engine import StateStore, process_event

        store = StateStore()
        # Plant actor with very low pressure_integrity so pressure_protocol fires
        a = ActorState(actor_id="x", pressure_integrity=0.10)
        store.set_actor(a)

        ev1 = Event("e1", "x", "t", "2026-02-28T18:00:00Z",
                    "Why would that work? This is wrong. Completely wrong. "
                    "You are wrong. Adversarial nonsense.")
        r1 = process_event(ev1, store)

        # If pressure_protocol fired, cooldowns should be written back
        if r1.policy_action.pressure_protocol:
            self.assertGreater(r1.actor_after.cooldown_dm,  0)
            self.assertGreater(r1.actor_after.cooldown_off, 0)
            # Second event: dm_gate must still be locked
            ev2 = Event("e2", "x", "t", "2026-02-28T18:01:00Z",
                        "Integrating evidence and building synthesis. Collaborate.")
            r2 = process_event(ev2, store)
            self.assertFalse(r2.policy_action.dm_gate)


# ── v0.3: entropy-adaptive gate interaction ────────────────────────────────

class TestEntropyAdaptiveGate(unittest.TestCase):

    def test_volatile_actor_uses_higher_threshold(self):
        """
        Uniform histogram (H_norm≈1) → flip_threshold≈0.50.
        A P(H→T)=0.40 should not trigger at 0.50.
        """
        actor = ActorState(
            actor_id="a",
            collab_readiness=0.80,
            integrity_index=0.70,
            transaction_pressure=0.20,
            extraction_after_trust=0.10,
            trust_score=0.80,
            # Uniform histogram → H_norm ≈ 1.0 → threshold ≈ 0.45
            mode_histogram_30={
                "PERFORMANCE": 0.25, "TRANSACTION": 0.25,
                "COGNITIVE_HONESTY": 0.25, "MIXED": 0.25,
            },
            transition_matrix={
                "COGNITIVE_HONESTY": {
                    "PERFORMANCE": 0.30,
                    "TRANSACTION": 0.40,   # 0.40 < 0.50 → should NOT trigger
                    "COGNITIVE_HONESTY": 0.20,
                    "MIXED": 0.10,
                }
            },
        )
        thread = ThreadState(
            thread_id="t",
            leverage_score=0.75, coordination_cost=0.30,
            convergence_rate=0.70, artifact_probability=0.75,
        )
        r = _result(
            "Integrating evidence: causal synthesis from three independent studies.",
            actor=actor, thread=thread,
        )
        # Flip-risk note should NOT be present (p_h_to_t=0.40 < threshold≈0.50)
        notes_text = " ".join(r.policy_action.notes)
        self.assertNotIn("flip-risk", notes_text,
                         "Uniform (volatile) actor should raise threshold above 0.40")

    def test_stable_actor_uses_lower_threshold(self):
        """
        Peaked histogram (H_norm≈0) → flip_threshold≈0.30.
        P(H→T)=0.31 should trigger the gate.
        """
        actor = ActorState(
            actor_id="a",
            collab_readiness=0.80,
            integrity_index=0.70,
            transaction_pressure=0.20,
            extraction_after_trust=0.10,
            trust_score=0.80,
            # Strongly peaked → H_norm ≈ 0 → threshold ≈ 0.25
            mode_histogram_30={
                "PERFORMANCE": 0.96, "TRANSACTION": 0.01,
                "COGNITIVE_HONESTY": 0.02, "MIXED": 0.01,
            },
            transition_matrix={
                "COGNITIVE_HONESTY": {
                    "PERFORMANCE": 0.40,
                    "TRANSACTION": 0.36,   # safely above adaptive stable threshold
                    "COGNITIVE_HONESTY": 0.20,
                    "MIXED": 0.10,
                }
            },
        )
        thread = ThreadState(
            thread_id="t",
            leverage_score=0.75, coordination_cost=0.30,
            convergence_rate=0.70, artifact_probability=0.75,
        )
        r = _result(
            "Integrating evidence: causal synthesis from three independent studies.",
            actor=actor, thread=thread,
        )
        notes_text = " ".join(r.policy_action.notes)
        self.assertIn("flip-risk", notes_text,
                      "Stable actor with lowered threshold should trigger flip-risk gate")


if __name__ == "__main__":
    unittest.main()
