from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

from app.retention.dispatch import plan_dispatch
from app.retention.identity import get_repo_root, sha256_hex
from app.retention.jsonl_store import REQUIRED_STATE_FILES, compute_record_hash


EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
LEDGER_ORDER = {name: index for index, name in enumerate(REQUIRED_STATE_FILES)}
ISSUE_ORDER = {
    "missing_ledger_file": 0,
    "invalid_jsonl_record": 1,
    "non_dict_jsonl_record": 2,
    "record_hash_mismatch": 3,
    "prev_hash_mismatch": 4,
    "raw_identifier_leakage": 5,
    "event_without_transition": 6,
    "transition_without_required_contact_snapshot": 7,
    "contact_snapshot_without_prior_event": 8,
    "contact_snapshot_references_unknown_first_touch_event": 9,
    "dispatch_without_valid_contact_state": 10,
}


def resolve_state_root(state_root: str | Path, *, repo_root: Path | None = None) -> Path:
    root = repo_root or get_repo_root()
    candidate = Path(state_root)
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


def _issue(issue_type: str, ledger: str, *, line_number: int | None = None, **fields: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "issue_type": issue_type,
        "ledger": ledger,
    }
    if line_number is not None:
        payload["line_number"] = int(line_number)
    payload.update(fields)
    return payload


def _load_ledger_rows(state_root: Path, ledger_name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    path = state_root / ledger_name
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    exists = path.exists()

    if not exists:
        issues.append(_issue("missing_ledger_file", ledger_name, path=str(path)))
        return rows, issues, {"ledger": ledger_name, "exists": False, "row_count": 0, "path": str(path)}

    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as exc:
                issues.append(
                    _issue(
                        "invalid_jsonl_record",
                        ledger_name,
                        line_number=line_number,
                        error=str(exc),
                    )
                )
                continue
            if not isinstance(record, dict):
                issues.append(_issue("non_dict_jsonl_record", ledger_name, line_number=line_number))
                continue
            rows.append(
                {
                    "ledger": ledger_name,
                    "line_number": line_number,
                    "record": record,
                }
            )

    return rows, issues, {"ledger": ledger_name, "exists": True, "row_count": len(rows), "path": str(path)}


def read_retention_ledgers(
    state_root: str | Path,
    *,
    repo_root: Path | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], list[dict[str, Any]], Path]:
    resolved_state_root = resolve_state_root(state_root, repo_root=repo_root)

    rows_by_ledger: dict[str, list[dict[str, Any]]] = {}
    ledger_stats: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    for ledger_name in REQUIRED_STATE_FILES:
        rows, load_issues, stats = _load_ledger_rows(resolved_state_root, ledger_name)
        rows_by_ledger[ledger_name] = rows
        ledger_stats.append(stats)
        issues.extend(load_issues)

    return rows_by_ledger, ledger_stats, issues, resolved_state_root


def _iter_string_values(value: Any, *, path: str = "$") -> Iterator[tuple[str, str]]:
    if isinstance(value, dict):
        for key in sorted(value):
            yield from _iter_string_values(value[key], path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_string_values(item, path=f"{path}[{index}]")
        return
    if isinstance(value, str):
        yield path, value


def _group_rows(rows: list[dict[str, Any]], key_builder) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[key_builder(row)].append(row)
    return grouped


def _detect_hash_issues(rows_by_ledger: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for ledger_name in REQUIRED_STATE_FILES:
        previous_record_hash: str | None = None
        for row in rows_by_ledger.get(ledger_name, []):
            record = row["record"]
            line_number = row["line_number"]
            stored_record_hash = record.get("record_hash")
            expected_record_hash = compute_record_hash(record)
            if stored_record_hash != expected_record_hash:
                issues.append(
                    _issue(
                        "record_hash_mismatch",
                        ledger_name,
                        line_number=line_number,
                        expected_record_hash=expected_record_hash,
                        observed_record_hash=stored_record_hash,
                    )
                )

            observed_prev_hash = record.get("prev_hash")
            if observed_prev_hash != previous_record_hash:
                issues.append(
                    _issue(
                        "prev_hash_mismatch",
                        ledger_name,
                        line_number=line_number,
                        expected_prev_hash=previous_record_hash,
                        observed_prev_hash=observed_prev_hash,
                    )
                )

            previous_record_hash = stored_record_hash if isinstance(stored_record_hash, str) else expected_record_hash

    return issues


def _detect_raw_identifier_leakage(rows_by_ledger: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for ledger_name in REQUIRED_STATE_FILES:
        for row in rows_by_ledger.get(ledger_name, []):
            for json_path, text_value in _iter_string_values(row["record"]):
                for match in EMAIL_PATTERN.finditer(text_value):
                    leaked_value = match.group(0).lower()
                    issues.append(
                        _issue(
                            "raw_identifier_leakage",
                            ledger_name,
                            line_number=row["line_number"],
                            json_path=json_path,
                            leak_type="email",
                            value_fingerprint=f"sha256:{sha256_hex(leaked_value)}",
                        )
                    )
    return issues


def _detect_event_transition_gaps(rows_by_ledger: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    events = [
        row
        for row in rows_by_ledger.get("events.jsonl", [])
        if row["record"].get("record_type") == "canonical_event"
    ]
    transitions = [
        row
        for row in rows_by_ledger.get("transitions.jsonl", [])
        if row["record"].get("record_type") == "transition_decision"
    ]

    events_by_key = _group_rows(
        events,
        lambda row: (row["record"].get("event_id"), row["record"].get("contact_id")),
    )
    transitions_by_key = _group_rows(
        transitions,
        lambda row: (row["record"].get("event_id"), row["record"].get("contact_id")),
    )

    for key in sorted(events_by_key):
        event_rows = events_by_key[key]
        transition_rows = transitions_by_key.get(key, [])
        for event_row in event_rows[len(transition_rows) :]:
            record = event_row["record"]
            issues.append(
                _issue(
                    "event_without_transition",
                    "events.jsonl",
                    line_number=event_row["line_number"],
                    event_id=record.get("event_id"),
                    contact_id=record.get("contact_id"),
                )
            )

    return issues


def _detect_transition_snapshot_gaps(rows_by_ledger: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    transitions = [
        row
        for row in rows_by_ledger.get("transitions.jsonl", [])
        if row["record"].get("record_type") == "transition_decision"
        and row["record"].get("decision") == "applied"
    ]
    contacts = [
        row
        for row in rows_by_ledger.get("contacts.jsonl", [])
        if row["record"].get("record_type") == "contact_snapshot"
    ]

    transitions_by_key = _group_rows(
        transitions,
        lambda row: (
            row["record"].get("event_id"),
            row["record"].get("contact_id"),
            row["record"].get("to_state"),
        ),
    )
    contacts_by_key = _group_rows(
        contacts,
        lambda row: (
            row["record"].get("last_touch_event"),
            row["record"].get("contact_id"),
            row["record"].get("current_state"),
        ),
    )

    for key in sorted(transitions_by_key):
        transition_rows = transitions_by_key[key]
        contact_rows = contacts_by_key.get(key, [])
        for transition_row in transition_rows[len(contact_rows) :]:
            record = transition_row["record"]
            issues.append(
                _issue(
                    "transition_without_required_contact_snapshot",
                    "transitions.jsonl",
                    line_number=transition_row["line_number"],
                    transition_id=record.get("transition_id"),
                    event_id=record.get("event_id"),
                    contact_id=record.get("contact_id"),
                    to_state=record.get("to_state"),
                )
            )

    return issues


def _detect_contact_without_event(rows_by_ledger: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    events = [
        row
        for row in rows_by_ledger.get("events.jsonl", [])
        if row["record"].get("record_type") == "canonical_event"
    ]
    contacts = [
        row
        for row in rows_by_ledger.get("contacts.jsonl", [])
        if row["record"].get("record_type") == "contact_snapshot"
    ]

    events_by_last_touch = _group_rows(
        events,
        lambda row: (row["record"].get("event_id"), row["record"].get("contact_id")),
    )
    known_event_ids = {row["record"].get("event_id") for row in events}

    for contact_row in contacts:
        record = contact_row["record"]
        last_touch_event = record.get("last_touch_event")
        contact_id = record.get("contact_id")
        key = (last_touch_event, contact_id)
        if not events_by_last_touch.get(key):
            issues.append(
                _issue(
                    "contact_snapshot_without_prior_event",
                    "contacts.jsonl",
                    line_number=contact_row["line_number"],
                    contact_id=contact_id,
                    last_touch_event=last_touch_event,
                )
            )
        first_touch_event = record.get("first_touch_event")
        if first_touch_event and first_touch_event not in known_event_ids:
            issues.append(
                _issue(
                    "contact_snapshot_references_unknown_first_touch_event",
                    "contacts.jsonl",
                    line_number=contact_row["line_number"],
                    contact_id=contact_id,
                    first_touch_event=first_touch_event,
                )
            )

    return issues


def _detect_dispatch_state_gaps(rows_by_ledger: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    contacts = [
        row
        for row in rows_by_ledger.get("contacts.jsonl", [])
        if row["record"].get("record_type") == "contact_snapshot"
    ]
    dispatch_rows = [
        row
        for row in rows_by_ledger.get("content_dispatch.jsonl", [])
        if row["record"].get("record_type") == "content_dispatch_plan"
    ]

    contacts_by_version = {
        (
            row["record"].get("contact_id"),
            row["record"].get("contact_version"),
        ): row
        for row in contacts
    }

    for dispatch_row in dispatch_rows:
        record = dispatch_row["record"]
        key = (record.get("contact_id"), record.get("contact_version"))
        contact_row = contacts_by_version.get(key)
        if contact_row is None:
            issues.append(
                _issue(
                    "dispatch_without_valid_contact_state",
                    "content_dispatch.jsonl",
                    line_number=dispatch_row["line_number"],
                    contact_id=record.get("contact_id"),
                    contact_version=record.get("contact_version"),
                    reason="missing_contact_snapshot",
                )
            )
            continue

        expected_plan = plan_dispatch(contact_row["record"], contact_id=record.get("contact_id"))
        expected_signature = {
            "decision": expected_plan.get("decision"),
            "dispatch_type": expected_plan.get("dispatch_type"),
            "channel": expected_plan.get("channel"),
            "template_key": expected_plan.get("template_key"),
            "current_state": expected_plan.get("current_state"),
        }
        observed_signature = {
            "decision": record.get("decision"),
            "dispatch_type": record.get("dispatch_type"),
            "channel": record.get("channel"),
            "template_key": record.get("template_key"),
            "current_state": record.get("current_state"),
        }
        if expected_signature["decision"] != "planned" or observed_signature != expected_signature:
            issues.append(
                _issue(
                    "dispatch_without_valid_contact_state",
                    "content_dispatch.jsonl",
                    line_number=dispatch_row["line_number"],
                    contact_id=record.get("contact_id"),
                    contact_version=record.get("contact_version"),
                    expected_plan=expected_signature,
                    observed_plan=observed_signature,
                )
            )

    return issues


def _sort_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _sort_key(issue: dict[str, Any]) -> tuple[Any, ...]:
        ledger = str(issue.get("ledger") or "")
        line_number = issue.get("line_number")
        normalized_line = int(line_number) if isinstance(line_number, int) else -1
        return (
            LEDGER_ORDER.get(ledger, len(LEDGER_ORDER)),
            normalized_line,
            ISSUE_ORDER.get(str(issue.get("issue_type") or ""), len(ISSUE_ORDER)),
            str(issue.get("issue_type") or ""),
            str(issue.get("event_id") or ""),
            str(issue.get("contact_id") or ""),
            str(issue.get("transition_id") or ""),
            str(issue.get("json_path") or ""),
        )

    return sorted(issues, key=_sort_key)


def reconcile_state(state_root: str | Path, *, repo_root: Path | None = None) -> dict[str, Any]:
    rows_by_ledger, ledger_stats, issues, resolved_state_root = read_retention_ledgers(
        state_root,
        repo_root=repo_root,
    )

    issues.extend(_detect_hash_issues(rows_by_ledger))
    issues.extend(_detect_raw_identifier_leakage(rows_by_ledger))
    issues.extend(_detect_event_transition_gaps(rows_by_ledger))
    issues.extend(_detect_transition_snapshot_gaps(rows_by_ledger))
    issues.extend(_detect_contact_without_event(rows_by_ledger))
    issues.extend(_detect_dispatch_state_gaps(rows_by_ledger))
    issues = _sort_issues(issues)

    return {
        "clean": len(issues) == 0,
        "issue_count": len(issues),
        "issues": issues,
        "ledgers": ledger_stats,
        "state_root": str(resolved_state_root),
    }
