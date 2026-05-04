from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.governed_shell.errors import AuditLogError
from app.governed_shell.logstore import (
    AUDIT_ZERO_HASH,
    append_audit_event,
    build_review_event,
    canonical_event_json,
    compute_event_hash,
    read_audit_events,
)
from app.governed_shell.replay import replay_session, summarize_review_chain, verify_log


def _event(
    *,
    session_id: str,
    event_index: int,
    decision_code: str = "allowed",
    status: str = "allowed",
    proposal_hash: str | None = None,
    policy_hash: str | None = None,
    details: dict | None = None,
) -> dict:
    return build_review_event(
        session_id=session_id,
        event_index=event_index,
        timestamp_utc=f"2026-05-03T12:00:0{event_index}Z",
        proposal_id=f"proposal_{session_id}_{event_index}",
        proposal_hash=proposal_hash or f"sha256:{'1' * 64}",
        policy_hash=policy_hash or f"sha256:{'2' * 64}",
        risk_level="low",
        decision_code=decision_code,
        status=status,
        details=details or {"issues": []},
    )


def test_append_first_audit_event_creates_zero_prev_hash(tmp_path: Path) -> None:
    ledger_path = tmp_path / "audit.jsonl"

    appended = append_audit_event(ledger_path, _event(session_id="sessionA", event_index=0))

    assert appended["prev_hash"] == AUDIT_ZERO_HASH
    assert appended["record_hash"].startswith("sha256:")


def test_append_second_audit_event_links_prev_hash_to_prior_record_hash(tmp_path: Path) -> None:
    ledger_path = tmp_path / "audit.jsonl"
    first = append_audit_event(ledger_path, _event(session_id="sessionA", event_index=0))
    second = append_audit_event(ledger_path, _event(session_id="sessionA", event_index=1))

    assert second["prev_hash"] == first["record_hash"]


def test_verify_log_passes_on_clean_two_event_ledger(tmp_path: Path) -> None:
    ledger_path = tmp_path / "audit.jsonl"
    append_audit_event(ledger_path, _event(session_id="sessionA", event_index=0))
    append_audit_event(ledger_path, _event(session_id="sessionA", event_index=1))

    result = verify_log(ledger_path)

    assert result.clean is True
    assert result.event_count == 2
    assert result.issues == []


def test_verify_log_fails_if_record_is_edited_after_writing(tmp_path: Path) -> None:
    ledger_path = tmp_path / "audit.jsonl"
    append_audit_event(
        ledger_path,
        _event(session_id="sessionA", event_index=0, details={"issues": ["initial"]}),
    )
    rows = read_audit_events(ledger_path)
    rows[0]["details"]["issues"] = ["tampered"]
    ledger_path.write_text("\n".join(canonical_event_json(row) for row in rows) + "\n", encoding="utf-8")

    result = verify_log(ledger_path)

    assert result.clean is False
    assert any("record_hash_mismatch" in issue for issue in result.issues)


def test_verify_log_fails_if_prev_hash_is_broken(tmp_path: Path) -> None:
    ledger_path = tmp_path / "audit.jsonl"
    append_audit_event(ledger_path, _event(session_id="sessionA", event_index=0))
    append_audit_event(ledger_path, _event(session_id="sessionA", event_index=1))
    rows = read_audit_events(ledger_path)
    rows[1]["prev_hash"] = AUDIT_ZERO_HASH
    rows[1]["record_hash"] = compute_event_hash(rows[1])
    ledger_path.write_text("\n".join(canonical_event_json(row) for row in rows) + "\n", encoding="utf-8")

    result = verify_log(ledger_path)

    assert result.clean is False
    assert any("broken_prev_hash" in issue for issue in result.issues)


def test_verify_log_fails_if_event_index_is_non_monotonic(tmp_path: Path) -> None:
    ledger_path = tmp_path / "audit.jsonl"
    append_audit_event(ledger_path, _event(session_id="sessionA", event_index=0))
    append_audit_event(ledger_path, _event(session_id="sessionA", event_index=1))
    rows = read_audit_events(ledger_path)
    rows[1]["event_index"] = 0
    rows[1]["record_hash"] = compute_event_hash(rows[1])
    ledger_path.write_text("\n".join(canonical_event_json(row) for row in rows) + "\n", encoding="utf-8")

    result = verify_log(ledger_path)

    assert result.clean is False
    assert any("non_monotonic_event_index" in issue for issue in result.issues)


def test_verify_log_fails_on_malformed_jsonl(tmp_path: Path) -> None:
    ledger_path = tmp_path / "audit.jsonl"
    ledger_path.write_text('{"broken": true\n', encoding="utf-8")

    result = verify_log(ledger_path)

    assert result.clean is False
    assert any("malformed_jsonl_line" in issue for issue in result.issues)


def test_replay_session_reconstructs_events_for_one_session(tmp_path: Path) -> None:
    ledger_path = tmp_path / "audit.jsonl"
    first = append_audit_event(ledger_path, _event(session_id="sessionA", event_index=0))
    second_policy_hash = f"sha256:{'3' * 64}"
    second = append_audit_event(
        ledger_path,
        _event(
            session_id="sessionA",
            event_index=1,
            decision_code="risk_requires_confirmation",
            status="require_confirmation",
            proposal_hash=first["proposal_hash"],
            policy_hash=second_policy_hash,
        ),
    )

    result = replay_session(ledger_path, "sessionA")

    assert result.clean is True
    assert result.session_id == "sessionA"
    assert result.event_count == 2
    assert result.proposal_hashes == [first["proposal_hash"]]
    assert result.policy_hashes == [first["policy_hash"], second_policy_hash]
    assert result.decision_codes == ["allowed", "risk_requires_confirmation"]
    assert result.latest_status == second["status"]


def test_replay_session_ignores_other_session_events(tmp_path: Path) -> None:
    ledger_path = tmp_path / "audit.jsonl"
    append_audit_event(ledger_path, _event(session_id="sessionA", event_index=0))
    append_audit_event(ledger_path, _event(session_id="sessionB", event_index=1))

    result = replay_session(ledger_path, "sessionA")

    assert result.clean is True
    assert result.event_count == 1
    assert result.decision_codes == ["allowed"]


def test_replay_session_reports_not_clean_for_missing_session(tmp_path: Path) -> None:
    ledger_path = tmp_path / "audit.jsonl"
    append_audit_event(ledger_path, _event(session_id="sessionA", event_index=0))

    result = replay_session(ledger_path, "sessionMissing")

    assert result.clean is False
    assert result.event_count == 0
    assert result.issues == ["session_not_found:sessionMissing"]


def test_append_audit_event_raises_explicit_exception_if_ledger_path_cannot_be_written(
    tmp_path: Path,
) -> None:
    blocked_parent = tmp_path / "blocked_parent"
    blocked_parent.write_text("not a directory", encoding="utf-8")
    ledger_path = blocked_parent / "audit.jsonl"

    with pytest.raises(AuditLogError):
        append_audit_event(ledger_path, _event(session_id="sessionA", event_index=0))


def test_record_hash_is_stable_for_canonical_event_content() -> None:
    event_a = _event(session_id="sessionA", event_index=0)
    event_b = json.loads(
        """
        {
          "timestamp_utc":"2026-05-03T12:00:00Z",
          "status":"allowed",
          "schema_version":"audit_event.v1",
          "session_id":"sessionA",
          "snapshot_ref":"data/state/governed_shell/snapshots/none.json",
          "risk_level":"low",
          "receipt_ref":"data/state/governed_shell/receipts/none.json",
          "record_type":"governed_shell_audit_event",
          "proposal_id":"proposal_sessionA_0",
          "proposal_hash":"sha256:1111111111111111111111111111111111111111111111111111111111111111",
          "policy_hash":"sha256:2222222222222222222222222222222222222222222222222222222222222222",
          "plan_id":"plan.none",
          "plan_hash":"sha256:0000000000000000000000000000000000000000000000000000000000000000",
          "prev_hash":"sha256:0000000000000000000000000000000000000000000000000000000000000000",
          "event_type":"proposal_reviewed",
          "event_index":0,
          "event_id":"proposal_reviewed.sessionA.0",
          "details":{"issues":[]},
          "decision_code":"allowed",
          "record_hash":"sha256:0000000000000000000000000000000000000000000000000000000000000000"
        }
        """
    )

    assert compute_event_hash(event_a) == compute_event_hash(event_b)


def test_changing_details_changes_record_hash() -> None:
    event = _event(session_id="sessionA", event_index=0, details={"issues": []})
    changed = _event(session_id="sessionA", event_index=0, details={"issues": ["changed"]})

    assert compute_event_hash(event) != compute_event_hash(changed)


def test_summarize_review_chain_reports_latest_status() -> None:
    summary = summarize_review_chain(
        [
            _event(session_id="sessionA", event_index=0, status="allowed"),
            _event(
                session_id="sessionA",
                event_index=1,
                decision_code="risk_requires_confirmation",
                status="require_confirmation",
            ),
        ]
    )

    assert summary["event_count"] == 2
    assert summary["decision_codes"] == ["allowed", "risk_requires_confirmation"]
    assert summary["latest_status"] == "require_confirmation"
