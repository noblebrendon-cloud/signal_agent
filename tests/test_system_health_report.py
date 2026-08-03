"""
tests/test_system_health_report.py
"""
import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

from shared.health import system_health_report
from shared.inspect import health_status

class TestSystemHealthReport(unittest.TestCase):
    def test_health_report_counts_and_unknowns(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            reg_path = tmp / "registry.jsonl"
            evt_path = tmp / "events.jsonl"
            ckpt_path = tmp / "checkpoint.json"
            
            # 1. State counting: two promoted, one routed, one random unknown
            reg_lines = [
                {"artifact_id": "art1", "state": "captured"}, # Overwritten
                {"artifact_id": "art1", "state": "promoted"}, # Latest
                {"artifact_id": "art2", "state": "routed"},
                {"artifact_id": "art3", "state": "archived"} # Unknown
            ]
            
            reg_path.write_text(
                "\n".join(json.dumps(r) for r in reg_lines) + "\n",
                encoding="utf-8"
            )
            
            # Events
            evt_lines = [
                {
                    "event_type": "PromotionSucceeded",
                    "artifact_id": "art1",
                    "timestamp": "2026-03-21T00:00:00Z",
                    "payload": {}
                },
                {
                    "event_type": "CoherenceCheckFailed",
                    "artifact_id": "artX",
                    "timestamp": "2026-03-21T00:01:00Z",
                    "payload": {"reason": "missing"}
                }
            ]
            evt_path.write_text(
                "\n".join(json.dumps(e) for e in evt_lines) + "\n",
                encoding="utf-8"
            )
            
            # Checkpoints (no processed events)
            ckpt_path.write_text(json.dumps({"processed_event_ids": []}), encoding="utf-8")
            
            # Mock the routing log internally for transition failures
            rout_log = tmp / "routing.jsonl"
            rout_log.write_text(json.dumps({
                "status": "fail",
                "bundle_filename": "art_fail",
                "error": "coherence"
            }) + "\n", encoding="utf-8")
            
            with patch("shared.health._default_routing_log_path", return_value=rout_log):
                report = system_health_report(
                    registry_path=reg_path,
                    event_log_path=evt_path,
                    checkpoint_path=ckpt_path
                )
                
                summs = report["summary"]
                counts = summs["artifact_counts_by_state"]
                
                # Check metrics structure
                self.assertEqual(counts["promoted"], 1)
                self.assertEqual(counts["routed"], 1)
                self.assertEqual(counts["captured"], 0)
                self.assertEqual(counts["unknown"], 1)
                
                # Coherence Failures
                self.assertEqual(summs["recent_coherence_failure_count"], 1)
                self.assertEqual(report["recent_coherence_failures"][0]["artifact_id"], "artX")
                
                # Transitions
                self.assertEqual(summs["blocked_or_failed_transition_count"], 1)
                self.assertEqual(report["blocked_or_failed_transitions"][0]["artifact_id"], "art_fail")
                
                # Unprocessed events
                # "PromotionSucceeded" and "CoherenceCheckFailed" are unprocessed
                # Wait: 'unprocessed_events' logic inside EventReader will fetch ALL events unless filtered. 
                # health report simply returns what `iter_unprocessed_events` provides.
                self.assertEqual(summs["unprocessed_event_count"], 2)

    def test_inspect_health_wrapper(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            # Empty files do not crash
            report = health_status(
                registry_path=tmp/"missing.jsonl",
                event_log_path=tmp/"missing_evt.jsonl",
                checkpoint_path=tmp/"missing_ckpt.json"
            )
            self.assertEqual(report["summary"]["artifact_counts_by_state"]["unknown"], 0)
            self.assertEqual(report["summary"]["recent_coherence_failure_count"], 0)
            self.assertEqual(report["summary"]["unprocessed_event_count"], 0)

if __name__ == "__main__":
    unittest.main()
