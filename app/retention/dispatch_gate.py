from __future__ import annotations

from pathlib import Path
from typing import Any

from app.retention.dispatch import plan_dispatch
from app.retention.models import DISPATCHABLE_CONSENT_STATUSES
from app.retention.reconcile import read_retention_ledgers, reconcile_state


TERMINAL_DISPATCH_STATUSES = {"sent", "canceled", "cancelled", "suppressed"}
RECOGNIZED_DISPATCH_TYPES: dict[str, dict[str, Any]] = {
    "orientation_email": {
        "allowed_states": {"subscribed"},
        "allowed_channels": {"email"},
        "requires_dispatchable_consent": True,
    },
    "internal_task": {
        "allowed_states": {"aware"},
        "allowed_channels": {"internal"},
        "requires_dispatchable_consent": False,
    },
}
GATE_ISSUE_ORDER = {
    "reconciliation_failed": 0,
    "dispatch_contact_missing": 1,
    "dispatch_type_unrecognized": 2,
    "dispatch_status_terminal": 3,
    "dispatch_contact_state_ineligible": 4,
    "dispatch_consent_ineligible": 5,
    "dispatch_channel_ineligible": 6,
    "dispatch_missing_content_reference": 7,
    "dispatch_plan_mismatch": 8,
}


def _issue(issue_type: str, *, line_number: int | None = None, **fields: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "issue_type": issue_type,
        "ledger": "content_dispatch.jsonl",
    }
    if line_number is not None:
        payload["line_number"] = int(line_number)
    payload.update(fields)
    return payload


def _normalized_dispatch_status(record: dict[str, Any]) -> str | None:
    for field in ("delivery_status", "dispatch_status", "status", "lifecycle_state"):
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


def _has_content_reference(record: dict[str, Any]) -> bool:
    for field in ("template_key", "content_reference", "content_ref", "content_id"):
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _latest_contact_by_id(contact_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in contact_rows:
        record = row["record"]
        contact_id = str(record.get("contact_id") or "")
        if not contact_id:
            continue
        previous = latest.get(contact_id)
        if previous is None:
            latest[contact_id] = row
            continue
        previous_version = int(previous["record"].get("contact_version", 0) or 0)
        current_version = int(record.get("contact_version", 0) or 0)
        if current_version >= previous_version:
            latest[contact_id] = row
    return latest


def _sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda record: (
            int(record.get("line_number", -1)),
            str(record.get("dispatch_id") or ""),
            str(record.get("contact_id") or ""),
        ),
    )


def _sort_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        issues,
        key=lambda issue: (
            int(issue.get("line_number", -1)) if isinstance(issue.get("line_number"), int) else -1,
            GATE_ISSUE_ORDER.get(str(issue.get("issue_type") or ""), len(GATE_ISSUE_ORDER)),
            str(issue.get("issue_type") or ""),
            str(issue.get("dispatch_id") or ""),
            str(issue.get("contact_id") or ""),
        ),
    )


def evaluate_dispatch_ready(state_root: str | Path, *, repo_root: Path | None = None) -> dict[str, Any]:
    reconciliation = reconcile_state(state_root, repo_root=repo_root)
    rows_by_ledger, _, _, resolved_state_root = read_retention_ledgers(state_root, repo_root=repo_root)

    contact_rows = [
        row
        for row in rows_by_ledger.get("contacts.jsonl", [])
        if row["record"].get("record_type") == "contact_snapshot"
    ]
    dispatch_rows = [
        row
        for row in rows_by_ledger.get("content_dispatch.jsonl", [])
        if row["record"].get("record_type") == "content_dispatch_plan"
        and row["record"].get("decision") == "planned"
    ]

    referenced_contacts = {
        (
            row["record"].get("contact_id"),
            row["record"].get("contact_version"),
        ): row
        for row in contact_rows
    }
    latest_contacts = _latest_contact_by_id(contact_rows)

    records: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    if not reconciliation["clean"]:
        issues.append(
            _issue(
                "reconciliation_failed",
                reconciliation_issue_count=reconciliation["issue_count"],
            )
        )
        for row in dispatch_rows:
            record = row["record"]
            records.append(
                {
                    "line_number": row["line_number"],
                    "dispatch_id": record.get("dispatch_id"),
                    "contact_id": record.get("contact_id"),
                    "contact_version": record.get("contact_version"),
                    "dispatch_type": record.get("dispatch_type"),
                    "channel": record.get("channel"),
                    "current_state": record.get("current_state"),
                    "result": "blocked",
                    "reason_codes": ["reconciliation_failed"],
                }
            )
        records = _sort_records(records)
        issues = _sort_issues(issues)
        return {
            "clean": False,
            "reconciliation_clean": False,
            "reconciliation_issue_count": reconciliation["issue_count"],
            "evaluated_count": len(records),
            "eligible_count": 0,
            "blocked_count": len(records),
            "skipped_count": 0,
            "records": records,
            "issues": issues,
            "state_root": str(resolved_state_root),
        }

    for row in dispatch_rows:
        record = row["record"]
        line_number = row["line_number"]
        dispatch_id = record.get("dispatch_id")
        contact_id = record.get("contact_id")
        contact_version = record.get("contact_version")
        dispatch_type = str(record.get("dispatch_type") or "")
        channel = str(record.get("channel") or "")
        record_evaluation = {
            "line_number": line_number,
            "dispatch_id": dispatch_id,
            "contact_id": contact_id,
            "contact_version": contact_version,
            "dispatch_type": dispatch_type or None,
            "channel": channel or None,
            "current_state": record.get("current_state"),
            "result": "eligible",
            "reason_codes": ["eligible"],
        }

        terminal_status = _normalized_dispatch_status(record)
        if terminal_status in TERMINAL_DISPATCH_STATUSES:
            record_evaluation["result"] = "skipped"
            record_evaluation["reason_codes"] = [f"dispatch_status_terminal:{terminal_status}"]
            records.append(record_evaluation)
            continue

        referenced_contact = referenced_contacts.get((contact_id, contact_version))
        latest_contact = latest_contacts.get(str(contact_id or ""))
        if referenced_contact is None or latest_contact is None:
            record_evaluation["result"] = "blocked"
            record_evaluation["reason_codes"] = ["contact_missing"]
            records.append(record_evaluation)
            issues.append(
                _issue(
                    "dispatch_contact_missing",
                    line_number=line_number,
                    dispatch_id=dispatch_id,
                    contact_id=contact_id,
                    contact_version=contact_version,
                )
            )
            continue

        contact_snapshot = latest_contact["record"]
        current_state = str(contact_snapshot.get("current_state") or "")
        consent_status = str(contact_snapshot.get("consent", {}).get("email_marketing_status") or "")
        dispatch_rule = RECOGNIZED_DISPATCH_TYPES.get(dispatch_type)

        if dispatch_rule is None:
            record_evaluation["result"] = "blocked"
            record_evaluation["reason_codes"] = ["dispatch_type_unrecognized"]
            records.append(record_evaluation)
            issues.append(
                _issue(
                    "dispatch_type_unrecognized",
                    line_number=line_number,
                    dispatch_id=dispatch_id,
                    contact_id=contact_id,
                    dispatch_type=dispatch_type or None,
                )
            )
            continue

        if current_state not in dispatch_rule["allowed_states"]:
            record_evaluation["result"] = "blocked"
            record_evaluation["reason_codes"] = [f"contact_state_ineligible:{current_state or 'missing'}"]
            records.append(record_evaluation)
            issues.append(
                _issue(
                    "dispatch_contact_state_ineligible",
                    line_number=line_number,
                    dispatch_id=dispatch_id,
                    contact_id=contact_id,
                    current_state=current_state or None,
                )
            )
            continue

        if dispatch_rule["requires_dispatchable_consent"] and consent_status not in DISPATCHABLE_CONSENT_STATUSES:
            record_evaluation["result"] = "blocked"
            record_evaluation["reason_codes"] = [f"consent_ineligible:{consent_status or 'missing'}"]
            records.append(record_evaluation)
            issues.append(
                _issue(
                    "dispatch_consent_ineligible",
                    line_number=line_number,
                    dispatch_id=dispatch_id,
                    contact_id=contact_id,
                    consent_status=consent_status or None,
                )
            )
            continue

        if channel not in dispatch_rule["allowed_channels"]:
            record_evaluation["result"] = "blocked"
            record_evaluation["reason_codes"] = [f"channel_ineligible:{channel or 'missing'}"]
            records.append(record_evaluation)
            issues.append(
                _issue(
                    "dispatch_channel_ineligible",
                    line_number=line_number,
                    dispatch_id=dispatch_id,
                    contact_id=contact_id,
                    channel=channel or None,
                )
            )
            continue

        if not _has_content_reference(record):
            record_evaluation["result"] = "blocked"
            record_evaluation["reason_codes"] = ["missing_content_reference"]
            records.append(record_evaluation)
            issues.append(
                _issue(
                    "dispatch_missing_content_reference",
                    line_number=line_number,
                    dispatch_id=dispatch_id,
                    contact_id=contact_id,
                )
            )
            continue

        expected_plan = plan_dispatch(contact_snapshot, contact_id=str(contact_id or ""))
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
            record_evaluation["result"] = "blocked"
            record_evaluation["reason_codes"] = ["dispatch_plan_mismatch"]
            records.append(record_evaluation)
            issues.append(
                _issue(
                    "dispatch_plan_mismatch",
                    line_number=line_number,
                    dispatch_id=dispatch_id,
                    contact_id=contact_id,
                    expected_plan=expected_signature,
                    observed_plan=observed_signature,
                )
            )
            continue

        records.append(record_evaluation)

    records = _sort_records(records)
    issues = _sort_issues(issues)

    eligible_count = sum(1 for record in records if record["result"] == "eligible")
    blocked_count = sum(1 for record in records if record["result"] == "blocked")
    skipped_count = sum(1 for record in records if record["result"] == "skipped")

    return {
        "clean": blocked_count == 0,
        "reconciliation_clean": True,
        "reconciliation_issue_count": 0,
        "evaluated_count": len(records),
        "eligible_count": eligible_count,
        "blocked_count": blocked_count,
        "skipped_count": skipped_count,
        "records": records,
        "issues": issues,
        "state_root": str(resolved_state_root),
    }
