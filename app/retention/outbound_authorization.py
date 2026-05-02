from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.retention.identity import get_repo_root, sha256_hex
from app.retention.jsonl_store import stable_json_dumps


ALLOWED_AUTHORIZATION_DECISIONS = ("approve", "deny")
AUTHORIZATION_MODE_EXPLICIT = "explicit"
ISSUE_ORDER = {
    "preview_file_missing": 0,
    "invalid_preview_json": 1,
    "invalid_preview_payload": 2,
    "missing_operator_id": 3,
    "unknown_decision": 4,
    "preview_not_clean": 5,
    "preview_adapter_unsupported": 6,
    "preview_count_mismatch": 7,
    "mixed_preview_results": 8,
    "preview_result_not_dict": 9,
    "preview_result_missing_required_field": 10,
    "preview_result_adapter_mismatch": 11,
    "preview_result_unsafe_sent": 12,
    "preview_result_unsafe_no_network": 13,
    "preview_result_status_invalid": 14,
}
AUTH_RECORD_STATUS_ORDER = {
    True: 0,
    False: 1,
}


def resolve_preview_path(preview_path: str | Path, *, repo_root: Path | None = None) -> Path:
    root = repo_root or get_repo_root()
    candidate = Path(preview_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


def _issue(issue_type: str, *, result_index: int | None = None, **fields: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"issue_type": issue_type}
    if result_index is not None:
        payload["result_index"] = int(result_index)
    payload.update(fields)
    return payload


def _sort_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        issues,
        key=lambda issue: (
            ISSUE_ORDER.get(str(issue.get("issue_type") or ""), len(ISSUE_ORDER)),
            int(issue.get("result_index", -1)) if isinstance(issue.get("result_index"), int) else -1,
            str(issue.get("source_dispatch_id") or ""),
            str(issue.get("queue_id") or ""),
        ),
    )


def _sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda record: (
            int(record.get("source_line_number", -1)) if isinstance(record.get("source_line_number"), int) else -1,
            str(record.get("source_dispatch_id") or ""),
            str(record.get("queue_id") or ""),
            AUTH_RECORD_STATUS_ORDER.get(bool(record.get("authorized")), 1),
            str(record.get("reason_code") or ""),
        ),
    )


def _preview_hash(payload: dict[str, Any]) -> str:
    return f"sha256:{sha256_hex(stable_json_dumps(payload))}"


def _authorization_id(
    *,
    source_preview_hash: str | None,
    operator_id: str,
    decision: str,
    queue_id: Any,
    source_dispatch_id: Any,
    source_line_number: Any,
) -> str:
    material = "|".join(
        [
            str(source_preview_hash or ""),
            str(operator_id or ""),
            str(decision or ""),
            str(queue_id or ""),
            str(source_dispatch_id or ""),
            str(int(source_line_number or 0)),
        ]
    )
    return f"aut_{sha256_hex(material)[:16]}"


def _load_preview_payload(
    preview_path: str | Path,
    *,
    repo_root: Path | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], Path]:
    resolved_preview_path = resolve_preview_path(preview_path, repo_root=repo_root)
    if not resolved_preview_path.exists():
        return None, [_issue("preview_file_missing", preview_path=str(resolved_preview_path))], resolved_preview_path

    try:
        payload = json.loads(resolved_preview_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return (
            None,
            [_issue("invalid_preview_json", preview_path=str(resolved_preview_path), error=str(exc))],
            resolved_preview_path,
        )

    if not isinstance(payload, dict):
        return (
            None,
            [_issue("invalid_preview_payload", preview_path=str(resolved_preview_path), reason="top_level_not_object")],
            resolved_preview_path,
        )

    return payload, [], resolved_preview_path


def _normalize_preview_results(payload: dict[str, Any]) -> list[tuple[int, Any]]:
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        return []
    indexed = list(enumerate(raw_results))
    return sorted(
        indexed,
        key=lambda item: (
            int(item[1].get("source_line_number", -1)) if isinstance(item[1], dict) and isinstance(item[1].get("source_line_number"), int) else -1,
            str(item[1].get("source_dispatch_id") or "") if isinstance(item[1], dict) else "",
            str(item[1].get("queue_id") or "") if isinstance(item[1], dict) else "",
            int(item[0]),
        ),
    )


def _validate_preview_payload(payload: dict[str, Any], preview_path: Path) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    results = payload.get("results")
    if not isinstance(results, list):
        issues.append(_issue("invalid_preview_payload", preview_path=str(preview_path), reason="results_not_list"))
        return issues

    if payload.get("clean") is not True:
        issues.append(
            _issue(
                "preview_not_clean",
                preview_path=str(preview_path),
                clean=payload.get("clean"),
            )
        )

    if payload.get("adapter") != "local-noop":
        issues.append(
            _issue(
                "preview_adapter_unsupported",
                preview_path=str(preview_path),
                adapter=payload.get("adapter"),
            )
        )

    attempted_count = payload.get("attempted_count")
    accepted_count = payload.get("accepted_count")
    rejected_count = payload.get("rejected_count")
    observed_attempted = len(results)
    observed_accepted = sum(
        1
        for result in results
        if isinstance(result, dict) and result.get("status") == "accepted_preview"
    )
    observed_rejected = sum(
        1
        for result in results
        if isinstance(result, dict) and result.get("status") == "rejected_preview"
    )
    if (
        not isinstance(attempted_count, int)
        or not isinstance(accepted_count, int)
        or not isinstance(rejected_count, int)
        or attempted_count != observed_attempted
        or accepted_count != observed_accepted
        or rejected_count != observed_rejected
    ):
        issues.append(
            _issue(
                "preview_count_mismatch",
                preview_path=str(preview_path),
                attempted_count=attempted_count,
                accepted_count=accepted_count,
                rejected_count=rejected_count,
                observed_attempted_count=observed_attempted,
                observed_accepted_count=observed_accepted,
                observed_rejected_count=observed_rejected,
            )
        )

    observed_statuses = {
        str(result.get("status") or "")
        for result in results
        if isinstance(result, dict) and isinstance(result.get("status"), str)
    }
    if "accepted_preview" in observed_statuses and "rejected_preview" in observed_statuses:
        issues.append(_issue("mixed_preview_results", preview_path=str(preview_path)))

    return issues


def _required_result_fields(record: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in ("queue_id", "source_dispatch_id", "adapter", "status", "reason_code", "projection_basis_hash"):
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            missing.append(field)
    return missing


def _validate_preview_result(record: Any, *, result_index: int) -> list[dict[str, Any]]:
    if not isinstance(record, dict):
        return [_issue("preview_result_not_dict", result_index=result_index)]

    issues: list[dict[str, Any]] = []
    queue_id = record.get("queue_id")
    source_dispatch_id = record.get("source_dispatch_id")
    missing_fields = _required_result_fields(record)
    if missing_fields:
        issues.append(
            _issue(
                "preview_result_missing_required_field",
                result_index=result_index,
                queue_id=queue_id,
                source_dispatch_id=source_dispatch_id,
                field=missing_fields[0],
            )
        )

    if record.get("adapter") != "local-noop":
        issues.append(
            _issue(
                "preview_result_adapter_mismatch",
                result_index=result_index,
                queue_id=queue_id,
                source_dispatch_id=source_dispatch_id,
                adapter=record.get("adapter"),
            )
        )

    if record.get("sent") is not False:
        issues.append(
            _issue(
                "preview_result_unsafe_sent",
                result_index=result_index,
                queue_id=queue_id,
                source_dispatch_id=source_dispatch_id,
                sent=record.get("sent"),
            )
        )

    if record.get("no_network") is not True:
        issues.append(
            _issue(
                "preview_result_unsafe_no_network",
                result_index=result_index,
                queue_id=queue_id,
                source_dispatch_id=source_dispatch_id,
                no_network=record.get("no_network"),
            )
        )

    if record.get("status") != "accepted_preview":
        issues.append(
            _issue(
                "preview_result_status_invalid",
                result_index=result_index,
                queue_id=queue_id,
                source_dispatch_id=source_dispatch_id,
                observed_status=record.get("status"),
            )
        )

    return issues


def _record_reason_code(
    *,
    decision: str,
    global_issues: list[dict[str, Any]],
    record_issues: list[dict[str, Any]],
) -> str:
    if global_issues:
        return str(global_issues[0]["issue_type"])
    if record_issues:
        return str(record_issues[0]["issue_type"])
    if decision == "deny":
        return "operator_denied"
    return "authorized_preview_only"


def authorize_send_preview(
    preview_path: str | Path,
    *,
    operator_id: str,
    decision: str,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    payload, issues, resolved_preview_path = _load_preview_payload(preview_path, repo_root=repo_root)

    normalized_operator_id = str(operator_id or "").strip()
    if not normalized_operator_id:
        issues.append(_issue("missing_operator_id"))
    if decision not in ALLOWED_AUTHORIZATION_DECISIONS:
        issues.append(
            _issue(
                "unknown_decision",
                decision=decision,
                allowed_decisions=list(ALLOWED_AUTHORIZATION_DECISIONS),
            )
        )

    if payload is None:
        issues = _sort_issues(issues)
        return {
            "clean": False,
            "authorization_mode": AUTHORIZATION_MODE_EXPLICIT,
            "decision": decision,
            "authorized": False,
            "operator_id": normalized_operator_id,
            "source_preview_hash": None,
            "authorized_count": 0,
            "denied_count": 0,
            "issues": issues,
            "records": [],
        }

    issues.extend(_validate_preview_payload(payload, resolved_preview_path))
    source_preview_hash = _preview_hash(payload)
    records: list[dict[str, Any]] = []
    global_issues = [issue for issue in issues if "result_index" not in issue]

    if not any(issue["issue_type"] == "invalid_preview_payload" for issue in issues):
        for result_index, result in _normalize_preview_results(payload):
            record_issues = _validate_preview_result(result, result_index=result_index)
            issues.extend(record_issues)
            global_issues = [issue for issue in issues if "result_index" not in issue]

            queue_id = result.get("queue_id") if isinstance(result, dict) else None
            source_dispatch_id = result.get("source_dispatch_id") if isinstance(result, dict) else None
            adapter = result.get("adapter") if isinstance(result, dict) else payload.get("adapter")
            source_line_number = result.get("source_line_number") if isinstance(result, dict) else None
            authorized = decision == "approve" and not global_issues and not record_issues
            records.append(
                {
                    "authorization_id": _authorization_id(
                        source_preview_hash=source_preview_hash,
                        operator_id=normalized_operator_id,
                        decision=decision,
                        queue_id=queue_id,
                        source_dispatch_id=source_dispatch_id,
                        source_line_number=source_line_number,
                    ),
                    "queue_id": queue_id,
                    "source_dispatch_id": source_dispatch_id,
                    "adapter": adapter,
                    "decision": decision,
                    "authorized": authorized,
                    "reason_code": _record_reason_code(
                        decision=decision,
                        global_issues=global_issues,
                        record_issues=record_issues,
                    ),
                    "sent": False,
                    "external_action_allowed": False,
                    "source_line_number": source_line_number,
                }
            )

    records = _sort_records(records)
    issues = _sort_issues(issues)
    authorized_count = sum(1 for record in records if record["authorized"] is True)
    denied_count = sum(1 for record in records if record["authorized"] is False)

    return {
        "clean": len(issues) == 0,
        "authorization_mode": AUTHORIZATION_MODE_EXPLICIT,
        "decision": decision,
        "authorized": decision == "approve" and len(issues) == 0 and authorized_count == len(records),
        "operator_id": normalized_operator_id,
        "source_preview_hash": source_preview_hash,
        "authorized_count": authorized_count,
        "denied_count": denied_count,
        "issues": issues,
        "records": records,
    }
