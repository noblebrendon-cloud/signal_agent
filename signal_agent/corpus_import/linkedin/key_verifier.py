from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from signal_agent.corpus_import.hashing import canonical_json, sha256_canonical_json
from signal_agent.corpus_import.receipts import utc_now_iso


KEY_ALGORITHM = "HMAC-SHA-256"
KEY_TOKEN_VERSION = "linkedin_email_identity_token.v1"
VERIFIER_VERSION = "governed-linkedin-import.email-identity-key-verifier.v1"
VERIFIER_MESSAGE = b"governed-linkedin-import/email-identity-key-verifier/v1"
VERIFIER_SCHEMA_VERSION = "signal_agent.relationship_identity_key_verifier.v1"
MINIMUM_KEY_BYTES = 32
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class LinkedInKeyError(RuntimeError):
    pass


@dataclass(frozen=True)
class KeyContext:
    key_id: str
    key_bytes: bytes
    algorithm: str = KEY_ALGORITHM
    token_version: str = KEY_TOKEN_VERSION


def load_key_context(
    key_file: str | Path,
    key_id: str,
    *,
    repo_root: str | Path,
) -> KeyContext:
    normalized_id = str(key_id or "").strip()
    if not _KEY_ID.fullmatch(normalized_id):
        raise LinkedInKeyError("linkedin_hmac_key_id_invalid")
    try:
        resolved_key = Path(key_file).expanduser().resolve(strict=True)
    except OSError as exc:
        raise LinkedInKeyError("linkedin_hmac_key_file_unreadable") from exc
    resolved_repo = Path(repo_root).expanduser().resolve(strict=False)
    if resolved_key == resolved_repo or resolved_repo in resolved_key.parents:
        raise LinkedInKeyError("linkedin_hmac_key_file_must_be_outside_repository")
    if not resolved_key.is_file():
        raise LinkedInKeyError("linkedin_hmac_key_file_not_regular")
    try:
        key_bytes = resolved_key.read_bytes()
    except OSError as exc:
        raise LinkedInKeyError("linkedin_hmac_key_file_unreadable") from exc
    if len(key_bytes) < MINIMUM_KEY_BYTES:
        raise LinkedInKeyError("linkedin_hmac_key_material_too_short")
    return KeyContext(key_id=normalized_id, key_bytes=key_bytes)


def _verifier_tag(key_bytes: bytes) -> str:
    return "hmac-sha256:" + hmac.new(key_bytes, VERIFIER_MESSAGE, hashlib.sha256).hexdigest()


def _record_hash(record: dict) -> str:
    material = dict(record)
    material.pop("record_hash", None)
    return "sha256:" + sha256_canonical_json(material)


def _validate_existing(record: object, context: KeyContext) -> None:
    if not isinstance(record, dict):
        raise LinkedInKeyError("linkedin_key_verifier_corrupt")
    required = {
        "schema_version",
        "key_id",
        "algorithm",
        "verifier_version",
        "verifier_tag",
        "initialized_at",
        "record_hash",
    }
    if not required.issubset(record):
        raise LinkedInKeyError("linkedin_key_verifier_metadata_missing")
    if record.get("record_hash") != _record_hash(record):
        raise LinkedInKeyError("linkedin_key_verifier_corrupt")
    if (
        record.get("schema_version") != VERIFIER_SCHEMA_VERSION
        or record.get("key_id") != context.key_id
        or record.get("algorithm") != context.algorithm
        or record.get("verifier_version") != VERIFIER_VERSION
    ):
        raise LinkedInKeyError("linkedin_key_verifier_metadata_mismatch")
    if not hmac.compare_digest(str(record.get("verifier_tag") or ""), _verifier_tag(context.key_bytes)):
        raise LinkedInKeyError("linkedin_key_id_material_mismatch")


def ensure_key_verifier(
    context: KeyContext,
    *,
    repo_root: str | Path,
    clock: Callable[[], str] = utc_now_iso,
) -> Path:
    registry = (
        Path(repo_root).resolve()
        / "data"
        / "state"
        / "relationship_identity_keys"
    )
    path = registry / f"{context.key_id}.json"
    if path.exists():
        try:
            _validate_existing(json.loads(path.read_text(encoding="utf-8")), context)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LinkedInKeyError("linkedin_key_verifier_corrupt") from exc
        return path

    record = {
        "schema_version": VERIFIER_SCHEMA_VERSION,
        "key_id": context.key_id,
        "algorithm": context.algorithm,
        "verifier_version": VERIFIER_VERSION,
        "verifier_tag": _verifier_tag(context.key_bytes),
        "initialized_at": clock(),
    }
    record["record_hash"] = _record_hash(record)
    registry.mkdir(parents=True, exist_ok=True)
    payload = (canonical_json(record) + "\n").encode("utf-8")
    try:
        with path.open("xb") as handle:
            written = handle.write(payload)
            if written != len(payload):
                raise OSError("short key-verifier write")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        try:
            _validate_existing(json.loads(path.read_text(encoding="utf-8")), context)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LinkedInKeyError("linkedin_key_verifier_corrupt") from exc
    except OSError as exc:
        raise LinkedInKeyError("linkedin_key_verifier_write_failed") from exc
    return path
