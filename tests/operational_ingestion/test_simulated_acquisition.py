from __future__ import annotations

import json
from pathlib import Path

import pytest

from signal_agent.operational_ingestion.simulator import (
    DeterministicVirtualClock,
    SimulatedAcquisitionCoordinator,
    SimulatedAcquisitionInterrupted,
    SimulatedOperationalTransport,
    SimulatedPermanentFailure,
    SimulatedRemoteInteractionSource,
    SimulatedRetryExhausted,
    build_simulated_intent,
    load_retry_policy,
    load_simulated_script,
)
from signal_agent.operational_ingestion.errors import SecretBoundaryError
from signal_agent.relationship_signals.simulated_operational_pipeline import (
    relationship_semantic_projection,
)

from .simulated_test_support import (
    FIXED_TIME,
    PROTECTION_KEY,
    PROTECTION_KEY_ID,
    SECOND_TIME,
    current_checkpoint,
    load_fixture,
    normalized_records,
    run_case,
    tree,
    write_script,
)


def test_base_acquisition_exercises_pagination_retry_dedup_change_and_tombstone(
    tmp_path: Path, repository_root: Path
) -> None:
    result = run_case(repository_root, tmp_path)
    execution = result.execution
    boundary = execution.ingestion.boundary.payload
    bounded = execution.ingestion.bounded_material.payload

    assert result.success is True
    assert [item.outcome for item in execution.attempts] == [
        "success",
        "rate_limited",
        "success",
        "success",
    ]
    assert execution.retry_count == 1
    assert execution.requested_delay_ms == 1200
    assert len(execution.pages) == 3
    assert execution.pages[-1].terminal is True
    assert dict(boundary["counts"]) == {
        "captured_record_count": 6,
        "canonical_observation_count": 5,
        "duplicate_observation_count": 1,
        "changed_observation_count": 2,
        "observation_version_count": 5,
        "source_record_identity_count": 3,
        "tombstone_observation_count": 1,
    }
    observations = bounded["observations"]
    assert len(observations) == 5
    assert len({item["observation_id"] for item in observations}) == 5
    duplicate = next(
        refs
        for refs in boundary["observation_capture_provenance"].values()
        if len(refs) == 2
    )
    assert {item["page_ordinal"] for item in duplicate} == {1, 2}
    changed = [
        item
        for item in observations
        if item["supersedes_observation_id"] is not None
    ]
    assert len(changed) == 2
    tombstone = next(item for item in observations if item["observation_state"] == "tombstone")
    assert tombstone["supersedes_observation_id"] is not None
    assert current_checkpoint(execution.ingestion.source_root) is not None


def test_identical_script_clock_and_policy_are_byte_reproducible(
    tmp_path: Path, repository_root: Path
) -> None:
    first = run_case(repository_root, tmp_path / "a")
    second = run_case(repository_root, tmp_path / "b")
    assert tree(tmp_path / "a" / "store") == tree(tmp_path / "b" / "store")
    assert tree(tmp_path / "a" / "governed") == tree(tmp_path / "b" / "governed")
    assert first.execution.ingestion.checkpoint_commit.payload == second.execution.ingestion.checkpoint_commit.payload


def test_retry_history_changes_capture_not_semantic_evidence(
    tmp_path: Path, repository_root: Path
) -> None:
    retried = run_case(repository_root, tmp_path / "retried")
    direct = run_case(
        repository_root,
        tmp_path / "direct",
        script_name="base_no_retry_script.json",
    )
    left = retried.execution.ingestion.boundary.payload
    right = direct.execution.ingestion.boundary.payload
    assert left["capture_set_hash"] != right["capture_set_hash"]
    assert left["observation_set_hash"] == right["observation_set_hash"]
    assert relationship_semantic_projection(tmp_path / "retried" / "governed") == relationship_semantic_projection(tmp_path / "direct" / "governed")


def test_page_partition_changes_capture_not_semantic_evidence(
    tmp_path: Path, repository_root: Path
) -> None:
    first = run_case(repository_root, tmp_path / "a", script_name="partition_a_script.json")
    second = run_case(repository_root, tmp_path / "b", script_name="partition_b_script.json")
    a = first.execution.ingestion.boundary.payload
    b = second.execution.ingestion.boundary.payload
    assert a["capture_set_hash"] != b["capture_set_hash"]
    assert a["observation_set_hash"] == b["observation_set_hash"]
    assert relationship_semantic_projection(tmp_path / "a" / "governed") == relationship_semantic_projection(tmp_path / "b" / "governed")


@pytest.mark.parametrize("interrupt_after", [1, 2])
def test_verified_partial_capture_reuse_loses_nothing_and_advances_only_at_commit(
    tmp_path: Path, repository_root: Path, interrupt_after: int
) -> None:
    with pytest.raises(SimulatedAcquisitionInterrupted) as caught:
        run_case(
            repository_root,
            tmp_path,
            interrupt_after_pages=interrupt_after,
        )
    partial = caught.value.partial
    assert current_checkpoint(partial.source_root) is None
    policy = load_retry_policy(
        repository_root / "config/operational_ingestion/retry_policy_v1.json"
    )
    script = load_simulated_script(
        repository_root / "tests/fixtures/operational_ingestion/base_script.json"
    )
    recovering_source = SimulatedRemoteInteractionSource(
        script=script,
        protection_key=PROTECTION_KEY,
        protection_key_id=PROTECTION_KEY_ID,
    )
    recovering_coordinator = SimulatedAcquisitionCoordinator(
        tmp_path / "store",
        clock=DeterministicVirtualClock(SECOND_TIME),
        retry_policy=policy,
    )
    recovered = recovering_coordinator.recover_partial(
        intent=partial.intent,
        source=recovering_source,
        session_started_at=partial.session_started_at,
    )
    assert recovered.next_request == partial.next_request
    assert [item.observation_id for page in recovered.pages for item in page.observations] == [
        item.observation_id for page in partial.pages for item in page.observations
    ]
    resumed = run_case(repository_root, tmp_path, resume=recovered)
    assert current_checkpoint(partial.source_root).payload["checkpoint_id"] == resumed.execution.ingestion.checkpoint_commit.payload["checkpoint_id"]
    assert len(normalized_records(tmp_path / "governed")) == 5
    assert resumed.execution.ingestion.boundary.payload["counts"]["duplicate_observation_count"] == 1


def test_conservative_full_reacquisition_from_committed_predecessor(
    tmp_path: Path, repository_root: Path
) -> None:
    store = tmp_path / "store"
    seed = run_case(
        repository_root,
        tmp_path / "cycle-0",
        operational_store_root=store,
    )
    prior = seed.execution.ingestion.checkpoint_commit
    with pytest.raises(SimulatedAcquisitionInterrupted):
        run_case(
            repository_root,
            tmp_path / "cycle-1-partial",
            prior_checkpoint=prior,
            start=SECOND_TIME,
            interrupt_after_pages=2,
            operational_store_root=store,
        )
    source_root = seed.execution.ingestion.source_root
    assert current_checkpoint(source_root).payload["checkpoint_id"] == prior.payload["checkpoint_id"]
    completed = run_case(
        repository_root,
        tmp_path / "cycle-1-full",
        prior_checkpoint=prior,
        start="2026-08-10T14:00:00Z",
        operational_store_root=store,
    )
    assert current_checkpoint(source_root).payload["checkpoint_id"] == completed.execution.ingestion.checkpoint_commit.payload["checkpoint_id"]
    assert completed.execution.ingestion.boundary.payload["observation_set_hash"] == seed.execution.ingestion.boundary.payload["observation_set_hash"]
    assert len(normalized_records(tmp_path / "cycle-1-full" / "governed")) == 5


@pytest.mark.parametrize(
    ("outcome", "status", "expected"),
    [
        ("permanent_failure", 403, SimulatedPermanentFailure),
        ("retryable_failure", 503, SimulatedRetryExhausted),
    ],
)
def test_permanent_and_exhausted_transport_fail_without_checkpoint(
    tmp_path: Path,
    repository_root: Path,
    outcome: str,
    status: int,
    expected: type[Exception],
) -> None:
    script = load_fixture(repository_root)
    script["pages"][0]["outcomes"] = [
        {
            "outcome": outcome,
            "status_code": status,
            "provider_error_code": "simulated_failure",
        }
    ]
    path = write_script(tmp_path / "failure.json", script)
    with pytest.raises(expected):
        run_case(repository_root, tmp_path / "case", script_path=path)
    assert not list((tmp_path / "case" / "store").rglob("checkpoint-commit.json"))


def test_generic_transport_interruption_persists_sanitized_failure_only(
    tmp_path: Path, repository_root: Path
) -> None:
    script = load_fixture(repository_root)
    script["pages"][0]["outcomes"] = [
        {
            "outcome": "interruption",
            "status_code": None,
            "private_error_detail": "Bearer PRIVATE_CANARY_123456789",
        }
    ]
    path = write_script(tmp_path / "interruption.json", script)
    with pytest.raises(SimulatedAcquisitionInterrupted):
        run_case(repository_root, tmp_path / "case", script_path=path)
    persisted = b"".join(tree(tmp_path / "case").values())
    assert b"PRIVATE_CANARY" not in persisted
    assert not list((tmp_path / "case" / "store").rglob("checkpoint-commit.json"))


def test_empty_terminal_page_is_valid_and_absence_is_not_deletion(
    tmp_path: Path, repository_root: Path
) -> None:
    script = load_fixture(repository_root, "base_no_retry_script.json")
    terminal = script["pages"][-1]["outcomes"][0]["page"]
    terminal["records"] = []
    path = write_script(tmp_path / "empty-terminal.json", script)
    result = run_case(repository_root, tmp_path / "case", script_path=path)
    records = normalized_records(tmp_path / "case" / "governed")
    assert len(records) == 3
    assert all(item["relationship"]["observation_state"] != "tombstone" for item in records)
    assert result.execution.pages[-1].terminal is True


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("malformed", "simulated_success_response_malformed"),
        ("empty_nonterminal", "simulated_empty_nonterminal_page_invalid"),
        ("repeated_cursor", "simulated_pagination_cycle"),
    ],
)
def test_invalid_successful_response_and_pagination_fail_closed(
    tmp_path: Path, repository_root: Path, mutation: str, message: str
) -> None:
    script = load_fixture(repository_root, "base_no_retry_script.json")
    if mutation == "malformed":
        script["pages"][0]["outcomes"][0].pop("page")
        script["pages"][0]["outcomes"][0]["raw_body"] = "{not-json"
    elif mutation == "empty_nonterminal":
        script["pages"][0]["outcomes"][0]["page"]["records"] = []
    else:
        script["pages"][1]["outcomes"][0]["page"]["next_cursor"] = "cursor-1"
    path = write_script(tmp_path / f"{mutation}.json", script)
    with pytest.raises(Exception, match=message):
        run_case(repository_root, tmp_path / "case", script_path=path)
    assert not list((tmp_path / "case" / "store").rglob("checkpoint-commit.json"))


def test_longer_pagination_cycle_is_rejected(tmp_path: Path, repository_root: Path) -> None:
    script = load_fixture(repository_root, "base_no_retry_script.json")
    final_page = script["pages"][-1]["outcomes"][0]["page"]
    final_page["terminal"] = False
    final_page["next_cursor"] = "cursor-1"
    path = write_script(tmp_path / "pagination-cycle.json", script)
    with pytest.raises(SimulatedPermanentFailure, match="simulated_pagination_cycle"):
        run_case(repository_root, tmp_path / "case", script_path=path)
    assert not list((tmp_path / "case" / "store").rglob("checkpoint-commit.json"))


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"maximum_pages": 2}, "simulated_maximum_page_bound_exhausted"),
        ({"maximum_records": 4}, "simulated_maximum_record_bound_exhausted"),
        ({"maximum_response_bytes": 100}, "simulated_response_size_bound_exhausted"),
    ],
)
def test_explicit_acquisition_bounds_fail_closed(
    tmp_path: Path, repository_root: Path, kwargs: dict[str, int], message: str
) -> None:
    with pytest.raises(Exception, match=message):
        run_case(repository_root, tmp_path, **kwargs)
    assert not list((tmp_path / "store").rglob("checkpoint-commit.json"))


def test_normalized_records_use_protected_identity_and_capture_provenance(
    tmp_path: Path, repository_root: Path
) -> None:
    run_case(repository_root, tmp_path)
    records = normalized_records(tmp_path / "governed")
    assert len(records) == 5
    serialized = json.dumps(records, sort_keys=True)
    for clear_id in ('"R1"', '"R2"', '"R3"'):
        assert clear_id not in serialized
    for record in records:
        assert record["privacy"]["clear_source_record_id_retained"] is False
        assert record["source_provenance"]["capture_provenance_resolution"] == "source_receipt_observation_map"
        assert record["identifiers"][0]["value"].startswith("hmac-sha256:")
        assert record["source_provenance"]["observation_id"]


def test_exact_page_replay_has_stable_request_response_and_observation_identity(
    repository_root: Path,
) -> None:
    script = load_simulated_script(
        repository_root / "tests/fixtures/operational_ingestion/base_script.json"
    )
    policy = load_retry_policy(
        repository_root / "config/operational_ingestion/retry_policy_v1.json"
    )
    source = SimulatedRemoteInteractionSource(
        script=script,
        protection_key=PROTECTION_KEY,
        protection_key_id=PROTECTION_KEY_ID,
    )
    intent = build_simulated_intent(
        source_instance_id=script.source_instance_id,
        retry_policy=policy,
    )
    request = source.initial_request(intent)
    first_outcome = SimulatedOperationalTransport(script).fetch(request)
    first = source.assess_response(
        request=request,
        outcome=first_outcome,
        attempt_ordinal=1,
        captured_at=DeterministicVirtualClock(FIXED_TIME)(),
    )
    source.reset()
    replay_outcome = SimulatedOperationalTransport(script).fetch(request)
    replay = source.assess_response(
        request=request,
        outcome=replay_outcome,
        attempt_ordinal=1,
        captured_at=DeterministicVirtualClock(FIXED_TIME)(),
    )
    assert request.request_fingerprint == source.initial_request(intent).request_fingerprint
    assert first.response_body == replay.response_body
    assert [item.observation_id for item in first.observations] == [
        item.observation_id for item in replay.observations
    ]


@pytest.mark.parametrize(
    "canary",
    [
        "Authorization: Bearer AUTHORIZATION_CANARY_123456",
        "Bearer BEARER_CANARY_123456789",
        "api_key=API_KEY_CANARY_123456",
        "refresh_token=REFRESH_CANARY_123456",
        "client_secret=CLIENT_SECRET_CANARY_123456",
        "https://example.invalid/capture?signature=SIGNED_URL_CANARY_123456",
        "https://example.invalid/capture?api_key=QUERY_KEY_CANARY_123456",
        "Cookie: session=SESSION_COOKIE_CANARY_123456",
        "https://example.invalid/callback?oauth_code=OAUTH_CODE_CANARY_123456",
        "https://example.invalid/callback?code_verifier=PKCE_CANARY_123456",
        "access_token=ERROR_RESPONSE_CANARY_123456",
    ],
)
def test_secret_bearing_success_response_fails_closed_without_persistence(
    tmp_path: Path, repository_root: Path, canary: str
) -> None:
    script = load_fixture(repository_root)
    outcome = script["pages"][0]["outcomes"][0]
    outcome.pop("page")
    outcome["raw_body"] = canary
    path = write_script(tmp_path / "secret.json", script)
    with pytest.raises(SecretBoundaryError):
        run_case(repository_root, tmp_path / "case", script_path=path)
    persisted = b"".join(tree(tmp_path / "case").values())
    assert canary.encode("utf-8") not in persisted
    assert not list((tmp_path / "case" / "store").rglob("checkpoint-commit.json"))


def test_retry_policy_is_versioned_bounded_and_uses_virtual_time(
    repository_root: Path,
) -> None:
    policy = load_retry_policy(
        repository_root / "config/operational_ingestion/retry_policy_v1.json"
    )
    assert policy.identity.policy_id == "simulated_operational_retry_policy"
    assert policy.identity.version == "1.0.0"
    assert policy.maximum_attempts == 3
    assert policy.maximum_elapsed_ms == 30000
    assert policy.retry_after_mode == "maximum_of_backoff_and_retry_after"
    first = policy.delay_ms(
        request_fingerprint="sha256:" + "1" * 64,
        attempt_ordinal=1,
        retry_after_ms=1200,
    )
    second = policy.delay_ms(
        request_fingerprint="sha256:" + "1" * 64,
        attempt_ordinal=1,
        retry_after_ms=1200,
    )
    assert first == second == 1200
