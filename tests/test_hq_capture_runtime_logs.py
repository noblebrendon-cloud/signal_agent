from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import app.hq.capture as capture_pkg
from app.hq.capture import decay, instability, stress


@pytest.fixture
def capture_dir(tmp_path: Path) -> Path:
    path = tmp_path / "capture"
    path.mkdir()
    return path


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_decay_log_uses_governed_append_and_fails_closed(capture_dir: Path) -> None:
    entry = {
        "timestamp_utc": "2026-05-21T00:00:00Z",
        "stage1_moved": ["raw_old.md"],
        "stage2_moved": [],
        "status": "ok",
    }
    log_path = capture_dir / "decay_log.jsonl"

    with patch.object(decay, "append_jsonl_atomic", wraps=decay.append_jsonl_atomic) as append:
        decay._append_decay_log(capture_dir, entry)

    append.assert_called_once()
    assert Path(append.call_args.args[0]) == log_path
    assert _read_jsonl(log_path) == [entry]

    with patch.object(decay, "append_jsonl_atomic", side_effect=OSError("append failed")):
        with pytest.raises(RuntimeError, match="Failed to append decay log"):
            decay._append_decay_log(capture_dir, entry)


def test_instability_log_uses_governed_append_and_fails_closed(capture_dir: Path) -> None:
    entry = {
        "timestamp_utc": "2026-05-21T00:00:00Z",
        "utc_day": "2026-05-21",
        "flags": [{"topic_id": "topic-001"}],
    }
    log_path = capture_dir / "instability_log.jsonl"

    with patch.object(
        instability,
        "append_jsonl_atomic",
        wraps=instability.append_jsonl_atomic,
    ) as append:
        instability._append_instability_log(capture_dir, entry)

    append.assert_called_once()
    assert Path(append.call_args.args[0]) == log_path
    assert _read_jsonl(log_path) == [entry]

    with patch.object(instability, "append_jsonl_atomic", side_effect=OSError("append failed")):
        with pytest.raises(RuntimeError, match="Failed to append instability log"):
            instability._append_instability_log(capture_dir, entry)


def test_instability_state_uses_atomic_write_and_fails_closed(capture_dir: Path) -> None:
    state_path = capture_dir / "instability_state.json"
    state = {
        "updated_utc": "2026-05-21T00:00:00Z",
        "topics": {"topic-001": {"last_seen_utc": "2026-05-21T00:00:00Z"}},
    }

    with patch.object(
        instability,
        "atomic_write_text",
        wraps=instability.atomic_write_text,
    ) as write:
        instability._save_state(state_path, state)

    write.assert_called_once()
    assert Path(write.call_args.args[0]) == state_path
    assert json.loads(state_path.read_text(encoding="utf-8")) == state

    with patch.object(instability, "atomic_write_text", side_effect=OSError("write failed")):
        with pytest.raises(RuntimeError, match="Failed to persist instability state"):
            instability._save_state(state_path, state)


def test_capture_contract_marks_runtime_boundaries_and_stress_diagnostics() -> None:
    assert "raw" in capture_pkg.DIRECTORY_LIFECYCLE_CONTRACT
    assert "hq_curation" in capture_pkg.BOUNDARY_CONTRACT
    assert "stress" in capture_pkg.DIAGNOSTIC_ONLY_MODULES
    assert "stress" not in capture_pkg.PROMOTED_RUNTIME_SURFACE
    assert stress.DIAGNOSTIC_ONLY is True
