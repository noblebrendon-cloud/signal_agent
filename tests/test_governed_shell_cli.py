from __future__ import annotations

import json
from pathlib import Path

from app.governed_shell.cli import main
from app.governed_shell.confirm import check_confirmation, require_confirmation
from app.governed_shell.execution_plan import build_execution_plan
from app.governed_shell.logstore import canonical_event_json, read_audit_events
from app.governed_shell.normalize import normalize_and_hash_proposal
from app.governed_shell.policy import evaluate_policy
from app.governed_shell.schema_validate import validate_command_proposal


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _valid_proposal(*, recurse: bool = False) -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "schema_version": "command_proposal.v1",
        "proposal_id": "proposal_cli_001",
        "created_at": "2026-05-04T12:00:00Z",
        "requested_execution_mode": "simulate",
        "intent": {
            "summary": "List reports",
            "justification": "CLI test fixture.",
            "requested_effect": "inspect",
        },
        "proposer": {
            "kind": "agent",
            "proposal_only": True,
            "agent_family": "codex",
            "agent_id": "cli_tests",
        },
        "path_refs": [
            {
                "path_ref_id": "reports_dir",
                "root_id": "reports",
                "relative_path": "operator",
                "path_kind": "directory",
                "must_exist": True,
            }
        ],
        "operations": [
            {
                "op_id": "op_list_reports",
                "operation_type": "powershell_cmdlet",
                "cmdlet_id": "ps.get_child_items_v1",
                "parameters": [
                    {
                        "name": "target_path_ref",
                        "value_type": "path_ref",
                        "path_ref": "reports_dir",
                    },
                    {
                        "name": "recurse",
                        "value_type": "boolean",
                        "boolean_value": recurse,
                    },
                ],
            }
        ],
        "model_annotations": {
            "proposal_source": "model_authored",
            "model_declared_risk_level": "low",
            "rationale": "CLI test fixture.",
        },
    }


def _denied_proposal() -> dict:
    payload = _valid_proposal()
    payload["operations"][0]["cmdlet_id"] = "ps.unknown_v1"
    return payload


def _sealed_plan(*, recurse: bool = False) -> dict:
    normalized = normalize_and_hash_proposal(_valid_proposal(recurse=recurse))
    decision = evaluate_policy(normalized)
    confirmation = check_confirmation(
        normalized.proposal_hash,
        None,
        decision.confirmation_required,
        decision.confirmation_mode,
    )
    if decision.confirmation_required:
        confirmation = require_confirmation(
            normalized.proposal_hash,
            normalized.proposal_hash,
            decision.confirmation_required,
            decision.confirmation_mode,
        )
    return build_execution_plan(normalized, decision, confirmation)


def _last_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def test_propose_stub_prints_valid_schema_compatible_json(capsys) -> None:
    exit_code = main(["propose-stub", "--intent", "List docs operator files"])

    payload = _last_json(capsys)
    validation = validate_command_proposal(payload)

    assert exit_code == 0
    assert validation.clean is True
    assert payload["operations"][0]["operation_type"] == "powershell_cmdlet"
    assert payload["operations"][0]["cmdlet_id"] == "ps.get_child_items_v1"


def test_policy_test_valid_proposal_exits_zero_and_returns_clean_true(tmp_path: Path, capsys) -> None:
    proposal_path = _write_json(tmp_path / "proposal.json", _valid_proposal())

    exit_code = main(["policy-test", "--proposal", str(proposal_path)])

    payload = _last_json(capsys)
    assert exit_code == 0
    assert payload["clean"] is True
    assert payload["status"] == "allow"


def test_policy_test_denied_proposal_exits_one(tmp_path: Path, capsys) -> None:
    proposal_path = _write_json(tmp_path / "proposal.json", _denied_proposal())

    exit_code = main(["policy-test", "--proposal", str(proposal_path)])

    payload = _last_json(capsys)
    assert exit_code == 1
    assert payload["clean"] is False


def test_review_with_audit_appends_review_event(tmp_path: Path, capsys) -> None:
    proposal_path = _write_json(tmp_path / "proposal.json", _valid_proposal())
    audit_path = tmp_path / "audit.jsonl"

    exit_code = main(["review", "--proposal", str(proposal_path), "--audit", str(audit_path)])

    payload = _last_json(capsys)
    events = read_audit_events(audit_path)
    assert exit_code == 0
    assert payload["clean"] is True
    assert events[-1]["event_type"] == "proposal_reviewed"


def test_review_without_audit_does_not_create_audit_file(tmp_path: Path, capsys) -> None:
    proposal_path = _write_json(tmp_path / "proposal.json", _valid_proposal())
    audit_path = tmp_path / "audit.jsonl"

    exit_code = main(["review", "--proposal", str(proposal_path)])

    payload = _last_json(capsys)
    assert exit_code == 0
    assert payload["clean"] is True
    assert audit_path.exists() is False


def test_approve_valid_proposal_writes_sealed_plan(tmp_path: Path, capsys) -> None:
    proposal = _valid_proposal()
    proposal_path = _write_json(tmp_path / "proposal.json", proposal)
    proposal_hash = normalize_and_hash_proposal(proposal).proposal_hash
    plan_path = tmp_path / "approved" / "plan.json"

    exit_code = main(
        [
            "approve",
            "--proposal",
            str(proposal_path),
            "--proposal-hash",
            proposal_hash,
            "--out",
            str(plan_path),
        ]
    )

    payload = _last_json(capsys)
    assert exit_code == 0
    assert payload["clean"] is True
    assert plan_path.exists() is True


def test_approve_with_wrong_hash_exits_one_and_writes_no_plan(tmp_path: Path, capsys) -> None:
    proposal_path = _write_json(tmp_path / "proposal.json", _valid_proposal())
    plan_path = tmp_path / "approved" / "plan.json"

    exit_code = main(
        [
            "approve",
            "--proposal",
            str(proposal_path),
            "--proposal-hash",
            "sha256:" + ("f" * 64),
            "--out",
            str(plan_path),
        ]
    )

    payload = _last_json(capsys)
    assert exit_code == 1
    assert payload["reason_code"] == "confirmation_mismatch"
    assert plan_path.exists() is False


def test_approve_denied_proposal_exits_one_and_writes_no_plan(tmp_path: Path, capsys) -> None:
    proposal_path = _write_json(tmp_path / "proposal.json", _denied_proposal())
    plan_path = tmp_path / "approved" / "plan.json"

    exit_code = main(
        [
            "approve",
            "--proposal",
            str(proposal_path),
            "--out",
            str(plan_path),
        ]
    )

    payload = _last_json(capsys)
    assert exit_code == 1
    assert payload["clean"] is False
    assert plan_path.exists() is False


def test_simulate_valid_sealed_plan_returns_executed_false(tmp_path: Path, capsys) -> None:
    plan_path = _write_json(tmp_path / "plan.json", _sealed_plan())
    snapshot_dir = tmp_path / "snapshots"

    exit_code = main(
        [
            "simulate",
            "--plan",
            str(plan_path),
            "--snapshot-dir",
            str(snapshot_dir),
        ]
    )

    payload = _last_json(capsys)
    assert exit_code == 0
    assert payload["executed"] is False


def test_simulate_appends_simulation_audit_events_when_audit_path_provided(
    tmp_path: Path,
    capsys,
) -> None:
    plan = _sealed_plan()
    plan_path = _write_json(tmp_path / "plan.json", plan)
    audit_path = tmp_path / "audit.jsonl"
    snapshot_dir = tmp_path / "snapshots"

    exit_code = main(
        [
            "simulate",
            "--plan",
            str(plan_path),
            "--audit",
            str(audit_path),
            "--snapshot-dir",
            str(snapshot_dir),
        ]
    )

    payload = _last_json(capsys)
    events = read_audit_events(audit_path)
    assert exit_code == 0
    assert payload["clean"] is True
    assert [event["event_type"] for event in events] == [
        "simulation_started",
        "simulation_finished",
    ]


def test_verify_log_passes_for_clean_audit(tmp_path: Path, capsys) -> None:
    plan_path = _write_json(tmp_path / "plan.json", _sealed_plan())
    audit_path = tmp_path / "audit.jsonl"
    snapshot_dir = tmp_path / "snapshots"
    main(["simulate", "--plan", str(plan_path), "--audit", str(audit_path), "--snapshot-dir", str(snapshot_dir)])
    capsys.readouterr()

    exit_code = main(["verify-log", "--audit", str(audit_path)])

    payload = _last_json(capsys)
    assert exit_code == 0
    assert payload["clean"] is True


def test_verify_log_exits_one_for_tampered_audit(tmp_path: Path, capsys) -> None:
    plan_path = _write_json(tmp_path / "plan.json", _sealed_plan())
    audit_path = tmp_path / "audit.jsonl"
    snapshot_dir = tmp_path / "snapshots"
    main(["simulate", "--plan", str(plan_path), "--audit", str(audit_path), "--snapshot-dir", str(snapshot_dir)])
    capsys.readouterr()
    rows = read_audit_events(audit_path)
    rows[-1]["details"]["receipt_hash"] = "tampered"
    audit_path.write_text("\n".join(canonical_event_json(row) for row in rows) + "\n", encoding="utf-8")

    exit_code = main(["verify-log", "--audit", str(audit_path)])

    payload = _last_json(capsys)
    assert exit_code == 1
    assert payload["clean"] is False


def test_replay_returns_one_session_summary(tmp_path: Path, capsys) -> None:
    plan = _sealed_plan()
    plan_path = _write_json(tmp_path / "plan.json", plan)
    audit_path = tmp_path / "audit.jsonl"
    snapshot_dir = tmp_path / "snapshots"
    main(["simulate", "--plan", str(plan_path), "--audit", str(audit_path), "--snapshot-dir", str(snapshot_dir)])
    capsys.readouterr()

    exit_code = main(["replay", "--audit", str(audit_path), "--session-id", plan["session_id"]])

    payload = _last_json(capsys)
    assert exit_code == 0
    assert payload["clean"] is True
    assert payload["decision_codes"] == ["simulation_started", "simulation_finished"]


def test_replay_missing_session_exits_one(tmp_path: Path, capsys) -> None:
    plan_path = _write_json(tmp_path / "plan.json", _sealed_plan())
    audit_path = tmp_path / "audit.jsonl"
    snapshot_dir = tmp_path / "snapshots"
    main(["simulate", "--plan", str(plan_path), "--audit", str(audit_path), "--snapshot-dir", str(snapshot_dir)])
    capsys.readouterr()

    exit_code = main(["replay", "--audit", str(audit_path), "--session-id", "session.missing"])

    payload = _last_json(capsys)
    assert exit_code == 1
    assert payload["clean"] is False


def test_every_command_emits_parseable_json(tmp_path: Path, capsys) -> None:
    proposal = _valid_proposal()
    proposal_path = _write_json(tmp_path / "proposal.json", proposal)
    proposal_hash = normalize_and_hash_proposal(proposal).proposal_hash
    plan_path = tmp_path / "plan.json"
    audit_path = tmp_path / "audit.jsonl"
    snapshot_dir = tmp_path / "snapshots"

    commands = [
        ["propose-stub", "--intent", "List docs operator files"],
        ["policy-test", "--proposal", str(proposal_path)],
        ["review", "--proposal", str(proposal_path)],
        ["approve", "--proposal", str(proposal_path), "--proposal-hash", proposal_hash, "--out", str(plan_path)],
    ]

    for command in commands:
        exit_code = main(command)
        payload = _last_json(capsys)
        assert isinstance(payload, dict)
        assert exit_code == 0

    exit_code = main(["simulate", "--plan", str(plan_path), "--audit", str(audit_path), "--snapshot-dir", str(snapshot_dir)])
    payload = _last_json(capsys)
    assert isinstance(payload, dict)
    assert exit_code == 0

    exit_code = main(["verify-log", "--audit", str(audit_path)])
    payload = _last_json(capsys)
    assert isinstance(payload, dict)
    assert exit_code == 0

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    exit_code = main(["replay", "--audit", str(audit_path), "--session-id", plan["session_id"]])
    payload = _last_json(capsys)
    assert isinstance(payload, dict)
    assert exit_code == 0


def test_cli_module_contains_no_subprocess_import() -> None:
    source = (Path(__file__).resolve().parents[1] / "app" / "governed_shell" / "cli.py").read_text(
        encoding="utf-8"
    )

    assert "import subprocess" not in source


def test_cli_module_contains_no_powershell_invocation_strings() -> None:
    source = (Path(__file__).resolve().parents[1] / "app" / "governed_shell" / "cli.py").read_text(
        encoding="utf-8"
    ).lower()

    assert "pwsh" not in source
    assert "powershell.exe" not in source
    assert "-command" not in source
