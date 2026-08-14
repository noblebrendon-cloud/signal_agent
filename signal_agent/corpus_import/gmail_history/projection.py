from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from signal_agent.operational_ingestion.canonical import (
    derive_id,
    seal,
    sha256_canonical,
    verify_seal,
)

from .models import (
    GMAIL_HISTORY_SOURCE_TYPE,
    GMAIL_PROJECTION_SCHEMA,
    GmailHistoryContractError,
    GmailHistoryCoverageError,
    GmailHistoryPolicy,
    GmailProjectionResult,
)


def _load_prior_projection(
    path: str | Path | None,
    *,
    policy: GmailHistoryPolicy,
    source: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]]]:
    if path is None:
        return None, {}
    prior_path = Path(path).resolve(strict=True)
    try:
        prior = json.loads(prior_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GmailHistoryContractError("gmail_prior_projection_unreadable") from exc
    if not isinstance(prior, dict):
        raise GmailHistoryContractError("gmail_prior_projection_object_required")
    if prior.get("schema_version") != GMAIL_PROJECTION_SCHEMA:
        raise GmailHistoryContractError("gmail_prior_projection_schema_invalid")
    if not verify_seal(prior, "projection_hash"):
        raise GmailHistoryContractError("gmail_prior_projection_hash_invalid")
    if prior.get("source") != dict(source):
        raise GmailHistoryContractError("gmail_prior_projection_source_mismatch")
    if prior.get("projection_policy") != policy.projection_policy:
        raise GmailHistoryContractError("gmail_prior_projection_policy_mismatch")
    if prior.get("target_label_ref") != {
        "label_id_hmac": policy.target_label_token,
        "clear_label_id_retained": False,
    }:
        raise GmailHistoryContractError("gmail_prior_projection_label_mismatch")
    states_value = prior.get("final_states")
    if not isinstance(states_value, list):
        raise GmailHistoryContractError("gmail_prior_projection_states_invalid")
    states: dict[str, dict[str, Any]] = {}
    for item in states_value:
        if not isinstance(item, dict):
            raise GmailHistoryContractError("gmail_prior_projection_state_invalid")
        message_id = str(item.get("message_id_hmac") or "")
        if not message_id or message_id in states:
            raise GmailHistoryContractError("gmail_prior_projection_state_identity_invalid")
        states[message_id] = dict(item)
    return (
        {
            "projection_id": prior["projection_id"],
            "projection_hash": prior["projection_hash"],
            "path_ref": f"gmail-projection:{prior['projection_id']}",
        },
        states,
    )


def _transition(
    *,
    policy: GmailHistoryPolicy,
    message_id_hmac: str,
    prior_state: str,
    resulting_state: str,
    transition_kind: str,
    provider_observation_id: str,
    provider_observation_hash: str,
    provider_event_id: str,
    history_record_id_sha256: str | None,
    prior_transition_id: str | None,
    sender_hmac: str | None,
    thread_id_hmac: str | None,
    occurred_at: str | None,
) -> dict[str, Any]:
    material = {
        "schema_version": "signal_agent.gmail_target_label_transition.v1",
        "projection_policy": policy.projection_policy,
        "target_label_ref": {
            "label_id_hmac": policy.target_label_token,
            "clear_label_id_retained": False,
        },
        "message_id_hmac": message_id_hmac,
        "prior_state": prior_state,
        "resulting_state": resulting_state,
        "transition_kind": transition_kind,
        "provider_observation": {
            "observation_id": provider_observation_id,
            "content_hash": provider_observation_hash,
            "provider_event_id": provider_event_id,
            "history_record_id_sha256": history_record_id_sha256,
            "capture_provenance_resolution": "source_receipt_observation_map",
        },
        "prior_transition_id": prior_transition_id,
        "sender_identity_hmac": sender_hmac,
        "thread_id_hmac": thread_id_hmac,
        "occurred_at": occurred_at,
        "automatic_merge_performed": False,
        "provider_native_projection_claimed": False,
    }
    transition_id = derive_id(
        "gtlt",
        "signal_agent.gmail_target_label_transition.v1",
        material,
    )
    return seal({**material, "transition_id": transition_id}, "transition_hash")


def _metadata_map(
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for observation in observations:
        if observation.get("record_type") != "gmail_message_metadata":
            continue
        message_id = str(observation["protected_source_record_id"])
        existing = result.get(message_id)
        value = dict(observation)
        if existing is not None and existing != value:
            raise GmailHistoryContractError("gmail_metadata_observation_conflict")
        result[message_id] = value
    return result


def _state_from_metadata(
    observation: Mapping[str, Any], policy: GmailHistoryPolicy
) -> tuple[str, str | None, str | None, str | None]:
    semantic = observation["semantic_payload"]
    labels = set(str(item) for item in semantic.get("label_hmacs", []))
    return (
        "inside" if policy.target_label_token in labels else "outside",
        str(semantic.get("from_header_hmac") or "") or None,
        str(semantic.get("thread_id_hmac") or "") or None,
        str(observation.get("source_event_time") or "") or None,
    )


def build_target_label_projection(
    *,
    bounded_material: Mapping[str, Any],
    policy: GmailHistoryPolicy,
    prior_projection_path: str | Path | None,
) -> GmailProjectionResult:
    if bounded_material.get("source", {}).get("source_type") != GMAIL_HISTORY_SOURCE_TYPE:
        raise GmailHistoryContractError("gmail_bounded_source_type_mismatch")
    source = dict(bounded_material["source"])
    kind = str(bounded_material.get("observation_boundary", {}).get("kind") or "")
    try:
        coverage = kind.split(":", 1)[1]
    except IndexError as exc:
        raise GmailHistoryContractError("gmail_bounded_coverage_missing") from exc
    if coverage in {"coverage_unknown", "unsupported_bootstrap_continuation"}:
        raise GmailHistoryCoverageError(coverage)
    if coverage not in policy.eligible_coverage:
        raise GmailHistoryCoverageError("gmail_coverage_not_checkpoint_eligible")
    observations_value = bounded_material.get("observations")
    if not isinstance(observations_value, list):
        raise GmailHistoryContractError("gmail_bounded_observations_invalid")
    observations = [dict(item) for item in observations_value]
    prior_ref, states = _load_prior_projection(
        prior_projection_path,
        policy=policy,
        source=source,
    )
    metadata = _metadata_map(observations)
    transitions: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    is_bootstrap = kind.startswith("gmail_bootstrap") or kind.startswith("gmail_recovery")
    if is_bootstrap:
        for message_id in sorted(metadata):
            observation = metadata[message_id]
            state, sender_hmac, thread_hmac, occurred_at = _state_from_metadata(
                observation, policy
            )
            previous = states.get(message_id)
            prior_state = "unknown" if previous is None else str(previous["state"])
            if state == "inside" and prior_state != "inside":
                transition = _transition(
                    policy=policy,
                    message_id_hmac=message_id,
                    prior_state=prior_state,
                    resulting_state="inside",
                    transition_kind=(
                        "recovery_membership_established"
                        if kind.startswith("gmail_recovery")
                        else "bootstrap_membership_established"
                    ),
                    provider_observation_id=str(observation["observation_id"]),
                    provider_observation_hash=str(observation["content_hash"]),
                    provider_event_id=str(
                        observation["semantic_payload"]["metadata_observation_id"]
                    ),
                    history_record_id_sha256=None,
                    prior_transition_id=(
                        None if previous is None else previous.get("last_transition_id")
                    ),
                    sender_hmac=sender_hmac,
                    thread_id_hmac=thread_hmac,
                    occurred_at=occurred_at,
                )
                transitions.append(transition)
                states[message_id] = {
                    "message_id_hmac": message_id,
                    "state": "inside",
                    "last_transition_id": transition["transition_id"],
                    "sender_identity_hmac": sender_hmac,
                    "thread_id_hmac": thread_hmac,
                }
            elif previous is None:
                states[message_id] = {
                    "message_id_hmac": message_id,
                    "state": state,
                    "last_transition_id": None,
                    "sender_identity_hmac": sender_hmac,
                    "thread_id_hmac": thread_hmac,
                }

    typed_events = [
        item for item in observations if item.get("record_type") == "gmail_history_typed_event"
    ]
    typed_events.sort(
        key=lambda item: (
            int(item["semantic_payload"]["history_sequence"]),
            int(item["semantic_payload"]["within_history_order"]["rank"]),
            str(item["semantic_payload"]["provider_event_id"]),
        )
    )
    for observation in typed_events:
        semantic = observation["semantic_payload"]
        message_id = str(observation["protected_source_record_id"])
        event_kind = str(semantic["event_kind"])
        affected = set(str(item) for item in semantic.get("affected_label_hmacs", []))
        message_labels = set(str(item) for item in semantic.get("message_label_hmacs", []))
        previous = states.get(message_id)
        prior_state = "unknown" if previous is None else str(previous["state"])
        metadata_observation = metadata.get(message_id)
        sender_hmac = None if previous is None else previous.get("sender_identity_hmac")
        thread_hmac = str(semantic.get("thread_id_hmac") or "") or None
        occurred_at = None
        if metadata_observation is not None:
            _metadata_state, metadata_sender, metadata_thread, metadata_time = _state_from_metadata(
                metadata_observation, policy
            )
            sender_hmac = metadata_sender or sender_hmac
            thread_hmac = metadata_thread or thread_hmac
            occurred_at = metadata_time

        transition_kind: str | None = None
        resulting_state = prior_state
        if event_kind == "message_added" and (
            policy.target_label_token in message_labels
            or (
                metadata_observation is not None
                and policy.target_label_token
                in set(metadata_observation["semantic_payload"].get("label_hmacs", []))
            )
        ):
            if prior_state != "inside":
                transition_kind = "entered_target_label"
                resulting_state = "inside"
        elif event_kind == "labels_added" and policy.target_label_token in affected:
            if prior_state != "inside":
                transition_kind = "entered_target_label"
                resulting_state = "inside"
        elif event_kind == "labels_removed" and policy.target_label_token in affected:
            if prior_state == "inside":
                transition_kind = "left_target_label"
                resulting_state = "outside"
            elif prior_state == "unknown":
                unresolved.append(
                    {
                        "message_id_hmac": message_id,
                        "provider_observation_id": observation["observation_id"],
                        "classification": "target_label_departure_prior_state_unknown",
                        "effect_emitted": False,
                    }
                )
        elif event_kind == "message_deleted":
            if prior_state == "inside":
                transition_kind = "mailbox_deleted_while_in_target_scope"
                resulting_state = "deleted"
            elif prior_state == "unknown":
                unresolved.append(
                    {
                        "message_id_hmac": message_id,
                        "provider_observation_id": observation["observation_id"],
                        "classification": "mailbox_deletion_target_relevance_unknown",
                        "effect_emitted": False,
                    }
                )
        if transition_kind is None:
            continue
        transition = _transition(
            policy=policy,
            message_id_hmac=message_id,
            prior_state=prior_state,
            resulting_state=resulting_state,
            transition_kind=transition_kind,
            provider_observation_id=str(observation["observation_id"]),
            provider_observation_hash=str(observation["content_hash"]),
            provider_event_id=str(semantic["provider_event_id"]),
            history_record_id_sha256=str(semantic["history_record_id_sha256"]),
            prior_transition_id=(
                None if previous is None else previous.get("last_transition_id")
            ),
            sender_hmac=None if sender_hmac is None else str(sender_hmac),
            thread_id_hmac=thread_hmac,
            occurred_at=occurred_at,
        )
        transitions.append(transition)
        states[message_id] = {
            "message_id_hmac": message_id,
            "state": resulting_state,
            "last_transition_id": transition["transition_id"],
            "sender_identity_hmac": sender_hmac,
            "thread_id_hmac": thread_hmac,
        }

    transitions.sort(key=lambda item: item["transition_id"])
    final_states = [states[key] for key in sorted(states)]
    unresolved.sort(
        key=lambda item: (item["message_id_hmac"], item["provider_observation_id"])
    )
    semantic_material = {
        "source": source,
        "projection_policy": policy.projection_policy,
        "target_label_ref": {
            "label_id_hmac": policy.target_label_token,
            "clear_label_id_retained": False,
        },
        "prior_projection": prior_ref,
        "coverage_classification": coverage,
        "transitions": transitions,
        "final_states": final_states,
        "unresolved_relevance": unresolved,
        "provider_observation_set_hash": bounded_material["observation_set_hash"],
    }
    projection_set_hash = sha256_canonical(semantic_material)
    projection_id = derive_id(
        "gtlp",
        GMAIL_PROJECTION_SCHEMA,
        projection_set_hash,
    )
    artifact = seal(
        {
            "schema_version": GMAIL_PROJECTION_SCHEMA,
            "projection_id": projection_id,
            **semantic_material,
            "target_label_projection_set_hash": projection_set_hash,
            "semantic_identity_excludes": [
                "acquisition_time",
                "capture_ids",
                "capture_set_hash",
                "page_boundaries",
                "request_attempts",
                "retry_history",
            ],
        },
        "projection_hash",
    )
    records = tuple(
        item
        for item in transitions
        if item["transition_kind"]
        in {
            "bootstrap_membership_established",
            "recovery_membership_established",
            "entered_target_label",
            "left_target_label",
            "mailbox_deleted_while_in_target_scope",
        }
    )
    return GmailProjectionResult(artifact=artifact, records=records)

