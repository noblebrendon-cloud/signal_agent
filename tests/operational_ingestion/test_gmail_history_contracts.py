from __future__ import annotations

import copy
import json

import pytest

from signal_agent.corpus_import.gmail_history import (
    GmailHistoryContractError,
    MailboxHistoryContinuation,
    PageContinuationToken,
    build_gmail_captured_inputs,
    load_gmail_fixture,
    load_gmail_history_policy,
)
from signal_agent.corpus_import.gmail_history.canonicalization import (
    history_request_from_continuation,
    page_request_from_continuation,
)
from signal_agent.operational_ingestion.errors import SecretBoundaryError
from signal_agent.operational_ingestion.simulator import DeterministicVirtualClock

from .gmail_test_support import (
    FIXED_TIME,
    PROTECTION_KEY,
    PROTECTION_KEY_ID,
    TARGET_LABEL_ID,
    fixture_path,
    load_fixture,
    policy_path,
    write_fixture,
)


def _policy():
    return load_gmail_history_policy(
        policy_path(),
        target_label_id=TARGET_LABEL_ID,
        protection_key=PROTECTION_KEY,
        protection_key_id=PROTECTION_KEY_ID,
    )


def _paginate_target_listing(payload, *, token="target-page-2"):
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


@pytest.mark.parametrize(
    "name,mode",
    [
        ("gmail_bootstrap_nonempty.json", "bootstrap"),
        ("gmail_bootstrap_empty_target.json", "bootstrap"),
        ("gmail_bootstrap_empty_mailbox.json", "bootstrap"),
        ("gmail_bootstrap_coverage_unknown.json", "bootstrap"),
        ("gmail_incremental_partition_a.json", "incremental"),
        ("gmail_incremental_partition_b.json", "incremental"),
        ("gmail_checkpoint_expired.json", "expired"),
        ("gmail_recovery.json", "recovery"),
        ("gmail_recovery_coverage_unknown.json", "recovery"),
    ],
)
def test_reviewed_offline_fixtures_are_contract_valid(name, mode):
    assert load_gmail_fixture(fixture_path(name), policy=_policy()).mode == mode


def test_history_requests_are_unfiltered_and_typed_events_ignore_generic_messages():
    policy = _policy()
    script = load_gmail_fixture(
        fixture_path("gmail_incremental_partition_a.json"), policy=policy
    )
    for operation in script.operations:
        if operation.operation == "users.history.list":
            assert "labelId" not in operation.request
            assert "historyTypes" not in operation.request
    _attempts, pages = build_gmail_captured_inputs(
        script,
        policy=policy,
        protection_key=PROTECTION_KEY,
        clock=DeterministicVirtualClock(FIXED_TIME),
    )
    observations = [item for page in pages for item in page.observations]
    assert len([item for item in observations if item.record_type == "gmail_history_typed_event"]) == 8
    assert all(
        item.semantic_payload.get("generic_history_message_effect_created") is False
        for item in observations
        if item.record_type == "gmail_history_typed_event"
    )


def test_history_ids_may_be_noncontiguous_but_remain_numerically_ordered():
    policy = _policy()
    script = load_gmail_fixture(
        fixture_path("gmail_incremental_partition_a.json"), policy=policy
    )
    _attempts, pages = build_gmail_captured_inputs(
        script,
        policy=policy,
        protection_key=PROTECTION_KEY,
        clock=DeterministicVirtualClock(FIXED_TIME),
    )
    sequence = [
        item.semantic_payload["history_sequence"]
        for page in pages
        for item in page.observations
        if item.record_type == "gmail_history_typed_event"
    ]
    assert sequence == sorted(sequence)
    assert 102 not in sequence and 249 not in sequence


def test_page_and_history_continuations_are_not_interchangeable():
    assert history_request_from_continuation(MailboxHistoryContinuation("300")) == {
        "startHistoryId": "300"
    }
    assert page_request_from_continuation(PageContinuationToken("opaque-page")) == {
        "pageToken": "opaque-page"
    }
    with pytest.raises(GmailHistoryContractError, match="history_continuation_type_required"):
        history_request_from_continuation(PageContinuationToken("300"))  # type: ignore[arg-type]
    with pytest.raises(GmailHistoryContractError, match="page_continuation_type_required"):
        page_request_from_continuation(MailboxHistoryContinuation("300"))  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["snippet", "raw", "sizeEstimate"])
def test_forbidden_message_fields_fail_closed(tmp_path, field):
    payload = load_fixture("gmail_bootstrap_nonempty.json")
    payload["operations"][1]["response"][field] = "prohibited"
    path = write_fixture(tmp_path / "forbidden.json", payload)
    with pytest.raises(GmailHistoryContractError, match=f"gmail_provider_field_forbidden:{field}"):
        load_gmail_fixture(path, policy=_policy())


@pytest.mark.parametrize("field", ["body", "parts", "attachmentId"])
def test_forbidden_nested_payload_fields_fail_closed(tmp_path, field):
    payload = load_fixture("gmail_bootstrap_nonempty.json")
    payload["operations"][1]["response"]["payload"][field] = {}
    path = write_fixture(tmp_path / "forbidden-nested.json", payload)
    with pytest.raises(GmailHistoryContractError, match=f"gmail_provider_field_forbidden:{field}"):
        load_gmail_fixture(path, policy=_policy())


def test_non_from_header_is_rejected(tmp_path):
    payload = load_fixture("gmail_bootstrap_nonempty.json")
    payload["operations"][1]["response"]["payload"]["headers"][0]["name"] = "Subject"
    path = write_fixture(tmp_path / "subject.json", payload)
    with pytest.raises(GmailHistoryContractError, match="gmail_metadata_header_not_allowlisted"):
        load_gmail_fixture(path, policy=_policy())


def test_metadata_request_cannot_expand_header_allowlist(tmp_path):
    payload = load_fixture("gmail_bootstrap_nonempty.json")
    payload["operations"][1]["request"]["metadataHeaders"] = ["From", "Subject"]
    path = write_fixture(tmp_path / "expanded-headers.json", payload)
    with pytest.raises(GmailHistoryContractError, match="gmail_metadata_request_contract_invalid"):
        load_gmail_fixture(path, policy=_policy())


@pytest.mark.parametrize("parameter", ["labelId", "historyTypes"])
def test_incremental_history_filters_are_forbidden(tmp_path, parameter):
    payload = load_fixture("gmail_incremental_partition_a.json")
    payload["operations"][0]["request"][parameter] = "Label_TARGET"
    path = write_fixture(tmp_path / "filtered.json", payload)
    with pytest.raises(GmailHistoryContractError, match="gmail_filtered_history_forbidden"):
        load_gmail_fixture(path, policy=_policy())


def test_history_page_token_chain_must_be_exact(tmp_path):
    payload = load_fixture("gmail_incremental_partition_a.json")
    payload["operations"][1]["request"]["pageToken"] = "wrong-token"
    path = write_fixture(tmp_path / "wrong-page-token.json", payload)
    with pytest.raises(GmailHistoryContractError, match="gmail_history_page_token_chain_invalid"):
        load_gmail_fixture(path, policy=_policy())


def test_terminal_history_id_must_match_contract(tmp_path):
    payload = load_fixture("gmail_incremental_partition_a.json")
    payload["operations"][1]["response"]["historyId"] = "301"
    path = write_fixture(tmp_path / "wrong-terminal.json", payload)
    with pytest.raises(GmailHistoryContractError, match="gmail_terminal_history_id_mismatch"):
        load_gmail_fixture(path, policy=_policy())


def test_bootstrap_anchor_must_come_from_first_listed_message(tmp_path):
    payload = load_fixture("gmail_bootstrap_nonempty.json")
    payload["expected_terminal_history_id"] = "80"
    path = write_fixture(tmp_path / "wrong-anchor.json", payload)
    with pytest.raises(GmailHistoryContractError, match="gmail_bootstrap_anchor_mismatch"):
        load_gmail_fixture(path, policy=_policy())


def test_two_page_target_bootstrap_contract_requires_exact_exhaustion(tmp_path):
    payload = _paginate_target_listing(load_fixture("gmail_bootstrap_nonempty.json"))
    path = write_fixture(tmp_path / "two-page-bootstrap.json", payload)
    script = load_gmail_fixture(path, policy=_policy())
    assert [operation.request.get("pageToken") for operation in script.operations[:2]] == [
        None,
        "target-page-2",
    ]


def test_dangling_bootstrap_target_page_token_fails_closed(tmp_path):
    payload = load_fixture("gmail_bootstrap_nonempty.json")
    payload["operations"][0]["response"]["nextPageToken"] = "missing-page"
    payload["operations"] = payload["operations"][:1]
    path = write_fixture(tmp_path / "dangling-bootstrap.json", payload)
    with pytest.raises(
        GmailHistoryContractError,
        match="gmail_target_list_terminal_page_required",
    ):
        load_gmail_fixture(path, policy=_policy())


def test_wrong_bootstrap_target_page_token_fails_closed(tmp_path):
    payload = _paginate_target_listing(load_fixture("gmail_bootstrap_nonempty.json"))
    payload["operations"][1]["request"]["pageToken"] = "wrong-page"
    path = write_fixture(tmp_path / "wrong-bootstrap-token.json", payload)
    with pytest.raises(
        GmailHistoryContractError,
        match="gmail_target_list_page_token_chain_invalid",
    ):
        load_gmail_fixture(path, policy=_policy())


def test_repeated_bootstrap_target_page_token_is_rejected_as_cycle(tmp_path):
    payload = _paginate_target_listing(load_fixture("gmail_bootstrap_nonempty.json"))
    payload["operations"][1]["response"]["nextPageToken"] = "target-page-2"
    path = write_fixture(tmp_path / "bootstrap-token-cycle.json", payload)
    with pytest.raises(
        GmailHistoryContractError,
        match="gmail_target_list_pagination_cycle",
    ):
        load_gmail_fixture(path, policy=_policy())


def test_missing_intermediate_bootstrap_page_fails_closed(tmp_path):
    payload = _paginate_target_listing(load_fixture("gmail_bootstrap_nonempty.json"))
    payload["operations"].pop(1)
    path = write_fixture(tmp_path / "missing-intermediate-page.json", payload)
    with pytest.raises(
        GmailHistoryContractError,
        match="gmail_target_list_page_token_chain_invalid",
    ):
        load_gmail_fixture(path, policy=_policy())


def test_malformed_intermediate_bootstrap_page_fails_closed(tmp_path):
    payload = _paginate_target_listing(load_fixture("gmail_bootstrap_nonempty.json"))
    payload["operations"][1]["response"]["messages"] = {"id": "malformed"}
    path = write_fixture(tmp_path / "malformed-intermediate-page.json", payload)
    with pytest.raises(GmailHistoryContractError, match="gmail_messages_list_invalid"):
        load_gmail_fixture(path, policy=_policy())


def test_bootstrap_target_page_count_is_bounded(tmp_path):
    payload = load_fixture("gmail_bootstrap_nonempty.json")
    initial = copy.deepcopy(payload["operations"][0])
    pages = []
    for ordinal in range(25):
        token = f"target-page-{ordinal + 1}"
        next_token = f"target-page-{ordinal + 2}"
        page = copy.deepcopy(initial)
        page["request"] = {"labelIds": [TARGET_LABEL_ID]}
        if ordinal:
            page["request"]["pageToken"] = token
        page["response"]["messages"] = []
        if ordinal < 24:
            page["response"]["nextPageToken"] = next_token
        else:
            page["response"].pop("nextPageToken", None)
        pages.append(page)
    payload["operations"] = pages
    path = write_fixture(tmp_path / "page-bound-exceeded.json", payload)
    with pytest.raises(GmailHistoryContractError, match="gmail_target_list_page_bound_exceeded"):
        load_gmail_fixture(path, policy=_policy())


def test_dangling_recovery_target_page_token_fails_closed(tmp_path):
    payload = load_fixture("gmail_recovery.json")
    payload["operations"][0]["response"]["nextPageToken"] = "missing-recovery-page"
    payload["operations"] = payload["operations"][:1]
    path = write_fixture(tmp_path / "dangling-recovery.json", payload)
    with pytest.raises(
        GmailHistoryContractError,
        match="gmail_target_list_terminal_page_required",
    ):
        load_gmail_fixture(path, policy=_policy())


def test_recovery_target_page_token_cycle_fails_closed(tmp_path):
    payload = _paginate_target_listing(
        load_fixture("gmail_recovery.json"),
        token="recovery-page-2",
    )
    payload["operations"][1]["response"]["nextPageToken"] = "recovery-page-2"
    path = write_fixture(tmp_path / "recovery-token-cycle.json", payload)
    with pytest.raises(
        GmailHistoryContractError,
        match="gmail_target_list_pagination_cycle",
    ):
        load_gmail_fixture(path, policy=_policy())


def test_target_result_size_estimate_does_not_prove_exhaustion(tmp_path):
    payload = load_fixture("gmail_bootstrap_nonempty.json")
    payload["operations"][0]["response"]["resultSizeEstimate"] = 0
    payload["operations"][0]["response"]["nextPageToken"] = "still-not-terminal"
    payload["operations"] = payload["operations"][:1]
    path = write_fixture(tmp_path / "result-estimate-not-terminal.json", payload)
    with pytest.raises(
        GmailHistoryContractError,
        match="gmail_target_list_terminal_page_required",
    ):
        load_gmail_fixture(path, policy=_policy())


def test_fixture_secret_canary_is_rejected(tmp_path):
    payload = copy.deepcopy(load_fixture("gmail_bootstrap_nonempty.json"))
    payload["operations"][0]["attempts"] = [
        {"outcome": "success", "status_code": 200, "provider_error_code": "Bearer abcdefgh12345678"}
    ]
    path = write_fixture(tmp_path / "secret.json", payload)
    with pytest.raises(SecretBoundaryError, match="secret_boundary_violation"):
        load_gmail_fixture(path, policy=_policy())


def test_policy_is_read_only_and_denies_all_authorizations():
    payload = json.loads(policy_path().read_text(encoding="utf-8"))
    assert payload["metadata"]["format"] == "METADATA"
    assert payload["metadata"]["allowed_headers"] == ["From"]
    assert payload["authorizations"] and not any(payload["authorizations"].values())


def test_repeated_next_page_token_is_rejected_as_pagination_cycle(tmp_path):
    payload = load_fixture("gmail_incremental_partition_b.json")
    payload["operations"][1]["response"]["nextPageToken"] = "partition-b-middle"
    path = write_fixture(tmp_path / "cycle.json", payload)
    with pytest.raises(GmailHistoryContractError, match="gmail_history_pagination_cycle"):
        load_gmail_fixture(path, policy=_policy())


def test_missing_terminal_history_id_fails_closed(tmp_path):
    payload = load_fixture("gmail_incremental_partition_a.json")
    payload["operations"][1]["response"].pop("historyId")
    path = write_fixture(tmp_path / "missing-terminal.json", payload)
    with pytest.raises(GmailHistoryContractError, match="gmail_terminal_history_id_mismatch"):
        load_gmail_fixture(path, policy=_policy())


def test_empty_terminal_history_page_is_valid(tmp_path):
    payload = load_fixture("gmail_incremental_partition_a.json")
    payload["operations"][1]["response"]["history"] = []
    path = write_fixture(tmp_path / "empty-terminal.json", payload)
    assert load_gmail_fixture(path, policy=_policy()).mode == "incremental"


def test_malformed_history_collection_is_rejected(tmp_path):
    payload = load_fixture("gmail_incremental_partition_a.json")
    payload["operations"][0]["response"]["history"] = {"id": "101"}
    path = write_fixture(tmp_path / "malformed-history.json", payload)
    with pytest.raises(GmailHistoryContractError, match="gmail_history_records_invalid"):
        load_gmail_fixture(path, policy=_policy())


@pytest.mark.parametrize(
    ("fixture_name", "operation_index", "field", "error"),
    [
        (
            "gmail_incremental_partition_a.json",
            0,
            "q",
            "gmail_history_request_field_forbidden",
        ),
        (
            "gmail_bootstrap_nonempty.json",
            0,
            "q",
            "gmail_messages_list_request_field_forbidden",
        ),
    ],
)
def test_provider_request_descriptors_use_exact_allowlists(
    tmp_path, fixture_name, operation_index, field, error
):
    payload = load_fixture(fixture_name)
    payload["operations"][operation_index]["request"][field] = "synthetic-query"
    path = write_fixture(tmp_path / "overbroad-request.json", payload)
    with pytest.raises(GmailHistoryContractError, match=error):
        load_gmail_fixture(path, policy=_policy())


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("authorization", "Basic synthetic-secret"),
        ("access_token", "ya29.synthetic-access-token"),
        ("refresh_token", "synthetic-refresh-token"),
        ("client_secret", "synthetic-client-secret"),
        ("cookie", "session=synthetic"),
        ("oauth_code", "synthetic-oauth-code"),
        ("pkce_verifier", "synthetic-pkce-verifier"),
        ("signed_url", "https://synthetic.invalid/read?signature=abcdefghi"),
    ],
)
def test_secret_key_classes_are_rejected_before_fixture_acceptance(tmp_path, key, value):
    payload = load_fixture("gmail_bootstrap_nonempty.json")
    payload[key] = value
    path = write_fixture(tmp_path / f"secret-{key}.json", payload)
    with pytest.raises(SecretBoundaryError, match="secret_key_prohibited"):
        load_gmail_fixture(path, policy=_policy())


@pytest.mark.parametrize(
    "value",
    [
        "Bearer abcdefgh123456789",
        "api_key=synthetic-key-value",
        "https://synthetic.invalid/read?oauth_code=abcdefghi",
    ],
)
def test_secret_value_patterns_are_rejected(tmp_path, value):
    payload = load_fixture("gmail_bootstrap_nonempty.json")
    payload["source_instance_ref"] = value
    path = write_fixture(tmp_path / "secret-value.json", payload)
    with pytest.raises(SecretBoundaryError, match="secret_boundary_violation"):
        load_gmail_fixture(path, policy=_policy())


def test_wire_member_order_does_not_change_metadata_observation_identity(tmp_path):
    payload = load_fixture("gmail_bootstrap_nonempty.json")
    response = payload["operations"][1]["response"]
    payload["operations"][1]["response"] = {
        key: response[key] for key in reversed(tuple(response))
    }
    reordered = write_fixture(tmp_path / "reordered.json", payload)
    policy = _policy()
    base_script = load_gmail_fixture(
        fixture_path("gmail_bootstrap_nonempty.json"), policy=policy
    )
    reordered_script = load_gmail_fixture(reordered, policy=policy)
    _attempts, base_pages = build_gmail_captured_inputs(
        base_script,
        policy=policy,
        protection_key=PROTECTION_KEY,
        clock=DeterministicVirtualClock(FIXED_TIME),
    )
    _attempts, reordered_pages = build_gmail_captured_inputs(
        reordered_script,
        policy=policy,
        protection_key=PROTECTION_KEY,
        clock=DeterministicVirtualClock(FIXED_TIME),
    )
    assert base_pages[1].observations[0].semantic_dict() == (
        reordered_pages[1].observations[0].semantic_dict()
    )
    assert base_pages[1].response_body != reordered_pages[1].response_body


def test_changed_approved_metadata_changes_observation_identity(tmp_path):
    payload = load_fixture("gmail_bootstrap_nonempty.json")
    payload["operations"][1]["response"]["payload"]["headers"][0]["value"] = (
        "Changed Fixture <changed@synthetic.invalid>"
    )
    changed = write_fixture(tmp_path / "changed.json", payload)
    policy = _policy()
    base = load_gmail_fixture(fixture_path("gmail_bootstrap_nonempty.json"), policy=policy)
    variant = load_gmail_fixture(changed, policy=policy)
    _attempts, base_pages = build_gmail_captured_inputs(
        base, policy=policy, protection_key=PROTECTION_KEY,
        clock=DeterministicVirtualClock(FIXED_TIME)
    )
    _attempts, variant_pages = build_gmail_captured_inputs(
        variant, policy=policy, protection_key=PROTECTION_KEY,
        clock=DeterministicVirtualClock(FIXED_TIME)
    )
    assert base_pages[1].observations[0].observation_id != (
        variant_pages[1].observations[0].observation_id
    )
