"""Tests for CASTS closure gaps — TTL enforcement and write unification."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch


class TestTTLEnforcement(unittest.TestCase):
    """Gap A: control states must not drift indefinitely."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ["SIGNAL_AGENT_ROOT"] = self.tmpdir

        # Write state_machine.yaml with TTL-enforced control states
        config_dir = Path(self.tmpdir) / "config"
        config_dir.mkdir(parents=True)
        policies_dir = config_dir / "policies"
        policies_dir.mkdir()

        sm = {
            "version": 1,
            "states": {
                "captured": {"kind": "working", "terminal": False, "recoverable": True, "blocked": False},
                "normalized": {"kind": "working", "terminal": False, "recoverable": True, "blocked": False},
                "held": {
                    "kind": "control",
                    "terminal": False,
                    "recoverable": True,
                    "blocked": True,
                    "resume_target": "previous_non_control_state",
                    "max_duration_seconds": 86400,
                    "expiry_target": "rejected",
                },
                "failed": {
                    "kind": "control",
                    "terminal": False,
                    "recoverable": True,
                    "blocked": True,
                    "resume_target": "previous_safe_working_state",
                    "max_duration_seconds": 3600,
                    "expiry_target": "rejected",
                },
                "rejected": {"kind": "control_terminal", "terminal": True, "recoverable": False, "blocked": True},
            },
            "transitions": [
                {"from": "captured", "to": "normalized", "verb": "normalize", "gate": "intake_policy"},
                {"from": "held", "to": "captured", "verb": "constrain", "gate": "governance_gate"},
                {"from": "failed", "to": "captured", "verb": "audit", "gate": "governance_gate"},
                {
                    "from_any": ["captured", "normalized"],
                    "to": "held",
                    "verb": "constrain",
                    "gate": "governance_gate",
                },
                {
                    "from_any": ["captured", "normalized"],
                    "to": "rejected",
                    "verb": "constrain",
                    "gate": "governance_gate",
                },
            ],
            "forbidden_transitions": [],
        }

        import yaml
        (config_dir / "state_machine.yaml").write_text(
            yaml.dump(sm), encoding="utf-8"
        )
        (config_dir / "lanes.yaml").write_text(
            yaml.dump({"version": 1, "lanes": [], "reserved_spines": []}),
            encoding="utf-8",
        )

    def tearDown(self):
        os.environ.pop("SIGNAL_AGENT_ROOT", None)

    def test_held_state_expires_after_ttl(self):
        """An object held for >24h must be force-transitioned to rejected."""
        from app.hq.governance.transition_gate import validate_transition

        entered_at = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        result = validate_transition(
            current_state="held",
            next_state="captured",  # attempting resume
            lane_id=None,
            context={"entered_at": entered_at},
        )
        self.assertTrue(result["allowed"])
        self.assertEqual(result["next_state"], "rejected")
        self.assertTrue(result.get("ttl_expired"))
        self.assertEqual(result.get("forced_target"), "rejected")

    def test_held_state_not_expired_within_ttl(self):
        """An object held for <24h proceeds with normal validation."""
        from app.hq.governance.transition_gate import validate_transition

        entered_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        result = validate_transition(
            current_state="held",
            next_state="captured",
            lane_id=None,
            context={"entered_at": entered_at},
        )
        # Should proceed to normal validation (may pass or fail on policy)
        # but NOT be TTL-forced.
        self.assertIsNone(result.get("ttl_expired"))

    def test_failed_state_expires_after_ttl(self):
        """An object failed for >1h must be force-transitioned to rejected."""
        from app.hq.governance.transition_gate import validate_transition

        entered_at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        result = validate_transition(
            current_state="failed",
            next_state="captured",
            lane_id=None,
            context={"entered_at": entered_at},
        )
        self.assertTrue(result["allowed"])
        self.assertEqual(result["next_state"], "rejected")
        self.assertTrue(result.get("ttl_expired"))

    def test_failed_state_not_expired_within_ttl(self):
        """An object failed for <1h proceeds with normal validation."""
        from app.hq.governance.transition_gate import validate_transition

        entered_at = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        result = validate_transition(
            current_state="failed",
            next_state="captured",
            lane_id=None,
            context={"entered_at": entered_at},
        )
        self.assertIsNone(result.get("ttl_expired"))

    def test_ttl_not_applied_without_entered_at(self):
        """If no entered_at in context, TTL is not enforced (safe default)."""
        from app.hq.governance.transition_gate import validate_transition

        result = validate_transition(
            current_state="held",
            next_state="captured",
            lane_id=None,
            context={},
        )
        self.assertIsNone(result.get("ttl_expired"))

    def test_ttl_not_applied_to_working_states(self):
        """Working states (captured, normalized) have no TTL enforcement."""
        from app.hq.governance.transition_gate import validate_transition

        entered_at = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        result = validate_transition(
            current_state="captured",
            next_state="normalized",
            lane_id=None,
            context={"entered_at": entered_at, "source_path": "/tmp/test"},
        )
        self.assertIsNone(result.get("ttl_expired"))

    def test_ttl_expiry_records_elapsed_seconds(self):
        """Expiry result includes elapsed_seconds for audit."""
        from app.hq.governance.transition_gate import validate_transition

        entered_at = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        result = validate_transition(
            current_state="held",
            next_state="captured",
            lane_id=None,
            context={"entered_at": entered_at},
        )
        policy = result.get("policy_result", {})
        self.assertTrue(policy.get("ttl_enforced"))
        self.assertGreater(policy.get("elapsed_seconds", 0), 86400)
        self.assertEqual(policy.get("max_duration_seconds"), 86400)


class TestActivationEventUnification(unittest.TestCase):
    """Gap B: activation_events must flow through the canonical gate ledger."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ["SIGNAL_AGENT_ROOT"] = self.tmpdir

        # Create minimal state dir for gate emit
        (Path(self.tmpdir) / "data" / "state").mkdir(parents=True)

    def tearDown(self):
        os.environ.pop("SIGNAL_AGENT_ROOT", None)

    def test_append_event_writes_to_gate_ledger(self):
        """append_event must dual-write: local ledger + canonical gate ledger."""
        from app.governor.activation_governor import append_event

        local_ledger = Path(self.tmpdir) / "data" / "state" / "activation_events.jsonl"
        gate_ledger = Path(self.tmpdir) / "data" / "state" / "transition_gate_events.jsonl"

        event = {
            "timestamp_utc": "2026-04-14T00:00:00Z",
            "event": "ENFORCE_BLOCKED",
            "scope": "test.scope",
            "reason": "test_reason",
        }
        append_event(local_ledger, event)

        # Local ledger written
        self.assertTrue(local_ledger.exists())
        local_lines = local_ledger.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(local_lines), 1)

        # Canonical gate ledger also written
        self.assertTrue(gate_ledger.exists())
        gate_lines = gate_ledger.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(gate_lines), 1)

        gate_record = json.loads(gate_lines[0])
        self.assertEqual(gate_record["event_type"], "activation_enforce_blocked")
        self.assertEqual(gate_record["module"], "app.governor.activation_governor")
        self.assertEqual(gate_record["operation"], "ENFORCE_BLOCKED")

    def test_drift_event_reaches_gate_ledger(self):
        """DRIFT_DETECTED events must also appear in the canonical ledger."""
        from app.governor.activation_governor import append_event

        local_ledger = Path(self.tmpdir) / "data" / "state" / "activation_events.jsonl"
        gate_ledger = Path(self.tmpdir) / "data" / "state" / "transition_gate_events.jsonl"

        event = {
            "timestamp_utc": "2026-04-14T00:00:00Z",
            "event": "DRIFT_DETECTED",
            "scope": "capture.intake",
            "lock_id": "lock_001",
        }
        append_event(local_ledger, event)

        gate_lines = gate_ledger.read_text(encoding="utf-8").strip().splitlines()
        gate_record = json.loads(gate_lines[0])
        self.assertEqual(gate_record["event_type"], "activation_drift_detected")

    def test_override_event_reaches_gate_ledger(self):
        """OVERRIDE_USED events must appear in the canonical ledger."""
        from app.governor.activation_governor import append_event

        local_ledger = Path(self.tmpdir) / "data" / "state" / "activation_events.jsonl"
        gate_ledger = Path(self.tmpdir) / "data" / "state" / "transition_gate_events.jsonl"

        event = {
            "timestamp_utc": "2026-04-14T00:00:00Z",
            "event": "OVERRIDE_USED",
            "scope": "capture.promote",
            "lock_id": "lock_002",
            "override_token_id": "override_abc",
        }
        append_event(local_ledger, event)

        gate_lines = gate_ledger.read_text(encoding="utf-8").strip().splitlines()
        gate_record = json.loads(gate_lines[0])
        self.assertEqual(gate_record["event_type"], "activation_override_used")
        self.assertEqual(gate_record["module"], "app.governor.activation_governor")


if __name__ == "__main__":
    unittest.main()
