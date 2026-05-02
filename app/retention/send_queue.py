from __future__ import annotations

from pathlib import Path
from typing import Any

from app.retention.dispatch_gate import evaluate_dispatch_ready
from app.retention.identity import sha256_hex
from app.retention.jsonl_store import stable_json_dumps
from app.retention.reconcile import read_retention_ledgers


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


def _content_reference(record: dict[str, Any]) -> str | None:
    for field in ("content_reference", "content_ref", "content_id"):
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _consent_basis(dispatch_record: dict[str, Any], contact_snapshot: dict[str, Any]) -> dict[str, Any]:
    channel = str(dispatch_record.get("channel") or "") or None
    consent_status = str(
        contact_snapshot.get("consent", {}).get("email_marketing_status")
        or dispatch_record.get("consent", {}).get("email_marketing_status")
        or ""
    ) or None
    if channel == "email":
        return {
            "channel": "email",
            "email_marketing_status": consent_status,
            "rule": "dispatchable_consent_required",
        }
    return {
        "channel": channel,
        "email_marketing_status": consent_status,
        "rule": "non_outbound_internal_dispatch",
    }


def _queue_id_from_dispatch(
    *,
    source_dispatch_id: str | None,
    source_line_number: int | None,
    contact_id: str | None,
    dispatch_type: str | None,
    template_key: str | None,
    content_reference: str | None,
) -> str:
    material = "|".join(
        [
            str(source_dispatch_id or ""),
            str(int(source_line_number or 0)),
            str(contact_id or ""),
            str(dispatch_type or ""),
            str(template_key or ""),
            str(content_reference or ""),
        ]
    )
    return f"que_{sha256_hex(material)[:16]}"


def _exclusion_from_gate(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "line_number": record.get("line_number"),
        "source_dispatch_id": record.get("dispatch_id"),
        "contact_id": record.get("contact_id"),
        "dispatch_type": record.get("dispatch_type"),
        "result": record.get("result"),
        "reason_codes": list(record.get("reason_codes") or []),
        "source_ledger": "content_dispatch.jsonl",
    }


def _projection_basis_hash(
    *,
    dispatch_ready_clean: bool,
    queue: list[dict[str, Any]],
    exclusions: list[dict[str, Any]],
    source_state_root: str,
) -> str:
    material = stable_json_dumps(
        {
            "dispatch_ready_clean": dispatch_ready_clean,
            "queue": queue,
            "exclusions": exclusions,
            "source_state_root": source_state_root,
        }
    )
    return f"sha256:{sha256_hex(material)}"


def project_send_queue(state_root: str | Path, *, repo_root: Path | None = None) -> dict[str, Any]:
    dispatch_ready = evaluate_dispatch_ready(state_root, repo_root=repo_root)
    source_state_root = str(dispatch_ready["state_root"])

    if not dispatch_ready["clean"]:
        exclusions = [_exclusion_from_gate(record) for record in dispatch_ready["records"]]
        return {
            "clean": False,
            "dispatch_ready_clean": False,
            "projected_count": 0,
            "excluded_count": len(exclusions),
            "queue": [],
            "exclusions": exclusions,
            "source_state_root": source_state_root,
            "projection_basis_hash": _projection_basis_hash(
                dispatch_ready_clean=False,
                queue=[],
                exclusions=exclusions,
                source_state_root=source_state_root,
            ),
        }

    rows_by_ledger, _, _, _ = read_retention_ledgers(state_root, repo_root=repo_root)
    contact_rows = [
        row
        for row in rows_by_ledger.get("contacts.jsonl", [])
        if row["record"].get("record_type") == "contact_snapshot"
    ]
    dispatch_rows_by_line = {
        int(row["line_number"]): row
        for row in rows_by_ledger.get("content_dispatch.jsonl", [])
        if row["record"].get("record_type") == "content_dispatch_plan"
        and row["record"].get("decision") == "planned"
    }
    latest_contacts = _latest_contact_by_id(contact_rows)

    queue: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    clean = True

    for record in dispatch_ready["records"]:
        if record.get("result") != "eligible":
            exclusions.append(_exclusion_from_gate(record))
            continue

        line_number = int(record.get("line_number", 0) or 0)
        dispatch_row = dispatch_rows_by_line.get(line_number)
        if dispatch_row is None:
            clean = False
            exclusions.append(
                {
                    "line_number": record.get("line_number"),
                    "source_dispatch_id": record.get("dispatch_id"),
                    "contact_id": record.get("contact_id"),
                    "dispatch_type": record.get("dispatch_type"),
                    "result": "blocked",
                    "reason_codes": ["projection_source_dispatch_missing"],
                    "source_ledger": "content_dispatch.jsonl",
                }
            )
            continue

        contact_row = latest_contacts.get(str(record.get("contact_id") or ""))
        if contact_row is None:
            clean = False
            exclusions.append(
                {
                    "line_number": record.get("line_number"),
                    "source_dispatch_id": record.get("dispatch_id"),
                    "contact_id": record.get("contact_id"),
                    "dispatch_type": record.get("dispatch_type"),
                    "result": "blocked",
                    "reason_codes": ["projection_contact_snapshot_missing"],
                    "source_ledger": "content_dispatch.jsonl",
                }
            )
            continue

        dispatch_record = dispatch_row["record"]
        contact_snapshot = contact_row["record"]
        template_key = dispatch_record.get("template_key")
        content_reference = _content_reference(dispatch_record)
        queue.append(
            {
                "queue_id": _queue_id_from_dispatch(
                    source_dispatch_id=str(dispatch_record.get("dispatch_id") or ""),
                    source_line_number=dispatch_row["line_number"],
                    contact_id=str(dispatch_record.get("contact_id") or ""),
                    dispatch_type=str(dispatch_record.get("dispatch_type") or ""),
                    template_key=str(template_key or "") or None,
                    content_reference=content_reference,
                ),
                "source_dispatch_id": dispatch_record.get("dispatch_id"),
                "contact_id": dispatch_record.get("contact_id"),
                "contact_version": dispatch_record.get("contact_version"),
                "dispatch_type": dispatch_record.get("dispatch_type"),
                "template_key": template_key,
                "content_reference": content_reference,
                "consent_basis": _consent_basis(dispatch_record, contact_snapshot),
                "status": "send_ready",
                "source_ledger": "content_dispatch.jsonl",
                "source_line_number": dispatch_row["line_number"],
                "source_record_hash": dispatch_record.get("record_hash"),
            }
        )

    return {
        "clean": clean,
        "dispatch_ready_clean": True,
        "projected_count": len(queue),
        "excluded_count": len(exclusions),
        "queue": queue,
        "exclusions": exclusions,
        "source_state_root": source_state_root,
        "projection_basis_hash": _projection_basis_hash(
            dispatch_ready_clean=True,
            queue=queue,
            exclusions=exclusions,
            source_state_root=source_state_root,
        ),
    }
