from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from typing import Any

from .errors import OperationalValidationError


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def canonical_json_bytes(payload: Any) -> bytes:
    return (canonical_json(payload) + "\n").encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def sha256_canonical(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def derive_id(prefix: str, *parts: Any, length: int = 20) -> str:
    digest = hashlib.sha256(canonical_json(list(parts)).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:length]}"


def sealed_hash(payload: dict[str, Any], field: str = "artifact_hash") -> str:
    material = deepcopy(payload)
    material.pop(field, None)
    return sha256_canonical(material)


def seal(payload: dict[str, Any], field: str = "artifact_hash") -> dict[str, Any]:
    sealed = deepcopy(payload)
    sealed[field] = sealed_hash(sealed, field)
    return sealed


def verify_seal(payload: dict[str, Any], field: str = "artifact_hash") -> bool:
    return payload.get(field) == sealed_hash(payload, field)


def require_sha256(value: str, label: str) -> str:
    candidate = str(value or "")
    if len(candidate) != 71 or not candidate.startswith("sha256:"):
        raise OperationalValidationError(f"{label}_sha256_required")
    try:
        int(candidate[7:], 16)
    except ValueError as exc:
        raise OperationalValidationError(f"{label}_sha256_required") from exc
    return candidate


def require_text(value: str, label: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        raise OperationalValidationError(f"{label}_required")
    return candidate


def require_offset_timestamp(value: str, label: str) -> str:
    candidate = require_text(value, label)
    normalized = candidate[:-1] + "+00:00" if candidate.endswith("Z") else candidate
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise OperationalValidationError(f"{label}_offset_timestamp_required") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OperationalValidationError(f"{label}_offset_timestamp_required")
    return candidate
