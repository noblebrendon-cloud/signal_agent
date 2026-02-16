import unittest
from app.utils.reprojection import ConstraintPack, compute_delta, ArtifactState

class TestReprojectionV2(unittest.TestCase):
    def test_v2_deny_rule_triggers_fail(self):
        state = ArtifactState(
            sections={}, claims=[], word_count=10, 
            full_text_lower="this text contains badword"
        )
        pack = ConstraintPack(
            scope="test",
            constraint_rules=[{
                "constraint_id": "C1",
                "rule_type": "DENY",
                "trigger": {"capability_id": "content:text"},
                "predicate": {
                    "op": "MATCHES",
                    "left": "snapshot.content",
                    "right": "badword"
                }
            }]
        )
        report = compute_delta(state, pack, "ctx", "path", 0.75)
        self.assertEqual(report.status, "FAIL")
        self.assertTrue(any("C1" in v for v in report.hard_violations))

    def test_v2_limit_rule_enforced(self):
        state = ArtifactState(
            sections={}, claims=[], word_count=100, 
            full_text_lower="clean text"
        )
        pack = ConstraintPack(
            scope="test",
            constraint_rules=[{
                "constraint_id": "L1",
                "rule_type": "LIMIT",
                "trigger": {"capability_id": "content:text"},
                "predicate": {}, 
                "parameters": {"max_value": 50, "metric_id": "word_count", "selector_key": "any"}
            }]
        )
        report = compute_delta(state, pack, "ctx", "path", 0.75)
        # LIMITs are enforced if metrics are populated
        self.assertEqual(report.status, "FAIL")
        self.assertTrue(any("LIMIT_EXCEEDED" in v for v in report.hard_violations))

    def test_v2_wrong_capability_ignored(self):
        state = ArtifactState(
            sections={}, claims=[], word_count=10, 
            full_text_lower="badword"
        )
        pack = ConstraintPack(
            scope="test",
            constraint_rules=[{
                "constraint_id": "C2",
                "rule_type": "DENY",
                "trigger": {"capability_id": "sys:exec"}, 
                "predicate": {
                    "op": "MATCHES",
                    "left": "snapshot.content",
                    "right": "badword"
                }
            }]
        )
        report = compute_delta(state, pack, "ctx", "path", 0.75)
        self.assertEqual(report.status, "PASS")

if __name__ == "__main__":
    unittest.main()
