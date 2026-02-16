import unittest
from typing import Any, Dict, List
from app.utils.policy_engine import resolve, EvalResult
from app.utils.dsl import predicate_eval, DSLViolation

class TestDSL(unittest.TestCase):
    def test_basic_ops(self):
        env = {"action": {"x": 10}, "snapshot": {}, "context": {}}
        self.assertTrue(predicate_eval({"op": "EQ", "left": "action.x", "right": 10}, env["action"], {}, {}))
        self.assertTrue(predicate_eval({"op": "GT", "left": "action.x", "right": 5}, env["action"], {}, {}))
        self.assertFalse(predicate_eval({"op": "LT", "left": "action.x", "right": 5}, env["action"], {}, {}))

    def test_logic_ops(self):
        env = {"action": {"x": 10, "y": 20}, "snapshot": {}, "context": {}}
        pred = {
            "op": "AND",
            "args": [
                {"op": "EQ", "left": "action.x", "right": 10},
                {"op": "GT", "left": "action.y", "right": 15}
            ]
        }
        self.assertTrue(predicate_eval(pred, env["action"], {}, {}))

    def test_regex_matches(self):
        env = {"action": {"text": "hello world"}, "snapshot": {}, "context": {}}
        self.assertTrue(predicate_eval({"op": "MATCHES", "left": "action.text", "right": r"hello"}, env["action"], {}, {}))
        self.assertFalse(predicate_eval({"op": "MATCHES", "left": "action.text", "right": r"^bye"}, env["action"], {}, {}))

    def test_dsl_violation_bad_op(self):
        with self.assertRaises(DSLViolation):
            predicate_eval({"op": "BAD_OP"}, {}, {}, {})

    def test_regex_safety(self):
        # Disallowed token
        with self.assertRaises(DSLViolation):
            predicate_eval({"op": "MATCHES", "left": "action.text", "right": r"(?="}, {}, {}, {})


class TestPolicyEngine(unittest.TestCase):
    def setUp(self):
        self.context = {"domain": "content"}
        self.snapshot = {"metrics": {"cost": 1.0}}
        self.action = {}

    def test_scope_priority(self):
        # GLOBAL DENY vs DOMAIN ALLOW -> GLOBAL DENY wins? 
        # Wait, typically resolve aggregates. 
        # DENY beats ALLOW universally in the implementation.
        # Check implementation: "Early exit on deny"
        packs = [
            {
                "pack_metadata": {"scope": "GLOBAL", "name": "global"},
                "constraint_rules": [{"constraint_id": "G1", "rule_type": "DENY"}]
            },
            {
                "pack_metadata": {"scope": "DOMAIN", "name": "domain"},
                "constraint_rules": [{"constraint_id": "D1", "rule_type": "ALLOW"}]
            }
        ]
        res = resolve(self.action, self.snapshot, packs, self.context)
        self.assertEqual(res.decision, "DENY")
        self.assertIn("G1", res.matched_constraints)

    def test_limit_aggregation(self):
        # Two limits on same metric -> min wins
        packs = [
            {
                "pack_metadata": {"scope": "GLOBAL"},
                "constraint_rules": [{
                    "constraint_id": "L1", "rule_type": "LIMIT",
                    "parameters": {"metric_id": "cost", "selector_key": "any", "max_value": 5.0}
                }]
            },
            {
                "pack_metadata": {"scope": "SESSION"},
                "constraint_rules": [{
                    "constraint_id": "L2", "rule_type": "LIMIT",
                    "parameters": {"metric_id": "cost", "selector_key": "any", "max_value": 2.0}
                }]
            }
        ]
        # Current cost is 1.0. Both limits (5.0 and 2.0) pass.
        # But effectve limit should be recorded as 2.0
        res = resolve(self.action, self.snapshot, packs, self.context)
        self.assertEqual(res.decision, "ALLOW")
        # Check if limits_applied contains the min limit
        effective = res.limits_applied[0] if res.limits_applied else {}
        self.assertEqual(effective.get("max_value"), 2.0)
        self.assertEqual(effective.get("constraint_id"), "L2")

        # Now simulate violation
        self.snapshot["metrics"]["cost"] = 3.0
        res = resolve(self.action, self.snapshot, packs, self.context)
        self.assertEqual(res.decision, "DENY")
        self.assertEqual(res.reason, "LIMIT_EXCEEDED")
        self.assertIn("L2", res.matched_constraints)

    def test_emergency_override(self):
        # EMERGENCY pack with ALLOW should override if enabled
        packs = [
            {
                "pack_metadata": {"scope": "GLOBAL"},
                "constraint_rules": [{"constraint_id": "G1", "rule_type": "DENY"}]
            },
            {
                "pack_metadata": {"scope": "EMERGENCY"},
                "constraint_rules": [{"constraint_id": "E1", "rule_type": "ALLOW"}]
            }
        ]
        # Disabled by default
        res = resolve(self.action, self.snapshot, packs, self.context)
        self.assertEqual(res.decision, "DENY")

        # Enabled
        ctx = {"domain": "content", "emergency_override_enabled": True}
        res = resolve(self.action, self.snapshot, packs, ctx)
        self.assertEqual(res.decision, "ALLOW")
        self.assertEqual(res.reason, "EMERGENCY_OVERRIDE")

if __name__ == "__main__":
    unittest.main()
