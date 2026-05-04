from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO

from jsonschema import Draft202012Validator

from app.utils.io_contract import append_jsonl_atomic_with_factory

from .errors import AuditLogError
from .proposal import dump_canonical_json


AUDIT_ZERO_HASH = f"sha256:{'0' * 64}"
AUDIT_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "audit_event.v1.json"


@dataclass(frozen=True)
class AuditVerificationResult:
    clean: bool
    event_count: int
    issues: list[str]
    first_event_id: str | None
    last_event_id: str | None
    last_record_hash: str | None


def canonical_event_json(event: dict) -> str:
    """Render audit events with deterministic key ordering."""

    return dump_canonical_json(event)


def compute_event_hash(event_without_record_hash: dict) -> str:
    """Compute a stable record hash excluding the record_hash field itself."""

    if type(event_without_record_hash) is not dict:
        raise AuditLogError("Audit event hash input must be a plain dict.")

    material = dict(event_without_record_hash)
    material.pop("record_hash", None)
    canonical_json = canonical_event_json(material)

    import hashlib

    return f"sha256:{hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()}"


def _format_error_path(parts: tuple[object, ...]) -> str:
    if not parts:
        return "$"

    rendered: list[str] = ["$"]
    for part in parts:
        if isinstance(part, int):
            rendered.append(f"[{part}]")
        else:
            rendered.append(f".{part}")
    return "".join(rendered)


@lru_cache(maxsize=1)
def _audit_event_validator() -> Draft202012Validator:
    try:
        schema = json.loads(AUDIT_SCHEMA_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AuditLogError(f"Unable to read audit event schema: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise AuditLogError(f"Audit event schema is malformed JSON: {exc}") from exc

    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise AuditLogError(f"Audit event schema is invalid: {exc}") from exc

    return Draft202012Validator(schema)


def _validate_audit_event(event: dict, *, line_number: int | None = None) -> None:
    validator = _audit_event_validator()
    errors = sorted(validator.iter_errors(event), key=lambda err: list(err.absolute_path))
    if not errors:
        return

    prefix = ""
    if line_number is not None:
        prefix = f" at line {line_number}"
    rendered = "; ".join(
        f"{_format_error_path(tuple(error.absolute_path))}: {error.message}" for error in errors
    )
    raise AuditLogError(f"Audit event schema validation failed{prefix}: {rendered}")


def _read_last_locked_event(handle: BinaryIO, path: Path) -> dict | None:
    handle.seek(0)
    raw_bytes = handle.read()
    if not raw_bytes:
        return None

    lines = raw_bytes.decode("utf-8").splitlines()
    for line_number in range(len(lines), 0, -1):
        raw = lines[line_number - 1].strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AuditLogError(
                f"Malformed audit JSONL in {path} at line {line_number}: {exc.msg}"
            ) from exc
        if type(payload) is not dict:
            raise AuditLogError(f"Audit JSONL record must be an object at line {line_number}.")
        _validate_audit_event(payload, line_number=line_number)
        return payload
    return None


def _prepare_event_payload(path: Path, event: dict, previous: dict | None) -> dict:
    if type(event) is not dict:
        raise AuditLogError("Audit event payload must be a plain dict.")

    payload = dict(event)
    payload.pop("record_hash", None)

    expected_index = 0 if previous is None else int(previous.get("event_index", -1)) + 1
    actual_index = payload.get("event_index")
    if not isinstance(actual_index, int):
        raise AuditLogError("Audit event must include an integer event_index.")
    if actual_index != expected_index:
        raise AuditLogError(
            f"Audit event_index must be {expected_index}, received {actual_index}."
        )

    payload["prev_hash"] = AUDIT_ZERO_HASH if previous is None else str(previous["record_hash"])
    payload["record_hash"] = compute_event_hash(payload)
    canonical_payload = json.loads(canonical_event_json(payload))
    _validate_audit_event(canonical_payload)
    return canonical_payload


def read_audit_events(path: Path) -> list[dict]:
    """Read and validate all audit events from a JSONL ledger."""

    ledger_path = Path(path)
    if not ledger_path.exists():
        raise AuditLogError(f"Audit ledger does not exist: {ledger_path}")

    events: list[dict] = []
    try:
        with open(ledger_path, "r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                raw = line.strip()
                if not raw:
                    raise AuditLogError(
                        f"Audit ledger contains a blank or malformed line at {line_number}."
                    )
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise AuditLogError(
                        f"Malformed audit JSONL in {ledger_path} at line {line_number}: {exc.msg}"
                    ) from exc
                if type(payload) is not dict:
                    raise AuditLogError(
                        f"Audit JSONL record must be an object in {ledger_path} at line {line_number}."
                    )
                _validate_audit_event(payload, line_number=line_number)
                events.append(payload)
    except OSError as exc:
        raise AuditLogError(f"Unable to read audit ledger {ledger_path}: {exc}") from exc

    return events


def verify_audit_chain(path: Path) -> AuditVerificationResult:
    """Verify hash-chain integrity and schema validity for the audit ledger."""

    ledger_path = Path(path)
    if not ledger_path.exists():
        return AuditVerificationResult(
            clean=False,
            event_count=0,
            issues=[f"audit_ledger_missing:{ledger_path}"],
            first_event_id=None,
            last_event_id=None,
            last_record_hash=None,
        )

    issues: list[str] = []
    event_count = 0
    first_event_id: str | None = None
    last_event_id: str | None = None
    last_record_hash: str | None = None
    expected_prev_hash = AUDIT_ZERO_HASH
    expected_index = 0

    try:
        with open(ledger_path, "r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                raw = line.strip()
                if not raw:
                    issues.append(f"malformed_jsonl_line:{line_number}")
                    break
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    issues.append(f"malformed_jsonl_line:{line_number}")
                    break

                if type(payload) is not dict:
                    issues.append(f"non_object_jsonl_line:{line_number}")
                    break

                try:
                    _validate_audit_event(payload, line_number=line_number)
                except AuditLogError as exc:
                    issues.append(str(exc))
                    break

                actual_event_index = payload.get("event_index")
                if actual_event_index != expected_index:
                    issues.append(
                        f"non_monotonic_event_index:{line_number}:expected={expected_index}:actual={actual_event_index}"
                    )

                actual_prev_hash = payload.get("prev_hash")
                if actual_prev_hash != expected_prev_hash:
                    issues.append(
                        f"broken_prev_hash:{line_number}:expected={expected_prev_hash}:actual={actual_prev_hash}"
                    )

                expected_record_hash = compute_event_hash(payload)
                actual_record_hash = payload.get("record_hash")
                if actual_record_hash != expected_record_hash:
                    issues.append(
                        f"record_hash_mismatch:{line_number}:expected={expected_record_hash}:actual={actual_record_hash}"
                    )

                event_count += 1
                event_id = payload.get("event_id")
                if first_event_id is None and isinstance(event_id, str):
                    first_event_id = event_id
                if isinstance(event_id, str):
                    last_event_id = event_id
                if isinstance(actual_record_hash, str):
                    last_record_hash = actual_record_hash

                expected_prev_hash = str(actual_record_hash or expected_prev_hash)
                expected_index += 1
    except OSError as exc:
        return AuditVerificationResult(
            clean=False,
            event_count=0,
            issues=[f"audit_ledger_unreadable:{ledger_path}:{exc}"],
            first_event_id=None,
            last_event_id=None,
            last_record_hash=None,
        )

    return AuditVerificationResult(
        clean=not issues,
        event_count=event_count,
        issues=issues,
        first_event_id=first_event_id,
        last_event_id=last_event_id,
        last_record_hash=last_record_hash,
    )


def append_audit_event(path: Path, event: dict) -> dict:
    """Append a single governed-shell audit event to a JSONL ledger."""

    ledger_path = Path(path)

    def _record_factory(handle: BinaryIO) -> dict:
        previous = _read_last_locked_event(handle, ledger_path)
        return _prepare_event_payload(ledger_path, event, previous)

    try:
        return append_jsonl_atomic_with_factory(ledger_path, _record_factory)
    except AuditLogError:
        raise
    except Exception as exc:
        raise AuditLogError(f"Unable to append audit event to {ledger_path}: {exc}") from exc


def build_review_event(
    *,
    session_id: str,
    event_index: int,
    timestamp_utc: str,
    proposal_id: str,
    proposal_hash: str,
    policy_hash: str,
    risk_level: str,
    decision_code: str,
    status: str,
    details: dict,
    event_id: str | None = None,
    event_type: str = "proposal_reviewed",
    plan_id: str = "plan.none",
    plan_hash: str = AUDIT_ZERO_HASH,
    snapshot_ref: str = "data/state/governed_shell/snapshots/none.json",
    receipt_ref: str = "data/state/governed_shell/receipts/none.json",
) -> dict:
    """Build a deterministic review event payload without appending it."""

    resolved_event_id = event_id or f"{event_type}.{session_id}.{event_index}"
    payload = {
        "schema_version": "audit_event.v1",
        "record_type": "governed_shell_audit_event",
        "event_id": resolved_event_id,
        "session_id": session_id,
        "event_index": event_index,
        "timestamp_utc": timestamp_utc,
        "event_type": event_type,
        "status": status,
        "proposal_id": proposal_id,
        "proposal_hash": proposal_hash,
        "plan_id": plan_id,
        "plan_hash": plan_hash,
        "policy_hash": policy_hash,
        "risk_level": risk_level,
        "decision_code": decision_code,
        "snapshot_ref": snapshot_ref,
        "receipt_ref": receipt_ref,
        "details": dict(details),
        "prev_hash": AUDIT_ZERO_HASH,
        "record_hash": AUDIT_ZERO_HASH,
    }
    _validate_audit_event(payload)
    return json.loads(canonical_event_json(payload))
