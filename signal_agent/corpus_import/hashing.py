from __future__ import annotations

from pathlib import Path
from typing import Any

from signal_agent.evidence_sources.canonical import (
    DEFAULT_CHUNK_SIZE,
    canonical_json as _canonical_json,
    sha256_canonical_json as _sha256_canonical_json,
    sha256_file as _sha256_file,
)


def sha256_file(path: Path, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> str:
    """Return the lowercase SHA-256 hex digest for a file without modifying it."""

    return _sha256_file(path, chunk_size=chunk_size)


def canonical_json(payload: Any) -> str:
    """Serialize data in the repository's stable JSON form."""

    return _canonical_json(payload)


def sha256_canonical_json(payload: Any) -> str:
    return _sha256_canonical_json(payload)
