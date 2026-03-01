"""
OIL Impact — Business Impact Mapper

Maps technical service names to business domain strings using
a static JSON map. Returns "unknown" for unmapped services.
"""
from __future__ import annotations

import json
from pathlib import Path

_DEFAULT_MAP_PATH = Path(__file__).resolve().parent / "impact_map.json"


def load_impact_map(path: Path | None = None) -> dict[str, str]:
    """Load the static service→business-domain map from JSON.

    Falls back to the bundled impact_map.json if *path* is not given.
    Returns empty dict on any I/O error.
    """
    target = path or _DEFAULT_MAP_PATH
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}


def map_impact(service: str, impact_map: dict[str, str]) -> str:
    """Return the business domain for *service*, or "unknown"."""
    return impact_map.get(service, "unknown")
