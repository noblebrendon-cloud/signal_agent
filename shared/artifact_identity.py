"""
shared/artifact_identity.py — Decouples artifact identity from raw filename meanings.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional


def normalize_artifact_ref(artifact_ref: str) -> Dict[str, Any]:
    """
    Normalizes a string reference into a structured artifact identity envelope.
    For legacy compatibility, strings identical to filenames are accepted as the ID.
    """
    if not isinstance(artifact_ref, str):
        raise TypeError("artifact_ref_must_be_str")
    if not artifact_ref.strip():
        raise ValueError("artifact_ref_required")

    looks_like_file = "." in artifact_ref or "/" in artifact_ref or "\\" in artifact_ref
    ext = None
    if looks_like_file:
        _, file_ext = os.path.splitext(artifact_ref)
        if file_ext:
            ext = file_ext

    return {
        "artifact_id": artifact_ref,
        "looks_like_filename": looks_like_file,
        "extension": ext,
    }


def artifact_display_name(artifact_ref: str, path: Optional[str] = None) -> str:
    """
    Provides a standardized human-readable display string for an artifact.
    """
    if path:
        return f"{artifact_ref} ({Path(path).name})"
    return artifact_ref
