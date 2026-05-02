from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from app.retention.dispatch import plan_dispatch
from app.retention.identity import (
    get_repo_root,
    identifier_hash,
    normalize_identifier,
    normalize_token,
    sha256_hex,
    utc_now_iso,
)
from app.retention.jsonl_store import (
    append_record,
    ensure_required_state_files,
    ensure_state_file,
    iter_jsonl,
    stable_json_dumps,
)
from app.retention.models import build_contact_seed_event, build_contact_snapshot
from app.retention.transitions import evaluate_transition, load_latest_contact_snapshot
from app.utils.io_contract import ensure_parent_dir


EMAIL_COLUMN_CANDIDATES = (
    "email",
    "subscriber_email",
)
STATUS_COLUMN_CANDIDATES = (
    "status",
    "subscription_status",
    "type",
)
OPTED_IN_STATUSES = {"active", "free", "paid", "subscribed", "founding"}
PENDING_STATUSES = {"imported", "pending", "unverified"}
UNSUBSCRIBED_STATUSES = {"unsubscribed", "canceled", "cancelled"}
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_header_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", normalize_token(value)).strip("_")


def _column_lookup(row: dict[str, Any], candidates: tuple[str, ...]) -> str:
    normalized_candidates = {_normalize_header_key(candidate) for candidate in candidates}
    for key, value in row.items():
        if _normalize_header_key(key) in normalized_candidates:
            return str(value or "").strip()
    return ""


def _read_csv_rows(input_path: Path) -> list[dict[str, str]]:
    with open(input_path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _file_checksum(input_path: Path) -> str:
    hasher = hashlib.sha256()
    with open(input_path, "rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def _batch_id_from_checksum(checksum: str) -> str:
    return f"sbx_{checksum.split(':', 1)[-1][:16]}"


def _normalize_status(raw_status: str) -> tuple[str, str]:
    status = normalize_token(raw_status)
    if status in OPTED_IN_STATUSES:
        return "contact_seeded", "opted_in"
    if status in PENDING_STATUSES:
        return "contact_seeded", "import_pending_verification"
    if status in UNSUBSCRIBED_STATUSES:
        return "unsubscribe", "unknown"
    return "contact_seeded", "unknown"


def _normalize_row(row: dict[str, str]) -> tuple[dict[str, str] | None, str | None]:
    raw_email = _column_lookup(row, EMAIL_COLUMN_CANDIDATES)
    if not raw_email:
        return None, "missing_email"

    email = normalize_identifier(raw_email)
    if not EMAIL_PATTERN.fullmatch(email):
        return None, "invalid_email"

    raw_status = _column_lookup(row, STATUS_COLUMN_CANDIDATES)
    event_type, consent_status = _normalize_status(raw_status)
    email_hash = identifier_hash("email", email)
    row_fingerprint = sha256_hex(
        stable_json_dumps(
            {
                "source": "substack",
                "identifier_hash": email_hash,
                "event_type": event_type,
                "consent_status": consent_status,
                "status": normalize_token(raw_status) or "missing",
            }
        )
    )
    return {
        "email": email,
        "event_type": event_type,
        "consent_status": consent_status,
        "row_fingerprint": row_fingerprint,
    }, None


def _load_existing_event_ids(repo_root: Path | None = None) -> set[str]:
    rows = iter_jsonl("events.jsonl", repo_root=repo_root)
    return {str(row.get("event_id") or "").strip() for row in rows if row.get("event_id")}


def _build_event_from_row(normalized_row: dict[str, str]) -> dict[str, Any]:
    return build_contact_seed_event(
        source="substack",
        identifier_kind="email",
        identifier_value=normalized_row["email"],
        consent_status=normalized_row["consent_status"],
        event_type=normalized_row["event_type"],
        source_mode="csv_export",
        event_key=normalized_row["row_fingerprint"],
    )


def _copy_raw_csv(input_path: Path, *, repo_root: Path | None = None, checksum: str) -> tuple[str, Path]:
    root = repo_root or get_repo_root()
    batch_id = _batch_id_from_checksum(checksum)
    date_component = utc_now_iso().split("T", 1)[0]
    raw_relative = Path("data") / "raw" / "substack" / date_component / f"{batch_id}.csv"
    raw_target = root / raw_relative
    ensure_parent_dir(raw_target)
    if not raw_target.exists():
        shutil.copyfile(input_path, raw_target)
    return raw_relative.as_posix(), raw_target


def _build_source_batch_manifest(
    *,
    batch_id: str,
    raw_path: str,
    checksum: str,
    rows_seen: int,
    rows_valid: int,
    rows_skipped: int,
    duplicate_skipped: int,
) -> dict[str, Any]:
    return {
        "record_type": "source_batch",
        "schema_version": "1.0",
        "batch_id": batch_id,
        "source": "substack",
        "source_mode": "csv_export",
        "raw_path": raw_path,
        "checksum": checksum,
        "rows_seen": rows_seen,
        "rows_valid": rows_valid,
        "rows_skipped": rows_skipped,
        "duplicate_skipped": duplicate_skipped,
        "created_at": utc_now_iso(),
    }


def ingest_substack_csv(
    input_path: str | Path,
    *,
    apply: bool,
    plan_dispatch_enabled: bool,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    root = repo_root or get_repo_root()
    csv_path = Path(input_path)
    rows = _read_csv_rows(csv_path)
    checksum = _file_checksum(csv_path)
    batch_id = _batch_id_from_checksum(checksum)

    skipped_reasons: Counter[str] = Counter()
    existing_event_ids = _load_existing_event_ids(repo_root=root)
    seen_event_ids = set(existing_event_ids)

    rows_seen = 0
    rows_valid = 0
    rows_skipped = 0
    duplicate_skipped = 0
    events_count = 0
    transitions_count = 0
    contacts_count = 0
    dispatch_count = 0
    manifests_count = 0
    raw_path_value: str | None = None

    if apply:
        ensure_required_state_files(repo_root=root)
        ensure_state_file("source_batches.jsonl", repo_root=root)
        raw_path_value, _ = _copy_raw_csv(csv_path, repo_root=root, checksum=checksum)

    for row in rows:
        rows_seen += 1
        normalized_row, skipped_reason = _normalize_row(row)
        if skipped_reason is not None:
            rows_skipped += 1
            skipped_reasons[skipped_reason] += 1
            continue

        rows_valid += 1
        event = _build_event_from_row(normalized_row)
        if event["event_id"] in seen_event_ids:
            rows_skipped += 1
            duplicate_skipped += 1
            skipped_reasons["duplicate_event_id"] += 1
            continue

        previous_snapshot = load_latest_contact_snapshot(event["contact_id"], repo_root=root)
        transition = evaluate_transition(event, previous_snapshot=previous_snapshot)
        contact_snapshot = build_contact_snapshot(
            previous_snapshot=previous_snapshot,
            event=event,
            transition=transition,
        )
        dispatch_plan = plan_dispatch(contact_snapshot, contact_id=event["contact_id"])

        events_count += 1
        transitions_count += 1
        if contact_snapshot is not None:
            contacts_count += 1
        if plan_dispatch_enabled and dispatch_plan.get("decision") == "planned":
            dispatch_count += 1

        if apply:
            append_record("events.jsonl", event, repo_root=root)
            append_record("transitions.jsonl", transition, repo_root=root)
            if contact_snapshot is not None:
                append_record("contacts.jsonl", contact_snapshot, repo_root=root)
            if plan_dispatch_enabled and dispatch_plan.get("decision") == "planned":
                append_record("content_dispatch.jsonl", dispatch_plan, repo_root=root)

        seen_event_ids.add(event["event_id"])

    if apply:
        manifest = _build_source_batch_manifest(
            batch_id=batch_id,
            raw_path=str(raw_path_value),
            checksum=checksum,
            rows_seen=rows_seen,
            rows_valid=rows_valid,
            rows_skipped=rows_skipped,
            duplicate_skipped=duplicate_skipped,
        )
        append_record("source_batches.jsonl", manifest, repo_root=root)
        manifests_count = 1

    return json.loads(
        json.dumps(
            {
                "source": "substack",
                "mode": "apply" if apply else "dry_run",
                "input_path": str(csv_path),
                "batch_id": batch_id,
                "checksum": checksum,
                "raw_path": raw_path_value,
                "rows_seen": rows_seen,
                "rows_valid": rows_valid,
                "rows_skipped": rows_skipped,
                "duplicate_skipped": duplicate_skipped,
                "skipped_reasons": dict(sorted(skipped_reasons.items())),
                "events_previewed": events_count,
                "transitions_previewed": transitions_count,
                "contacts_previewed": contacts_count,
                "dispatches_previewed": dispatch_count,
                "source_batches_appended": manifests_count,
            },
            sort_keys=True,
        )
    )
