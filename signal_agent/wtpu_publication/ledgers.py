from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

from signal_agent.transport.ledgers import AppendOnlyJsonlLedger, utc_now_iso
from signal_agent.transport.schemas import stable_digest

from .models import WTPUPublicationEvent, reject_forbidden_publication_fields, validate_event_type


WTPU_PUBLICATION_LEDGER_SCHEMA_VERSION = "wtpu_publication.ledger_event.v1"
WTPU_PUBLICATION_EVENT_LEDGER_NAME = "events"
WTPU_PUBLICATION_LEDGER_DIR = Path("data") / "state" / "wtpu_publication"


class WTPULedgerError(Exception):
    pass


class UnsupportedWTPUEventType(ValueError, WTPULedgerError):
    pass


class MalformedWTPULedgerRecord(ValueError, WTPULedgerError):
    pass


class DuplicateWTPUEventId(WTPULedgerError):
    pass


class WTPULedgerIntegrityError(WTPULedgerError):
    pass


def default_wtpu_publication_ledger_path(root: str | Path | None = None) -> Path:
    base = Path(root) if root is not None else Path.cwd()
    return base / WTPU_PUBLICATION_LEDGER_DIR / f"{WTPU_PUBLICATION_EVENT_LEDGER_NAME}.jsonl"


class WTPUPublicationLedger:
    """Append-only WTPU civic publication event stream.

    The ledger is the only authority for WTPU editorial state. Projections are
    rebuilt by replaying this hash-chained JSONL stream.
    """

    def __init__(
        self,
        *,
        root: str | Path | None = None,
        path: str | Path | None = None,
        clock: Callable[[], str] = utc_now_iso,
    ) -> None:
        if root is not None and path is not None:
            raise ValueError("wtpu_publication_ledger_accepts_root_or_path_not_both")
        self.root = Path(root) if root is not None else None
        self.path = Path(path) if path is not None else default_wtpu_publication_ledger_path(root)
        self.clock = clock
        self._ledger = AppendOnlyJsonlLedger(self.path, clock=clock, lock_on_ledger=True)

    def append(self, event: WTPUPublicationEvent | Mapping[str, Any]) -> dict[str, Any]:
        publication_event = _coerce_event(event)
        self._reject_duplicate_event_id(publication_event.event_id)
        return self._ledger.append(_event_payload(publication_event))

    def read_records(self, *, validate: bool = True) -> list[dict[str, Any]]:
        rows = _read_jsonl(self.path)
        if validate:
            validate_wtpu_publication_ledger_records(rows)
        return rows

    def iter_records(self, *, validate: bool = True):
        yield from self.read_records(validate=validate)

    def read_events(self, *, validate: bool = True) -> list[WTPUPublicationEvent]:
        rows = self.read_records(validate=validate)
        return [_event_from_record(row) for row in rows]

    def validate(self) -> dict[str, Any]:
        rows = self.read_records(validate=False)
        validate_wtpu_publication_ledger_records(rows)
        return {
            "clean": True,
            "event_count": len(rows),
            "last_record_hash": rows[-1].get("record_hash") if rows else None,
            "path": str(self.path),
        }

    def _reject_duplicate_event_id(self, event_id: str) -> None:
        for row in self.read_records(validate=True):
            if str(row.get("event_id") or "") == event_id:
                raise DuplicateWTPUEventId(f"duplicate_wtpu_publication_event_id:{event_id}")


def validate_wtpu_publication_ledger_records(rows: list[Mapping[str, Any]]) -> None:
    seen_event_ids: set[str] = set()
    previous_hash: str | None = None
    seen_command_hashes: dict[str, str] = {}
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise MalformedWTPULedgerRecord(f"wtpu_publication_ledger_record_not_object:{index}")
        _validate_record_shape(row, index)
        event_id = str(row.get("event_id") or "")
        if event_id in seen_event_ids:
            raise DuplicateWTPUEventId(f"duplicate_wtpu_publication_event_id:{event_id}")
        seen_event_ids.add(event_id)
        command_id = str(row.get("command_id") or "").strip()
        command_payload_hash = str(row.get("command_payload_hash") or "").strip()
        if command_id:
            existing_hash = seen_command_hashes.get(command_id)
            if existing_hash is not None and existing_hash != command_payload_hash:
                raise WTPULedgerIntegrityError(f"wtpu_publication_command_payload_hash_conflict:{command_id}")
            seen_command_hashes[command_id] = command_payload_hash
        if row.get("sequence") != index:
            raise WTPULedgerIntegrityError(f"wtpu_publication_sequence_break:{index}")
        if row.get("prev_hash") != previous_hash:
            raise WTPULedgerIntegrityError(f"wtpu_publication_prev_hash_break:{index}")
        record_hash = str(row.get("record_hash") or "")
        expected_hash = _record_hash(row)
        if record_hash != expected_hash:
            raise WTPULedgerIntegrityError(f"wtpu_publication_record_hash_break:{index}")
        previous_hash = record_hash


def _validate_record_shape(row: Mapping[str, Any], index: int) -> None:
    schema_version = str(row.get("schema_version") or "")
    if schema_version != WTPU_PUBLICATION_LEDGER_SCHEMA_VERSION:
        raise MalformedWTPULedgerRecord(f"wtpu_publication_schema_version_invalid:{index}")
    for key in ("event_id", "event_type", "occurred_at", "metadata", "recorded_at", "sequence", "record_hash"):
        if key not in row:
            raise MalformedWTPULedgerRecord(f"wtpu_publication_ledger_record_missing_{key}:{index}")
    try:
        validate_event_type(str(row.get("event_type") or ""))
    except ValueError as exc:
        raise UnsupportedWTPUEventType(str(exc)) from exc
    if not str(row.get("event_id") or "").strip():
        raise MalformedWTPULedgerRecord(f"wtpu_publication_event_id_required:{index}")
    if not str(row.get("occurred_at") or "").strip():
        raise MalformedWTPULedgerRecord(f"wtpu_publication_occurred_at_required:{index}")
    if not isinstance(row.get("metadata"), Mapping):
        raise MalformedWTPULedgerRecord(f"wtpu_publication_metadata_must_be_object:{index}")
    try:
        reject_forbidden_publication_fields(row)
        WTPUPublicationEvent.from_dict(row)
    except (TypeError, ValueError) as exc:
        raise MalformedWTPULedgerRecord(f"wtpu_publication_event_malformed:{index}:{exc}") from exc


def _coerce_event(event: WTPUPublicationEvent | Mapping[str, Any]) -> WTPUPublicationEvent:
    try:
        if isinstance(event, WTPUPublicationEvent):
            return event
        if isinstance(event, Mapping):
            return WTPUPublicationEvent.from_dict(event)
    except (TypeError, ValueError) as exc:
        raise MalformedWTPULedgerRecord(f"wtpu_publication_event_malformed:{exc}") from exc
    raise MalformedWTPULedgerRecord("wtpu_publication_event_must_be_mapping_or_event")


def _event_payload(event: WTPUPublicationEvent) -> dict[str, Any]:
    payload = event.to_dict()
    payload["schema_version"] = WTPU_PUBLICATION_LEDGER_SCHEMA_VERSION
    return payload


def _event_from_record(row: Mapping[str, Any]) -> WTPUPublicationEvent:
    try:
        return WTPUPublicationEvent.from_dict(row)
    except (TypeError, ValueError) as exc:
        raise MalformedWTPULedgerRecord(f"wtpu_publication_event_malformed:{exc}") from exc


def _record_hash(row: Mapping[str, Any]) -> str:
    material = dict(row)
    material.pop("record_hash", None)
    return f"sha256:{stable_digest(material)}"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise MalformedWTPULedgerRecord(
                    f"wtpu_publication_ledger_invalid_json:{line_number}"
                ) from exc
            if not isinstance(payload, dict):
                raise MalformedWTPULedgerRecord(f"wtpu_publication_ledger_record_not_object:{line_number}")
            rows.append(payload)
    return rows
