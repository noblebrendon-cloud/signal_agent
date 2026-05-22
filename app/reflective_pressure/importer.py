from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.reflective_pressure.classify import classify_input
from app.reflective_pressure.generate import SUPPORTED_TEMPLATE_OUTPUTS, generate_draft as generate_reflective_draft
from app.reflective_pressure.models import build_input_record
from app.reflective_pressure.store import append_classification, append_draft, append_input


def import_inputs_from_jsonl(
    path: str | Path,
    *,
    classify: bool = False,
    generate_draft: bool = False,
    output_type: str | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    if generate_draft and not classify:
        raise ValueError("generate_draft_requires_classify")
    if generate_draft and not output_type:
        raise ValueError("generate_draft_requires_output_type")
    if output_type and output_type not in SUPPORTED_TEMPLATE_OUTPUTS:
        raise ValueError(f"unsupported_template_output_type:{output_type}")

    import_path = Path(path)
    failures: list[dict[str, Any]] = []
    created_input_ids: list[str] = []
    created_classification_ids: list[str] = []
    created_draft_ids: list[str] = []

    with open(import_path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError("record_must_be_object")
                input_record = _build_input_from_payload(payload)
                written_input = append_input(input_record, repo_root=repo_root)
                created_input_ids.append(written_input["input_id"])
                written_classification = None
                if classify:
                    written_classification = append_classification(
                        classify_input(written_input),
                        repo_root=repo_root,
                    )
                    created_classification_ids.append(written_classification["classification_id"])
                if generate_draft:
                    assert written_classification is not None
                    written_draft = append_draft(
                        generate_reflective_draft(
                            written_input,
                            written_classification,
                            output_type=str(output_type),
                            target_platform=written_input["source_platform"],
                        ),
                        repo_root=repo_root,
                    )
                    created_draft_ids.append(written_draft["draft_id"])
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                failures.append(
                    {
                        "line_number": line_number,
                        "error_type": exc.__class__.__name__,
                        "error": str(exc),
                    }
                )

    return {
        "schema_version": "1.0",
        "command": "rp-import-inputs",
        "source_path": str(import_path),
        "imported_count": len(created_input_ids),
        "failed_count": len(failures),
        "failures": failures,
        "created_input_ids": created_input_ids,
        "created_classification_ids": created_classification_ids,
        "created_draft_ids": created_draft_ids,
        "external_action_allowed": False,
        "irreversible_action_allowed": False,
    }


def _build_input_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    tags = payload.get("tags", [])
    if tags is None:
        tags = []
    if not isinstance(tags, list):
        raise ValueError("tags_must_be_list")
    return build_input_record(
        source_platform=str(payload.get("source_platform") or ""),
        source_type=str(payload.get("source_type") or ""),
        raw_text=str(payload.get("raw_text") or ""),
        source_context=str(payload.get("source_context") or ""),
        group_or_channel=str(payload.get("group_or_channel") or ""),
        intended_spine=str(payload.get("intended_spine") or "unknown"),
        tags=[str(tag) for tag in tags],
        notes=str(payload.get("notes") or ""),
    )
