from __future__ import annotations

import json
from pathlib import Path

from app.utils.io_contract import append_jsonl_atomic_with_factory


def test_append_jsonl_atomic_with_factory_reads_locked_handle_and_returns_record(
    tmp_path: Path,
) -> None:
    jsonl_path = tmp_path / "events.jsonl"
    existing_record = {"record_id": "existing", "event_index": 0}
    jsonl_path.write_text(json.dumps(existing_record) + "\n", encoding="utf-8")

    appended_record = {"record_id": "appended", "event_index": 1}
    observed: dict[str, object] = {}

    def record_factory(handle) -> dict:
        observed["handle_path"] = Path(handle.name)
        observed["handle_closed"] = handle.closed
        handle.seek(0)
        observed["existing_rows"] = [
            json.loads(line)
            for line in handle.read().decode("utf-8").splitlines()
            if line.strip()
        ]
        return appended_record

    returned_record = append_jsonl_atomic_with_factory(jsonl_path, record_factory)

    rows = [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert observed == {
        "handle_path": jsonl_path,
        "handle_closed": False,
        "existing_rows": [existing_record],
    }
    assert jsonl_path.with_suffix(".jsonl.lock").exists()
    assert returned_record is appended_record
    assert rows == [existing_record, returned_record]
