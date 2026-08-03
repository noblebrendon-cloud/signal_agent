from __future__ import annotations

import hashlib
import hmac
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from signal_agent.corpus_import.preservation import preserve_source_file
from signal_agent.corpus_import.receipts import seal_receipt, utc_now_iso
from signal_agent.transport.schemas import derive_id

from .key import InteractionEventKeyContext


RELATIONSHIP_SCHEMA_VERSION = "signal_agent.relationship_record.v1"
MATCH_REPORT_SCHEMA_VERSION = "signal_agent.unresolved_relationship_matches.v1"
SOURCE_RECEIPT_SCHEMA_VERSION = "signal_agent.interaction_event_source_receipt.v1"
SOURCE_TYPE = "interaction_event_export.v1"
PRESERVED_FILENAME = "interaction_events.jsonl"
HASH_RECORD_FILENAME = "interaction_events.jsonl.sha256.txt"
PRESERVED_RELATIVE_PATH = "00_original/interaction_events.jsonl"
HASH_RELATIVE_PATH = "00_original/interaction_events.jsonl.sha256.txt"
SOURCE_RECEIPT_RELATIVE_PATH = "05_receipts/source_receipt.json"

_REQUIRED_FIELDS = ("event_id", "actor_id", "thread_id", "timestamp", "text")
_META_FIELDS = ("display_name", "company", "position")
_EXPLICIT_OFFSET = re.compile(r"(?:Z|[+-]\d{2}:\d{2})$")


class InteractionEventImportError(RuntimeError):
    pass


@dataclass(frozen=True)
class ParsedInteractionEvent:
    event_id: str
    actor_id: str
    thread_id: str
    timestamp_raw: str
    timestamp_utc: str
    text: str
    display_name: str
    company: str
    position: str
    physical_line: int
    raw_line_sha256: str


@dataclass(frozen=True)
class InteractionEventImportPlan:
    source_path: Path
    source_sha256: str
    source_size_bytes: int
    source_stat: Any
    source_receipt: dict[str, Any]
    events: tuple[ParsedInteractionEvent, ...]
    records: tuple[dict[str, Any], ...]
    unresolved_matches: dict[str, Any]
    total_line_count: int
    blank_line_count: int
    timestamp_min_utc: str
    timestamp_max_utc: str


def _clean(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value)).strip()


def _require_nonempty_string(payload: dict[str, Any], field: str, line: int) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not _clean(value):
        raise InteractionEventImportError(
            f"interaction_event_{field}_required:line:{line}"
        )
    return _clean(value)


def _timestamp(value: str, line: int) -> tuple[str, str]:
    raw = value.strip()
    if not _EXPLICIT_OFFSET.search(raw):
        raise InteractionEventImportError(
            f"interaction_event_timestamp_offset_required:line:{line}"
        )
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InteractionEventImportError(
            f"interaction_event_timestamp_invalid:line:{line}"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InteractionEventImportError(
            f"interaction_event_timestamp_offset_required:line:{line}"
        )
    canonical = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return raw, canonical


def _parse_meta(value: object, line: int) -> tuple[str, str, str]:
    if value is None:
        return "", "", ""
    if not isinstance(value, dict):
        raise InteractionEventImportError(f"interaction_event_meta_object_required:line:{line}")
    parsed: list[str] = []
    for field in _META_FIELDS:
        field_value = value.get(field, "")
        if not isinstance(field_value, str):
            raise InteractionEventImportError(
                f"interaction_event_meta_{field}_string_required:line:{line}"
            )
        parsed.append(_clean(field_value))
    return parsed[0], parsed[1], parsed[2]


def _parse_events(raw_bytes: bytes) -> tuple[tuple[ParsedInteractionEvent, ...], int, int]:
    try:
        raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InteractionEventImportError("interaction_event_jsonl_utf8_required") from exc
    physical_lines = raw_bytes.splitlines(keepends=True)
    if raw_bytes and not physical_lines:
        physical_lines = [raw_bytes]
    events: list[ParsedInteractionEvent] = []
    blank_count = 0
    seen_event_ids: set[str] = set()
    for line_number, physical_line in enumerate(physical_lines, start=1):
        raw_line = physical_line.rstrip(b"\r\n")
        if not raw_line.strip():
            blank_count += 1
            continue
        try:
            payload = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InteractionEventImportError(
                f"interaction_event_json_invalid:line:{line_number}"
            ) from exc
        if not isinstance(payload, dict):
            raise InteractionEventImportError(
                f"interaction_event_object_required:line:{line_number}"
            )
        missing = [field for field in _REQUIRED_FIELDS if field not in payload]
        if missing:
            raise InteractionEventImportError(
                f"interaction_event_required_field_missing:{missing[0]}:line:{line_number}"
            )
        event_id = _require_nonempty_string(payload, "event_id", line_number)
        if event_id in seen_event_ids:
            raise InteractionEventImportError(
                f"interaction_event_duplicate_event_id:line:{line_number}"
            )
        seen_event_ids.add(event_id)
        actor_id = _require_nonempty_string(payload, "actor_id", line_number)
        thread_id = _require_nonempty_string(payload, "thread_id", line_number)
        timestamp_value = _require_nonempty_string(payload, "timestamp", line_number)
        timestamp_raw, timestamp_utc = _timestamp(timestamp_value, line_number)
        text = payload["text"]
        if not isinstance(text, str):
            raise InteractionEventImportError(
                f"interaction_event_text_string_required:line:{line_number}"
            )
        display_name, company, position = _parse_meta(payload.get("meta"), line_number)
        events.append(
            ParsedInteractionEvent(
                event_id=event_id,
                actor_id=actor_id,
                thread_id=thread_id,
                timestamp_raw=timestamp_raw,
                timestamp_utc=timestamp_utc,
                text=text,
                display_name=display_name,
                company=company,
                position=position,
                physical_line=line_number,
                raw_line_sha256=hashlib.sha256(raw_line).hexdigest(),
            )
        )
    if not events:
        raise InteractionEventImportError("interaction_event_jsonl_has_no_records")
    return tuple(events), len(physical_lines), blank_count


def _protected_identifier(
    *,
    kind: str,
    value: str,
    key_context: InteractionEventKeyContext,
) -> dict[str, Any]:
    if kind == "actor_id_hmac":
        digest = hmac.new(
            key_context.key_bytes,
            value.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "kind": kind,
            "value": f"hmac-sha256:{digest}",
            "key_id": key_context.key_id,
            "algorithm": key_context.algorithm,
            "version": key_context.token_version,
            "personal_data": True,
            "export_policy": "restricted_local_only",
        }
    return {
        "kind": kind,
        "value": "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest(),
        "personal_data": True,
        "export_policy": "restricted_local_only",
    }


def _build_record(
    *,
    event: ParsedInteractionEvent,
    source_sha256: str,
    receipt_id: str,
    record_number: int,
    key_context: InteractionEventKeyContext,
    actor_metadata_conflict: bool,
) -> dict[str, Any]:
    event_hash = hashlib.sha256(event.event_id.encode("utf-8")).hexdigest()
    record_id = derive_id(
        "rel",
        SOURCE_TYPE,
        source_sha256,
        event_hash,
        event.raw_line_sha256,
        length=20,
    )
    evidence_ref = (
        f"interaction-event-source:sha256:{source_sha256}:record:{record_number}:"
        f"line:{event.physical_line}:raw-line-sha256:{event.raw_line_sha256}"
    )
    issues: list[str] = []
    if not event.display_name:
        issues.append("display_name_missing")
    if not event.company:
        issues.append("company_missing")
    if not event.position:
        issues.append("position_missing")
    if not event.text.strip():
        issues.append("text_blank")
    if actor_metadata_conflict:
        issues.append("actor_metadata_conflict")
    identifiers = [
        _protected_identifier(
            kind="actor_id_hmac", value=event.actor_id, key_context=key_context
        ),
        _protected_identifier(
            kind="event_id_sha256", value=event.event_id, key_context=key_context
        ),
        _protected_identifier(
            kind="thread_id_sha256", value=event.thread_id, key_context=key_context
        ),
    ]
    text_state = "blank" if not event.text.strip() else "present"
    return {
        "schema_version": RELATIONSHIP_SCHEMA_VERSION,
        "relationship_record_id": record_id,
        "source_provenance": {
            "source_type": SOURCE_TYPE,
            "source_sha256": f"sha256:{source_sha256}",
            "source_receipt_id": receipt_id,
            "record_number": record_number,
            "line_start": event.physical_line,
            "line_end": event.physical_line,
            "raw_row_sha256": f"sha256:{event.raw_line_sha256}",
            "raw_line_sha256": f"sha256:{event.raw_line_sha256}",
            "evidence_ref": evidence_ref,
        },
        "person": {
            "first_name": "",
            "middle_name": "",
            "last_name": "",
            "display_name": event.display_name,
        },
        "professional_context": {
            "company": event.company,
            "position": event.position,
        },
        "relationship": {
            "platform": "interaction_event_export",
            "kind": "interaction_event",
            "occurred_at_raw": event.timestamp_raw,
            "occurred_at_utc": event.timestamp_utc,
            "occurred_at_state": "parsed",
            "text_state": text_state,
            "text_sha256": "sha256:"
            + hashlib.sha256(event.text.encode("utf-8")).hexdigest(),
        },
        "identifiers": identifiers,
        "deterministic_classification": {
            "source_platform": "interaction_event_export",
            "source_format": SOURCE_TYPE,
            "relationship_kind": "interaction_event",
            "field_presence": {
                "display_name": bool(event.display_name),
                "company": bool(event.company),
                "position": bool(event.position),
                "text": bool(event.text.strip()),
            },
            "timestamp_state": "parsed",
            "text_state": text_state,
        },
        "data_quality_issues": sorted(issues),
        "privacy": {
            "contains_personal_data": True,
            "clear_actor_id_retained": False,
            "clear_event_id_retained": False,
            "clear_thread_id_retained": False,
            "clear_text_retained": False,
            "public_export_allowed": False,
        },
    }


def _conflict_report(
    *,
    events: tuple[ParsedInteractionEvent, ...],
    records: tuple[dict[str, Any], ...],
    source_sha256: str,
    blank_line_count: int,
    total_line_count: int,
) -> dict[str, Any]:
    by_actor: dict[str, list[tuple[ParsedInteractionEvent, dict[str, Any]]]] = defaultdict(list)
    for event, record in zip(events, records):
        actor_token = next(
            item["value"] for item in record["identifiers"] if item["kind"] == "actor_id_hmac"
        )
        by_actor[actor_token].append((event, record))
    groups: list[dict[str, Any]] = []
    for actor_token, occurrences in sorted(by_actor.items()):
        metadata_states = {
            (event.display_name, event.company, event.position)
            for event, _record in occurrences
        }
        if len(occurrences) < 2 or len(metadata_states) < 2:
            continue
        record_ids = sorted(record["relationship_record_id"] for _event, record in occurrences)
        evidence_refs = sorted(
            record["source_provenance"]["evidence_ref"]
            for _event, record in occurrences
        )
        groups.append(
            {
                "candidate_group_id": derive_id(
                    "rcg",
                    source_sha256,
                    "actor_metadata_conflict",
                    actor_token,
                    record_ids,
                    length=20,
                ),
                "state": "review_required",
                "match_strength": "exact_protected_actor_id",
                "match_basis": "within_source_actor_metadata_conflict",
                "identifier_fingerprint": actor_token,
                "personal_data": True,
                "relationship_record_ids": record_ids,
                "evidence_refs": evidence_refs,
                "conflicting_fields": sorted(
                    field
                    for index, field in enumerate(_META_FIELDS)
                    if len({state[index] for state in metadata_states}) > 1
                ),
                "automatic_merge_performed": False,
                "canonical_identity_selected": False,
            }
        )
    groups.sort(key=lambda item: item["candidate_group_id"])
    involved = sorted(
        {
            record_id
            for group in groups
            for record_id in group["relationship_record_ids"]
        }
    )
    return {
        "schema_version": MATCH_REPORT_SCHEMA_VERSION,
        "state": "review_required",
        "source_sha256": f"sha256:{source_sha256}",
        "relationship_record_count": len(records),
        "source_parse_summary": {
            "physical_line_count": total_line_count,
            "nonblank_record_count": len(records),
            "blank_line_count": blank_line_count,
        },
        "candidate_group_count": len(groups),
        "records_in_candidate_groups": involved,
        "unresolved_record_ids": sorted(
            record["relationship_record_id"] for record in records
        ),
        "candidate_groups": groups,
        "excluded_match_methods": [
            "cross_source_matching",
            "fuzzy_identity_matching",
            "metadata_similarity",
        ],
        "automatic_merge_performed": False,
        "canonical_identity_selected": False,
    }


def _source_receipt(
    *,
    source_path: Path,
    source_sha256: str,
    source_size: int,
    created_at: str,
    events: tuple[ParsedInteractionEvent, ...],
    total_line_count: int,
    blank_line_count: int,
    key_context: InteractionEventKeyContext,
) -> dict[str, Any]:
    timestamp_values = sorted(event.timestamp_utc for event in events)
    receipt = {
        "schema_version": SOURCE_RECEIPT_SCHEMA_VERSION,
        "receipt_id": f"interaction-event-source.{source_sha256[:16]}",
        "created_at": created_at,
        "preservation_timestamp": created_at,
        "status": "completed",
        "operation": "preserve_interaction_event_export_source",
        "source": {
            "source_type": SOURCE_TYPE,
            "source_version": "v1",
            "observed_name": source_path.name,
            "sha256": f"sha256:{source_sha256}",
            "size_bytes": source_size,
            "physical_line_count": total_line_count,
            "blank_line_count": blank_line_count,
            "record_count": len(events),
            "timestamp_min_utc": timestamp_values[0],
            "timestamp_max_utc": timestamp_values[-1],
            "capture_time": created_at,
            "preserved_path": PRESERVED_RELATIVE_PATH,
            "preserved_sha256": f"sha256:{source_sha256}",
            "original_preserved": True,
            "hash_verified": True,
            "byte_for_byte_equal": True,
            "source_stat_stable": True,
            "source_stat_stability_fields": ["size_bytes", "mtime_ns"],
        },
        "identifier_protection": {
            "algorithm": key_context.algorithm,
            "key_id": key_context.key_id,
            "version": key_context.token_version,
        },
        "overwrite_policy": "refuse",
        "authorizations": {
            "authorization_scope": "none",
            "contact_allowed": False,
            "external_action_allowed": False,
            "message_allowed": False,
            "network_allowed": False,
            "publication_allowed": False,
            "routing_allowed": False,
        },
    }
    return seal_receipt(receipt)


def build_interaction_event_import_plan(
    source: str | Path,
    *,
    key_context: InteractionEventKeyContext,
    clock: Callable[[], str] = utc_now_iso,
) -> InteractionEventImportPlan:
    try:
        source_path = Path(source).expanduser().resolve(strict=True)
    except OSError as exc:
        raise InteractionEventImportError("interaction_event_source_unreadable") from exc
    if not source_path.is_file():
        raise InteractionEventImportError("interaction_event_source_not_regular_file")
    try:
        source_stat = source_path.stat()
        raw_bytes = source_path.read_bytes()
    except OSError as exc:
        raise InteractionEventImportError("interaction_event_source_unreadable") from exc
    source_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    events, total_line_count, blank_line_count = _parse_events(raw_bytes)
    receipt_id = f"interaction-event-source.{source_sha256[:16]}"
    metadata_by_actor: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    for event in events:
        metadata_by_actor[event.actor_id].add(
            (event.display_name, event.company, event.position)
        )
    conflicting_actor_ids = {
        actor_id
        for actor_id, metadata_states in metadata_by_actor.items()
        if len(metadata_states) > 1
    }
    records = tuple(
        _build_record(
            event=event,
            source_sha256=source_sha256,
            receipt_id=receipt_id,
            record_number=index,
            key_context=key_context,
            actor_metadata_conflict=event.actor_id in conflicting_actor_ids,
        )
        for index, event in enumerate(events, start=1)
    )
    created_at = clock()
    receipt = _source_receipt(
        source_path=source_path,
        source_sha256=source_sha256,
        source_size=len(raw_bytes),
        created_at=created_at,
        events=events,
        total_line_count=total_line_count,
        blank_line_count=blank_line_count,
        key_context=key_context,
    )
    timestamp_values = sorted(event.timestamp_utc for event in events)
    return InteractionEventImportPlan(
        source_path=source_path,
        source_sha256=source_sha256,
        source_size_bytes=len(raw_bytes),
        source_stat=source_stat,
        source_receipt=receipt,
        events=events,
        records=records,
        unresolved_matches=_conflict_report(
            events=events,
            records=records,
            source_sha256=source_sha256,
            blank_line_count=blank_line_count,
            total_line_count=total_line_count,
        ),
        total_line_count=total_line_count,
        blank_line_count=blank_line_count,
        timestamp_min_utc=timestamp_values[0],
        timestamp_max_utc=timestamp_values[-1],
    )


def preserve_interaction_event_source(
    plan: InteractionEventImportPlan,
    run_root: str | Path,
) -> None:
    result = preserve_source_file(
        plan.source_path,
        Path(run_root),
        expected_sha256=plan.source_sha256,
        expected_stat=plan.source_stat,
        preserved_filename=PRESERVED_FILENAME,
        hash_record_filename=HASH_RECORD_FILENAME,
    )
    if result.preserved_sha256 != plan.source_sha256:
        raise InteractionEventImportError(
            "interaction_event_preserved_source_hash_mismatch"
        )
