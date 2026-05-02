from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.retention import cli as retention_cli
from app.retention.jsonl_store import append_record
from app.retention.models import build_contact_seed_event, build_contact_snapshot
from app.retention.transitions import evaluate_transition


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


def test_clean_dispatch_plan_becomes_eligible(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _seed_clean_sequence("eligible@example.com") == 0
    capsys.readouterr()

    result = retention_cli.main(["dispatch-ready", "--state-root", "data/state"])
    report = _read_stdout_json(capsys)

    assert result == 0
    assert report["clean"] is True
    assert report["reconciliation_clean"] is True
    assert report["reconciliation_issue_count"] == 0
    assert report["eligible_count"] == 1
    assert report["blocked_count"] == 0
    assert report["skipped_count"] == 0
    assert report["records"][0]["result"] == "eligible"


def test_reconciliation_failure_blocks_all_dispatches(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _seed_clean_sequence("blocked-by-reconcile@example.com") == 0
    capsys.readouterr()

    event = build_contact_seed_event(
        source="substack",
        identifier_kind="email",
        identifier_value="leak-block@example.com",
        consent_status="opted_in",
    )
    event["debug_email"] = "leak-block@example.com"
    append_record("events.jsonl", event)

    result = retention_cli.main(["dispatch-ready", "--state-root", "data/state"])
    report = _read_stdout_json(capsys)

    assert result != 0
    assert report["clean"] is False
    assert report["reconciliation_clean"] is False
    assert report["reconciliation_issue_count"] > 0
    assert report["blocked_count"] == 1
    assert report["records"][0]["result"] == "blocked"
    assert "reconciliation_failed" in report["records"][0]["reason_codes"]


def test_dispatch_without_valid_contact_is_blocked(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _seed_clean_sequence("orphan-dispatch@example.com") == 0
    dispatch_rows = _read_rows(retention_root, "content_dispatch.jsonl")
    broken_row = _clone_for_append(
        dispatch_rows[0],
        dispatch_id="dsp_broken_contact",
        contact_version=999,
    )
    append_record("content_dispatch.jsonl", broken_row)
    capsys.readouterr()

    result = retention_cli.main(["dispatch-ready", "--state-root", "data/state"])
    report = _read_stdout_json(capsys)

    assert result != 0
    assert report["blocked_count"] == 2
    assert report["reconciliation_clean"] is False
    assert any(record["dispatch_id"] == "dsp_broken_contact" and record["result"] == "blocked" for record in report["records"])


@pytest.mark.parametrize("mode", ["suppressed", "opted_out"])
def test_suppressed_or_opted_out_contact_is_blocked(
    retention_root: Path,
    capsys: pytest.CaptureFixture[str],
    mode: str,
) -> None:
    identifier = f"{mode}@example.com"
    assert _seed_clean_sequence(identifier) == 0
    capsys.readouterr()

    event_rows = _read_rows(retention_root, "events.jsonl")
    contact_rows = _read_rows(retention_root, "contacts.jsonl")
    seed_event = event_rows[0]
    latest_snapshot = contact_rows[-1]

    if mode == "suppressed":
        suppression_event = build_contact_seed_event(
            source="operator",
            identifier_kind="email",
            identifier_value=identifier,
            consent_status="opted_in",
            event_type="unsubscribe",
        )
        suppression_transition = evaluate_transition(suppression_event, previous_snapshot=latest_snapshot)
        suppressed_snapshot = build_contact_snapshot(
            previous_snapshot=latest_snapshot,
            event=suppression_event,
            transition=suppression_transition,
        )
        assert suppressed_snapshot is not None
        append_record("events.jsonl", suppression_event)
        append_record("transitions.jsonl", suppression_transition)
        append_record("contacts.jsonl", suppressed_snapshot)
    else:
        opted_out_snapshot = _clone_for_append(
            latest_snapshot,
            contact_version=int(latest_snapshot["contact_version"]) + 1,
            consent={"email_marketing_status": "opted_out"},
            last_touch_event=seed_event["event_id"],
        )
        append_record("contacts.jsonl", opted_out_snapshot)

    result = retention_cli.main(["dispatch-ready", "--state-root", "data/state"])
    report = _read_stdout_json(capsys)

    assert result != 0
    assert report["reconciliation_clean"] is True
    assert report["blocked_count"] == 1
    assert report["records"][0]["result"] == "blocked"


def test_unknown_dispatch_type_is_blocked(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _seed_clean_sequence("unknown-type@example.com") == 0
    dispatch_rows = _read_rows(retention_root, "content_dispatch.jsonl")
    unknown_row = _clone_for_append(
        dispatch_rows[0],
        dispatch_id="dsp_unknown_type",
        dispatch_type="mystery_channel",
    )
    append_record("content_dispatch.jsonl", unknown_row)
    capsys.readouterr()

    result = retention_cli.main(["dispatch-ready", "--state-root", "data/state"])
    report = _read_stdout_json(capsys)

    assert result != 0
    assert report["blocked_count"] == 2
    assert report["reconciliation_clean"] is False
    assert any(record["dispatch_id"] == "dsp_unknown_type" and record["result"] == "blocked" for record in report["records"])


@pytest.mark.parametrize("terminal_status", ["sent", "canceled", "suppressed"])
def test_terminal_dispatch_status_is_skipped(
    retention_root: Path,
    capsys: pytest.CaptureFixture[str],
    terminal_status: str,
) -> None:
    assert _seed_clean_sequence(f"{terminal_status}@example.com") == 0
    dispatch_rows = _read_rows(retention_root, "content_dispatch.jsonl")
    terminal_row = _clone_for_append(
        dispatch_rows[0],
        dispatch_id=f"dsp_{terminal_status}",
        delivery_status=terminal_status,
    )
    append_record("content_dispatch.jsonl", terminal_row)
    capsys.readouterr()

    result = retention_cli.main(["dispatch-ready", "--state-root", "data/state"])
    report = _read_stdout_json(capsys)

    assert result == 0
    assert report["clean"] is True
    assert report["eligible_count"] == 1
    assert report["skipped_count"] == 1
    assert any(record["dispatch_id"] == f"dsp_{terminal_status}" and record["result"] == "skipped" for record in report["records"])


def test_dispatch_gate_output_order_is_deterministic(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _seed_clean_sequence("ordered-dispatch-a@example.com") == 0
    assert _seed_clean_sequence("ordered-dispatch-b@example.com") == 0
    assert _seed_clean_sequence("ordered-dispatch-c@example.com") == 0
    dispatch_rows = _read_rows(retention_root, "content_dispatch.jsonl")

    skipped_row = _clone_for_append(
        dispatch_rows[1],
        dispatch_id="dsp_skipped_terminal",
        delivery_status="sent",
    )
    append_record("content_dispatch.jsonl", skipped_row)

    latest_c_snapshot = _read_rows(retention_root, "contacts.jsonl")[-1]
    opted_out_snapshot = _clone_for_append(
        latest_c_snapshot,
        contact_version=int(latest_c_snapshot["contact_version"]) + 1,
        consent={"email_marketing_status": "opted_out"},
    )
    append_record("contacts.jsonl", opted_out_snapshot)
    capsys.readouterr()

    first_exit = retention_cli.main(["dispatch-ready", "--state-root", "data/state"])
    first_output = capsys.readouterr().out
    second_exit = retention_cli.main(["dispatch-ready", "--state-root", "data/state"])
    second_output = capsys.readouterr().out

    assert first_exit != 0
    assert second_exit != 0
    assert first_output == second_output

    report = json.loads(first_output)
    assert [(record["line_number"], record["dispatch_id"], record["result"]) for record in report["records"]] == [
        (1, dispatch_rows[0]["dispatch_id"], "eligible"),
        (2, dispatch_rows[1]["dispatch_id"], "eligible"),
        (3, dispatch_rows[2]["dispatch_id"], "blocked"),
        (4, "dsp_skipped_terminal", "skipped"),
    ]


def test_dispatch_ready_command_is_read_only(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _seed_clean_sequence("readonly@example.com") == 0
    capsys.readouterr()
    state_root = retention_root / "data" / "state"
    before = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(state_root.glob("*.jsonl"))
    }

    result = retention_cli.main(["dispatch-ready", "--state-root", "data/state"])
    report = _read_stdout_json(capsys)
    after = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(state_root.glob("*.jsonl"))
    }

    assert result == 0
    assert report["clean"] is True
    assert before == after
