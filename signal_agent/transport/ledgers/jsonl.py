from __future__ import annotations

import contextlib
import json
import os
import time
from pathlib import Path
from typing import Any, BinaryIO, Callable, Mapping

from signal_agent.transport.schemas import stable_digest
from signal_agent.transport.schemas.models import stable_json_dumps


def utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class _LedgerLock:
    def __init__(
        self,
        path: Path,
        retries: int = 30,
        base_sleep_s: float = 0.02,
        *,
        initializer: bytes = b"\0",
    ) -> None:
        self.path = path
        self.retries = retries
        self.base_sleep_s = base_sleep_s
        self.initializer = initializer
        self.handle: BinaryIO | None = None

    def __enter__(self) -> "_LedgerLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, "a+b")
        if self.handle.tell() == 0:
            self.handle.write(self.initializer)
            self.handle.flush()
            os.fsync(self.handle.fileno())

        for attempt in range(self.retries):
            try:
                self._lock()
                return self
            except OSError:
                if attempt == self.retries - 1:
                    raise TimeoutError(f"ledger_lock_timeout:{self.path}")
                time.sleep(self.base_sleep_s * (attempt + 1))
        raise TimeoutError(f"ledger_lock_timeout:{self.path}")

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self._unlock()
        finally:
            if self.handle is not None:
                self.handle.close()
                self.handle = None

    def _lock(self) -> None:
        if self.handle is None:
            raise RuntimeError("ledger_lock_handle_missing")
        if os.name == "nt":
            import msvcrt

            self.handle.seek(0)
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            return

        import fcntl

        fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(self) -> None:
        if self.handle is None:
            return
        if os.name == "nt":
            import msvcrt

            self.handle.seek(0)
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            return

        import fcntl

        fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)


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
                raise ValueError(f"invalid_transport_jsonl:{path}:{line_number}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"non_dict_transport_jsonl:{path}:{line_number}")
            rows.append(payload)
    return rows


def _read_last_locked(handle: BinaryIO, path: Path) -> dict[str, Any] | None:
    handle.seek(0)
    raw = handle.read()
    if not raw:
        return None
    for reverse_index, line in enumerate(reversed(raw.decode("utf-8").splitlines()), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            line_number = len(raw.decode("utf-8").splitlines()) - reverse_index + 1
            raise ValueError(f"invalid_transport_jsonl:{path}:{line_number}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"non_dict_transport_jsonl:{path}")
        return payload
    return None


def _write_locked(handle: BinaryIO, path: Path, record: Mapping[str, Any]) -> None:
    payload = (stable_json_dumps(record) + "\n").encode("utf-8")
    handle.seek(0, os.SEEK_END)
    start_position = handle.tell()
    try:
        written = handle.write(payload)
        if written != len(payload):
            raise OSError(f"short_transport_ledger_write:{path}")
        handle.flush()
        os.fsync(handle.fileno())
    except Exception:
        with contextlib.suppress(Exception):
            handle.seek(start_position)
            handle.truncate(start_position)
            handle.flush()
            os.fsync(handle.fileno())
        raise


class AppendOnlyJsonlLedger:
    """Hash-chained JSONL append surface for transport audit events."""

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Callable[[], str] = utc_now_iso,
        lock_on_ledger: bool = False,
    ) -> None:
        self.path = Path(path)
        self.clock = clock
        self.lock_path = self.path if lock_on_ledger else self.path.with_suffix(self.path.suffix + ".lock")
        self.lock_initializer = b"\n" if lock_on_ledger else b"\0"

    def read(self) -> list[dict[str, Any]]:
        return _read_jsonl(self.path)

    def append(self, record: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(record, Mapping):
            raise TypeError("transport_ledger_record_must_be_mapping")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _LedgerLock(self.lock_path, initializer=self.lock_initializer) as ledger_lock:
            if self.lock_path == self.path:
                if ledger_lock.handle is None:
                    raise RuntimeError("transport_ledger_lock_handle_missing")
                return self._append_locked(ledger_lock.handle, record)
            with open(self.path, "ab+") as handle:
                return self._append_locked(handle, record)

    def _append_locked(self, handle: BinaryIO, record: Mapping[str, Any]) -> dict[str, Any]:
        previous = _read_last_locked(handle, self.path)
        payload = dict(record)
        payload.pop("record_hash", None)
        payload.pop("prev_hash", None)
        payload["recorded_at"] = str(payload.get("recorded_at") or self.clock())
        payload["sequence"] = int(previous.get("sequence", 0) or 0) + 1 if previous else 1
        payload["prev_hash"] = _previous_hash(previous, self.path)
        payload["record_hash"] = f"sha256:{stable_digest(payload)}"
        _write_locked(handle, self.path, payload)
        return json.loads(stable_json_dumps(payload))


def _previous_hash(previous: Mapping[str, Any] | None, path: Path) -> str | None:
    if previous is None:
        return None
    record_hash = str(previous.get("record_hash") or "").strip()
    if not record_hash:
        raise ValueError(f"transport_ledger_prev_hash_missing:{path}")
    return record_hash
