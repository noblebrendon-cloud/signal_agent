from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from shared import events, state_registry


def test_record_state_uses_governed_append_under_temp_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(tmp_path))
    expected_registry = tmp_path / "data" / "state" / "artifact_registry.jsonl"

    with patch.object(
        state_registry,
        "append_jsonl_atomic",
        wraps=state_registry.append_jsonl_atomic,
    ) as append:
        state_registry.record_state("artifact-001", "captured", "incoming/raw.md")

    append.assert_called_once()
    assert Path(append.call_args.args[0]) == expected_registry
    assert expected_registry.exists()
    assert json.loads(expected_registry.read_text(encoding="utf-8").strip()) == {
        "artifact_id": "artifact-001",
        "state": "captured",
        "path": "incoming/raw.md",
        "updated_at": append.call_args.args[1]["updated_at"],
    }


def test_emit_event_uses_governed_append_and_remains_best_effort(
    tmp_path: Path,
) -> None:
    event_log = tmp_path / "event_log.jsonl"

    with patch.object(events, "append_jsonl_atomic", wraps=events.append_jsonl_atomic) as append:
        events.emit_event(
            "PromotionSucceeded",
            "bundle-001",
            {"bundle_path": tmp_path / "bundle.md"},
            event_log_path=event_log,
        )

    append.assert_called_once()
    assert Path(append.call_args.args[0]) == event_log

    row = json.loads(event_log.read_text(encoding="utf-8").strip())
    assert row["event_type"] == "PromotionSucceeded"
    assert row["artifact_id"] == "bundle-001"
    assert row["payload"]["bundle_path"] == str(tmp_path / "bundle.md")

    with patch.object(events, "append_jsonl_atomic", side_effect=OSError("append failed")):
        events.emit_event("PromotionFailed", "bundle-002", {}, event_log_path=event_log)
