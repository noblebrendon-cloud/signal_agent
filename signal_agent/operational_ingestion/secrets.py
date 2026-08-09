from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .errors import SecretBoundaryError


_FORBIDDEN_KEYS = {
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "authorization",
    "proxy_authorization",
    "cookie",
    "set_cookie",
    "session_cookie",
    "client_secret",
    "client_secrets",
    "signed_url",
    "password",
    "passwd",
    "oauth_code",
    "pkce_verifier",
}

_FORBIDDEN_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}",
        r"\b(?:access|refresh)[_-]?token\s*[:=]\s*[^\s,;]{6,}",
        r"\bapi[_-]?key\s*[:=]\s*[^\s,;&]{6,}",
        r"\bclient[_-]?secret\s*[:=]\s*[^\s,;&]{6,}",
        r"\bAuthorization\s*:",
        r"\bCookie\s*:",
        r"(?:\?|&)(?:[^=&]*[_-])?(?:token|secret|signature|sig|api[_-]?key|key|oauth[_-]?code|code[_-]?verifier)(?:[_-][^=&]*)?=",
        r"\bgh[pousr]_[A-Za-z0-9]{20,}",
        r"\bya29\.[A-Za-z0-9._-]{12,}",
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    )
)


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_")


def assert_secret_free_text(value: str, *, label: str) -> None:
    for pattern in _FORBIDDEN_PATTERNS:
        if pattern.search(value):
            raise SecretBoundaryError(f"secret_boundary_violation:{label}")


def assert_secret_free_bytes(value: bytes, *, label: str) -> None:
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError:
        text = value.decode("utf-8", errors="ignore")
    assert_secret_free_text(text, label=label)


def assert_secret_free(value: Any, *, label: str = "artifact") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = _normalized_key(key)
            if normalized in _FORBIDDEN_KEYS:
                raise SecretBoundaryError(f"secret_key_prohibited:{label}:{normalized}")
            assert_secret_free(child, label=f"{label}.{normalized or 'field'}")
        return
    if isinstance(value, (str, bytes)):
        if isinstance(value, bytes):
            assert_secret_free_bytes(value, label=label)
        else:
            assert_secret_free_text(value, label=label)
        return
    if isinstance(value, Sequence):
        for index, child in enumerate(value):
            assert_secret_free(child, label=f"{label}[{index}]")
