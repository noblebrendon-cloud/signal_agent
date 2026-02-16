"""
Meme Spec v1 — deterministic schema for CONTENT_MEME_OFFLOAD artifacts.

All IDs are SHA256-derived. No randomness.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional


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
    spec_version: str = "1.0.0"
    meme_id: str = ""
    pack: MemePackRef = field(default_factory=lambda: MemePackRef("", "", ""))
    format: str = "two_panel"  # "two_panel" | "infographic_list"
    canvas: MemeCanvas = field(default_factory=MemeCanvas)
    text: Any = field(default_factory=lambda: MemeTextTwoPanel())
    output: MemeOutput = field(default_factory=MemeOutput)
    provenance: MemeProvenance = field(default_factory=MemeProvenance)

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
