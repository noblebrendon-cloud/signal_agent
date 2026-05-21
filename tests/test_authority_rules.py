"""
tests/test_authority_rules.py
"""
import unittest
import tempfile
import json
from pathlib import Path

from shared.authority import evaluate_authority, check_preconditions_for_routing
from shared.result_schemas import make_coherence_result


ROUTING_LANE = "content_publishing"
ROUTING_CONTEXT = {
    "bundle_filename": "bundle_test.md",
    "router_ruleset_hash": "ruleset_sha256",
}


class TestAuthorityRules(unittest.TestCase):

    def test_coherence_failure_blocks_routing(self):
        coh = make_coherence_result("art_1", "promoted", False, None, None, False, False, "missing")
        result = evaluate_authority(
            artifact_id="art_1",
            expected_state="promoted",
            current_state="promoted",
            target_state="routed",
            registry_entry={"state": "promoted"},
            coherence_result=coh,
            recent_events=[{"event_type": "Progress"}],
            path_hint="whatever"
        )
        self.assertFalse(result["allowed"])
        self.assertEqual(result["authoritative_source"], "coherence_guard")

    def test_invalid_lifecycle_transition_blocks(self):
        coh = make_coherence_result("art_1", "promoted", True, "promoted", "/test", True, True, "coherent")
        result = evaluate_authority(
            artifact_id="art_1",
            expected_state="promoted",
            current_state="promoted",
            target_state="promoted",  # invalid: cannot transition to itself
            registry_entry={"state": "promoted"},
            coherence_result=coh,
            recent_events=None,
            path_hint=None
        )
        self.assertFalse(result["allowed"])
        self.assertEqual(result["authoritative_source"], "lifecycle_rules")
        self.assertEqual(result["blocking_reason"], "transition_not_defined:promoted->promoted")

    def test_missing_routing_context_fails_closed(self):
        coh = make_coherence_result("art_1", "promoted", True, "promoted", "/test", True, True, "coherent")
        result = evaluate_authority(
            artifact_id="art_1",
            expected_state="promoted",
            current_state="promoted",
            target_state="routed",
            transition_lane_id=ROUTING_LANE,
            registry_entry={"state": "promoted"},
            coherence_result=coh,
        )
        self.assertFalse(result["allowed"])
        self.assertEqual(result["authoritative_source"], "lifecycle_rules")
        self.assertIn("bundle_reference_present", result["blocking_reason"])
        self.assertIn("router_ruleset_hash_present", result["blocking_reason"])

    def test_matching_registry_allows_routing(self):
        coh = make_coherence_result("art_1", "promoted", True, "promoted", "/test", True, True, "coherent")
        result = evaluate_authority(
            artifact_id="art_1",
            expected_state="promoted",
            current_state="promoted",
            target_state="routed", # valid transition
            transition_lane_id=ROUTING_LANE,
            transition_context=ROUTING_CONTEXT,
            registry_entry={"state": "promoted"},
            coherence_result=coh,
            recent_events=None,
            path_hint=None
        )
        self.assertTrue(result["allowed"])
        self.assertEqual(result["authoritative_source"], "state_registry")

    def test_registry_mismatch_blocks_routing(self):
        coh = make_coherence_result("art_1", "promoted", True, "captured", "/test", True, True, "coherent")
        result = evaluate_authority(
            artifact_id="art_1",
            expected_state="promoted",
            current_state="captured",
            target_state="routed", # "captured" to "routed" is invalid, wait, "captured"->"routed" is invalid transition!
            registry_entry={"state": "captured"},
            coherence_result=coh,
            recent_events=None,
            path_hint=None
        )
        self.assertFalse(result["allowed"])
        self.assertEqual(result["authoritative_source"], "lifecycle_rules")

    def test_registry_mismatch_blocks_routing_on_valid_transition(self):
        coh = make_coherence_result("art_1", "promoted", True, "captured", "/test", True, True, "coherent")
        result = evaluate_authority(
            artifact_id="art_1",
            expected_state="promoted",
            current_state="constrained",
            target_state="promoted",
            transition_lane_id="content_publishing",
            transition_context={
                "cluster_id": "cluster-001",
                "bundle_filename": "bundle_test.md",
                "candidate_cluster_members": ["raw_001.md"],
            },
            registry_entry={"state": "constrained"},
            coherence_result=coh,
            recent_events=None,
            path_hint=None
        )
        # Transition passes "constrained" -> "promoted".
        # Now registry_entry["state"] (constrained) != expected_state (promoted).
        # Blocks!
        self.assertFalse(result["allowed"])
        self.assertEqual(result["authoritative_source"], "state_registry")
        self.assertEqual(result["blocking_reason"], "state_mismatch")

    def test_events_alone_do_not_authorize(self):
        result = evaluate_authority(
            artifact_id="art_unknown",
            expected_state="promoted",
            current_state=None,
            target_state=None,
            registry_entry=None,
            coherence_result=None,
            recent_events=[{"event_type": "PromotionSucceeded"}],
            path_hint=None
        )
        self.assertFalse(result["allowed"])
        self.assertEqual(result["authoritative_source"], "default_conservative")
        
    def test_check_preconditions_helper(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            reg_path = tmp / "registry.jsonl"
            evt_path = tmp / "events.jsonl"
            
            # Setup mismatch
            reg_path.write_text(json.dumps({"artifact_id": "artx", "state": "captured"}) + "\n", encoding="utf-8")
            
            res = check_preconditions_for_routing(
                "artx", 
                expected_state="promoted", 
                target_state="routed",  # "captured" -> "routed" will fail lifecycle transition
                registry_path=reg_path, 
                event_log_path=evt_path
            )
            
            self.assertFalse(res["authority"]["allowed"])
            self.assertEqual(res["authority"]["authoritative_source"], "coherence_guard") # Coherence is checked FIRST in authority logic, so it fails on coherence_guard because missing path!
            
if __name__ == "__main__":
    unittest.main()
