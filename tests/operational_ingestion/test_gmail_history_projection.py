from __future__ import annotations

import json
import copy

import pytest

from signal_agent.corpus_import.gmail_history import GmailHistoryContractError
from signal_agent.corpus_import.gmail_history import (
    build_gmail_captured_inputs,
    load_gmail_fixture,
    load_gmail_history_policy,
)
from signal_agent.operational_ingestion.checkpoints import resolve_current_checkpoint
from signal_agent.operational_ingestion.simulator import DeterministicVirtualClock
from signal_agent.relationship_signals.gmail_history_pipeline import (
    gmail_relationship_semantic_projection,
)
from signal_agent.corpus_import.gmail_history.projection import (
    build_target_label_projection,
)

from .gmail_test_support import (
    FIXED_TIME,
    SECOND_TIME,
    THIRD_TIME,
    PROTECTION_KEY,
    PROTECTION_KEY_ID,
    TARGET_LABEL_ID,
    fixture_path,
    load_fixture,
    load_projection,
    normalized_records,
    policy_path,
    projection_path,
    run_case,
)


def _bootstrap(case_root):
    governed = case_root / "bootstrap-governed"
    result = run_case(
        case_root,
        script_name="gmail_bootstrap_nonempty.json",
        governed_run_root=governed,
    )
    return result, governed


def _paginate_target_listing(payload, *, token):
    first = copy.deepcopy(payload["operations"][0])
    messages = list(first["response"]["messages"])
    assert len(messages) >= 2
    first["response"]["messages"] = messages[:1]
    first["response"]["nextPageToken"] = token
    second = copy.deepcopy(first)
    second["request"] = {
        "labelIds": [TARGET_LABEL_ID],
        "pageToken": token,
    }
    second["response"]["messages"] = messages[1:]
    second["response"].pop("nextPageToken", None)
    payload["operations"] = [first, second, *payload["operations"][1:]]
    return payload


def test_nonempty_bootstrap_commits_two_membership_effects(tmp_path):
    result, governed = _bootstrap(tmp_path)
    assert result.success and result.result.status == "checkpoint_committed"
    projection = load_projection(governed)
    assert [item["state"] for item in projection["final_states"]] == ["inside", "inside"]
    assert {item["transition_kind"] for item in projection["transitions"]} == {
        "bootstrap_membership_established"
    }
    records = normalized_records(governed)
    assert len(records) == 2
    assert all(item["relationship"]["absence_inference_used"] is False for item in records)
    assert result.result.execution.checkpoint_commit.path.is_file()


def test_two_page_target_bootstrap_commits_only_after_terminal_exhaustion(tmp_path):
    payload = _paginate_target_listing(
        load_fixture("gmail_bootstrap_nonempty.json"),
        token="bootstrap-target-page-2",
    )
    fixture = tmp_path / "two-page-bootstrap.json"
    fixture.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    governed = tmp_path / "two-page-governed"
    result = run_case(
        tmp_path,
        script_name="gmail_bootstrap_nonempty.json",
        script_path=fixture,
        governed_run_root=governed,
    )
    assert result.success
    projection = load_projection(governed)
    assert len(projection["transitions"]) == 2
    assert {item["transition_kind"] for item in projection["transitions"]} == {
        "bootstrap_membership_established"
    }


def test_empty_target_bootstrap_commits_zero_relationship_effects(tmp_path):
    governed = tmp_path / "empty-target-governed"
    result = run_case(
        tmp_path,
        script_name="gmail_bootstrap_empty_target.json",
        governed_run_root=governed,
    )
    assert result.success
    assert load_projection(governed)["transitions"] == []
    assert normalized_records(governed) == []


def test_empty_target_anchor_lookup_is_bounded_not_exhaustive_and_creates_no_membership(
    tmp_path,
):
    payload = load_fixture("gmail_bootstrap_empty_target.json")
    anchor_response = payload["operations"][1]["response"]
    anchor_response["nextPageToken"] = "ignored-bounded-anchor-continuation"
    anchor_response["resultSizeEstimate"] = 999
    fixture = tmp_path / "bounded-anchor.json"
    fixture.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    governed = tmp_path / "bounded-anchor-governed"
    result = run_case(
        tmp_path,
        script_name="gmail_bootstrap_empty_target.json",
        script_path=fixture,
        governed_run_root=governed,
    )
    assert result.success
    assert load_projection(governed)["transitions"] == []
    assert normalized_records(governed) == []


@pytest.mark.parametrize(
    "script_name,status",
    [
        ("gmail_bootstrap_empty_mailbox.json", "unsupported_bootstrap_continuation"),
        ("gmail_bootstrap_coverage_unknown.json", "coverage_unknown"),
    ],
)
def test_unknown_bootstrap_coverage_cannot_advance_checkpoint(tmp_path, script_name, status):
    governed = tmp_path / status
    result = run_case(tmp_path / script_name, script_name=script_name, governed_run_root=governed)
    assert not result.success and result.result.status == status
    assert result.result.failure_receipt is not None
    source_roots = list((tmp_path / script_name / "store").glob("osi_*"))
    assert len(source_roots) == 1
    assert resolve_current_checkpoint(source_roots[0]) is None
    assert not (governed / "05_receipts/gmail_operational_completed_manifest.json").exists()


def test_incremental_projection_distinguishes_entry_departure_and_mailbox_deletion(tmp_path):
    bootstrap, bootstrap_governed = _bootstrap(tmp_path)
    governed = tmp_path / "incremental-governed"
    result = run_case(
        tmp_path,
        script_name="gmail_incremental_partition_a.json",
        start=SECOND_TIME,
        session_started_at=SECOND_TIME,
        prior_checkpoint=bootstrap.result.execution.checkpoint_commit,
        prior_projection_path=projection_path(bootstrap_governed),
        governed_run_root=governed,
    )
    assert result.success
    projection = load_projection(governed)
    kinds = [item["transition_kind"] for item in projection["transitions"]]
    assert sorted(kinds) == sorted(
        [
            "entered_target_label",
            "entered_target_label",
            "left_target_label",
            "mailbox_deleted_while_in_target_scope",
        ]
    )
    assert len(projection["unresolved_relevance"]) == 1
    assert projection["unresolved_relevance"][0]["classification"] == (
        "mailbox_deletion_target_relevance_unknown"
    )
    records = normalized_records(governed)
    deletion = next(
        item for item in records if item["relationship"]["mailbox_deletion"]
    )
    departure = next(
        item for item in records if item["relationship"]["target_label_departure"]
    )
    assert deletion["relationship"]["kind"] == "mailbox_deleted_while_in_target_scope"
    assert departure["relationship"]["kind"] == "left_target_label"
    assert all(item["relationship"]["absence_inference_used"] is False for item in records)


def test_unrelated_mailbox_events_do_not_change_target_projection(tmp_path):
    bootstrap, bootstrap_governed = _bootstrap(tmp_path)
    governed = tmp_path / "incremental-governed"
    run_case(
        tmp_path,
        script_name="gmail_incremental_partition_a.json",
        start=SECOND_TIME,
        session_started_at=SECOND_TIME,
        prior_checkpoint=bootstrap.result.execution.checkpoint_commit,
        prior_projection_path=projection_path(bootstrap_governed),
        governed_run_root=governed,
    )
    projection = load_projection(governed)
    assert len(projection["transitions"]) == 4
    assert not any(
        "Label_OTHER" in json.dumps(item, sort_keys=True)
        for item in projection["transitions"]
    )


def test_page_partition_changes_capture_identity_not_semantic_evidence(tmp_path):
    outputs = []
    for suffix, script in (("a", "gmail_incremental_partition_a.json"), ("b", "gmail_incremental_partition_b.json")):
        root = tmp_path / suffix
        bootstrap, bootstrap_governed = _bootstrap(root)
        governed = root / "incremental-governed"
        incremental = run_case(
            root,
            script_name=script,
            start=SECOND_TIME,
            session_started_at=SECOND_TIME,
            prior_checkpoint=bootstrap.result.execution.checkpoint_commit,
            prior_projection_path=projection_path(bootstrap_governed),
            governed_run_root=governed,
        )
        outputs.append((incremental, governed))
    (left, left_root), (right, right_root) = outputs
    assert left.result.execution.boundary.payload["capture_set_hash"] != right.result.execution.boundary.payload["capture_set_hash"]
    assert left.result.execution.bounded_material.payload["observation_set_hash"] == right.result.execution.bounded_material.payload["observation_set_hash"]
    assert gmail_relationship_semantic_projection(left_root) == gmail_relationship_semantic_projection(right_root)


def test_retry_history_changes_transport_not_semantic_evidence(tmp_path):
    retry_payload = load_fixture("gmail_incremental_partition_a.json")
    retry_payload["operations"][0]["attempts"] = [
        {
            "outcome": "retryable_failure",
            "status_code": 503,
            "provider_error_code": "synthetic_transient",
            "requested_delay_ms": 250,
            "applied_delay_ms": 250,
        },
        {"outcome": "success", "status_code": 200},
    ]
    retry_fixture = tmp_path / "retry-history.json"
    retry_fixture.write_text(
        json.dumps(retry_payload, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    outputs = []
    for suffix, override in (("base", None), ("retry", retry_fixture)):
        root = tmp_path / suffix
        bootstrap, bootstrap_governed = _bootstrap(root)
        governed = root / "incremental-governed"
        incremental = run_case(
            root,
            script_name="gmail_incremental_partition_a.json",
            script_path=override,
            start=SECOND_TIME,
            session_started_at=SECOND_TIME,
            prior_checkpoint=bootstrap.result.execution.checkpoint_commit,
            prior_projection_path=projection_path(bootstrap_governed),
            governed_run_root=governed,
        )
        outputs.append((incremental, governed))
    (base, base_root), (retry, retry_root) = outputs
    assert base.result.execution.boundary.payload["capture_set_hash"] != (
        retry.result.execution.boundary.payload["capture_set_hash"]
    )
    assert base.result.execution.boundary.payload["observation_set_hash"] == (
        retry.result.execution.boundary.payload["observation_set_hash"]
    )
    assert gmail_relationship_semantic_projection(base_root) == (
        gmail_relationship_semantic_projection(retry_root)
    )


def test_exact_fixture_replay_produces_identical_immutable_capture_inputs():
    policy = load_gmail_history_policy(
        policy_path(),
        target_label_id=TARGET_LABEL_ID,
        protection_key=PROTECTION_KEY,
        protection_key_id=PROTECTION_KEY_ID,
    )
    script = load_gmail_fixture(
        fixture_path("gmail_bootstrap_nonempty.json"), policy=policy
    )
    first = build_gmail_captured_inputs(
        script,
        policy=policy,
        protection_key=PROTECTION_KEY,
        clock=DeterministicVirtualClock(FIXED_TIME),
    )
    second = build_gmail_captured_inputs(
        script,
        policy=policy,
        protection_key=PROTECTION_KEY,
        clock=DeterministicVirtualClock(FIXED_TIME),
    )
    assert first == second


def test_corrupt_prior_projection_fails_without_checkpoint_advance(tmp_path):
    bootstrap, governed = _bootstrap(tmp_path)
    prior_checkpoint = bootstrap.result.execution.checkpoint_commit
    corrupt = tmp_path / "corrupt-projection.json"
    payload = load_projection(governed)
    payload["projection_hash"] = "sha256:" + "0" * 64
    corrupt.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(GmailHistoryContractError, match="gmail_prior_projection_hash_invalid"):
        run_case(
            tmp_path,
            script_name="gmail_incremental_partition_a.json",
            start=SECOND_TIME,
            session_started_at=SECOND_TIME,
            prior_checkpoint=prior_checkpoint,
            prior_projection_path=corrupt,
            governed_run_root=tmp_path / "corrupt-governed",
        )
    current = resolve_current_checkpoint(bootstrap.result.execution.source_root)
    assert current is not None
    assert current.payload == prior_checkpoint.payload


def test_expiry_preserves_prior_checkpoint_and_recovery_is_explicit(tmp_path):
    bootstrap, bootstrap_governed = _bootstrap(tmp_path)
    incremental_root = tmp_path / "incremental-governed"
    incremental = run_case(
        tmp_path,
        script_name="gmail_incremental_partition_a.json",
        start=SECOND_TIME,
        session_started_at=SECOND_TIME,
        prior_checkpoint=bootstrap.result.execution.checkpoint_commit,
        prior_projection_path=projection_path(bootstrap_governed),
        governed_run_root=incremental_root,
    )
    prior = incremental.result.execution.checkpoint_commit
    expired = run_case(
        tmp_path,
        script_name="gmail_checkpoint_expired.json",
        start=THIRD_TIME,
        session_started_at=THIRD_TIME,
        prior_checkpoint=prior,
        prior_projection_path=projection_path(incremental_root),
        governed_run_root=tmp_path / "expired-governed",
    )
    assert not expired.success and expired.result.status == "checkpoint_expired"
    current = resolve_current_checkpoint(incremental.result.execution.source_root)
    assert current is not None and current.payload == prior.payload
    recovery_root = tmp_path / "recovery-governed"
    recovery = run_case(
        tmp_path,
        script_name="gmail_recovery.json",
        start="2026-08-10T15:00:00Z",
        session_started_at="2026-08-10T15:00:00Z",
        prior_checkpoint=prior,
        prior_projection_path=projection_path(incremental_root),
        governed_run_root=recovery_root,
    )
    assert recovery.success
    projection = load_projection(recovery_root)
    assert projection["coverage_classification"] == "recovery_current_state_history_gap_acknowledged"
    assert [item["transition_kind"] for item in projection["transitions"]] == [
        "recovery_membership_established"
    ]
    assert not any(
        item["transition_kind"] == "mailbox_deleted_while_in_target_scope"
        for item in projection["transitions"]
    )


def test_paginated_expiry_recovery_commits_after_target_enumeration_exhaustion(tmp_path):
    bootstrap, bootstrap_governed = _bootstrap(tmp_path)
    payload = _paginate_target_listing(
        load_fixture("gmail_recovery.json"),
        token="recovery-target-page-2",
    )
    fixture = tmp_path / "paginated-recovery.json"
    fixture.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    governed = tmp_path / "paginated-recovery-governed"
    recovery = run_case(
        tmp_path,
        script_name="gmail_recovery.json",
        script_path=fixture,
        start=SECOND_TIME,
        session_started_at=SECOND_TIME,
        prior_checkpoint=bootstrap.result.execution.checkpoint_commit,
        prior_projection_path=projection_path(bootstrap_governed),
        governed_run_root=governed,
    )
    assert recovery.success
    projection = load_projection(governed)
    assert projection["coverage_classification"] == (
        "recovery_current_state_history_gap_acknowledged"
    )
    assert len(projection["transitions"]) == 2
    assert {item["transition_kind"] for item in projection["transitions"]} == {
        "recovery_membership_established"
    }


def test_ambiguous_recovery_cannot_advance_checkpoint(tmp_path):
    bootstrap, bootstrap_governed = _bootstrap(tmp_path)
    prior = bootstrap.result.execution.checkpoint_commit
    result = run_case(
        tmp_path,
        script_name="gmail_recovery_coverage_unknown.json",
        start=SECOND_TIME,
        session_started_at=SECOND_TIME,
        prior_checkpoint=prior,
        prior_projection_path=projection_path(bootstrap_governed),
        governed_run_root=tmp_path / "ambiguous-recovery",
    )
    assert not result.success and result.result.status == "coverage_unknown"
    current = resolve_current_checkpoint(bootstrap.result.execution.source_root)
    assert current is not None and current.payload == prior.payload


def test_duplicate_typed_event_is_semantically_suppressed(tmp_path):
    payload = load_fixture("gmail_incremental_partition_a.json")
    duplicate = copy.deepcopy(payload["operations"][0]["response"]["history"][0])
    payload["operations"][0]["response"]["history"].insert(1, duplicate)
    duplicate_path = tmp_path / "duplicate-event.json"
    duplicate_path.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    bootstrap, bootstrap_governed = _bootstrap(tmp_path / "case")
    governed = tmp_path / "duplicate-governed"
    result = run_case(
        tmp_path / "case",
        script_name="gmail_incremental_partition_a.json",
        script_path=duplicate_path,
        start=SECOND_TIME,
        session_started_at=SECOND_TIME,
        prior_checkpoint=bootstrap.result.execution.checkpoint_commit,
        prior_projection_path=projection_path(bootstrap_governed),
        governed_run_root=governed,
    )
    assert result.success
    projection = load_projection(governed)
    assert len(projection["transitions"]) == 4
    assert len({item["transition_id"] for item in projection["transitions"]}) == 4
    assert result.result.execution.boundary.payload["counts"]["duplicate_observation_count"] >= 1


def test_projection_policy_file_hash_participates_in_projection_identity(tmp_path):
    governed = tmp_path / "governed"
    result = run_case(
        tmp_path,
        script_name="gmail_bootstrap_nonempty.json",
        governed_run_root=governed,
    )
    base_projection = load_projection(governed)
    copied_policy_path = tmp_path / "policy-copy.json"
    copied_policy_path.write_text(policy_path().read_text(encoding="utf-8") + "\n", encoding="utf-8")
    changed_policy = load_gmail_history_policy(
        copied_policy_path,
        target_label_id=TARGET_LABEL_ID,
        protection_key=PROTECTION_KEY,
        protection_key_id=PROTECTION_KEY_ID,
    )
    changed = build_target_label_projection(
        bounded_material=json.loads(
            result.result.execution.bounded_material.path.read_text(encoding="utf-8")
        ),
        policy=changed_policy,
        prior_projection_path=None,
    )
    assert changed_policy.file_sha256 != base_projection["projection_policy"]["file_sha256"]
    assert changed.artifact["projection_id"] != base_projection["projection_id"]
