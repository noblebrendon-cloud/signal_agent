import datetime
import unittest

from signal_agent.leviathan.diagnostic.stability_snapshot.policy import (
    evaluate_operation,
    get_band_for_score,
)


class TestSnapshotPolicy(unittest.TestCase):
    def test_get_band_for_score_boundaries(self):
        self.assertEqual(get_band_for_score(15), "GREEN")
        self.assertEqual(get_band_for_score(13), "GREEN")
        self.assertEqual(get_band_for_score(12), "YELLOW")
        self.assertEqual(get_band_for_score(10), "YELLOW")
        self.assertEqual(get_band_for_score(9), "ORANGE")
        self.assertEqual(get_band_for_score(6), "ORANGE")
        self.assertEqual(get_band_for_score(5), "RED")
        self.assertEqual(get_band_for_score(0), "RED")

        with self.assertRaises(ValueError):
            get_band_for_score(-1)
        with self.assertRaises(ValueError):
            get_band_for_score(16)

    def test_operation_allow_block_across_bands(self):
        self.assertTrue(evaluate_operation(13, "deployment_promotion"))
        self.assertFalse(evaluate_operation(12, "deployment_promotion"))
        self.assertFalse(evaluate_operation(9, "deployment_promotion"))
        self.assertFalse(evaluate_operation(5, "deployment_promotion"))

        self.assertTrue(evaluate_operation(12, "state_schema_migration"))
        self.assertFalse(evaluate_operation(5, "state_schema_migration"))

    def test_unknown_operation_policy(self):
        self.assertTrue(evaluate_operation(13, "unknown_operation"))
        self.assertTrue(evaluate_operation(10, "unknown_operation"))
        self.assertFalse(evaluate_operation(9, "unknown_operation"))
        self.assertFalse(evaluate_operation(5, "unknown_operation"))

    def test_override_validity(self):
        now = datetime.datetime(2026, 3, 3, 12, 0, 0, tzinfo=datetime.timezone.utc)

        valid_metadata = {
            "reason": "critical deployment recovery",
            "owner": "eng_lead",
            "utc_timestamp": "2026-03-03T10:00:00Z",
            "expiry_utc": "2026-03-03T13:00:00Z",
            "operation": "deployment_promotion",
            "band": "RED",
            "score": 5,
        }
        self.assertTrue(evaluate_operation(5, "deployment_promotion", valid_metadata, now))

        missing_field = valid_metadata.copy()
        del missing_field["reason"]
        self.assertFalse(evaluate_operation(5, "deployment_promotion", missing_field, now))

        expired = valid_metadata.copy()
        expired["expiry_utc"] = "2026-03-03T11:00:00Z"
        self.assertFalse(evaluate_operation(5, "deployment_promotion", expired, now))

        too_long = valid_metadata.copy()
        too_long["expiry_utc"] = "2026-03-03T14:30:00Z"
        self.assertFalse(evaluate_operation(5, "deployment_promotion", too_long, now))

        not_allowlisted = valid_metadata.copy()
        not_allowlisted["operation"] = "inbox_ingest"
        self.assertFalse(evaluate_operation(5, "inbox_ingest", not_allowlisted, now))


if __name__ == "__main__":
    unittest.main()
