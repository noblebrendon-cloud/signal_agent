from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.retention import cli as retention_cli


def _read_stdout_json(capsys: pytest.CaptureFixture[str]) -> dict:
    return json.loads(capsys.readouterr().out)


@pytest.fixture
def retention_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    monkeypatch.setenv("SIGNAL_AGENT_ROOT", str(root))
    return root


def _seed_clean_sequence(identifier_value: str) -> int:
    return retention_cli.main(
        [
            "add-contact",
            "--source",
            "substack",
            "--identifier-kind",
            "email",
            "--identifier-value",
            identifier_value,
            "--consent-status",
            "opted_in",
            "--apply",
            "--plan-dispatch",
        ]
    )


def _project_queue(root: Path) -> Path:
    queue_path = root / "data" / "state" / "send_queue_preview.json"
    result = retention_cli.main(
        [
            "project-send-queue",
            "--state-root",
            "data/state",
            "--out",
            "data/state/send_queue_preview.json",
        ]
    )
    assert result == 0
    assert queue_path.exists()
    return queue_path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_valid_send_queue_is_accepted_by_local_noop(
    retention_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _seed_clean_sequence("sender-valid@example.com") == 0
    capsys.readouterr()
    queue_path = _project_queue(retention_root)
    queue_payload = _read_json(queue_path)
    capsys.readouterr()

    result = retention_cli.main(
        ["send-preview", "--queue", "data/state/send_queue_preview.json", "--adapter", "local-noop"]
    )
    report = _read_stdout_json(capsys)

    assert result == 0
    assert report["clean"] is True
    assert report["adapter"] == "local-noop"
    assert report["attempted_count"] == 1
    assert report["accepted_count"] == 1
    assert report["rejected_count"] == 0
    assert report["issues"] == []
    assert report["results"][0] == {
        "adapter": "local-noop",
        "no_network": True,
        "projection_basis_hash": queue_payload["projection_basis_hash"],
        "queue_id": queue_payload["queue"][0]["queue_id"],
        "reason_code": "accepted_preview",
        "sent": False,
        "source_dispatch_id": queue_payload["queue"][0]["source_dispatch_id"],
        "source_line_number": queue_payload["queue"][0]["source_line_number"],
        "status": "accepted_preview",
    }


def test_unknown_adapter_fails_closed(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _seed_clean_sequence("sender-unknown@example.com") == 0
    capsys.readouterr()
    _project_queue(retention_root)
    capsys.readouterr()

    result = retention_cli.main(
        ["send-preview", "--queue", "data/state/send_queue_preview.json", "--adapter", "mystery-adapter"]
    )
    report = _read_stdout_json(capsys)

    assert result != 0
    assert report["clean"] is False
    assert report["attempted_count"] == 0
    assert report["accepted_count"] == 0
    assert report["rejected_count"] == 0
    assert report["results"] == []
    assert report["issues"][0]["issue_type"] == "unknown_adapter"


def test_missing_queue_file_fails_closed(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    result = retention_cli.main(
        ["send-preview", "--queue", "data/state/missing_send_queue.json", "--adapter", "local-noop"]
    )
    report = _read_stdout_json(capsys)

    assert result != 0
    assert report["clean"] is False
    assert report["attempted_count"] == 0
    assert report["issues"][0]["issue_type"] == "queue_file_missing"


def test_invalid_queue_json_fails_closed(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    broken_path = retention_root / "data" / "state" / "send_queue_preview.json"
    broken_path.parent.mkdir(parents=True, exist_ok=True)
    broken_path.write_text('{"queue":[', encoding="utf-8")

    result = retention_cli.main(
        ["send-preview", "--queue", "data/state/send_queue_preview.json", "--adapter", "local-noop"]
    )
    report = _read_stdout_json(capsys)

    assert result != 0
    assert report["clean"] is False
    assert report["attempted_count"] == 0
    assert report["issues"][0]["issue_type"] == "invalid_queue_json"


def test_unsafe_queue_status_fails_closed(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _seed_clean_sequence("sender-unsafe-status@example.com") == 0
    capsys.readouterr()
    queue_path = _project_queue(retention_root)
    queue_payload = _read_json(queue_path)
    queue_payload["queue"][0]["status"] = "sent"
    queue_path.write_text(json.dumps(queue_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    capsys.readouterr()

    result = retention_cli.main(
        ["send-preview", "--queue", "data/state/send_queue_preview.json", "--adapter", "local-noop"]
    )
    report = _read_stdout_json(capsys)

    assert result != 0
    assert report["clean"] is False
    assert report["attempted_count"] == 1
    assert report["accepted_count"] == 0
    assert report["rejected_count"] == 1
    assert report["results"][0]["status"] == "rejected_preview"
    assert report["results"][0]["reason_code"] == "unsafe_status:sent"
    assert report["issues"][0]["issue_type"] == "queue_record_unsafe_status"


def test_missing_template_or_content_reference_is_rejected(
    retention_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _seed_clean_sequence("sender-missing-template@example.com") == 0
    capsys.readouterr()
    queue_path = _project_queue(retention_root)
    queue_payload = _read_json(queue_path)
    queue_payload["queue"][0]["template_key"] = None
    queue_payload["queue"][0]["content_reference"] = None
    queue_path.write_text(json.dumps(queue_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    capsys.readouterr()

    result = retention_cli.main(
        ["send-preview", "--queue", "data/state/send_queue_preview.json", "--adapter", "local-noop"]
    )
    report = _read_stdout_json(capsys)

    assert result != 0
    assert report["clean"] is False
    assert report["rejected_count"] == 1
    assert report["results"][0]["reason_code"] == "missing_template_or_content_reference"
    assert report["issues"][0]["issue_type"] == "queue_record_missing_content_reference"


def test_stdout_preview_writes_no_file(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _seed_clean_sequence("sender-preview@example.com") == 0
    capsys.readouterr()
    queue_path = _project_queue(retention_root)
    state_root = retention_root / "data" / "state"
    output_path = state_root / "send_preview_result.json"
    queue_before = queue_path.read_text(encoding="utf-8")
    capsys.readouterr()

    result = retention_cli.main(
        ["send-preview", "--queue", "data/state/send_queue_preview.json", "--adapter", "local-noop"]
    )
    report = _read_stdout_json(capsys)

    assert result == 0
    assert report["clean"] is True
    assert not output_path.exists()
    assert queue_path.read_text(encoding="utf-8") == queue_before


def test_out_writes_only_declared_file(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _seed_clean_sequence("sender-out@example.com") == 0
    capsys.readouterr()
    queue_path = _project_queue(retention_root)
    state_root = retention_root / "data" / "state"
    output_path = state_root / "send_preview_result.json"
    before_entries = {path.name for path in state_root.iterdir()}
    ledger_before = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(state_root.glob("*.jsonl"))
    }
    queue_before = queue_path.read_text(encoding="utf-8")
    capsys.readouterr()

    result = retention_cli.main(
        [
            "send-preview",
            "--queue",
            "data/state/send_queue_preview.json",
            "--adapter",
            "local-noop",
            "--out",
            "data/state/send_preview_result.json",
        ]
    )
    report = _read_stdout_json(capsys)
    after_entries = {path.name for path in state_root.iterdir()}
    ledger_after = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(state_root.glob("*.jsonl"))
    }

    assert result == 0
    assert report["clean"] is True
    assert output_path.exists()
    assert json.loads(output_path.read_text(encoding="utf-8")) == report
    assert after_entries - before_entries == {"send_preview_result.json"}
    assert "send_preview_result.json.lock" not in after_entries
    assert queue_path.read_text(encoding="utf-8") == queue_before
    assert ledger_before == ledger_after


def test_no_mutation_of_retention_ledgers(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _seed_clean_sequence("sender-readonly@example.com") == 0
    capsys.readouterr()
    queue_path = _project_queue(retention_root)
    state_root = retention_root / "data" / "state"
    before = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(state_root.glob("*.jsonl"))
    }
    queue_stat_before = (queue_path.stat().st_size, queue_path.stat().st_mtime_ns)
    capsys.readouterr()

    result = retention_cli.main(
        ["send-preview", "--queue", "data/state/send_queue_preview.json", "--adapter", "local-noop"]
    )
    report = _read_stdout_json(capsys)
    after = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(state_root.glob("*.jsonl"))
    }
    queue_stat_after = (queue_path.stat().st_size, queue_path.stat().st_mtime_ns)

    assert result == 0
    assert report["clean"] is True
    assert before == after
    assert queue_stat_before == queue_stat_after


def test_output_order_is_deterministic(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _seed_clean_sequence("sender-order-a@example.com") == 0
    assert _seed_clean_sequence("sender-order-b@example.com") == 0
    capsys.readouterr()
    queue_path = _project_queue(retention_root)
    queue_payload = _read_json(queue_path)
    reversed_queue = list(reversed(queue_payload["queue"]))
    malformed = dict(reversed_queue[0])
    malformed["queue_id"] = ""
    queue_payload["queue"] = reversed_queue + [malformed]
    queue_payload["projected_count"] = len(queue_payload["queue"])
    queue_path.write_text(json.dumps(queue_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    capsys.readouterr()

    first_exit = retention_cli.main(
        ["send-preview", "--queue", "data/state/send_queue_preview.json", "--adapter", "local-noop"]
    )
    first_output = capsys.readouterr().out
    second_exit = retention_cli.main(
        ["send-preview", "--queue", "data/state/send_queue_preview.json", "--adapter", "local-noop"]
    )
    second_output = capsys.readouterr().out

    assert first_exit != 0
    assert second_exit != 0
    assert first_output == second_output

    report = json.loads(first_output)
    assert [(result["source_line_number"], result["source_dispatch_id"], result["status"]) for result in report["results"]] == [
        (1, queue_payload["queue"][1]["source_dispatch_id"], "accepted_preview"),
        (2, queue_payload["queue"][0]["source_dispatch_id"], "accepted_preview"),
        (2, queue_payload["queue"][0]["source_dispatch_id"], "rejected_preview"),
    ]
