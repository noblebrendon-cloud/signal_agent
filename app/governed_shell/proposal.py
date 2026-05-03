from __future__ import annotations

import json
from pathlib import Path

from .errors import ProposalLoadError, ProposalNormalizationError


def load_json_text(text: str) -> dict:
    """Parse proposal JSON text into a plain dict."""

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        message = (
            f"Malformed proposal JSON at line {exc.lineno}, column {exc.colno}: "
            f"{exc.msg}"
        )
        raise ProposalLoadError(message) from exc

    if type(payload) is not dict:
        raise ProposalLoadError("Proposal JSON must decode to a top-level object.")

    return payload


def load_proposal(path: Path) -> dict:
    """Load proposal JSON from disk into a plain dict."""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProposalLoadError(f"Unable to read proposal file '{path}': {exc}") from exc

    return load_json_text(text)


def dump_canonical_json(obj: dict) -> str:
    """Serialize a proposal object with deterministic JSON formatting."""

    if type(obj) is not dict:
        raise ProposalNormalizationError(
            "Canonical JSON serialization requires a plain dict proposal object."
        )

    try:
        return json.dumps(
            obj,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProposalNormalizationError(
            f"Proposal cannot be serialized to canonical JSON: {exc}"
        ) from exc
