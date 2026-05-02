from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.retention.identity import get_repo_root


ALLOWED_ADAPTER_NAMES = ("local-noop",)
QUEUE_STATUS_SEND_READY = "send_ready"
RESULT_STATUS_ORDER = {
    "accepted_preview": 0,
    "rejected_preview": 1,
}
ISSUE_ORDER = {
    "unknown_adapter": 0,
    "queue_file_missing": 1,
    "invalid_queue_json": 2,
    "invalid_queue_payload": 3,
    "queue_projection_not_clean": 4,
    "queue_projection_basis_missing": 5,
    "queue_projection_count_mismatch": 6,
    "queue_record_not_dict": 7,
    "queue_record_missing_required_field": 8,
    "queue_record_missing_contact_reference": 9,
    "queue_record_unsafe_status": 10,
    "queue_record_missing_content_reference": 11,
    "queue_record_invalid_consent_basis": 12,
    "queue_record_invalid_source_provenance": 13,
}


def resolve_queue_path(queue_path: str | Path, *, repo_root: Path | None = None) -> Path:
    root = repo_root or get_repo_root()
    candidate = Path(queue_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


def _issue(issue_type: str, *, queue_index: int | None = None, **fields: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"issue_type": issue_type}
    if queue_index is not None:
        payload["queue_index"] = int(queue_index)
    payload.update(fields)
    return payload


def _result(
    *,
    adapter: str,
    projection_basis_hash: str | None,
    queue_id: Any,
    source_dispatch_id: Any,
    status: str,
    reason_code: str,
    source_line_number: Any = None,
) -> dict[str, Any]:
    payload = {
        "queue_id": queue_id,
        "source_dispatch_id": source_dispatch_id,
        "adapter": adapter,
        "status": status,
        "reason_code": reason_code,
        "projection_basis_hash": projection_basis_hash,
        "no_network": True,
        "sent": False,
    }
    if source_line_number is not None:
        payload["source_line_number"] = source_line_number
    return payload


def _sort_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        results,
        key=lambda result: (
            int(result.get("source_line_number", -1)) if isinstance(result.get("source_line_number"), int) else -1,
            str(result.get("source_dispatch_id") or ""),
            RESULT_STATUS_ORDER.get(str(result.get("status") or ""), len(RESULT_STATUS_ORDER)),
            str(result.get("queue_id") or ""),
            str(result.get("reason_code") or ""),
        ),
    )


def _sort_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        issues,
        key=lambda issue: (
            ISSUE_ORDER.get(str(issue.get("issue_type") or ""), len(ISSUE_ORDER)),
            int(issue.get("queue_index", -1)) if isinstance(issue.get("queue_index"), int) else -1,
            str(issue.get("source_dispatch_id") or ""),
            str(issue.get("queue_id") or ""),
        ),
    )


def _load_queue_projection(
    queue_path: str | Path,
    *,
    repo_root: Path | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], Path]:
    resolved_queue_path = resolve_queue_path(queue_path, repo_root=repo_root)
    if not resolved_queue_path.exists():
        return None, [_issue("queue_file_missing", queue_path=str(resolved_queue_path))], resolved_queue_path

    try:
        payload = json.loads(resolved_queue_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return (
            None,
            [_issue("invalid_queue_json", queue_path=str(resolved_queue_path), error=str(exc))],
            resolved_queue_path,
        )

    if not isinstance(payload, dict):
        return (
            None,
            [_issue("invalid_queue_payload", queue_path=str(resolved_queue_path), reason="top_level_not_object")],
            resolved_queue_path,
        )

    return payload, [], resolved_queue_path


def _normalize_queue_records(payload: dict[str, Any]) -> list[tuple[int, Any]]:
    raw_queue = payload.get("queue")
    if not isinstance(raw_queue, list):
        return []
    indexed = list(enumerate(raw_queue))
    return sorted(
        indexed,
        key=lambda item: (
            int(item[1].get("source_line_number", -1)) if isinstance(item[1], dict) and isinstance(item[1].get("source_line_number"), int) else -1,
            str(item[1].get("source_dispatch_id") or "") if isinstance(item[1], dict) else "",
            str(item[1].get("queue_id") or "") if isinstance(item[1], dict) else "",
            int(item[0]),
        ),
    )


def _has_contact_reference(record: dict[str, Any]) -> bool:
    for field in ("contact_id", "identity_reference", "identifier_hash", "hashed_identity_reference"):
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _has_content_reference(record: dict[str, Any]) -> bool:
    for field in ("template_key", "content_reference"):
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            return True
    return False


def _required_string_fields(record: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in ("queue_id", "source_dispatch_id", "dispatch_type", "status", "source_ledger", "source_record_hash"):
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            missing.append(field)
    return missing


def _validate_queue_projection(payload: dict[str, Any], queue_path: Path) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not isinstance(payload.get("queue"), list):
        issues.append(_issue("invalid_queue_payload", queue_path=str(queue_path), reason="queue_not_list"))
        return issues

    if payload.get("clean") is not True or payload.get("dispatch_ready_clean") is not True:
        issues.append(
            _issue(
                "queue_projection_not_clean",
                queue_path=str(queue_path),
                clean=payload.get("clean"),
                dispatch_ready_clean=payload.get("dispatch_ready_clean"),
            )
        )

    projection_basis_hash = payload.get("projection_basis_hash")
    if not isinstance(projection_basis_hash, str) or not projection_basis_hash.startswith("sha256:"):
        issues.append(_issue("queue_projection_basis_missing", queue_path=str(queue_path)))

    projected_count = payload.get("projected_count")
    queue_rows = payload.get("queue")
    if isinstance(projected_count, int) and isinstance(queue_rows, list) and projected_count != len(queue_rows):
        issues.append(
            _issue(
                "queue_projection_count_mismatch",
                queue_path=str(queue_path),
                projected_count=projected_count,
                observed_queue_count=len(queue_rows),
            )
        )

    return issues


def _validate_queue_record(
    record: Any,
    *,
    queue_index: int,
    adapter: str,
    projection_basis_hash: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(record, dict):
        result = _result(
            adapter=adapter,
            projection_basis_hash=projection_basis_hash,
            queue_id=None,
            source_dispatch_id=None,
            status="rejected_preview",
            reason_code="queue_record_not_dict",
        )
        return result, [_issue("queue_record_not_dict", queue_index=queue_index)]

    queue_id = record.get("queue_id")
    source_dispatch_id = record.get("source_dispatch_id")
    source_line_number = record.get("source_line_number")

    missing_fields = _required_string_fields(record)
    if missing_fields:
        reason_code = f"missing_required_field:{missing_fields[0]}"
        result = _result(
            adapter=adapter,
            projection_basis_hash=projection_basis_hash,
            queue_id=queue_id,
            source_dispatch_id=source_dispatch_id,
            source_line_number=source_line_number,
            status="rejected_preview",
            reason_code=reason_code,
        )
        return result, [
            _issue(
                "queue_record_missing_required_field",
                queue_index=queue_index,
                queue_id=queue_id,
                source_dispatch_id=source_dispatch_id,
                field=missing_fields[0],
            )
        ]

    if not _has_contact_reference(record):
        result = _result(
            adapter=adapter,
            projection_basis_hash=projection_basis_hash,
            queue_id=queue_id,
            source_dispatch_id=source_dispatch_id,
            source_line_number=source_line_number,
            status="rejected_preview",
            reason_code="missing_contact_reference",
        )
        return result, [
            _issue(
                "queue_record_missing_contact_reference",
                queue_index=queue_index,
                queue_id=queue_id,
                source_dispatch_id=source_dispatch_id,
            )
        ]

    if record.get("status") != QUEUE_STATUS_SEND_READY:
        reason_code = f"unsafe_status:{record.get('status')}"
        result = _result(
            adapter=adapter,
            projection_basis_hash=projection_basis_hash,
            queue_id=queue_id,
            source_dispatch_id=source_dispatch_id,
            source_line_number=source_line_number,
            status="rejected_preview",
            reason_code=reason_code,
        )
        return result, [
            _issue(
                "queue_record_unsafe_status",
                queue_index=queue_index,
                queue_id=queue_id,
                source_dispatch_id=source_dispatch_id,
                observed_status=record.get("status"),
            )
        ]

    if not _has_content_reference(record):
        result = _result(
            adapter=adapter,
            projection_basis_hash=projection_basis_hash,
            queue_id=queue_id,
            source_dispatch_id=source_dispatch_id,
            source_line_number=source_line_number,
            status="rejected_preview",
            reason_code="missing_template_or_content_reference",
        )
        return result, [
            _issue(
                "queue_record_missing_content_reference",
                queue_index=queue_index,
                queue_id=queue_id,
                source_dispatch_id=source_dispatch_id,
            )
        ]

    consent_basis = record.get("consent_basis")
    if not isinstance(consent_basis, dict) or not consent_basis:
        result = _result(
            adapter=adapter,
            projection_basis_hash=projection_basis_hash,
            queue_id=queue_id,
            source_dispatch_id=source_dispatch_id,
            source_line_number=source_line_number,
            status="rejected_preview",
            reason_code="invalid_consent_basis",
        )
        return result, [
            _issue(
                "queue_record_invalid_consent_basis",
                queue_index=queue_index,
                queue_id=queue_id,
                source_dispatch_id=source_dispatch_id,
            )
        ]

    source_line_value = record.get("source_line_number")
    source_ledger = record.get("source_ledger")
    source_record_hash = record.get("source_record_hash")
    if not isinstance(source_line_value, int) or source_ledger != "content_dispatch.jsonl" or not isinstance(source_record_hash, str) or not source_record_hash.startswith("sha256:"):
        result = _result(
            adapter=adapter,
            projection_basis_hash=projection_basis_hash,
            queue_id=queue_id,
            source_dispatch_id=source_dispatch_id,
            source_line_number=source_line_number,
            status="rejected_preview",
            reason_code="invalid_source_provenance",
        )
        return result, [
            _issue(
                "queue_record_invalid_source_provenance",
                queue_index=queue_index,
                queue_id=queue_id,
                source_dispatch_id=source_dispatch_id,
            )
        ]

    return (
        _result(
            adapter=adapter,
            projection_basis_hash=projection_basis_hash,
            queue_id=queue_id,
            source_dispatch_id=source_dispatch_id,
            source_line_number=source_line_number,
            status="accepted_preview",
            reason_code="accepted_preview",
        ),
        [],
    )


def preview_send_queue(
    queue_path: str | Path,
    *,
    adapter: str,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    if adapter not in ALLOWED_ADAPTER_NAMES:
        issues = _sort_issues([_issue("unknown_adapter", adapter=adapter, allowed_adapters=list(ALLOWED_ADAPTER_NAMES))])
        return {
            "clean": False,
            "adapter": adapter,
            "attempted_count": 0,
            "accepted_count": 0,
            "rejected_count": 0,
            "results": [],
            "issues": issues,
        }

    payload, issues, resolved_queue_path = _load_queue_projection(queue_path, repo_root=repo_root)
    if payload is None:
        issues = _sort_issues(issues)
        return {
            "clean": False,
            "adapter": adapter,
            "attempted_count": 0,
            "accepted_count": 0,
            "rejected_count": 0,
            "results": [],
            "issues": issues,
        }

    issues.extend(_validate_queue_projection(payload, resolved_queue_path))
    projection_basis_hash = payload.get("projection_basis_hash") if isinstance(payload.get("projection_basis_hash"), str) else None

    results: list[dict[str, Any]] = []
    if not any(issue["issue_type"] in {"invalid_queue_payload"} for issue in issues):
        for queue_index, record in _normalize_queue_records(payload):
            result, record_issues = _validate_queue_record(
                record,
                queue_index=queue_index,
                adapter=adapter,
                projection_basis_hash=projection_basis_hash,
            )
            results.append(result)
            issues.extend(record_issues)

    results = _sort_results(results)
    issues = _sort_issues(issues)
    accepted_count = sum(1 for result in results if result["status"] == "accepted_preview")
    rejected_count = sum(1 for result in results if result["status"] == "rejected_preview")

    return {
        "clean": len(issues) == 0 and rejected_count == 0,
        "adapter": adapter,
        "attempted_count": len(results),
        "accepted_count": accepted_count,
        "rejected_count": rejected_count,
        "results": results,
        "issues": issues,
    }
