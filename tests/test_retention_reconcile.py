from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.retention import cli as retention_cli
from app.retention.jsonl_store import append_record, ensure_required_state_files
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


def test_reconcile_clean_four_ledger_sequence(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _seed_clean_sequence("clean@example.com") == 0
    capsys.readouterr()

    result = retention_cli.main(["reconcile", "--state-root", "data/state"])
    report = _read_stdout_json(capsys)

    assert result == 0
    assert report["clean"] is True
    assert report["issue_count"] == 0
    assert [entry["ledger"] for entry in report["ledgers"]] == [
        "contacts.jsonl",
        "events.jsonl",
        "transitions.jsonl",
        "content_dispatch.jsonl",
    ]


def test_reconcile_reports_missing_transition(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ensure_required_state_files()
    event = build_contact_seed_event(
        source="substack",
        identifier_kind="email",
        identifier_value="missing-transition@example.com",
        consent_status="opted_in",
    )
    append_record("events.jsonl", event)

    result = retention_cli.main(["reconcile", "--state-root", "data/state"])
    report = _read_stdout_json(capsys)

    assert result != 0
    assert any(issue["issue_type"] == "event_without_transition" for issue in report["issues"])


def test_reconcile_reports_dispatch_without_valid_contact(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ensure_required_state_files()
    append_record(
        "content_dispatch.jsonl",
        {
            "record_type": "content_dispatch_plan",
            "schema_version": "1.0",
            "contact_id": "ctc_missing",
            "contact_version": 1,
            "current_state": "subscribed",
            "consent": {"email_marketing_status": "opted_in"},
            "decision": "planned",
            "dispatch_id": "dsp_missing",
            "dispatch_type": "orientation_email",
            "channel": "email",
            "template_key": "orientation_email_v1",
            "reason_codes": ["subscribed_contact_ready_for_orientation"],
        },
    )

    result = retention_cli.main(["reconcile", "--state-root", "data/state"])
    report = _read_stdout_json(capsys)

    assert result != 0
    assert any(issue["issue_type"] == "dispatch_without_valid_contact_state" for issue in report["issues"])


def test_reconcile_reports_raw_email_leakage(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ensure_required_state_files()
    event = build_contact_seed_event(
        source="substack",
        identifier_kind="email",
        identifier_value="leak@example.com",
        consent_status="opted_in",
    )
    event["debug_email"] = "leak@example.com"
    transition = evaluate_transition(event, previous_snapshot=None)
    snapshot = build_contact_snapshot(previous_snapshot=None, event=event, transition=transition)
    assert snapshot is not None

    append_record("events.jsonl", event)
    append_record("transitions.jsonl", transition)
    append_record("contacts.jsonl", snapshot)

    result = retention_cli.main(["reconcile", "--state-root", "data/state"])
    report = _read_stdout_json(capsys)

    assert result != 0
    leakage_issues = [issue for issue in report["issues"] if issue["issue_type"] == "raw_identifier_leakage"]
    assert leakage_issues
    assert all("@" not in json.dumps(issue, sort_keys=True) for issue in leakage_issues)


def test_reconcile_after_dry_run_creates_no_artifacts(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    state_root = retention_root / "data" / "state"
    assert retention_cli.main(
        [
            "add-contact",
            "--source",
            "substack",
            "--identifier-kind",
            "email",
            "--identifier-value",
            "dryrun@example.com",
            "--consent-status",
            "opted_in",
            "--dry-run",
        ]
    ) == 0
    capsys.readouterr()
    assert not state_root.exists()

    result = retention_cli.main(["reconcile", "--state-root", "data/state"])
    report = _read_stdout_json(capsys)

    assert result != 0
    assert not state_root.exists()
    assert any(issue["issue_type"] == "missing_ledger_file" for issue in report["issues"])


def test_reconcile_output_order_is_deterministic(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ensure_required_state_files()
    append_record(
        "content_dispatch.jsonl",
        {
            "record_type": "content_dispatch_plan",
            "schema_version": "1.0",
            "contact_id": "ctc_orphan",
            "contact_version": 1,
            "current_state": "subscribed",
            "consent": {"email_marketing_status": "opted_in"},
            "decision": "planned",
            "dispatch_id": "dsp_orphan",
            "dispatch_type": "orientation_email",
            "channel": "email",
            "template_key": "orientation_email_v1",
            "reason_codes": ["subscribed_contact_ready_for_orientation"],
        },
    )
    event = build_contact_seed_event(
        source="substack",
        identifier_kind="email",
        identifier_value="ordered@example.com",
        consent_status="opted_in",
    )
    event["leak"] = "ordered@example.com"
    append_record("events.jsonl", event)

    first_exit = retention_cli.main(["reconcile", "--state-root", "data/state"])
    first_output = capsys.readouterr().out
    second_exit = retention_cli.main(["reconcile", "--state-root", "data/state"])
    second_output = capsys.readouterr().out

    assert first_exit != 0
    assert second_exit != 0
    assert first_output == second_output

    report = json.loads(first_output)
    ordered_pairs = [(issue["ledger"], issue["issue_type"]) for issue in report["issues"]]
    assert ordered_pairs[:3] == [
        ("events.jsonl", "raw_identifier_leakage"),
        ("events.jsonl", "event_without_transition"),
        ("content_dispatch.jsonl", "dispatch_without_valid_contact_state"),
    ]
