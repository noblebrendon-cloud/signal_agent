from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path


STANDARD_EVENT_FILES = (
    "00_EVENT.md",
    "01_EVIDENCE.md",
    "02_TEACHING_ATOMS.md",
    "03_DERIVATIVE_BACKLOG.md",
    "04_PUBLICATION_LEDGER.md",
)

DEFAULT_EVENT_TEMPLATES = {
    "00_EVENT.md": """# {{EVENT_ID}}: {{TITLE}}

Status: draft
Captured: {{CAPTURED_DATE}}
Year: {{YEAR}}

## Summary

## Verified Facts

## Boundaries

## Source References

## Test Evidence

""",
    "01_EVIDENCE.md": """# Evidence

Event ID: `{{EVENT_ID}}`

## Verified Facts

| Fact | Evidence |
| --- | --- |

## Test Evidence

| Command | Result |
| --- | --- |

""",
    "02_TEACHING_ATOMS.md": """# Teaching Atoms

Event ID: `{{EVENT_ID}}`

| Atom | Concept | Origin |
| --- | --- | --- |

""",
    "03_DERIVATIVE_BACKLOG.md": """# Derivative Backlog

Event ID: `{{EVENT_ID}}`

Status: queued only.

| Candidate | Source Atom | Format | Status | Boundary |
| --- | --- | --- | --- | --- |

""",
    "04_PUBLICATION_LEDGER.md": """# Publication Ledger

Event ID: `{{EVENT_ID}}`

No public content has been published from this event.

| Publication ID | Date | Surface | Source Atom IDs | URL or File | Notes |
| --- | --- | --- | --- | --- | --- |

""",
}


def library_root() -> Path:
    return Path(__file__).resolve().parents[1]


def create_or_reopen_event(
    event_id: str,
    year: str,
    title: str,
    *,
    library_root_path: Path | None = None,
) -> str:
    root = library_root_path or library_root()
    normalized_event_id = _validate_event_id(event_id)
    normalized_year = _validate_year(year)
    normalized_title = _required(title, "title")
    event_dir = root / "events" / normalized_year / normalized_event_id
    existed = event_dir.exists()
    event_dir.mkdir(parents=True, exist_ok=True)

    context = {
        "EVENT_ID": normalized_event_id,
        "YEAR": normalized_year,
        "TITLE": normalized_title,
        "CAPTURED_DATE": date.today().isoformat(),
    }

    created_files: list[str] = []
    for filename in STANDARD_EVENT_FILES:
        path = event_dir / filename
        if path.exists():
            continue
        template = _template_for(root, filename)
        path.write_text(_render(template, context), encoding="utf-8")
        created_files.append(str(path.relative_to(root)).replace("\\", "/"))

    index_changed = _ensure_index_row(root, normalized_event_id, normalized_year, normalized_title)

    if existed:
        detail = "no missing files created"
        if created_files:
            detail = "created missing files: " + ", ".join(created_files)
        if index_changed:
            detail += "; restored missing index row"
        return f"Reopened existing event {normalized_event_id}; {detail}."

    detail = "created files: " + ", ".join(created_files)
    if index_changed:
        detail += "; added CONTENT_LIBRARY_INDEX.md row"
    return f"Created new event {normalized_event_id}; {detail}."


def _template_for(root: Path, filename: str) -> str:
    if filename == "00_EVENT.md":
        template_path = root / "_templates" / "BUILD_EVENT_TEMPLATE.md"
        if template_path.exists():
            return template_path.read_text(encoding="utf-8")
    return DEFAULT_EVENT_TEMPLATES[filename]


def _ensure_index_row(root: Path, event_id: str, year: str, title: str) -> bool:
    index_path = root / "CONTENT_LIBRARY_INDEX.md"
    if not index_path.exists():
        index_path.write_text(
            "# Content Library Index\n\n"
            "| Event ID | Captured | Title | Status | Source Paths | Teaching Atoms | Event Record |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n",
            encoding="utf-8",
        )

    index_text = index_path.read_text(encoding="utf-8")
    if f"`{event_id}`" in index_text:
        return False

    row = (
        f"| `{event_id}` | {year} | {title} | draft | | | "
        f"[00_EVENT.md](events/{year}/{event_id}/00_EVENT.md) |\n"
    )
    if not index_text.endswith("\n"):
        index_text += "\n"
    index_path.write_text(index_text + row, encoding="utf-8")
    return True


def _render(template: str, context: dict[str, str]) -> str:
    rendered = template
    for key, value in context.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def _validate_event_id(value: str) -> str:
    event_id = _required(value, "event_id")
    if "/" in event_id or "\\" in event_id or ".." in event_id:
        raise ValueError("event_id_must_be_path_safe")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", event_id):
        raise ValueError("event_id_must_use_safe_characters")
    return event_id


def _validate_year(value: str) -> str:
    year = _required(value, "year")
    if not re.fullmatch(r"\d{4}", year):
        raise ValueError("year_must_be_four_digits")
    return year


def _required(value: str, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name}_required")
    return normalized


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create or reopen a content-library event.")
    parser.add_argument("event_id", help="Stable event ID, for example EVT-2026-06-29-name")
    parser.add_argument("year", help="Four-digit event year")
    parser.add_argument("title", nargs="+", help="Human-readable event title")
    args = parser.parse_args(argv)

    message = create_or_reopen_event(args.event_id, args.year, " ".join(args.title))
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

