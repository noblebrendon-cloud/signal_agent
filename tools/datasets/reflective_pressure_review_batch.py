from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
APPROVED_INPUT_DIR = REPO_ROOT / "data" / "inputs" / "reflective_pressure"
ALLOWED_DECISIONS = ("KEEP", "SKIP", "NEEDS_CORRECTION", "GOLD_CANDIDATE")
APPROVED_DECISIONS = ("KEEP", "NEEDS_CORRECTION", "GOLD_CANDIDATE")


def build_review(input_jsonl: str | Path, review_dir: str | Path) -> dict[str, Any]:
    input_path = Path(input_jsonl)
    output_dir = Path(review_dir)
    records = _read_jsonl(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = _review_base_name(input_path)
    table_path = output_dir / f"{base_name}_table.md"
    decisions_path = output_dir / f"{base_name}_decisions.template.jsonl"
    manifest_path = output_dir / f"{base_name}_manifest.json"

    _write_review_table(table_path, records)
    _write_decision_template(decisions_path, records)
    manifest = {
        "schema_version": "1.0",
        "source_file": str(input_path),
        "created_at": _utc_now_iso(),
        "total_records": len(records),
        "allowed_decisions": list(ALLOWED_DECISIONS),
        "next_steps": [
            "Fill every decision with KEEP, SKIP, NEEDS_CORRECTION, or GOLD_CANDIDATE.",
            "Use summarize-decisions to confirm blank_count and invalid_count are zero.",
            "Use apply-decisions to create an approved JSONL batch.",
            "Use copy-approved-to-repo only after manual review is complete.",
            "Import approved seeds with the Reflective Pressure CLI.",
        ],
        "import_blocked_until_decisions_present": True,
        "external_action_allowed": False,
        "irreversible_action_allowed": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "schema_version": "1.0",
        "command": "build-review",
        "source_file": str(input_path),
        "review_dir": str(output_dir),
        "total_records": len(records),
        "table_path": str(table_path),
        "decisions_template_path": str(decisions_path),
        "manifest_path": str(manifest_path),
        "external_action_allowed": False,
        "irreversible_action_allowed": False,
    }


def apply_decisions(
    input_jsonl: str | Path,
    decisions_jsonl: str | Path,
    output_jsonl: str | Path,
    *,
    min_keep_count: int = 1,
) -> dict[str, Any]:
    input_path = Path(input_jsonl)
    decisions_path = Path(decisions_jsonl)
    output_path = _safe_review_output_path(output_jsonl, decisions_path.parent)
    records = _read_jsonl(input_path)
    decisions = _read_jsonl(decisions_path)
    _validate_decisions(records, decisions)

    approved_records = [
        dict(record)
        for record, decision in zip(records, decisions, strict=True)
        if str(decision.get("decision") or "").strip().upper() in APPROVED_DECISIONS
    ]
    if len(approved_records) < int(min_keep_count):
        raise ValueError(f"approved_count_below_min:{len(approved_records)}")

    _write_jsonl(output_path, approved_records)
    summary = summarize_decisions(decisions_path)
    return {
        "schema_version": "1.0",
        "command": "apply-decisions",
        "source_file": str(input_path),
        "decisions_file": str(decisions_path),
        "output_path": str(output_path),
        "input_count": len(records),
        "approved_count": len(approved_records),
        "skipped_count": summary["skip_count"],
        "min_keep_count": int(min_keep_count),
        "external_action_allowed": False,
        "irreversible_action_allowed": False,
    }


def summarize_decisions(decisions_jsonl: str | Path) -> dict[str, Any]:
    decisions_path = Path(decisions_jsonl)
    rows = _read_jsonl(decisions_path)
    normalized = [_normalize_decision(row.get("decision")) for row in rows]
    counts = Counter(normalized)
    invalid_count = sum(1 for value in normalized if value and value not in ALLOWED_DECISIONS)
    blank_count = counts.get("", 0)
    corrected_counts = Counter(
        _clean_text(row.get("corrected_pressure_type"))
        for row in rows
        if _clean_text(row.get("corrected_pressure_type"))
    )
    return {
        "schema_version": "1.0",
        "command": "summarize-decisions",
        "decisions_file": str(decisions_path),
        "total": len(rows),
        "keep_count": counts.get("KEEP", 0),
        "skip_count": counts.get("SKIP", 0),
        "needs_correction_count": counts.get("NEEDS_CORRECTION", 0),
        "gold_candidate_count": counts.get("GOLD_CANDIDATE", 0),
        "blank_count": blank_count,
        "invalid_count": invalid_count,
        "corrected_pressure_type_counts": dict(corrected_counts),
        "ready_for_import": blank_count == 0 and invalid_count == 0 and any(
            value in APPROVED_DECISIONS for value in normalized
        ),
        "external_action_allowed": False,
        "irreversible_action_allowed": False,
    }


def copy_approved_to_repo(
    approved_jsonl: str | Path,
    repo_output_path: str | Path,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    allowed_dir = (root / "data" / "inputs" / "reflective_pressure").resolve()
    approved_path = Path(approved_jsonl)
    destination = Path(repo_output_path)
    if not destination.is_absolute():
        destination = root / destination
    resolved_destination = destination.resolve()
    if allowed_dir != resolved_destination.parent:
        raise ValueError(f"repo_output_path_outside_reflective_pressure_inputs:{repo_output_path}")
    if not approved_path.exists():
        raise ValueError(f"approved_file_missing:{approved_path}")
    rows = _read_jsonl(approved_path)
    if not rows:
        raise ValueError(f"approved_file_empty:{approved_path}")
    resolved_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(approved_path, resolved_destination)
    return {
        "schema_version": "1.0",
        "command": "copy-approved-to-repo",
        "approved_jsonl": str(approved_path),
        "repo_output_path": str(resolved_destination),
        "copied_count": len(rows),
        "external_action_allowed": False,
        "irreversible_action_allowed": False,
    }


def _write_review_table(path: Path, records: list[dict[str, Any]]) -> None:
    headers = (
        "row_number",
        "decision",
        "source_platform",
        "source_type",
        "group_or_channel",
        "guessed_pressure_type",
        "intended_spine",
        "raw_text_excerpt",
        "source_context_excerpt",
        "tags",
        "notes_excerpt",
    )
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for index, record in enumerate(records, start=1):
        notes = _clean_text(record.get("notes"))
        row = [
            str(index),
            "",
            _clean_text(record.get("source_platform")),
            _clean_text(record.get("source_type")),
            _clean_text(record.get("group_or_channel")),
            _extract_guessed_pressure_type(notes),
            _clean_text(record.get("intended_spine")),
            _excerpt(record.get("raw_text")),
            _excerpt(record.get("source_context")),
            ", ".join(str(tag) for tag in record.get("tags", []) if str(tag).strip()),
            _excerpt(notes),
        ]
        lines.append("| " + " | ".join(_markdown_cell(value) for value in row) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_decision_template(path: Path, records: list[dict[str, Any]]) -> None:
    rows = [
        {
            "row_number": index,
            "decision": "",
            "reason": "",
            "corrected_pressure_type": "",
            "corrected_hidden_pressure": "",
            "gold_candidate": False,
            "operator_notes": "",
        }
        for index, _record in enumerate(records, start=1)
    ]
    _write_jsonl(path, rows)


def _validate_decisions(records: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> None:
    if len(records) != len(decisions):
        raise ValueError(f"row_count_mismatch:records={len(records)} decisions={len(decisions)}")
    for index, decision in enumerate(decisions, start=1):
        row_number = decision.get("row_number")
        if row_number != index:
            raise ValueError(f"row_number_mismatch:expected={index} actual={row_number}")
        value = _normalize_decision(decision.get("decision"))
        if not value:
            raise ValueError(f"blank_decision:row={index}")
        if value not in ALLOWED_DECISIONS:
            raise ValueError(f"invalid_decision:row={index} value={value}")


def _safe_review_output_path(output_jsonl: str | Path, review_dir: Path) -> Path:
    output_path = Path(output_jsonl)
    if not output_path.is_absolute():
        output_path = review_dir / output_path
    if output_path.suffix.lower() != ".jsonl":
        raise ValueError(f"output_must_be_jsonl:{output_jsonl}")
    resolved_review_dir = review_dir.resolve()
    resolved_output = output_path.resolve()
    if resolved_review_dir != resolved_output.parent:
        raise ValueError(f"output_outside_review_dir:{output_jsonl}")
    return output_path


def _review_base_name(input_path: Path) -> str:
    stem = input_path.stem
    if stem.startswith("reddit_seed_"):
        return "reddit_" + stem[len("reddit_seed_") :]
    return stem


def _extract_guessed_pressure_type(notes: str) -> str:
    match = re.search(r"Guessed pressure type:\s*([^;]+)", notes)
    if not match:
        return ""
    return match.group(1).strip()


def _excerpt(value: object, *, limit: int = 180) -> str:
    text = _clean_text(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _markdown_cell(value: object) -> str:
    text = _clean_text(value)
    text = text.replace("|", "\\|")
    return text.replace("\n", "<br>")


def _normalize_decision(value: object) -> str:
    return _clean_text(value).upper()


def _clean_text(value: object) -> str:
    return str(value or "").replace("\x00", "").strip()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError(f"jsonl_record_must_be_object:{path}")
            rows.append(payload)
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and apply human-gated Reflective Pressure review batches.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build-review")
    build.add_argument("--input-jsonl", required=True)
    build.add_argument("--review-dir", required=True)

    apply = subparsers.add_parser("apply-decisions")
    apply.add_argument("--input-jsonl", required=True)
    apply.add_argument("--decisions-jsonl", required=True)
    apply.add_argument("--output-jsonl", required=True)
    apply.add_argument("--min-keep-count", type=int, default=1)

    summarize = subparsers.add_parser("summarize-decisions")
    summarize.add_argument("--decisions-jsonl", required=True)

    copy = subparsers.add_parser("copy-approved-to-repo")
    copy.add_argument("--approved-jsonl", required=True)
    copy.add_argument("--repo-output-path", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "build-review":
            payload = build_review(args.input_jsonl, args.review_dir)
        elif args.command == "apply-decisions":
            payload = apply_decisions(
                args.input_jsonl,
                args.decisions_jsonl,
                args.output_jsonl,
                min_keep_count=args.min_keep_count,
            )
        elif args.command == "summarize-decisions":
            payload = summarize_decisions(args.decisions_jsonl)
        elif args.command == "copy-approved-to-repo":
            payload = copy_approved_to_repo(args.approved_jsonl, args.repo_output_path)
        else:
            parser.error(f"unsupported_command:{args.command}")
            return 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
