import unittest

from signal_agent.leviathan.diagnostic.stability_snapshot.policy_gate import evaluate_gate


class TestPolicyGateInvariantV1(unittest.TestCase):
    def _valid_override(self, *, score: int, band: str, operation: str, issued: str, expiry: str) -> dict:
        return {
            "reason": "break-glass for controlled recovery",
            "owner": "ops_owner",
            "utc_timestamp": issued,
            "expiry_utc": expiry,
            "operation": operation,
            "band": band,
            "score": score,
        }

    def test_band_boundaries(self):
        cases = [
            (13, "GREEN"),
            (12, "YELLOW"),
            (10, "YELLOW"),
            (9, "ORANGE"),
            (6, "ORANGE"),
            (5, "RED"),
        ]
        for score, expected_band in cases:
            with self.subTest(score=score):
                decision = evaluate_gate(score, "deployment_promotion")
                self.assertEqual(decision.band, expected_band)

    def test_deployment_promotion_blocking_by_band(self):
        self.assertTrue(evaluate_gate(13, "deployment_promotion").allow)
        self.assertFalse(evaluate_gate(12, "deployment_promotion").allow)
        self.assertFalse(evaluate_gate(9, "deployment_promotion").allow)
        self.assertFalse(evaluate_gate(5, "deployment_promotion").allow)

    def test_unknown_operation_policy(self):
        self.assertTrue(evaluate_gate(13, "unknown_operation").allow)
        self.assertTrue(evaluate_gate(12, "unknown_operation").allow)

        orange = evaluate_gate(9, "unknown_operation")
        self.assertFalse(orange.allow)
        self.assertEqual(orange.blocked_reason, "operation_not_defined_in_invariant")

        red = evaluate_gate(5, "unknown_operation")
        self.assertFalse(red.allow)
        self.assertEqual(red.blocked_reason, "operation_not_defined_in_invariant")

    def test_override_validation_constraints(self):
        now_utc = "2026-03-03T12:00:00Z"

        valid_orange = self._valid_override(
            score=9,
            band="ORANGE",
            operation="deployment_promotion",
            issued="2026-03-03T10:00:00Z",
            expiry="2026-03-03T13:00:00Z",
        )
        self.assertTrue(
            evaluate_gate(
                9,
                "deployment_promotion",
                now_utc_iso=now_utc,
                override=valid_orange,
            ).allow
        )

        yellow_override = self._valid_override(
            score=12,
            band="YELLOW",
            operation="deployment_promotion",
            issued="2026-03-03T10:00:00Z",
            expiry="2026-03-03T13:00:00Z",
        )
        self.assertFalse(
            evaluate_gate(
                12,
                "deployment_promotion",
                now_utc_iso=now_utc,
                override=yellow_override,
            ).allow
        )

        non_allowlisted = self._valid_override(
            score=5,
            band="RED",
            operation="inbox_ingest",
            issued="2026-03-03T10:00:00Z",
            expiry="2026-03-03T13:00:00Z",
        )
        self.assertFalse(
            evaluate_gate(
                5,
                "inbox_ingest",
                now_utc_iso=now_utc,
                override=non_allowlisted,
            ).allow
        )

        expired = self._valid_override(
            score=9,
            band="ORANGE",
            operation="deployment_promotion",
            issued="2026-03-03T10:00:00Z",
            expiry="2026-03-03T11:00:00Z",
        )
        self.assertFalse(
            evaluate_gate(
                9,
                "deployment_promotion",
                now_utc_iso=now_utc,
                override=expired,
            ).allow
        )

        too_long = self._valid_override(
            score=9,
            band="ORANGE",
            operation="deployment_promotion",
            issued="2026-03-03T08:00:00Z",
            expiry="2026-03-03T13:00:01Z",
        )
        self.assertFalse(
            evaluate_gate(
                9,
                "deployment_promotion",
                now_utc_iso=now_utc,
                override=too_long,
            ).allow
        )

    def test_override_requires_now_utc(self):
        override = self._valid_override(
            score=9,
            band="ORANGE",
            operation="deployment_promotion",
            issued="2026-03-03T10:00:00Z",
            expiry="2026-03-03T13:00:00Z",
        )
        self.assertFalse(evaluate_gate(9, "deployment_promotion", override=override).allow)


if __name__ == "__main__":
    unittest.main()
