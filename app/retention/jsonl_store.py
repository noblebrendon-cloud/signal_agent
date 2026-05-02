from __future__ import annotations

import json
from typing import BinaryIO
from pathlib import Path
from typing import Callable

from app.retention.identity import get_repo_root, get_state_root, sha256_hex, utc_now_iso
from app.utils.io_contract import append_jsonl_atomic_with_factory, ensure_parent_dir


REQUIRED_STATE_FILES = (
    "contacts.jsonl",
    "events.jsonl",
    "transitions.jsonl",
    "content_dispatch.jsonl",
)


def stable_json_dumps(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _state_root(repo_root: Path | None = None) -> Path:
    return get_state_root(repo_root or get_repo_root())


def _canonical_path(path_or_name: str | Path, repo_root: Path | None = None) -> Path:
    root = _state_root(repo_root).resolve()
    path = Path(path_or_name)
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"state_path_outside_allowed_root:{resolved}") from exc
    if resolved.parent != root:
        raise ValueError(f"state_path_parent_not_allowed:{resolved.parent}")
    return resolved


def ensure_state_file(path_or_name: str | Path, repo_root: Path | None = None) -> Path:
    path = _canonical_path(path_or_name, repo_root=repo_root)
    ensure_parent_dir(path)
    path.touch(exist_ok=True)
    return path


def ensure_required_state_files(repo_root: Path | None = None) -> list[Path]:
    created_or_existing: list[Path] = []
    for name in REQUIRED_STATE_FILES:
        created_or_existing.append(ensure_state_file(name, repo_root=repo_root))
    return created_or_existing


def iter_jsonl(path_or_name: str | Path, repo_root: Path | None = None) -> list[dict]:
    path = _canonical_path(path_or_name, repo_root=repo_root)
    if not path.exists():
        return []

    rows: list[dict] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid_jsonl:{path}:{line_number}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"non_dict_jsonl_record:{path}:{line_number}")
            rows.append(payload)
    return rows


def last_record(path_or_name: str | Path, repo_root: Path | None = None) -> dict | None:
    rows = iter_jsonl(path_or_name, repo_root=repo_root)
    return rows[-1] if rows else None


def find_latest_record(
    path_or_name: str | Path,
    predicate: Callable[[dict], bool],
    repo_root: Path | None = None,
) -> dict | None:
    matched: dict | None = None
    for row in iter_jsonl(path_or_name, repo_root=repo_root):
        if predicate(row):
            matched = row
    return matched


def compute_record_hash(record: dict) -> str:
    if not isinstance(record, dict):
        raise TypeError("record must be a dict")
    material = {key: value for key, value in record.items() if key != "record_hash"}
    stable_json = stable_json_dumps(material)
    return f"sha256:{sha256_hex(stable_json)}"


def _previous_record_hash(previous: dict | None, path: Path) -> str | None:
    if previous is None:
        return None

    record_hash = str(previous.get("record_hash") or "").strip()
    if not record_hash:
        raise ValueError(f"missing_record_hash:{path}")
    return record_hash


def _prepare_record_payload(
    path: Path,
    record: dict,
    previous: dict | None,
    *,
    recorded_at: str | None = None,
) -> dict:
    if not isinstance(record, dict):
        raise TypeError("record must be a dict")

    payload = dict(record)
    payload.pop("record_hash", None)
    payload["recorded_at"] = str(payload.get("recorded_at") or recorded_at or utc_now_iso())
    payload["prev_hash"] = _previous_record_hash(previous, path)
    payload["record_hash"] = compute_record_hash(payload)
    return json.loads(stable_json_dumps(payload))


def _read_last_locked_record(handle: BinaryIO, path: Path) -> dict | None:
    handle.seek(0)
    raw_bytes = handle.read()
    if not raw_bytes:
        return None

    lines = raw_bytes.decode("utf-8").splitlines()
    for index in range(len(lines) - 1, -1, -1):
        raw = lines[index].strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid_jsonl:{path}:{index + 1}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"non_dict_jsonl_record:{path}:{index + 1}")
        return payload
    return None


def preview_record(
    path_or_name: str | Path,
    record: dict,
    *,
    repo_root: Path | None = None,
    recorded_at: str | None = None,
) -> dict:
    path = _canonical_path(path_or_name, repo_root=repo_root)
    previous = last_record(path, repo_root=repo_root)
    return _prepare_record_payload(path, record, previous, recorded_at=recorded_at)


def append_record(
    path_or_name: str | Path,
    record: dict,
    *,
    repo_root: Path | None = None,
    retries: int = 30,
    base_sleep_s: float = 0.02,
    recorded_at: str | None = None,
) -> dict:
    path = _canonical_path(path_or_name, repo_root=repo_root)
    if not isinstance(record, dict):
        raise TypeError("record must be a dict")

    def _record_factory(handle: BinaryIO) -> dict:
        previous = _read_last_locked_record(handle, path)
        return _prepare_record_payload(path, record, previous, recorded_at=recorded_at)

    return append_jsonl_atomic_with_factory(
        path,
        _record_factory,
        retries=retries,
        base_sleep_s=base_sleep_s,
    )
