from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

import yaml

PLACEHOLDER_ALIASES = {
    "[Title]": "title",
    "[Subtitle]": "subtitle",
    "[Author]": "author",
    "[Your Name]": "author",
    "[Year]": "year",
    "[Copyright Holder]": "copyright_holder",
}


def load_spec(spec_path: Path) -> Dict[str, Any]:
    with spec_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("Spec file must be a YAML mapping/object at the top level.")
    return normalize_spec(data)


def normalize_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    normalized = deepcopy(spec)

    meta = dict(normalized.get("meta") or {})
    front_matter = dict(normalized.get("front_matter") or {})
    end_matter = dict(normalized.get("end_matter") or {})
    letter = dict(normalized.get("letter") or {})

    author = _clean(meta.get("author"))
    year = _clean(meta.get("year"))
    copyright_holder = _clean(meta.get("copyright_holder"))

    if _is_placeholder(author) and not _is_placeholder(copyright_holder):
        author = copyright_holder
    if (not author or _is_placeholder(author)) and copyright_holder:
        author = copyright_holder
    if not copyright_holder or _is_placeholder(copyright_holder):
        copyright_holder = author

    meta["title"] = _clean(meta.get("title"))
    meta["subtitle"] = _clean(meta.get("subtitle"))
    meta["author"] = author
    meta["year"] = year
    meta["copyright_holder"] = copyright_holder
    meta["copyright_line"] = _build_copyright_line(year, copyright_holder)

    letter["one_sentence"] = _clean(letter.get("one_sentence")) or _clean(letter.get("content"))

    normalized["meta"] = meta
    normalized["front_matter"] = front_matter
    normalized["chapters"] = list(normalized.get("chapters") or [])
    normalized["end_matter"] = end_matter
    normalized["letter"] = letter

    replacements = {
        token: meta.get(field, "")
        for token, field in PLACEHOLDER_ALIASES.items()
        if meta.get(field)
    }

    normalized = _resolve_placeholders(normalized, replacements)
    normalized["meta"]["copyright_line"] = _build_copyright_line(
        _clean(normalized["meta"].get("year")),
        _clean(normalized["meta"].get("copyright_holder")),
    )
    normalized["letter"]["one_sentence"] = _clean(
        normalized["letter"].get("one_sentence") or normalized["letter"].get("content")
    )

    return normalized


def find_unresolved_placeholders(text: str) -> list[str]:
    unresolved = [token for token in PLACEHOLDER_ALIASES if token in text]
    return sorted(set(unresolved))


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_placeholder(value: str) -> bool:
    return value in PLACEHOLDER_ALIASES


def _build_copyright_line(year: str, holder: str) -> str:
    if year and holder:
        return f"© {year} {holder}"
    if holder:
        return f"© {holder}"
    return ""


def _resolve_placeholders(value: Any, replacements: Dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_placeholders(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_placeholders(item, replacements) for item in value]
    if isinstance(value, str):
        resolved = value
        for placeholder, replacement in replacements.items():
            if replacement:
                resolved = resolved.replace(placeholder, replacement)
        return resolved
    return value
