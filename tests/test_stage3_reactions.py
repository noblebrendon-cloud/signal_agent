"""
tests/test_stage3_reactions.py — Unit tests for Stage 3 minimal reaction layer.

Covers:
1. read_events() filters by event_type correctly
2. Derived event_id is stable when event_id field is absent
3. iter_unprocessed_events() skips already-processed events
4. process_promotion_events(dry_run=True) returns action summaries without routing
5. process_promotion_events(dry_run=False) attempts routing for PromotionSucceeded
6. Processed events are checkpointed and not reprocessed
7. Malformed checkpoint file does not crash processing
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_event(log_path: Path, event_type: str, artifact_id: str,
                  payload: dict, timestamp: str = "2026-03-20T06:00:00Z") -> None:
    entry = {
        "event_type": event_type,
        "artifact_id": artifact_id,
        "timestamp": timestamp,
        "payload": payload,
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# 1. read_events filters by event_type
# ---------------------------------------------------------------------------

class TestReadEvents(unittest.TestCase):

    def test_read_all_events(self):
        from shared.event_reader import read_events

        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "events.jsonl"
            _write_event(log, "PromotionSucceeded", "art1", {})
            _write_event(log, "RoutingSucceeded", "art2", {})
            _write_event(log, "PromotionSucceeded", "art3", {})

            events = read_events(event_log_path=log)
            self.assertEqual(len(events), 3)

    def test_filter_by_event_type(self):
        from shared.event_reader import read_events

        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "events.jsonl"
            _write_event(log, "PromotionSucceeded", "art1", {})
            _write_event(log, "RoutingSucceeded", "art2", {})

            events = read_events(event_log_path=log, event_type="PromotionSucceeded")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["artifact_id"], "art1")

    def test_limit_returns_most_recent(self):
        from shared.event_reader import read_events

        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "events.jsonl"
            for i in range(5):
                _write_event(log, "PromotionSucceeded", f"art{i}", {},
                              timestamp=f"2026-03-20T0{i}:00:00Z")

            events = read_events(event_log_path=log, limit=2)
            self.assertEqual(len(events), 2)
            self.assertEqual(events[-1]["artifact_id"], "art4")

    def test_missing_log_returns_empty(self):
        from shared.event_reader import read_events

        result = read_events(event_log_path=Path("/nonexistent/events.jsonl"))
        self.assertEqual(result, [])

    def test_malformed_lines_skipped(self):
        from shared.event_reader import read_events

        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "events.jsonl"
            log.write_text(
                '{"event_type": "A", "artifact_id": "x", "timestamp": "t", "payload": {}}\n'
                'NOT JSON\n'
                '{"event_type": "B", "artifact_id": "y", "timestamp": "t", "payload": {}}\n',
                encoding="utf-8",
            )
            events = read_events(event_log_path=log)
            self.assertEqual(len(events), 2)


# ---------------------------------------------------------------------------
# 2. Derived event_id is stable
# ---------------------------------------------------------------------------

class TestDeriveEventId(unittest.TestCase):

    def test_stable_without_event_id_field(self):
        from shared.event_reader import _derive_event_id

        event = {
            "event_type": "PromotionSucceeded",
            "artifact_id": "art001",
            "timestamp": "2026-03-20T06:00:00Z",
            "payload": {},
        }
        id1 = _derive_event_id(event)
        id2 = _derive_event_id(event)
        self.assertEqual(id1, id2)
        self.assertEqual(len(id1), 16)

    def test_different_events_get_different_ids(self):
        from shared.event_reader import _derive_event_id

        e1 = {"event_type": "A", "artifact_id": "x", "timestamp": "t1", "payload": {}}
        e2 = {"event_type": "A", "artifact_id": "x", "timestamp": "t2", "payload": {}}
        self.assertNotEqual(_derive_event_id(e1), _derive_event_id(e2))

    def test_uses_event_id_field_if_present(self):
        from shared.event_reader import _derive_event_id

        event = {"event_id": "custom_id_abc", "event_type": "A", "artifact_id": "x"}
        self.assertEqual(_derive_event_id(event), "custom_id_abc")


# ---------------------------------------------------------------------------
# 3. iter_unprocessed_events skips processed events
# ---------------------------------------------------------------------------

class TestIterUnprocessed(unittest.TestCase):

    def test_skips_already_processed(self):
        from shared.event_reader import (
            iter_unprocessed_events, mark_event_processed, _derive_event_id,
        )

        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "events.jsonl"
            ckpt = Path(d) / "checkpoint.json"
            _write_event(log, "PromotionSucceeded", "art1", {}, "2026-01-01T00:00:00Z")
            _write_event(log, "PromotionSucceeded", "art2", {}, "2026-01-01T00:00:01Z")

            # Mark first event as processed
            events = iter_unprocessed_events(checkpoint_path=ckpt, event_log_path=log)
            first_id = _derive_event_id(events[0])
            mark_event_processed(first_id, ckpt)

            # Second call should only return art2
            remaining = iter_unprocessed_events(checkpoint_path=ckpt, event_log_path=log)
            self.assertEqual(len(remaining), 1)
            self.assertEqual(remaining[0]["artifact_id"], "art2")

    def test_empty_checkpoint_processes_all(self):
        from shared.event_reader import iter_unprocessed_events

        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "events.jsonl"
            ckpt = Path(d) / "checkpoint.json"
            _write_event(log, "PromotionSucceeded", "art1", {})
            _write_event(log, "PromotionSucceeded", "art2", {})

            events = iter_unprocessed_events(checkpoint_path=ckpt, event_log_path=log)
            self.assertEqual(len(events), 2)


# ---------------------------------------------------------------------------
# 4-5. process_promotion_events dry_run and live
# ---------------------------------------------------------------------------

class TestProcessPromotionEvents(unittest.TestCase):

    def test_dry_run_returns_summaries_without_routing(self):
        from shared.reactions import process_promotion_events

        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "events.jsonl"
            ckpt = Path(d) / "checkpoint.json"
            _write_event(log, "PromotionSucceeded", "art1",
                          {"bundle_path": "/tmp/bundle_abc.md"})

            routing_called = []

            def fake_route(**kwargs):
                routing_called.append(True)
                return {"status": "ok"}

            # route_bundle is lazily imported inside process_promotion_events,
            # so it must be patched at its actual module location.
            with patch("app.hq.capture.router.route_bundle", side_effect=fake_route):
                results = process_promotion_events(
                    event_log_path=log,
                    checkpoint_path=ckpt,
                    dry_run=True,
                )

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["status"], "dry_run")
            self.assertEqual(results[0]["action"], "route_bundle")
            self.assertEqual(len(routing_called), 0)

    def test_live_run_calls_routing(self):
        from shared.reactions import process_promotion_events

        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "events.jsonl"
            ckpt = Path(d) / "checkpoint.json"

            # Create a real bundle file so path.exists() passes
            bundle = Path(d) / "bundle_real.md"
            bundle.write_text(
                "---\nlifecycle_state: promoted\n---\n\nContent capture hashing\n",
                encoding="utf-8",
            )
            _write_event(log, "PromotionSucceeded", "art1",
                          {"bundle_path": str(bundle)})

            routing_calls = []

            def fake_route(bundle_path, **kwargs):
                routing_calls.append(str(bundle_path))
                return {"status": "ok"}

            # Patch the actual import location (lazy import inside reactions.py).
            with patch("app.hq.capture.router.route_bundle", side_effect=fake_route):
                results = process_promotion_events(
                    event_log_path=log,
                    checkpoint_path=ckpt,
                    dry_run=False,
                )

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["status"], "ok")

    def test_missing_bundle_path_returns_fail(self):
        from shared.reactions import process_promotion_events

        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "events.jsonl"
            ckpt = Path(d) / "checkpoint.json"
            _write_event(log, "PromotionSucceeded", "art1",
                          {"bundle_path": "/nonexistent/bundle.md"})

            results = process_promotion_events(
                event_log_path=log,
                checkpoint_path=ckpt,
                dry_run=False,
            )

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["status"], "fail")
            self.assertIsNotNone(results[0]["error"])


# ---------------------------------------------------------------------------
# 6. Processed events are checkpointed and not reprocessed
# ---------------------------------------------------------------------------

class TestCheckpointing(unittest.TestCase):

    def test_events_not_reprocessed_on_second_call(self):
        from shared.reactions import process_promotion_events

        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "events.jsonl"
            ckpt = Path(d) / "checkpoint.json"
            _write_event(log, "PromotionSucceeded", "art1",
                          {"bundle_path": ""})

            # First call
            r1 = process_promotion_events(
                event_log_path=log, checkpoint_path=ckpt, dry_run=True
            )
            # Second call — same event should be skipped
            r2 = process_promotion_events(
                event_log_path=log, checkpoint_path=ckpt, dry_run=True
            )

            self.assertEqual(len(r1), 1)
            self.assertEqual(len(r2), 0)


# ---------------------------------------------------------------------------
# 7. Malformed checkpoint does not crash
# ---------------------------------------------------------------------------

class TestMalformedCheckpoint(unittest.TestCase):

    def test_malformed_checkpoint_is_treated_as_empty(self):
        from shared.event_reader import iter_unprocessed_events

        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "events.jsonl"
            ckpt = Path(d) / "checkpoint.json"
            _write_event(log, "PromotionSucceeded", "art1", {})
            ckpt.write_text("NOT VALID JSON", encoding="utf-8")

            # Should not raise; treats checkpoint as empty
            try:
                events = iter_unprocessed_events(
                    checkpoint_path=ckpt, event_log_path=log
                )
                self.assertEqual(len(events), 1)
            except Exception as e:
                self.fail(f"iter_unprocessed_events raised on malformed checkpoint: {e}")


if __name__ == "__main__":
    unittest.main()
