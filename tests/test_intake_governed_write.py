from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.intake import intake
from app.utils import io_contract


@pytest.fixture
def intake_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "repo"
    data_dir = root / "data"
    intake_dir = data_dir / "intake"
    text_dir = intake_dir / "text"
    ledger = intake_dir / "intake.jsonl"
    summary = intake_dir / "INTAKE_LOG.md"

    monkeypatch.setattr(intake, "ROOT", root)
    monkeypatch.setattr(intake, "DATA_DIR", data_dir)
    monkeypatch.setattr(intake, "INTAKE_DIR", intake_dir)
    monkeypatch.setattr(intake, "INTAKE_LEDGER", ledger)
    monkeypatch.setattr(intake, "INTAKE_TEXT_DIR", text_dir)
    monkeypatch.setattr(intake, "INTAKE_SUMMARY", summary)

    return {
        "root": root,
        "ledger": ledger,
        "lock": ledger.with_suffix(".jsonl.lock"),
        "text_dir": text_dir,
    }


def _make_system(root: Path) -> intake.IntakeSystem:
    return intake.IntakeSystem(scan_roots=[root], explicit_roots=True)


def test_append_event_uses_io_contract_locking_and_preserves_jsonl_shape(
    intake_paths: dict[str, Path],
) -> None:
    system = _make_system(intake_paths["root"])
    event = {
        "event_type": "TEST_APPEND",
        "source_path": "incoming/note.txt",
        "status": "success",
        "mode": "NORMAL",
    }

    with (
        patch.object(intake, "append_jsonl_atomic", wraps=intake.append_jsonl_atomic) as mock_append,
        patch.object(io_contract, "_FileLock", wraps=io_contract._FileLock) as mock_lock,
    ):
        system.append_event(event)

    mock_append.assert_called_once()
    assert Path(mock_append.call_args.args[0]) == intake_paths["ledger"]
    assert mock_lock.call_count == 1
    assert intake_paths["lock"].exists()

    raw_lines = intake_paths["ledger"].read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 1
    assert raw_lines[0].startswith('{"timestamp":')

    written_event = json.loads(raw_lines[0])
    assert written_event["event_type"] == event["event_type"]
    assert written_event["source_path"] == event["source_path"]
    assert written_event["status"] == event["status"]
    assert written_event["mode"] == event["mode"]
    assert "timestamp" in written_event


def test_append_event_fails_closed_when_governed_write_fails(
    intake_paths: dict[str, Path],
) -> None:
    system = _make_system(intake_paths["root"])

    with patch.object(intake, "append_jsonl_atomic", side_effect=OSError("append failed")):
        with pytest.raises(RuntimeError, match="Failed to append intake ledger event"):
            system.append_event(
                {
                    "event_type": "TEST_APPEND",
                    "source_path": "incoming/note.txt",
                    "status": "error",
                }
            )

    assert not intake_paths["ledger"].exists()


def test_process_file_writes_one_valid_success_record_without_duplicate_append(
    intake_paths: dict[str, Path],
) -> None:
    source = intake_paths["root"] / "incoming" / "note.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("hello governed intake\n", encoding="utf-8")

    system = _make_system(intake_paths["root"])

    with patch.object(intake, "_safe_emit_upstream_transition"), patch.object(
        intake, "new_run_id", return_value="intake-run-001"
    ):
        system.process_file(source)

    raw_lines = intake_paths["ledger"].read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 1

    record = json.loads(raw_lines[0])
    assert record["status"] == "success"
    assert record["source_path"] == "incoming/note.txt"
    assert record["run_id"] == "intake-run-001"
    assert record["text_output_path"].startswith("text/")

    text_outputs = list(intake_paths["text_dir"].glob("*.txt"))
    assert len(text_outputs) == 1


def test_supported_input_allowlist_is_authoritative(
    intake_paths: dict[str, Path],
) -> None:
    system = _make_system(intake_paths["root"])
    supported = intake_paths["root"] / "incoming" / "note.txt"
    unsupported = intake_paths["root"] / "incoming" / "note.json"
    supported.parent.mkdir(parents=True, exist_ok=True)
    supported.write_text("hello\n", encoding="utf-8")
    unsupported.write_text('{"hello": true}\n', encoding="utf-8")

    assert intake.is_supported_input_type(supported) is True
    assert intake.is_supported_input_type(unsupported) is False

    with pytest.raises(ValueError, match=r"unsupported_input_type:\.json"):
        system.extract_text_content(unsupported)


def test_process_file_logs_unsupported_extension_explicitly(
    intake_paths: dict[str, Path],
) -> None:
    source = intake_paths["root"] / "incoming" / "note.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('{"hello": true}\n', encoding="utf-8")

    system = _make_system(intake_paths["root"])
    system.process_file(source)

    raw_lines = intake_paths["ledger"].read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 1

    record = json.loads(raw_lines[0])
    assert record["status"] == "skipped_unsupported"
    assert record["source_path"] == "incoming/note.json"
    assert record["doc_type"] == "json"
    assert record["error_message"] == "unsupported_input_type:.json"

    text_outputs = list(intake_paths["text_dir"].glob("*.txt"))
    assert text_outputs == []


def test_process_file_rejects_empty_after_sanitization(
    intake_paths: dict[str, Path],
) -> None:
    source = intake_paths["root"] / "incoming" / "empty.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("\x00\r\n\t \r\n", encoding="utf-8")

    system = _make_system(intake_paths["root"])
    system.process_file(source)

    raw_lines = intake_paths["ledger"].read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 1

    record = json.loads(raw_lines[0])
    assert record["status"] == "error"
    assert record["source_path"] == "incoming/empty.txt"
    assert record["error_message"] == "sanitization_empty_content"

    text_outputs = list(intake_paths["text_dir"].glob("*.txt"))
    assert text_outputs == []


def test_process_file_uses_batch_intake_boundary_without_capture_calls(
    intake_paths: dict[str, Path],
) -> None:
    source = intake_paths["root"] / "incoming" / "batch_note.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("batch intake note\n", encoding="utf-8")

    system = _make_system(intake_paths["root"])

    with (
        patch("app.hq.capture.capture.capture_add", side_effect=AssertionError("hq_capture boundary crossed")),
        patch.object(intake, "_safe_emit_upstream_transition"),
        patch.object(intake, "new_run_id", return_value="intake-run-boundary"),
    ):
        system.process_file(source)

    raw_lines = intake_paths["ledger"].read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 1

    record = json.loads(raw_lines[0])
    assert record["status"] == "success"
    assert record["module"] == "app.intake.intake"
    assert record["operation"] == "process_file"
