"""
Meme Spec v1 — deterministic schema for CONTENT_MEME_OFFLOAD artifacts.

All IDs are SHA256-derived. No randomness.
Schema identity: spec_version MUST equal "meme_spec_v1".
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional

# Canonical schema identity — NOT a semver string.
SPEC_VERSION_CANONICAL = "meme_spec_v1"


@dataclass(frozen=True)
class MemePackRef:
    pack_id: str
    pack_version: str
    pack_hash: str


@dataclass(frozen=True)
class MemeCanvas:
    w: int = 1080
    h: int = 1080
    bg: str = "#1a1a2e"


@dataclass(frozen=True)
class MemeTextTwoPanel:
    top: str = ""
    bottom: str = ""


@dataclass(frozen=True)
class MemeTextInfographic:
    title: str = ""
    bullets: tuple = ()


@dataclass(frozen=True)
class MemeOutput:
    spec_path: str = ""
    render_dir: str = ""
    filename: str = ""


@dataclass(frozen=True)
class MemeProvenance:
    source_artifact_id: str = ""
    session_id: str = ""
    created_at_utc: str = ""


@dataclass(frozen=True)
class MemeSpecV1:
    spec_version: str = SPEC_VERSION_CANONICAL
    meme_id: str = ""
    pack: MemePackRef = field(default_factory=lambda: MemePackRef("", "", ""))
    format: str = "two_panel"  # "two_panel" | "infographic_list"
    canvas: MemeCanvas = field(default_factory=MemeCanvas)
    text: Any = field(default_factory=lambda: MemeTextTwoPanel())
    output: MemeOutput = field(default_factory=MemeOutput)
    provenance: MemeProvenance = field(default_factory=MemeProvenance)

    def __post_init__(self):
        # Strict spec_version enforcement — fail closed
        if self.spec_version != SPEC_VERSION_CANONICAL:
            raise ValueError(
                f"Invalid spec_version: '{self.spec_version}'. "
                f"Must be '{SPEC_VERSION_CANONICAL}'."
            )

    def validate(self) -> None:
        """
        Validate required fields. Raises ValueError on missing fields.
        Fail closed: missing pack metadata is a hard error.
        """
        if not self.pack.pack_hash:
            raise ValueError("Missing required field: pack.pack_hash")
        if not self.pack.pack_id:
            raise ValueError("Missing required field: pack.pack_id")
        if not self.pack.pack_version:
            raise ValueError("Missing required field: pack.pack_version")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2)


def generate_meme_id(
    pack_hash: str,
    frame_id: str,
    normalized_text: str,
    fmt: str,
) -> str:
    """
    Deterministic meme ID via SHA256.
    meme_id = sha256(pack_hash + frame_id + normalized_text + format)[:12]
    """
    payload = f"{pack_hash}{frame_id}{normalized_text}{fmt}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
