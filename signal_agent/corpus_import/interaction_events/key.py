from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


KEY_ALGORITHM = "HMAC-SHA-256"
KEY_TOKEN_VERSION = "interaction_event_actor_identity_token.v1"
MINIMUM_KEY_BYTES = 32
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class InteractionEventKeyError(RuntimeError):
    pass


@dataclass(frozen=True)
class InteractionEventKeyContext:
    key_id: str
    key_bytes: bytes
    key_path: Path
    key_sha256: str
    algorithm: str = KEY_ALGORITHM
    token_version: str = KEY_TOKEN_VERSION


def load_interaction_event_key(
    key_file: str | Path,
    key_id: str,
    *,
    repository_root: str | Path,
) -> InteractionEventKeyContext:
    normalized_id = str(key_id or "").strip()
    if not _KEY_ID.fullmatch(normalized_id):
        raise InteractionEventKeyError("interaction_event_hmac_key_id_invalid")
    try:
        resolved_key = Path(key_file).expanduser().resolve(strict=True)
    except OSError as exc:
        raise InteractionEventKeyError("interaction_event_hmac_key_file_unreadable") from exc
    repository = Path(repository_root).expanduser().resolve(strict=False)
    if resolved_key == repository or repository in resolved_key.parents:
        raise InteractionEventKeyError(
            "interaction_event_hmac_key_file_must_be_outside_repository"
        )
    if not resolved_key.is_file():
        raise InteractionEventKeyError("interaction_event_hmac_key_file_not_regular")
    try:
        key_bytes = resolved_key.read_bytes()
    except OSError as exc:
        raise InteractionEventKeyError("interaction_event_hmac_key_file_unreadable") from exc
    if len(key_bytes) < MINIMUM_KEY_BYTES:
        raise InteractionEventKeyError("interaction_event_hmac_key_material_too_short")
    return InteractionEventKeyContext(
        key_id=normalized_id,
        key_bytes=key_bytes,
        key_path=resolved_key,
        key_sha256=hashlib.sha256(key_bytes).hexdigest(),
    )


def validate_interaction_event_key(
    context: InteractionEventKeyContext,
    *,
    repository_root: str | Path,
) -> None:
    current = load_interaction_event_key(
        context.key_path,
        context.key_id,
        repository_root=repository_root,
    )
    if current.key_sha256 != context.key_sha256:
        raise InteractionEventKeyError("interaction_event_hmac_key_material_changed")
