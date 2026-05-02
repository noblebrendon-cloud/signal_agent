from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.retention import cli as retention_cli
from app.retention.jsonl_store import append_record


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


def _read_rows(root: Path, ledger_name: str) -> list[dict]:
    path = root / "data" / "state" / ledger_name
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _clone_for_append(row: dict, **updates: object) -> dict:
    cloned = dict(row)
    cloned.pop("record_hash", None)
    cloned.pop("prev_hash", None)
    cloned.pop("recorded_at", None)
    cloned.update(updates)
    return cloned


def test_eligible_dispatch_projects_into_queue(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _seed_clean_sequence("queue-eligible@example.com") == 0
    dispatch_rows = _read_rows(retention_root, "content_dispatch.jsonl")
    capsys.readouterr()

    result = retention_cli.main(["project-send-queue", "--state-root", "data/state"])
    report = _read_stdout_json(capsys)

    assert result == 0
    assert report["clean"] is True
    assert report["dispatch_ready_clean"] is True
    assert report["projected_count"] == 1
    assert report["excluded_count"] == 0
    assert len(report["queue"]) == 1
    assert report["queue"][0]["status"] == "send_ready"
    assert report["queue"][0]["source_dispatch_id"] == dispatch_rows[0]["dispatch_id"]
    assert report["queue"][0]["template_key"] == "orientation_email_v1"
    assert report["queue"][0]["source_ledger"] == "content_dispatch.jsonl"
    assert report["projection_basis_hash"].startswith("sha256:")


def test_blocked_dispatch_is_excluded(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _seed_clean_sequence("queue-blocked@example.com") == 0
    latest_snapshot = _read_rows(retention_root, "contacts.jsonl")[-1]
    opted_out_snapshot = _clone_for_append(
        latest_snapshot,
        contact_version=int(latest_snapshot["contact_version"]) + 1,
        consent={"email_marketing_status": "opted_out"},
    )
    append_record("contacts.jsonl", opted_out_snapshot)
    capsys.readouterr()

    result = retention_cli.main(["project-send-queue", "--state-root", "data/state"])
    report = _read_stdout_json(capsys)

    assert result != 0
    assert report["clean"] is False
    assert report["dispatch_ready_clean"] is False
    assert report["projected_count"] == 0
    assert report["excluded_count"] == 1
    assert report["queue"] == []
    assert report["exclusions"][0]["result"] == "blocked"
    assert any(code.startswith("consent_ineligible:") for code in report["exclusions"][0]["reason_codes"])


def test_skipped_dispatch_is_excluded(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _seed_clean_sequence("queue-skipped@example.com") == 0
    dispatch_rows = _read_rows(retention_root, "content_dispatch.jsonl")
    terminal_row = _clone_for_append(
        dispatch_rows[0],
        dispatch_id="dsp_sent_projection_skip",
        delivery_status="sent",
    )
    append_record("content_dispatch.jsonl", terminal_row)
    capsys.readouterr()

    result = retention_cli.main(["project-send-queue", "--state-root", "data/state"])
    report = _read_stdout_json(capsys)

    assert result == 0
    assert report["clean"] is True
    assert report["dispatch_ready_clean"] is True
    assert report["projected_count"] == 1
    assert report["excluded_count"] == 1
    assert len(report["queue"]) == 1
    assert report["exclusions"][0]["source_dispatch_id"] == "dsp_sent_projection_skip"
    assert report["exclusions"][0]["result"] == "skipped"
    assert "dispatch_status_terminal:sent" in report["exclusions"][0]["reason_codes"]


def test_dispatch_ready_failure_prevents_projection(
    retention_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _seed_clean_sequence("queue-reconcile-block@example.com") == 0
    event_rows = _read_rows(retention_root, "events.jsonl")
    leaked_event = _clone_for_append(
        event_rows[0],
        event_id="evt_projection_leak",
        debug_email="queue-reconcile-block@example.com",
    )
    append_record("events.jsonl", leaked_event)
    capsys.readouterr()

    result = retention_cli.main(["project-send-queue", "--state-root", "data/state"])
    report = _read_stdout_json(capsys)

    assert result != 0
    assert report["clean"] is False
    assert report["dispatch_ready_clean"] is False
    assert report["projected_count"] == 0
    assert report["excluded_count"] == 1
    assert report["queue"] == []
    assert "reconciliation_failed" in report["exclusions"][0]["reason_codes"]


def test_stdout_preview_writes_no_file(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _seed_clean_sequence("queue-preview@example.com") == 0
    state_root = retention_root / "data" / "state"
    output_path = state_root / "send_queue_preview.json"
    before = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(state_root.glob("*.jsonl"))
    }
    capsys.readouterr()

    result = retention_cli.main(["project-send-queue", "--state-root", "data/state"])
    report = _read_stdout_json(capsys)
    after = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(state_root.glob("*.jsonl"))
    }

    assert result == 0
    assert report["clean"] is True
    assert not output_path.exists()
    assert before == after


def test_out_writes_only_declared_file(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _seed_clean_sequence("queue-out@example.com") == 0
    state_root = retention_root / "data" / "state"
    output_path = state_root / "send_queue_preview.json"
    before_entries = {path.name for path in state_root.iterdir()}
    before_ledgers = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(state_root.glob("*.jsonl"))
    }
    capsys.readouterr()

    result = retention_cli.main(
        [
            "project-send-queue",
            "--state-root",
            "data/state",
            "--out",
            "data/state/send_queue_preview.json",
        ]
    )
    stdout_report = _read_stdout_json(capsys)
    after_entries = {path.name for path in state_root.iterdir()}
    after_ledgers = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(state_root.glob("*.jsonl"))
    }

    assert result == 0
    assert stdout_report["clean"] is True
    assert output_path.exists()
    assert json.loads(output_path.read_text(encoding="utf-8")) == stdout_report
    assert after_entries - before_entries == {"send_queue_preview.json"}
    assert "send_queue_preview.json.lock" not in after_entries
    assert before_ledgers == after_ledgers


def test_output_order_is_deterministic(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _seed_clean_sequence("queue-order-a@example.com") == 0
    assert _seed_clean_sequence("queue-order-b@example.com") == 0
    dispatch_rows = _read_rows(retention_root, "content_dispatch.jsonl")
    skipped_row = _clone_for_append(
        dispatch_rows[1],
        dispatch_id="dsp_order_skip",
        delivery_status="sent",
    )
    append_record("content_dispatch.jsonl", skipped_row)
    capsys.readouterr()

    first_exit = retention_cli.main(["project-send-queue", "--state-root", "data/state"])
    first_output = capsys.readouterr().out
    second_exit = retention_cli.main(["project-send-queue", "--state-root", "data/state"])
    second_output = capsys.readouterr().out

    assert first_exit == 0
    assert second_exit == 0
    assert first_output == second_output

    report = json.loads(first_output)
    assert [(record["source_line_number"], record["source_dispatch_id"]) for record in report["queue"]] == [
        (1, dispatch_rows[0]["dispatch_id"]),
        (2, dispatch_rows[1]["dispatch_id"]),
    ]
    assert [(record["line_number"], record["source_dispatch_id"], record["result"]) for record in report["exclusions"]] == [
        (3, "dsp_order_skip", "skipped"),
    ]


def test_project_send_queue_command_is_read_only(
    retention_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _seed_clean_sequence("queue-readonly@example.com") == 0
    state_root = retention_root / "data" / "state"
    before = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(state_root.glob("*.jsonl"))
    }
    capsys.readouterr()

    result = retention_cli.main(["project-send-queue", "--state-root", "data/state"])
    report = _read_stdout_json(capsys)
    after = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(state_root.glob("*.jsonl"))
    }

    assert result == 0
    assert report["clean"] is True
    assert before == after
