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


def _send_preview(root: Path) -> Path:
    preview_path = root / "data" / "state" / "send_preview.json"
    result = retention_cli.main(
        [
            "send-preview",
            "--queue",
            "data/state/send_queue_preview.json",
            "--adapter",
            "local-noop",
            "--out",
            "data/state/send_preview.json",
        ]
    )
    assert result == 0
    assert preview_path.exists()
    return preview_path


def _prepare_preview(root: Path, identifier_value: str) -> Path:
    assert _seed_clean_sequence(identifier_value) == 0
    _project_queue(root)
    return _send_preview(root)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_clean_accepted_preview_can_be_approved(
    retention_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    preview_path = _prepare_preview(retention_root, "authorize-approve@example.com")
    preview_payload = _read_json(preview_path)
    capsys.readouterr()

    result = retention_cli.main(
        [
            "authorize-send",
            "--preview",
            "data/state/send_preview.json",
            "--operator-id",
            "local-operator",
            "--decision",
            "approve",
        ]
    )
    report = _read_stdout_json(capsys)

    assert result == 0
    assert report["clean"] is True
    assert report["authorization_mode"] == "explicit"
    assert report["decision"] == "approve"
    assert report["authorized"] is True
    assert report["operator_id"] == "local-operator"
    assert report["source_preview_hash"].startswith("sha256:")
    assert report["authorized_count"] == 1
    assert report["denied_count"] == 0
    assert report["issues"] == []
    assert report["records"][0] == {
        "adapter": "local-noop",
        "authorization_id": report["records"][0]["authorization_id"],
        "authorized": True,
        "decision": "approve",
        "external_action_allowed": False,
        "queue_id": preview_payload["results"][0]["queue_id"],
        "reason_code": "authorized_preview_only",
        "sent": False,
        "source_dispatch_id": preview_payload["results"][0]["source_dispatch_id"],
        "source_line_number": preview_payload["results"][0]["source_line_number"],
    }


def test_clean_accepted_preview_can_be_denied(
    retention_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _prepare_preview(retention_root, "authorize-deny@example.com")
    capsys.readouterr()

    result = retention_cli.main(
        [
            "authorize-send",
            "--preview",
            "data/state/send_preview.json",
            "--operator-id",
            "local-operator",
            "--decision",
            "deny",
        ]
    )
    report = _read_stdout_json(capsys)

    assert result == 0
    assert report["clean"] is True
    assert report["decision"] == "deny"
    assert report["authorized"] is False
    assert report["authorized_count"] == 0
    assert report["denied_count"] == 1
    assert report["issues"] == []
    assert report["records"][0]["authorized"] is False
    assert report["records"][0]["reason_code"] == "operator_denied"
    assert report["records"][0]["external_action_allowed"] is False


def test_rejected_preview_cannot_be_approved(
    retention_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    preview_path = _prepare_preview(retention_root, "authorize-rejected@example.com")
    preview_payload = _read_json(preview_path)
    preview_payload["clean"] = False
    preview_payload["accepted_count"] = 0
    preview_payload["rejected_count"] = 1
    preview_payload["results"][0]["status"] = "rejected_preview"
    preview_payload["results"][0]["reason_code"] = "unsafe_status:sent"
    preview_path.write_text(json.dumps(preview_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    capsys.readouterr()

    result = retention_cli.main(
        [
            "authorize-send",
            "--preview",
            "data/state/send_preview.json",
            "--operator-id",
            "local-operator",
            "--decision",
            "approve",
        ]
    )
    report = _read_stdout_json(capsys)

    assert result != 0
    assert report["clean"] is False
    assert report["authorized"] is False
    assert report["authorized_count"] == 0
    assert report["denied_count"] == 1
    assert any(issue["issue_type"] == "preview_not_clean" for issue in report["issues"])
    assert any(issue["issue_type"] == "preview_result_status_invalid" for issue in report["issues"])
    assert report["records"][0]["authorized"] is False


def test_mixed_preview_fails_closed(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    preview_path = _prepare_preview(retention_root, "authorize-mixed@example.com")
    preview_payload = _read_json(preview_path)
    accepted = dict(preview_payload["results"][0])
    rejected = dict(accepted)
    rejected["status"] = "rejected_preview"
    rejected["reason_code"] = "unsafe_status:sent"
    preview_payload["clean"] = False
    preview_payload["attempted_count"] = 2
    preview_payload["accepted_count"] = 1
    preview_payload["rejected_count"] = 1
    preview_payload["results"] = [accepted, rejected]
    preview_path.write_text(json.dumps(preview_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    capsys.readouterr()

    result = retention_cli.main(
        [
            "authorize-send",
            "--preview",
            "data/state/send_preview.json",
            "--operator-id",
            "local-operator",
            "--decision",
            "approve",
        ]
    )
    report = _read_stdout_json(capsys)

    assert result != 0
    assert report["clean"] is False
    assert report["authorized"] is False
    assert report["authorized_count"] == 0
    assert report["denied_count"] == 2
    assert any(issue["issue_type"] == "mixed_preview_results" for issue in report["issues"])
    assert all(record["authorized"] is False for record in report["records"])


def test_unknown_decision_fails_closed(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _prepare_preview(retention_root, "authorize-unknown-decision@example.com")
    capsys.readouterr()

    result = retention_cli.main(
        [
            "authorize-send",
            "--preview",
            "data/state/send_preview.json",
            "--operator-id",
            "local-operator",
            "--decision",
            "ship",
        ]
    )
    report = _read_stdout_json(capsys)

    assert result != 0
    assert report["clean"] is False
    assert report["authorized"] is False
    assert any(issue["issue_type"] == "unknown_decision" for issue in report["issues"])


def test_missing_operator_id_fails_closed(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _prepare_preview(retention_root, "authorize-missing-operator@example.com")
    capsys.readouterr()

    result = retention_cli.main(
        [
            "authorize-send",
            "--preview",
            "data/state/send_preview.json",
            "--operator-id",
            "",
            "--decision",
            "approve",
        ]
    )
    report = _read_stdout_json(capsys)

    assert result != 0
    assert report["clean"] is False
    assert report["authorized"] is False
    assert any(issue["issue_type"] == "missing_operator_id" for issue in report["issues"])


def test_unsafe_sent_true_preview_fails_closed(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    preview_path = _prepare_preview(retention_root, "authorize-sent-unsafe@example.com")
    preview_payload = _read_json(preview_path)
    preview_payload["results"][0]["sent"] = True
    preview_path.write_text(json.dumps(preview_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    capsys.readouterr()

    result = retention_cli.main(
        [
            "authorize-send",
            "--preview",
            "data/state/send_preview.json",
            "--operator-id",
            "local-operator",
            "--decision",
            "approve",
        ]
    )
    report = _read_stdout_json(capsys)

    assert result != 0
    assert report["clean"] is False
    assert any(issue["issue_type"] == "preview_result_unsafe_sent" for issue in report["issues"])
    assert report["records"][0]["authorized"] is False


def test_unsafe_no_network_false_preview_fails_closed(
    retention_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    preview_path = _prepare_preview(retention_root, "authorize-network-unsafe@example.com")
    preview_payload = _read_json(preview_path)
    preview_payload["results"][0]["no_network"] = False
    preview_path.write_text(json.dumps(preview_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    capsys.readouterr()

    result = retention_cli.main(
        [
            "authorize-send",
            "--preview",
            "data/state/send_preview.json",
            "--operator-id",
            "local-operator",
            "--decision",
            "approve",
        ]
    )
    report = _read_stdout_json(capsys)

    assert result != 0
    assert report["clean"] is False
    assert any(issue["issue_type"] == "preview_result_unsafe_no_network" for issue in report["issues"])
    assert report["records"][0]["authorized"] is False


def test_stdout_preview_writes_no_file(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    preview_path = _prepare_preview(retention_root, "authorize-stdout@example.com")
    state_root = retention_root / "data" / "state"
    output_path = state_root / "send_authorization.json"
    preview_before = preview_path.read_text(encoding="utf-8")
    queue_path = state_root / "send_queue_preview.json"
    queue_before = queue_path.read_text(encoding="utf-8")
    capsys.readouterr()

    result = retention_cli.main(
        [
            "authorize-send",
            "--preview",
            "data/state/send_preview.json",
            "--operator-id",
            "local-operator",
            "--decision",
            "approve",
        ]
    )
    report = _read_stdout_json(capsys)

    assert result == 0
    assert report["clean"] is True
    assert not output_path.exists()
    assert preview_path.read_text(encoding="utf-8") == preview_before
    assert queue_path.read_text(encoding="utf-8") == queue_before


def test_out_writes_only_declared_file(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    preview_path = _prepare_preview(retention_root, "authorize-out@example.com")
    state_root = retention_root / "data" / "state"
    queue_path = state_root / "send_queue_preview.json"
    output_path = state_root / "send_authorization.json"
    before_entries = {path.name for path in state_root.iterdir()}
    ledger_before = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(state_root.glob("*.jsonl"))
    }
    preview_before = preview_path.read_text(encoding="utf-8")
    queue_before = queue_path.read_text(encoding="utf-8")
    capsys.readouterr()

    result = retention_cli.main(
        [
            "authorize-send",
            "--preview",
            "data/state/send_preview.json",
            "--operator-id",
            "local-operator",
            "--decision",
            "approve",
            "--out",
            "data/state/send_authorization.json",
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
    assert after_entries - before_entries == {"send_authorization.json"}
    assert "send_authorization.json.lock" not in after_entries
    assert preview_path.read_text(encoding="utf-8") == preview_before
    assert queue_path.read_text(encoding="utf-8") == queue_before
    assert ledger_before == ledger_after


def test_output_order_is_deterministic(retention_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _seed_clean_sequence("authorize-order-a@example.com") == 0
    assert _seed_clean_sequence("authorize-order-b@example.com") == 0
    _project_queue(retention_root)
    _send_preview(retention_root)
    preview_path = retention_root / "data" / "state" / "send_preview.json"
    preview_payload = _read_json(preview_path)
    reversed_results = list(reversed(preview_payload["results"]))
    rejected = dict(reversed_results[0])
    rejected["status"] = "rejected_preview"
    rejected["reason_code"] = "unsafe_status:sent"
    preview_payload["clean"] = False
    preview_payload["attempted_count"] = 3
    preview_payload["accepted_count"] = 2
    preview_payload["rejected_count"] = 1
    preview_payload["results"] = reversed_results + [rejected]
    preview_path.write_text(json.dumps(preview_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    capsys.readouterr()

    first_exit = retention_cli.main(
        [
            "authorize-send",
            "--preview",
            "data/state/send_preview.json",
            "--operator-id",
            "local-operator",
            "--decision",
            "approve",
        ]
    )
    first_output = capsys.readouterr().out
    second_exit = retention_cli.main(
        [
            "authorize-send",
            "--preview",
            "data/state/send_preview.json",
            "--operator-id",
            "local-operator",
            "--decision",
            "approve",
        ]
    )
    second_output = capsys.readouterr().out

    assert first_exit != 0
    assert second_exit != 0
    assert first_output == second_output

    report = json.loads(first_output)
    assert [(record["source_line_number"], record["source_dispatch_id"], record["authorized"]) for record in report["records"]] == [
        (1, preview_payload["results"][1]["source_dispatch_id"], False),
        (2, preview_payload["results"][0]["source_dispatch_id"], False),
        (2, preview_payload["results"][0]["source_dispatch_id"], False),
    ]


def test_no_mutation_of_retention_ledgers_or_queue_files(
    retention_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    preview_path = _prepare_preview(retention_root, "authorize-readonly@example.com")
    state_root = retention_root / "data" / "state"
    queue_path = state_root / "send_queue_preview.json"
    ledger_before = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(state_root.glob("*.jsonl"))
    }
    queue_before = (queue_path.stat().st_size, queue_path.stat().st_mtime_ns)
    preview_before = (preview_path.stat().st_size, preview_path.stat().st_mtime_ns)
    capsys.readouterr()

    result = retention_cli.main(
        [
            "authorize-send",
            "--preview",
            "data/state/send_preview.json",
            "--operator-id",
            "local-operator",
            "--decision",
            "approve",
        ]
    )
    report = _read_stdout_json(capsys)
    ledger_after = {
        path.name: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(state_root.glob("*.jsonl"))
    }
    queue_after = (queue_path.stat().st_size, queue_path.stat().st_mtime_ns)
    preview_after = (preview_path.stat().st_size, preview_path.stat().st_mtime_ns)

    assert result == 0
    assert report["clean"] is True
    assert ledger_before == ledger_after
    assert queue_before == queue_after
    assert preview_before == preview_after
