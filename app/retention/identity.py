from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path


def get_repo_root() -> Path:
    override = os.environ.get("SIGNAL_AGENT_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2]


def get_state_root(repo_root: Path | None = None) -> Path:
    root = repo_root or get_repo_root()
    return root / "data" / "state"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_token(value: str) -> str:
    return str(value or "").strip().lower()


def normalize_identifier(value: str) -> str:
    return normalize_token(value)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def identifier_hash(identifier_kind: str, identifier_value: str) -> str:
    material = f"{normalize_token(identifier_kind)}|{normalize_identifier(identifier_value)}"
    return f"sha256:{sha256_hex(material)}"


def contact_id_from_identifier(identifier_kind: str, identifier_value: str) -> str:
    material = f"{normalize_token(identifier_kind)}|{normalize_identifier(identifier_value)}"
    return f"ctc_{sha256_hex(material)[:16]}"


def event_id_from_material(
    event_type: str,
    source: str,
    identifier_hash_value: str,
    consent_status: str,
    event_key: str | None = None,
) -> str:
    parts = [
        normalize_token(event_type),
        normalize_token(source),
        normalize_token(identifier_hash_value),
        normalize_token(consent_status),
    ]
    if event_key:
        parts.append(normalize_token(event_key))
    material = "|".join(parts)
    return f"evt_{sha256_hex(material)[:16]}"


def transition_id_from_material(
    event_id: str,
    contact_id: str,
    from_state: str | None,
    to_state: str | None,
    rule_id: str,
) -> str:
    material = "|".join(
        [
            normalize_token(event_id),
            normalize_token(contact_id),
            normalize_token(from_state or "missing"),
            normalize_token(to_state or "missing"),
            normalize_token(rule_id),
        ]
    )
    return f"trn_{sha256_hex(material)[:16]}"


def dispatch_id_from_material(
    contact_id: str,
    contact_version: int,
    dispatch_type: str,
    channel: str,
) -> str:
    material = "|".join(
        [
            normalize_token(contact_id),
            str(int(contact_version)),
            normalize_token(dispatch_type),
            normalize_token(channel),
        ]
    )
    return f"dsp_{sha256_hex(material)[:16]}"
