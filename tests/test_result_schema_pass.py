"""
tests/test_result_schema_pass.py
"""
import unittest

from shared.result_schemas import (
    make_coherence_result,
    make_route_result,
    make_reaction_result,
    make_health_transition_entry,
)

class TestResultSchemaPass(unittest.TestCase):
    def test_make_coherence_result(self):
        res = make_coherence_result(
            artifact_id="art1",
            expected_state="routed",
            registry_found=False,
            registry_state=None,
            registry_path=None,
            filesystem_exists=False,
            coherent=False,
            reason="missing",
        )
        self.assertEqual(res["artifact_id"], "art1")
        self.assertFalse(res["coherent"])
        
    def test_make_route_result(self):
        res = make_route_result(
            status="ok",
            artifact_id="art1",
            error=None,
            details={"score": 0.99}
        )
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["details"]["score"], 0.99)
        self.assertIsNone(res["coherence"])
        
    def test_make_reaction_result(self):
        res = make_reaction_result(
            event_type="Promotion",
            artifact_id="art1",
            action="route",
            status="ok",
            details={"extra": True}
        )
        self.assertEqual(res["event_type"], "Promotion")
        self.assertTrue(res["details"]["extra"])
        
    def test_make_health_transition_entry(self):
        res = make_health_transition_entry(
            source="routing_log",
            artifact_id="art1",
            status="fail",
            error="bad",
        )
        self.assertEqual(res["source"], "routing_log")
        self.assertEqual(res["error"], "bad")
        
if __name__ == "__main__":
    unittest.main()
