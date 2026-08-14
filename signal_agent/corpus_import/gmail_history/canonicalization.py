from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from signal_agent.operational_ingestion.canonical import (
    derive_id,
    sha256_bytes,
    sha256_canonical,
)
from signal_agent.operational_ingestion.models import (
    AcquisitionIntent,
    CanonicalObservation,
    CapturedPage,
    PersistedArtifact,
    PolicyIdentity,
    RequestAttempt,
    SourceIdentity,
)
from signal_agent.operational_ingestion.secrets import assert_secret_free

from .models import (
    GMAIL_FIXTURE_SCHEMA,
    GMAIL_HISTORY_SOURCE_TYPE,
    GmailFixtureOperation,
    GmailFixtureScript,
    GmailHistoryContractError,
    GmailHistoryExpiredError,
    GmailHistoryPolicy,
    MailboxHistoryContinuation,
    PageContinuationToken,
    thaw,
)


Clock = Callable[[], str]

_TOP_LEVEL_FIXTURE_FIELDS = {
    "schema_version",
    "script_id",
    "mode",
    "source_instance_ref",
    "target_label_id",
    "coverage_classification",
    "expected_terminal_history_id",
    "operations",
}
_OPERATION_FIELDS = {"operation", "request", "status_code", "response", "attempts"}
_OPERATIONS = {
    "users.history.list",
    "users.messages.list",
    "users.messages.get",
}
_TYPED_EVENTS = (
    ("messagesAdded", "message_added", 10),
    ("labelsAdded", "labels_added", 20),
    ("labelsRemoved", "labels_removed", 30),
    ("messagesDeleted", "message_deleted", 40),
)
_HISTORY_FIELDS = {
    "id",
    "messages",
    "messagesAdded",
    "messagesDeleted",
    "labelsAdded",
    "labelsRemoved",
}
_MESSAGE_REFERENCE_FIELDS = {"id", "threadId", "labelIds"}


def _require_text(value: Any, code: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        raise GmailHistoryContractError(code)
    return candidate


def _require_exact_fields(value: Mapping[str, Any], allowed: set[str], code: str) -> None:
    if set(value) - allowed:
        raise GmailHistoryContractError(code)


def _protect(key: bytes, namespace: str, kind: str, value: str) -> str:
    material = f"{namespace}:{kind}:{value}".encode("utf-8")
    return "hmac-sha256:" + hmac.new(key, material, hashlib.sha256).hexdigest()


def protect_gmail_value(policy: GmailHistoryPolicy, key: bytes, kind: str, value: str) -> str:
    return _protect(key, str(policy.payload["protection"]["namespace"]), kind, value)


def _hash_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def _policy_identity(policy_id: str, policy: GmailHistoryPolicy) -> PolicyIdentity:
    return PolicyIdentity(
        policy_id=policy_id,
        version=policy.version,
        file_sha256=policy.file_sha256,
    )


def load_gmail_history_policy(
    path: str | Path,
    *,
    target_label_id: str,
    protection_key: bytes,
    protection_key_id: str,
) -> GmailHistoryPolicy:
    policy_path = Path(path).resolve(strict=True)
    raw = policy_path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise GmailHistoryContractError("gmail_policy_unreadable") from exc
    if not isinstance(payload, dict):
        raise GmailHistoryContractError("gmail_policy_object_required")
    if payload.get("schema_version") != "signal_agent.gmail_history_metadata_policy.v1":
        raise GmailHistoryContractError("gmail_policy_schema_invalid")
    if payload.get("source_type") != GMAIL_HISTORY_SOURCE_TYPE:
        raise GmailHistoryContractError("gmail_policy_source_type_invalid")
    if len(protection_key) < 32:
        raise GmailHistoryContractError("gmail_protection_key_too_short")
    label = _require_text(target_label_id, "gmail_target_label_required")
    key_id = _require_text(protection_key_id, "gmail_protection_key_id_required")
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("allowed_headers") != ["From"]:
        raise GmailHistoryContractError("gmail_metadata_header_policy_invalid")
    authorizations = payload.get("authorizations")
    if not isinstance(authorizations, dict) or any(authorizations.values()):
        raise GmailHistoryContractError("gmail_policy_authorization_forbidden")
    assert_secret_free(payload, label="gmail_history_policy")
    file_sha256 = sha256_bytes(raw)
    namespace = str(payload["protection"]["namespace"])
    return GmailHistoryPolicy(
        path=policy_path,
        file_sha256=file_sha256,
        payload=payload,
        target_label_id=label,
        target_label_token=_protect(protection_key, namespace, "label_id", label),
        protection_key_id=key_id,
    )


def _validate_operation_shape(value: Any) -> GmailFixtureOperation:
    if not isinstance(value, dict):
        raise GmailHistoryContractError("gmail_fixture_operation_object_required")
    _require_exact_fields(value, _OPERATION_FIELDS, "gmail_fixture_operation_field_forbidden")
    operation = _require_text(value.get("operation"), "gmail_fixture_operation_required")
    if operation not in _OPERATIONS:
        raise GmailHistoryContractError("gmail_fixture_operation_unsupported")
    request = value.get("request")
    if not isinstance(request, dict):
        raise GmailHistoryContractError("gmail_fixture_request_object_required")
    status_code = value.get("status_code")
    if not isinstance(status_code, int):
        raise GmailHistoryContractError("gmail_fixture_status_code_required")
    response = value.get("response")
    if response is not None and not isinstance(response, dict):
        raise GmailHistoryContractError("gmail_fixture_response_object_required")
    attempts_value = value.get("attempts")
    if attempts_value is None:
        attempts_value = (
            [{"outcome": "success", "status_code": status_code}]
            if status_code == 200
            else [{"outcome": "permanent_failure", "status_code": status_code}]
        )
    if not isinstance(attempts_value, list) or not attempts_value:
        raise GmailHistoryContractError("gmail_fixture_attempts_required")
    attempts: list[Mapping[str, Any]] = []
    for attempt in attempts_value:
        if not isinstance(attempt, dict):
            raise GmailHistoryContractError("gmail_fixture_attempt_object_required")
        allowed = {
            "outcome",
            "status_code",
            "provider_error_code",
            "requested_delay_ms",
            "applied_delay_ms",
        }
        _require_exact_fields(attempt, allowed, "gmail_fixture_attempt_field_forbidden")
        attempts.append(attempt)
    if status_code == 200 and str(attempts[-1].get("outcome")) != "success":
        raise GmailHistoryContractError("gmail_fixture_success_attempt_required")
    return GmailFixtureOperation(
        operation=operation,
        request=request,
        status_code=status_code,
        response=response,
        attempts=tuple(attempts),
    )


def _forbidden_field_scan(value: Any, forbidden: frozenset[str]) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key) in forbidden:
                raise GmailHistoryContractError(f"gmail_provider_field_forbidden:{key}")
            _forbidden_field_scan(child, forbidden)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _forbidden_field_scan(child, forbidden)


def load_gmail_fixture(path: str | Path, *, policy: GmailHistoryPolicy) -> GmailFixtureScript:
    fixture_path = Path(path).resolve(strict=True)
    try:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GmailHistoryContractError("gmail_fixture_unreadable") from exc
    if not isinstance(payload, dict):
        raise GmailHistoryContractError("gmail_fixture_object_required")
    assert_secret_free(payload, label="gmail_history_fixture")
    _require_exact_fields(payload, _TOP_LEVEL_FIXTURE_FIELDS, "gmail_fixture_field_forbidden")
    if payload.get("schema_version") != GMAIL_FIXTURE_SCHEMA:
        raise GmailHistoryContractError("gmail_fixture_schema_invalid")
    if payload.get("target_label_id") != policy.target_label_id:
        raise GmailHistoryContractError("gmail_fixture_target_label_mismatch")
    mode = _require_text(payload.get("mode"), "gmail_fixture_mode_required")
    if mode not in {"bootstrap", "incremental", "recovery", "expired"}:
        raise GmailHistoryContractError("gmail_fixture_mode_unsupported")
    coverage = _require_text(
        payload.get("coverage_classification"),
        "gmail_fixture_coverage_required",
    )
    terminal = payload.get("expected_terminal_history_id")
    if terminal is not None and (not isinstance(terminal, str) or not terminal.isdecimal()):
        raise GmailHistoryContractError("gmail_fixture_terminal_history_id_invalid")
    operations_value = payload.get("operations")
    if not isinstance(operations_value, list) or not operations_value:
        raise GmailHistoryContractError("gmail_fixture_operations_required")
    forbidden = frozenset(str(item) for item in policy.payload["forbidden_provider_fields"])
    _forbidden_field_scan(payload, forbidden)
    operations = tuple(_validate_operation_shape(item) for item in operations_value)
    script = GmailFixtureScript(
        path=fixture_path,
        script_id=_require_text(payload.get("script_id"), "gmail_fixture_script_id_required"),
        mode=mode,
        source_instance_ref=_require_text(
            payload.get("source_instance_ref"),
            "gmail_fixture_source_instance_required",
        ),
        target_label_id=policy.target_label_id,
        coverage_classification=coverage,
        expected_terminal_history_id=terminal,
        operations=operations,
    )
    _validate_script_contract(script, policy=policy)
    maximum_operations = int(policy.payload["bounds"]["maximum_operations"])
    if len(operations_value) > maximum_operations:
        raise GmailHistoryContractError("gmail_fixture_operation_bound_exceeded")
    return script


def _validate_message_reference(value: Any) -> tuple[str, str, tuple[str, ...]]:
    if not isinstance(value, dict):
        raise GmailHistoryContractError("gmail_message_reference_object_required")
    _require_exact_fields(value, _MESSAGE_REFERENCE_FIELDS, "gmail_message_reference_field_forbidden")
    message_id = _require_text(value.get("id"), "gmail_message_id_required")
    thread_id = _require_text(value.get("threadId"), "gmail_thread_id_required")
    labels_value = value.get("labelIds", [])
    if not isinstance(labels_value, list) or any(not isinstance(item, str) or not item for item in labels_value):
        raise GmailHistoryContractError("gmail_label_ids_invalid")
    return message_id, thread_id, tuple(sorted(set(labels_value)))


def _validate_history_response(response: Mapping[str, Any]) -> None:
    _require_exact_fields(
        response,
        {"history", "nextPageToken", "historyId"},
        "gmail_history_response_field_forbidden",
    )
    history = response.get("history", [])
    if not isinstance(history, list):
        raise GmailHistoryContractError("gmail_history_records_invalid")
    next_page_token = response.get("nextPageToken")
    if next_page_token is not None and (
        not isinstance(next_page_token, str) or not next_page_token
    ):
        raise GmailHistoryContractError("gmail_history_page_token_invalid")
    terminal_history_id = response.get("historyId")
    if terminal_history_id is not None and (
        not isinstance(terminal_history_id, str)
        or not terminal_history_id.isdecimal()
    ):
        raise GmailHistoryContractError("gmail_history_terminal_id_invalid")
    for record in history:
        if not isinstance(record, dict):
            raise GmailHistoryContractError("gmail_history_record_object_required")
        _require_exact_fields(record, _HISTORY_FIELDS, "gmail_history_record_field_forbidden")
        record_id = _require_text(record.get("id"), "gmail_history_record_id_required")
        if not record_id.isdecimal():
            raise GmailHistoryContractError("gmail_history_record_id_invalid")
        generic = record.get("messages", [])
        if not isinstance(generic, list):
            raise GmailHistoryContractError("gmail_generic_messages_invalid")
        for item in generic:
            _validate_message_reference(item)
        for provider_name, _event_kind, _rank in _TYPED_EVENTS:
            events = record.get(provider_name, [])
            if not isinstance(events, list):
                raise GmailHistoryContractError("gmail_typed_events_invalid")
            for event in events:
                if not isinstance(event, dict):
                    raise GmailHistoryContractError("gmail_typed_event_object_required")
                allowed = {"message"} if provider_name.startswith("messages") else {"message", "labelIds"}
                _require_exact_fields(event, allowed, "gmail_typed_event_field_forbidden")
                _validate_message_reference(event.get("message"))
                if "labelIds" in allowed:
                    labels = event.get("labelIds")
                    if not isinstance(labels, list) or not labels or any(
                        not isinstance(item, str) or not item for item in labels
                    ):
                        raise GmailHistoryContractError("gmail_typed_event_labels_invalid")


def _validate_messages_list_response(response: Mapping[str, Any]) -> None:
    _require_exact_fields(
        response,
        {"messages", "nextPageToken", "resultSizeEstimate"},
        "gmail_messages_list_response_field_forbidden",
    )
    messages = response.get("messages", [])
    if not isinstance(messages, list):
        raise GmailHistoryContractError("gmail_messages_list_invalid")
    for message in messages:
        if not isinstance(message, dict) or set(message) != {"id", "threadId"}:
            raise GmailHistoryContractError("gmail_messages_list_reference_invalid")
        _require_text(message.get("id"), "gmail_message_id_required")
        _require_text(message.get("threadId"), "gmail_thread_id_required")


def _validate_metadata_response(response: Mapping[str, Any], policy: GmailHistoryPolicy) -> None:
    allowed = set(str(item) for item in policy.payload["metadata"]["allowed_message_fields"])
    if set(response) != allowed:
        raise GmailHistoryContractError("gmail_metadata_message_fields_invalid")
    message_id, _thread_id, _labels = _validate_message_reference(
        {key: response[key] for key in ("id", "threadId", "labelIds")}
    )
    del message_id
    history_id = _require_text(response.get("historyId"), "gmail_metadata_history_id_required")
    internal_date = _require_text(response.get("internalDate"), "gmail_internal_date_required")
    if not history_id.isdecimal() or not internal_date.isdecimal():
        raise GmailHistoryContractError("gmail_metadata_numeric_field_invalid")
    payload = response.get("payload")
    if not isinstance(payload, dict) or set(payload) != {"headers"}:
        raise GmailHistoryContractError("gmail_metadata_payload_invalid")
    headers = payload.get("headers")
    if not isinstance(headers, list) or len(headers) != 1:
        raise GmailHistoryContractError("gmail_metadata_from_header_required")
    header = headers[0]
    if not isinstance(header, dict) or set(header) != {"name", "value"}:
        raise GmailHistoryContractError("gmail_metadata_header_invalid")
    if header.get("name") != "From" or not str(header.get("value") or "").strip():
        raise GmailHistoryContractError("gmail_metadata_header_not_allowlisted")


def _validate_script_contract(script: GmailFixtureScript, *, policy: GmailHistoryPolicy) -> None:
    history_ids: list[int] = []
    expected_page_token: str | None = None
    history_operation_count = 0
    metadata_count = 0
    listed_message_ids: list[str] = []
    metadata_ids: set[str] = set()
    metadata_history_ids: dict[str, str] = {}
    terminal_history_id: str | None = None
    seen_page_tokens: set[str] = set()
    target_list_started = False
    target_list_exhausted = False
    expected_target_page_token: str | None = None
    seen_target_page_tokens: set[str] = set()
    target_page_count = 0
    anchor_lookup_seen = False
    maximum_target_pages = int(
        policy.payload["bounds"].get(
            "maximum_target_label_pages",
            policy.payload["bounds"]["maximum_operations"],
        )
    )
    for operation in script.operations:
        if operation.status_code == 404:
            if script.mode != "expired" or operation.operation != "users.history.list":
                raise GmailHistoryContractError("gmail_expiry_shape_invalid")
            continue
        if script.mode in {"bootstrap", "recovery"}:
            if not target_list_started and operation.operation != "users.messages.list":
                raise GmailHistoryContractError("gmail_bootstrap_target_list_required")
            if (
                expected_target_page_token is not None
                and operation.operation != "users.messages.list"
            ):
                raise GmailHistoryContractError(
                    "gmail_target_list_page_token_chain_invalid"
                )
        if operation.status_code != 200 or operation.response is None:
            raise GmailHistoryContractError("gmail_fixture_success_response_required")
        request = thaw(operation.request)
        response = thaw(operation.response)
        if operation.operation == "users.history.list":
            history_operation_count += 1
            if "labelId" in request or "historyTypes" in request:
                raise GmailHistoryContractError("gmail_filtered_history_forbidden")
            if set(request) - {"startHistoryId", "pageToken", "maxResults"}:
                raise GmailHistoryContractError("gmail_history_request_field_forbidden")
            if script.mode not in {"incremental", "expired"}:
                raise GmailHistoryContractError("gmail_history_operation_mode_invalid")
            if "startHistoryId" not in request:
                raise GmailHistoryContractError("gmail_history_start_required")
            if not str(request["startHistoryId"]).isdecimal():
                raise GmailHistoryContractError("gmail_history_start_invalid")
            supplied_page = request.get("pageToken")
            if expected_page_token != supplied_page:
                raise GmailHistoryContractError("gmail_history_page_token_chain_invalid")
            _validate_history_response(response)
            for record in response.get("history", []):
                history_ids.append(int(record["id"]))
            next_page_token = response.get("nextPageToken")
            if next_page_token is not None:
                if next_page_token in seen_page_tokens:
                    raise GmailHistoryContractError("gmail_history_pagination_cycle")
                seen_page_tokens.add(next_page_token)
            expected_page_token = next_page_token
            if expected_page_token is None:
                terminal_history_id = str(response.get("historyId") or "") or None
        elif operation.operation == "users.messages.list":
            if script.mode not in {"bootstrap", "recovery"}:
                raise GmailHistoryContractError("gmail_messages_list_mode_invalid")
            if set(request) - {"labelIds", "pageToken", "maxResults"}:
                raise GmailHistoryContractError("gmail_messages_list_request_field_forbidden")
            _validate_messages_list_response(response)
            labels = request.get("labelIds")
            supplied_page = request.get("pageToken")
            if expected_target_page_token is not None and (
                labels != [policy.target_label_id]
                or supplied_page != expected_target_page_token
            ):
                raise GmailHistoryContractError(
                    "gmail_target_list_page_token_chain_invalid"
                )
            if labels is not None:
                if labels != [policy.target_label_id]:
                    raise GmailHistoryContractError("gmail_bootstrap_target_list_required")
                if target_list_exhausted:
                    raise GmailHistoryContractError("gmail_target_list_after_terminal")
                if not target_list_started:
                    if supplied_page is not None:
                        raise GmailHistoryContractError(
                            "gmail_target_list_initial_page_token_forbidden"
                        )
                    target_list_started = True
                elif supplied_page != expected_target_page_token:
                    raise GmailHistoryContractError(
                        "gmail_target_list_page_token_chain_invalid"
                    )
                if supplied_page is not None:
                    if supplied_page in seen_target_page_tokens:
                        raise GmailHistoryContractError(
                            "gmail_target_list_page_token_replayed"
                        )
                    seen_target_page_tokens.add(str(supplied_page))
                target_page_count += 1
                if target_page_count > maximum_target_pages:
                    raise GmailHistoryContractError(
                        "gmail_target_list_page_bound_exceeded"
                    )
                next_target_page = response.get("nextPageToken")
                if next_target_page is not None:
                    if next_target_page in seen_target_page_tokens:
                        raise GmailHistoryContractError(
                            "gmail_target_list_pagination_cycle"
                        )
                    expected_target_page_token = str(next_target_page)
                else:
                    expected_target_page_token = None
                    target_list_exhausted = True
            else:
                if expected_target_page_token is not None:
                    raise GmailHistoryContractError(
                        "gmail_target_list_page_token_chain_invalid"
                    )
                if not target_list_exhausted:
                    raise GmailHistoryContractError(
                        "gmail_target_list_terminal_page_required"
                    )
                if anchor_lookup_seen:
                    raise GmailHistoryContractError("gmail_anchor_lookup_repeated")
                if listed_message_ids:
                    raise GmailHistoryContractError(
                        "gmail_anchor_lookup_target_not_empty"
                    )
                if supplied_page is not None or request.get("maxResults") != 1:
                    raise GmailHistoryContractError("gmail_anchor_lookup_bound_invalid")
                if len(response.get("messages", [])) > 1:
                    raise GmailHistoryContractError("gmail_anchor_lookup_result_bound_exceeded")
                anchor_lookup_seen = True
            listed_message_ids.extend(str(item["id"]) for item in response.get("messages", []))
        elif operation.operation == "users.messages.get":
            metadata_count += 1
            if request.get("format") != "METADATA" or request.get("metadataHeaders") != ["From"]:
                raise GmailHistoryContractError("gmail_metadata_request_contract_invalid")
            if set(request) != {"id", "format", "metadataHeaders"}:
                raise GmailHistoryContractError("gmail_metadata_request_field_forbidden")
            _validate_metadata_response(response, policy)
            if response.get("id") != request.get("id"):
                raise GmailHistoryContractError("gmail_metadata_request_identity_mismatch")
            metadata_ids.add(str(response["id"]))
            metadata_history_ids[str(response["id"])] = str(response["historyId"])
    if history_ids != sorted(history_ids):
        raise GmailHistoryContractError("gmail_history_order_invalid")
    if len(history_ids) > int(policy.payload["bounds"]["maximum_history_records"]):
        raise GmailHistoryContractError("gmail_history_record_bound_exceeded")
    if history_operation_count and expected_page_token is not None:
        raise GmailHistoryContractError("gmail_history_terminal_page_missing")
    if metadata_count > int(policy.payload["bounds"]["maximum_metadata_lookups"]):
        raise GmailHistoryContractError("gmail_metadata_lookup_bound_exceeded")
    if script.mode in {"bootstrap", "recovery"}:
        if not target_list_started:
            raise GmailHistoryContractError("gmail_bootstrap_target_list_required")
        if expected_target_page_token is not None or not target_list_exhausted:
            raise GmailHistoryContractError("gmail_target_list_terminal_page_required")
        missing = set(listed_message_ids) - metadata_ids
        if missing:
            raise GmailHistoryContractError("gmail_bootstrap_metadata_lookup_missing")
        if listed_message_ids:
            if script.expected_terminal_history_id != metadata_history_ids[listed_message_ids[0]]:
                raise GmailHistoryContractError("gmail_bootstrap_anchor_mismatch")
        elif script.expected_terminal_history_id is not None:
            raise GmailHistoryContractError("gmail_bootstrap_anchor_without_message")
    if script.mode == "expired":
        if len(script.operations) != 1 or script.operations[0].status_code != 404:
            raise GmailHistoryContractError("gmail_expiry_operation_required")
        if script.expected_terminal_history_id is not None:
            raise GmailHistoryContractError("gmail_expiry_terminal_history_forbidden")
    elif script.coverage_classification not in {
        *policy.eligible_coverage,
        "coverage_unknown",
        "unsupported_bootstrap_continuation",
    }:
        raise GmailHistoryContractError("gmail_coverage_classification_unsupported")
    if script.mode == "incremental" and terminal_history_id != script.expected_terminal_history_id:
        raise GmailHistoryContractError("gmail_terminal_history_id_mismatch")


def history_request_from_continuation(
    continuation: MailboxHistoryContinuation,
) -> dict[str, str]:
    if not isinstance(continuation, MailboxHistoryContinuation):
        raise GmailHistoryContractError("gmail_history_continuation_type_required")
    return {"startHistoryId": continuation.value}


def page_request_from_continuation(continuation: PageContinuationToken) -> dict[str, str]:
    if not isinstance(continuation, PageContinuationToken):
        raise GmailHistoryContractError("gmail_page_continuation_type_required")
    return {"pageToken": continuation.value}


def _safe_request(operation: GmailFixtureOperation) -> dict[str, Any]:
    request = thaw(operation.request)
    return {
        "endpoint_id": operation.operation,
        "parameter_names": sorted(request),
        "parameter_hashes": {
            key: sha256_canonical(request[key]) for key in sorted(request)
        },
        "method": "GET",
    }


def _safe_page_continuation(token: str) -> dict[str, str]:
    return {
        "kind": "gmail_page_continuation_token",
        "value_sha256": _hash_text(PageContinuationToken(token).value),
    }


def _safe_history_continuation(value: str, policy: GmailHistoryPolicy, key: bytes) -> dict[str, str]:
    continuation = MailboxHistoryContinuation(value)
    return {
        "kind": "gmail_mailbox_history_continuation",
        "classification": "protected_operational_reference",
        "value_hmac": protect_gmail_value(policy, key, "history_continuation", continuation.value),
        "value_sha256": _hash_text(continuation.value),
    }


def _internal_date(value: str) -> str:
    parsed = datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    return parsed.isoformat().replace("+00:00", "Z")


def _message_parts(
    message: Mapping[str, Any], policy: GmailHistoryPolicy, key: bytes
) -> tuple[str, str, tuple[str, ...]]:
    message_id, thread_id, labels = _validate_message_reference(
        {field: message[field] for field in _MESSAGE_REFERENCE_FIELDS}
    )
    return (
        protect_gmail_value(policy, key, "message_id", message_id),
        protect_gmail_value(policy, key, "thread_id", thread_id),
        tuple(sorted(protect_gmail_value(policy, key, "label_id", item) for item in labels)),
    )


def _history_observations(
    response: Mapping[str, Any], policy: GmailHistoryPolicy, key: bytes
) -> tuple[CanonicalObservation, ...]:
    observations: list[tuple[tuple[Any, ...], CanonicalObservation]] = []
    for record in response.get("history", []):
        history_id = str(record["id"])
        history_hash = _hash_text(history_id)
        for provider_name, event_kind, rank in _TYPED_EVENTS:
            for event in record.get(provider_name, []):
                message_hmac, thread_hmac, message_labels = _message_parts(
                    event["message"], policy, key
                )
                affected = tuple(
                    sorted(
                        protect_gmail_value(policy, key, "label_id", str(item))
                        for item in event.get("labelIds", [])
                    )
                )
                event_material = {
                    "history_record_id_sha256": history_hash,
                    "history_sequence": int(history_id),
                    "event_kind": event_kind,
                    "message_id_hmac": message_hmac,
                    "thread_id_hmac": thread_hmac,
                    "affected_label_hmacs": list(affected),
                    "message_label_hmacs": list(message_labels),
                    "within_history_order": {
                        "rule": "event_kind_rank_then_protected_identity.v1",
                        "provider_temporal_order_claimed": False,
                        "rank": rank,
                    },
                }
                provider_event_id = derive_id(
                    "ghe",
                    "gmail_history_typed_event.v1",
                    event_material,
                )
                semantic = {
                    **event_material,
                    "provider_event_id": provider_event_id,
                    "generic_history_message_effect_created": False,
                }
                observation = CanonicalObservation(
                    record_type="gmail_history_typed_event",
                    protected_source_record_id=message_hmac,
                    protection=policy.protection,
                    semantic_payload=semantic,
                )
                observations.append(
                    ((int(history_id), rank, message_hmac, affected, provider_event_id), observation)
                )
    return tuple(item for _key, item in sorted(observations, key=lambda pair: pair[0]))


def _metadata_observation(
    response: Mapping[str, Any], policy: GmailHistoryPolicy, key: bytes
) -> CanonicalObservation:
    message_hmac, thread_hmac, label_hmacs = _message_parts(response, policy, key)
    header = response["payload"]["headers"][0]
    from_value = " ".join(str(header["value"]).split())
    semantic = {
        "metadata_observation_id": derive_id(
            "gmo",
            "gmail_message_metadata.v1",
            message_hmac,
            _hash_text(str(response["historyId"])),
            _hash_text(str(response["internalDate"])),
            label_hmacs,
            protect_gmail_value(policy, key, "from_header", from_value.casefold()),
        ),
        "message_id_hmac": message_hmac,
        "thread_id_hmac": thread_hmac,
        "message_history_id_sha256": _hash_text(str(response["historyId"])),
        "internal_date_epoch_ms_sha256": _hash_text(str(response["internalDate"])),
        "label_hmacs": list(label_hmacs),
        "from_header_hmac": protect_gmail_value(
            policy, key, "from_header", from_value.casefold()
        ),
        "approved_header_names": ["From"],
        "clear_header_values_retained": False,
        "metadata_format": "METADATA",
    }
    return CanonicalObservation(
        record_type="gmail_message_metadata",
        protected_source_record_id=message_hmac,
        protection=policy.protection,
        semantic_payload=semantic,
        source_event_time=_internal_date(str(response["internalDate"])),
    )


def _operation_observations(
    operation: GmailFixtureOperation, policy: GmailHistoryPolicy, key: bytes
) -> tuple[CanonicalObservation, ...]:
    if operation.response is None:
        return ()
    response = thaw(operation.response)
    if operation.operation == "users.history.list":
        return _history_observations(response, policy, key)
    if operation.operation == "users.messages.get":
        return (_metadata_observation(response, policy, key),)
    return ()


def _attempts_for_operation(
    *,
    operation: GmailFixtureOperation,
    page_ordinal: int,
    request_fingerprint: str,
    continuation_hash: str,
    clock: Clock,
) -> tuple[RequestAttempt, ...]:
    attempts: list[RequestAttempt] = []
    for attempt_ordinal, value in enumerate(operation.attempts, start=1):
        material = thaw(value)
        started_at = clock()
        completed_at = clock()
        attempts.append(
            RequestAttempt(
                page_ordinal=page_ordinal,
                attempt_ordinal=attempt_ordinal,
                request_fingerprint=request_fingerprint,
                continuation_hash=continuation_hash,
                started_at=started_at,
                completed_at=completed_at,
                outcome=str(material["outcome"]),
                status_code=int(material.get("status_code", operation.status_code)),
                provider_error_code=(
                    None
                    if material.get("provider_error_code") is None
                    else str(material["provider_error_code"])
                ),
                requested_delay_ms=int(material.get("requested_delay_ms", 0)),
                applied_delay_ms=int(material.get("applied_delay_ms", 0)),
                response_metadata={"endpoint_id": operation.operation},
            )
        )
    return tuple(attempts)


def build_gmail_captured_inputs(
    script: GmailFixtureScript,
    *,
    policy: GmailHistoryPolicy,
    protection_key: bytes,
    clock: Clock,
) -> tuple[tuple[RequestAttempt, ...], tuple[CapturedPage, ...]]:
    if script.mode == "expired":
        raise GmailHistoryExpiredError("gmail_history_checkpoint_expired")
    if script.expected_terminal_history_id is None:
        terminal_value = "0"
    else:
        terminal_value = script.expected_terminal_history_id
    all_attempts: list[RequestAttempt] = []
    pages: list[CapturedPage] = []
    previous_continuation: dict[str, Any] = {"kind": "gmail_acquisition_root"}
    total_response_bytes = 0
    for page_ordinal, operation in enumerate(script.operations, start=1):
        if operation.status_code != 200 or operation.response is None:
            raise GmailHistoryContractError("gmail_successful_capture_required")
        safe_request = _safe_request(operation)
        request_fingerprint = sha256_canonical(safe_request)
        continuation_hash = sha256_canonical(previous_continuation)
        attempts = _attempts_for_operation(
            operation=operation,
            page_ordinal=page_ordinal,
            request_fingerprint=request_fingerprint,
            continuation_hash=continuation_hash,
            clock=clock,
        )
        all_attempts.extend(attempts)
        response = thaw(operation.response)
        body = (
            json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        total_response_bytes += len(body)
        if total_response_bytes > int(policy.payload["bounds"]["maximum_response_bytes"]):
            raise GmailHistoryContractError("gmail_response_byte_bound_exceeded")
        is_last = page_ordinal == len(script.operations)
        if is_last:
            next_continuation = (
                {"kind": "gmail_bootstrap_continuation_unavailable"}
                if script.expected_terminal_history_id is None
                else _safe_history_continuation(terminal_value, policy, protection_key)
            )
        else:
            page_token = response.get("nextPageToken")
            if page_token is not None:
                next_continuation = _safe_page_continuation(str(page_token))
            else:
                next_operation = script.operations[page_ordinal]
                next_continuation = {
                    "kind": "gmail_required_offline_operation",
                    "endpoint_id": next_operation.operation,
                    "request_fingerprint": sha256_canonical(_safe_request(next_operation)),
                }
        successful_ordinal = next(
            index
            for index, attempt in enumerate(attempts, start=1)
            if attempt.outcome == "success"
        )
        pages.append(
            CapturedPage(
                page_ordinal=page_ordinal,
                successful_attempt_ordinal=successful_ordinal,
                request_fingerprint=request_fingerprint,
                continuation_hash=continuation_hash,
                response_body=body,
                response_schema=(
                    "gmail.users.history.list.response.v1"
                    if operation.operation == "users.history.list"
                    else (
                        "gmail.users.messages.list.response.v1"
                        if operation.operation == "users.messages.list"
                        else "gmail.users.messages.get.metadata.response.v1"
                    )
                ),
                media_type="application/json",
                captured_at=clock(),
                terminal=is_last,
                next_continuation=next_continuation,
                observations=_operation_observations(operation, policy, protection_key),
                response_metadata={
                    "endpoint_id": operation.operation,
                    "provider_kind": "gmail_offline_fixture",
                    "status_code": 200,
                },
            )
        )
        previous_continuation = next_continuation
    return tuple(all_attempts), tuple(pages)


def build_expired_attempt(
    script: GmailFixtureScript,
    *,
    clock: Clock,
) -> RequestAttempt:
    if script.mode != "expired":
        raise GmailHistoryContractError("gmail_expired_script_required")
    operation = script.operations[0]
    safe_request = _safe_request(operation)
    return RequestAttempt(
        page_ordinal=1,
        attempt_ordinal=1,
        request_fingerprint=sha256_canonical(safe_request),
        continuation_hash=sha256_canonical({"kind": "gmail_committed_history_start"}),
        started_at=clock(),
        completed_at=clock(),
        outcome="permanent_failure",
        status_code=404,
        provider_error_code="gmail_history_checkpoint_expired",
        response_metadata={"endpoint_id": operation.operation},
    )


def build_gmail_intent(
    script: GmailFixtureScript,
    *,
    policy: GmailHistoryPolicy,
    protection_key: bytes,
    prior_checkpoint: PersistedArtifact | None,
) -> AcquisitionIntent:
    source_instance_ref = protect_gmail_value(
        policy, protection_key, "source_instance", script.source_instance_ref
    )
    source_instance_id = derive_id(
        "gsi",
        GMAIL_HISTORY_SOURCE_TYPE,
        source_instance_ref,
        policy.target_label_token,
        policy.file_sha256,
    )
    first_request = thaw(script.operations[0].request)
    lower = (
        _hash_text(str(first_request["startHistoryId"]))
        if "startHistoryId" in first_request
        else "root"
    )
    upper = (
        "unavailable"
        if script.expected_terminal_history_id is None
        else _hash_text(script.expected_terminal_history_id)
    )
    prior_id = None if prior_checkpoint is None else str(prior_checkpoint.payload["checkpoint_id"])
    prior_hash = None if prior_checkpoint is None else str(prior_checkpoint.payload["artifact_hash"])
    return AcquisitionIntent(
        source=SourceIdentity(
            source_type=GMAIL_HISTORY_SOURCE_TYPE,
            source_instance_id=source_instance_id,
        ),
        adapter=_policy_identity("gmail_history_offline_adapter.v1", policy),
        acquisition_policy=_policy_identity("gmail_history_offline_acquisition.v1", policy),
        assembly_policy=_policy_identity("gmail_history_provider_observation_assembly.v1", policy),
        retry_policy=_policy_identity("gmail_history_offline_retry.v1", policy),
        secret_policy=_policy_identity("gmail_history_offline_secret_boundary.v1", policy),
        observation_boundary={
            "kind": f"gmail_{script.mode}:{script.coverage_classification}",
            "lower": lower,
            "upper": upper,
        },
        credential_profile_ref="gmail-offline-fixture-profile",
        authentication_mode="offline_fixture_no_auth",
        prior_checkpoint_id=prior_id,
        prior_checkpoint_hash=prior_hash,
    )
