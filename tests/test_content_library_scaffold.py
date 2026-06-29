from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_tool():
    tool_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "operator"
        / "content_library"
        / "tools"
        / "new_content_event.py"
    )
    spec = importlib.util.spec_from_file_location("new_content_event", tool_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_new_content_event_creates_standard_files_and_index_row(tmp_path: Path) -> None:
    tool = _load_tool()
    root = tmp_path / "content_library"

    message = tool.create_or_reopen_event(
        "EVT-2026-06-29-test-event",
        "2026",
        "Test Event",
        library_root_path=root,
    )

    event_dir = root / "events" / "2026" / "EVT-2026-06-29-test-event"
    assert "Created new event EVT-2026-06-29-test-event" in message
    assert (event_dir / "00_EVENT.md").exists()
    assert (event_dir / "01_EVIDENCE.md").exists()
    assert (event_dir / "02_TEACHING_ATOMS.md").exists()
    assert (event_dir / "03_DERIVATIVE_BACKLOG.md").exists()
    assert (event_dir / "04_PUBLICATION_LEDGER.md").exists()
    index = (root / "CONTENT_LIBRARY_INDEX.md").read_text(encoding="utf-8")
    assert "`EVT-2026-06-29-test-event`" in index
    assert "[00_EVENT.md](events/2026/EVT-2026-06-29-test-event/00_EVENT.md)" in index


def test_new_content_event_reopens_without_overwriting_or_duplicate_index(tmp_path: Path) -> None:
    tool = _load_tool()
    root = tmp_path / "content_library"
    event_id = "EVT-2026-06-29-repeatable"

    tool.create_or_reopen_event(event_id, "2026", "Repeatable", library_root_path=root)
    event_dir = root / "events" / "2026" / event_id
    event_file = event_dir / "00_EVENT.md"
    event_file.write_text("operator evidence stays intact\n", encoding="utf-8")
    (event_dir / "01_EVIDENCE.md").unlink()

    message = tool.create_or_reopen_event(event_id, "2026", "Changed Title", library_root_path=root)

    assert "Reopened existing event EVT-2026-06-29-repeatable" in message
    assert event_file.read_text(encoding="utf-8") == "operator evidence stays intact\n"
    assert (event_dir / "01_EVIDENCE.md").exists()
    index = (root / "CONTENT_LIBRARY_INDEX.md").read_text(encoding="utf-8")
    assert index.count(f"`{event_id}`") == 1

