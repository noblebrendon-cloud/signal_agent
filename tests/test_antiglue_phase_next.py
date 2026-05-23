"""
tests/test_antiglue_phase_next.py
"""
import unittest
import tempfile
import json
import os
import hashlib
from pathlib import Path
from unittest.mock import patch

from shared.artifact_identity import normalize_artifact_ref
from app.hq.governance import validate_transition
from shared.lifecycle import InvalidTransitionError
from shared.reconcile import reconciliation_report
from shared.inspect import artifact_truth
from app.hq.capture.router import route_bundle


class TestAntiGluePhaseNext(unittest.TestCase):
    def test_normalize_artifact_ref(self):
        # returns stable structure for filename-like refs
        ref1 = normalize_artifact_ref("test.md")
        self.assertEqual(ref1["artifact_id"], "test.md")
        self.assertTrue(ref1["looks_like_filename"])
        self.assertEqual(ref1["extension"], ".md")

        ref2 = normalize_artifact_ref("abstract_artifact")
        self.assertEqual(ref2["artifact_id"], "abstract_artifact")
        self.assertFalse(ref2["looks_like_filename"])
        self.assertIsNone(ref2["extension"])

    def test_lifecycle_transitions_via_canonical_gate(self):
        """Validate that the canonical gate enforces the state machine."""
        # promoted->routed is a defined transition (should be allowed with proper context)
        result = validate_transition(
            current_state="promoted",
            next_state="routed",
            lane_id=None,
            context={"bundle_filename": "test.md", "router_ruleset_hash": "abc123"},
        )
        self.assertTrue(result["allowed"])

        # promoted->captured is NOT a defined transition (should be rejected)
        result = validate_transition(
            current_state="promoted",
            next_state="captured",
            lane_id=None,
        )
        self.assertFalse(result["allowed"])

    def test_reconciliation_missing_fs(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            reg_path = tmp / "registry.jsonl"
            reg_path.write_text(json.dumps({
                "artifact_id": "art_1",
                "state": "promoted",
                "path": str(tmp / "missing.md")
            }) + "\n", encoding="utf-8")

            report = reconciliation_report(registry_path=reg_path, event_log_path=tmp / "events.jsonl")
            self.assertEqual(report["summary"]["missing_filesystem_artifacts"], 1)
            self.assertEqual(report["issues"][0]["issue_type"], "missing_filesystem_artifact")

    def test_reconciliation_content_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            file_path = tmp / "found.md"
            file_path.write_text("actual content", encoding="utf-8")

            expected_hash = hashlib.sha256(b"different content").hexdigest()

            reg_path = tmp / "registry.jsonl"
            reg_path.write_text(json.dumps({
                "artifact_id": "art_2",
                "state": "promoted",
                "path": str(file_path),
                "sha256": expected_hash
            }) + "\n", encoding="utf-8")

            report = reconciliation_report(registry_path=reg_path, event_log_path=tmp / "events.jsonl")
            self.assertEqual(report["summary"]["content_mismatches"], 1)
            self.assertEqual(report["issues"][0]["issue_type"], "content_mismatch")

    def test_artifact_truth(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            reg_path = tmp / "registry.jsonl"
            evt_path = tmp / "events.jsonl"

            file_path = tmp / "art.md"
            file_path.write_text("...", encoding="utf-8")

            reg_path.write_text(json.dumps({
                "artifact_id": "art.md",
                "state": "promoted",
                "path": str(file_path),
                "updated_at": "2026-03-20T00:00:00Z"
            }) + "\n", encoding="utf-8")

            evt_path.write_text(json.dumps({
                "timestamp_utc": "2026-03-20T00:00:00Z",
                "event_type": "PromotionSucceeded",
                "artifact_id": "art.md"
            }) + "\n", encoding="utf-8")

            truth = artifact_truth("art.md", registry_path=reg_path, event_log_path=evt_path)

            self.assertTrue(truth["registry"]["found"])
            self.assertEqual(truth["registry"]["state"], "promoted")
            self.assertTrue(truth["coherence"]["coherent"])
            self.assertEqual(len(truth["events"]), 1)
            self.assertTrue(truth["summary"]["coherent"])

    def test_router_invalid_transition(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            capture_dir = tmp / "capture"
            capture_dir.mkdir()
            spines_dir = tmp / "spines"

            bundle = capture_dir / "bundle.md"
            bundle.write_text("---\nlifecycle_state: promoted\n---\nbody\n", encoding="utf-8")

            # Setup registry
            reg_dir = tmp / "data" / "state"
            reg_dir.mkdir(parents=True)
            reg_path = reg_dir / "artifact_registry.jsonl"

            reg_path.write_text(json.dumps({
                "artifact_id": "bundle.md",
                "state": "captured",
                "path": str(bundle)
            }) + "\n", encoding="utf-8")

            with patch.dict("os.environ", {"SIGNAL_AGENT_ROOT": str(tmp)}):
                route_bundle(bundle_path=bundle, capture_dir=capture_dir, spines_dir=spines_dir, dry_run=False)

                # Check registry
                lines = reg_path.read_text(encoding="utf-8").strip().split("\n")
                # Captured state should not have advanced to routed since captured->routed is unsupported
                self.assertEqual(len(lines), 1)
                entry = json.loads(lines[-1])
                self.assertEqual(entry["state"], "captured")

if __name__ == "__main__":
    unittest.main()
