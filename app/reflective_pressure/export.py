from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.reflective_pressure.store import (
    get_classification_by_id,
    get_correction_by_id,
    get_draft_by_id,
    get_input_by_id,
    list_golden_examples,
)
from app.reflective_pressure.taxonomy import PRESSURE_TYPES
from app.retention.identity import get_repo_root
from app.utils.io_contract import atomic_write_text


OUTPUT_DIR = Path("data") / "outputs" / "reflective_pressure"


def export_prompt_pack(
    path: str | Path,
    *,
    pressure_type: str | None = None,
    approved_only: bool = True,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    root = repo_root or get_repo_root()
    output_path = _resolve_output_path(path, repo_root=root)
    examples = list_golden_examples(
        pressure_type=pressure_type,
        approved_only=approved_only,
        repo_root=repo_root,
    )
    payload = _render_prompt_pack(examples, pressure_type=pressure_type, approved_only=approved_only, repo_root=repo_root)
    result = atomic_write_text(output_path, payload)
    return {
        "schema_version": "1.0",
        "command": "rp-export-prompt-pack",
        "path": str(result.final_path),
        "bytes_written": result.bytes_written,
        "example_count": len(examples),
        "pressure_type": pressure_type,
        "approved_only": approved_only,
        "external_action_allowed": False,
        "irreversible_action_allowed": False,
    }


def _resolve_output_path(path: str | Path, *, repo_root: Path) -> Path:
    root = repo_root.resolve()
    allowed_root = (root / OUTPUT_DIR).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    try:
        candidate.relative_to(allowed_root)
    except ValueError as exc:
        raise ValueError(f"prompt_pack_path_outside_allowed_root:{candidate}") from exc
    if candidate.name.endswith(".lock"):
        raise ValueError("prompt_pack_lock_path_not_allowed")
    return candidate


def _render_prompt_pack(
    examples: list[dict[str, Any]],
    *,
    pressure_type: str | None,
    approved_only: bool,
    repo_root: Path | None,
) -> str:
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for example in examples:
        grouped[str(example["pressure_type"])].append(example)

    lines = [
        "# Reflective Pressure Prompt Pack",
        "",
        f"Generated: {generated_at}",
        f"Approved only: {str(approved_only).lower()}",
        f"Pressure filter: {pressure_type or 'all'}",
        "",
        "## Taxonomy Snapshot",
        "",
    ]
    for item in PRESSURE_TYPES:
        lines.append(f"- `{item}`")
    lines.append("")
    lines.append("## Golden Examples")
    lines.append("")

    if not examples:
        lines.append("No golden examples matched the export filters.")
        lines.append("")
        return "\n".join(lines)

    for group in sorted(grouped):
        lines.append(f"### {group}")
        lines.append("")
        for example in sorted(grouped[group], key=lambda row: (str(row["title"]).lower(), str(row["golden_id"]))):
            input_record = get_input_by_id(example["input_id"], repo_root=repo_root)
            classification = get_classification_by_id(example["classification_id"], repo_root=repo_root)
            correction = (
                get_correction_by_id(example["correction_id"], repo_root=repo_root)
                if example.get("correction_id")
                else None
            )
            draft = get_draft_by_id(example["draft_id"], repo_root=repo_root) if example.get("draft_id") else None
            hidden_pressure = (
                correction.get("corrected_hidden_pressure")
                if correction
                else (classification or {}).get("hidden_pressure", "")
            )
            lines.extend(
                [
                    f"#### {example['title']}",
                    "",
                    f"- Golden ID: `{example['golden_id']}`",
                    f"- Source excerpt: {_excerpt((input_record or {}).get('raw_text', ''))}",
                    f"- Pressure type: `{example['pressure_type']}`",
                    f"- Hidden pressure: {hidden_pressure}",
                    f"- Reusable pattern: {example['reusable_pattern']}",
                    f"- Voice notes: {example.get('voice_notes') or 'none'}",
                    f"- Risk notes: {example.get('risk_notes') or 'none'}",
                    f"- Correction notes: {(correction or {}).get('correction_reason') or 'none'}",
                ]
            )
            if draft:
                lines.extend(["", "Draft text:", "", "```text", str(draft["draft_text"]), "```"])
            lines.append("")
    return "\n".join(lines)


def _excerpt(value: object, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return "none"
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."
