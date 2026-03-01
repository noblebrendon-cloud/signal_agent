"""Tests for core/phase_space.py -- 4D interaction dynamics."""
import unittest
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent.parent.parent))

from signal_agent.leviathan.interaction_signals.core.types import PhasePoint, ActorState, ThreadState
from signal_agent.leviathan.interaction_signals.core.phase_space import (
    phase_point, phase_velocity, region_tag
)

class TestPhaseSpace(unittest.TestCase):
    def test_phase_point_extraction(self):
        actor = ActorState(actor_id="a", trust_score=0.8, pressure_integrity=0.6)
        thread = ThreadState(thread_id="t", leverage_score=0.9)
        pt = phase_point(actor, thread, V=0.3)
        self.assertAlmostEqual(pt.T, 0.8)
        self.assertAlmostEqual(pt.Σ, 0.6)
        self.assertAlmostEqual(pt.V, 0.3)
        self.assertAlmostEqual(pt.Λ, 0.9)

    def test_velocity_computation(self):
        pt1 = PhasePoint(T=0.5, Σ=0.5, V=0.5, Λ=0.5)
        pt2 = PhasePoint(T=0.6, Σ=0.4, V=0.5, Λ=0.5)
        vel = phase_velocity(pt1, pt2)
        self.assertAlmostEqual(vel.dT, 0.1)
        self.assertAlmostEqual(vel.dΣ, -0.1)
        self.assertAlmostEqual(vel.dV, 0.0)
        self.assertAlmostEqual(vel.dΛ, 0.0)
        self.assertAlmostEqual(vel.norm_l2, (0.1**2 + (-0.1)**2)**0.5)

    def test_velocity_from_none(self):
        pt = PhasePoint(T=0.5, Σ=0.5, V=0.5, Λ=0.5)
        vel = phase_velocity(None, pt)
        self.assertEqual(vel.norm_l2, 0.0)

    def test_region_tags(self):
        self.assertEqual(region_tag(PhasePoint(0,0,V=0.40,Λ=0.70)), "stable_high_leverage")
        self.assertEqual(region_tag(PhasePoint(0,0,V=0.40,Λ=0.50)), "stable_low_leverage")
        self.assertEqual(region_tag(PhasePoint(0,0,V=0.50,Λ=0.70)), "unstable_high_leverage")
        self.assertEqual(region_tag(PhasePoint(0,0,V=0.50,Λ=0.50)), "unstable_low_leverage")

if __name__ == "__main__":
    unittest.main()
