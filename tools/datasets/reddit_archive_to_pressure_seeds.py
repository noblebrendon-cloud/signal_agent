from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.reflective_pressure.taxonomy import PRESSURE_TYPES, SPINES, validate_taxonomy_value


NORMALIZED_FILE = "reddit_interactions_normalized.jsonl"
CANDIDATES_FILE = "reddit_pressure_candidates.jsonl"
SEED_FILE = "reddit_seed_batch_001.jsonl"
REPORT_FILE = "reddit_seed_report.md"

PRESSURE_TERMS = {
    "faith": ("faith", "god", "bible", "jesus", "church", "sin", "gospel", "salvation"),
    "morality": ("wrong", "right", "evil", "good", "truth", "false", "virtue", "moral", "hypocrisy"),
    "politics": ("politics", "government", "power", "authority", "law", "society"),
    "systems_ai": ("ai", "system", "algorithm", "model", "machine", "automation"),
    "identity": ("we", "they", "people like", "everyone", "nobody", "us", "them"),
    "conflict": ("intent", "offense", "offended", "misunderstood", "conflict", "accusation", "you missed"),
    "family_work": ("fatherhood", "parenting", "work", "family", "children", "dad", "mother"),
    "meaning": ("meaning", "purpose", "truth", "reality", "existential", "life"),
}

CLARIFICATION_MARKERS = (
    "what i mean",
    "that's not what i said",
    "that is not what i said",
    "my point is",
    "you missed",
    "i think",
    "to clarify",
)

SARCASM_MARKERS = ("lol", "lmao", "sure", "yeah right", "/s")
ARGUMENT_MARKERS = ("but", "however", "disagree", "argue", "because", "actually", "you are", "you're")


def inspect_dataset(dataset_root: str | Path) -> dict[str, Any]:
    root = Path(dataset_root)
    raw_root = root / "raw"
    derived_root = root / "derived"
    zip_path = root / "reddit_export.zip"
    extracted = _ensure_extracted_if_needed(root)
    raw_files = sorted(_iter_data_files(raw_root))
    derived_files = sorted(_iter_data_files(derived_root))
    file_summaries = [_summarize_file(path, raw_root) for path in raw_files]
    return {
        "schema_version": "1.0",
        "command": "inspect",
        "dataset_root": str(root),
        "zip_exists": zip_path.exists(),
        "zip_path": str(zip_path),
        "zip_entries": _zip_entries(zip_path),
        "raw_exists": raw_root.exists(),
        "derived_exists": derived_root.exists(),
        "extraction": extracted,
        "raw_files": file_summaries,
        "derived_files": [str(path.relative_to(derived_root)) for path in derived_files] if derived_root.exists() else [],
        "comments_files": [summary for summary in file_summaries if _looks_like_comment_file(summary)],
        "posts_files": [summary for summary in file_summaries if _looks_like_post_file(summary)],
        "external_action_allowed": False,
        "irreversible_action_allowed": False,
    }


def normalize_dataset(dataset_root: str | Path) -> dict[str, Any]:
    root = Path(dataset_root)
    raw_root = root / "raw"
    derived_root = root / "derived"
    derived_root.mkdir(parents=True, exist_ok=True)
    output_path = derived_root / NORMALIZED_FILE
    warnings: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    raw_records_seen = 0
    skipped_empty_or_deleted = 0

    for raw_file in sorted(_iter_data_files(raw_root)):
        file_kind = _file_kind(raw_file)
        if file_kind not in {"comment", "post"}:
            continue
        try:
            for raw_index, row in enumerate(_iter_records(raw_file), start=1):
                raw_records_seen += 1
                normalized = _normalize_row(row, raw_file=raw_file, raw_root=raw_root, raw_index=raw_index, kind=file_kind)
                if normalized is not None:
                    records.append(normalized)
                else:
                    skipped_empty_or_deleted += 1
        except (OSError, UnicodeError, csv.Error, json.JSONDecodeError) as exc:
            warnings.append({"raw_file": str(raw_file), "error_type": exc.__class__.__name__, "error": str(exc)})

    records = sorted(records, key=lambda row: (str(row["created_utc"]), str(row["record_id"])))
    _write_jsonl(output_path, records)
    return {
        "schema_version": "1.0",
        "command": "normalize",
        "output_path": str(output_path),
        "raw_records_seen": raw_records_seen,
        "normalized_count": len(records),
        "skipped_empty_or_deleted": skipped_empty_or_deleted,
        "warnings": warnings,
        "external_action_allowed": False,
        "irreversible_action_allowed": False,
    }


def filter_candidates(dataset_root: str | Path) -> dict[str, Any]:
    root = Path(dataset_root)
    derived_root = root / "derived"
    normalized_path = derived_root / NORMALIZED_FILE
    candidates_path = derived_root / CANDIDATES_FILE
    records = _read_jsonl(normalized_path)
    candidates: list[dict[str, Any]] = []
    for record in records:
        score, reasons = score_candidate(record)
        if score < 3:
            continue
        candidate = dict(record)
        candidate["candidate_score"] = score
        candidate["candidate_reasons"] = reasons
        candidate["guessed_pressure_type"] = _guess_pressure_type(record)
        candidate["guessed_spine"] = _guess_spine(record)
        candidate["recommended_output_type"] = _recommended_output_type(record)
        candidate["notes"] = "Deterministic local heuristic candidate. No external action authorized."
        candidates.append(candidate)
    candidates = sorted(candidates, key=lambda row: (-int(row["candidate_score"]), str(row["created_utc"]), str(row["record_id"])))
    _write_jsonl(candidates_path, candidates)
    return {
        "schema_version": "1.0",
        "command": "filter-candidates",
        "input_path": str(normalized_path),
        "output_path": str(candidates_path),
        "normalized_count": len(records),
        "candidate_count": len(candidates),
        "external_action_allowed": False,
        "irreversible_action_allowed": False,
    }


def export_seeds(
    dataset_root: str | Path,
    *,
    limit: int = 100,
    min_score: float | None = None,
    pressure_type: str | None = None,
    spine: str | None = None,
    subreddit: str | None = None,
    contains: str | None = None,
    exclude_deleted: bool = False,
    output_name: str = SEED_FILE,
    copy_to_repo: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(dataset_root)
    derived_root = root / "derived"
    candidates_path = derived_root / CANDIDATES_FILE
    seed_path = _safe_derived_output_path(derived_root, output_name)
    report_path = derived_root / REPORT_FILE
    filters = _build_export_filters(
        min_score=min_score,
        pressure_type=pressure_type,
        spine=spine,
        subreddit=subreddit,
        contains=contains,
        exclude_deleted=exclude_deleted,
    )
    candidates = _read_jsonl(candidates_path)
    filtered_candidates = [candidate for candidate in candidates if _candidate_matches_filters(candidate, filters)]
    selected = filtered_candidates[: max(0, int(limit))]
    seeds = [_candidate_to_seed(candidate) for candidate in selected if _usable_text(candidate.get("text_for_pressure_analysis"))]
    _write_jsonl(seed_path, seeds)
    copied_to = None
    if copy_to_repo:
        copied_to = _copy_seed_to_repo(seed_path, Path(copy_to_repo))
    normalized_count = len(_read_jsonl(derived_root / NORMALIZED_FILE)) if (derived_root / NORMALIZED_FILE).exists() else 0
    _write_report(
        report_path,
        raw_records_found=_count_raw_relevant_records(root / "raw"),
        normalized_count=normalized_count,
        candidates=candidates,
        filtered_candidates=filtered_candidates,
        exported_candidates=selected,
        seeds=seeds,
        filters=filters,
        seed_path=seed_path,
        copied_to=copied_to,
    )
    skipped_count = len(candidates) - len(seeds)
    return {
        "schema_version": "1.0",
        "command": "export-seeds",
        "seed_path": str(seed_path),
        "report_path": str(report_path),
        "filters_applied": filters,
        "candidates_before_filtering": len(candidates),
        "candidates_after_filtering": len(filtered_candidates),
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "exported_seed_count": len(seeds),
        "skipped_count": skipped_count,
        "top_exported_pressure_types": _counter_dict(selected, "guessed_pressure_type"),
        "top_exported_subreddits": _counter_dict(selected, "subreddit"),
        "copied_to": str(copied_to) if copied_to else None,
        "external_action_allowed": False,
        "irreversible_action_allowed": False,
    }


def score_candidate(record: dict[str, Any]) -> tuple[int, list[str]]:
    text = str(record.get("text_for_pressure_analysis") or "")
    lowered = text.lower()
    reasons: list[str] = []
    score = 0
    word_count = len(re.findall(r"\w+", text))
    if word_count >= 80:
        score += 4
        reasons.append("substantial_long_text")
    elif word_count >= 35:
        score += 2
        reasons.append("substantial_text")
    elif word_count >= 15:
        score += 1
        reasons.append("moderate_text")

    raw_score = _as_int(record.get("score"), 0)
    if raw_score >= 10:
        score += 2
        reasons.append("high_score")
    if raw_score <= -1:
        score += 2
        reasons.append("low_or_negative_score")

    for label, terms in PRESSURE_TERMS.items():
        if _contains_any_term(lowered, terms):
            score += 2
            reasons.append(f"{label}_language")

    if _contains_any_term(lowered, ARGUMENT_MARKERS):
        score += 2
        reasons.append("argumentative_language")
    if _contains_any_term(lowered, SARCASM_MARKERS):
        score += 1
        reasons.append("sarcasm_marker")
    if _contains_any_term(lowered, CLARIFICATION_MARKERS):
        score += 2
        reasons.append("clarification_marker")
    if str(record.get("reddit_kind")) == "reply":
        score += 1
        reasons.append("reply_context")

    return score, sorted(set(reasons))


def _ensure_extracted_if_needed(root: Path) -> dict[str, Any]:
    raw_root = root / "raw"
    zip_path = root / "reddit_export.zip"
    if raw_root.exists() and any(_iter_data_files(raw_root)):
        return {"needed": False, "performed": False, "reason": "raw_data_files_present"}
    if not zip_path.exists():
        return {"needed": True, "performed": False, "reason": "zip_missing"}
    extract_root = raw_root / "reddit_export"
    if extract_root.exists() and any(extract_root.iterdir()):
        return {"needed": True, "performed": False, "reason": "extract_target_not_empty", "path": str(extract_root)}
    extract_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        _safe_extract_zip(archive, extract_root)
    return {"needed": True, "performed": True, "path": str(extract_root)}


def _safe_extract_zip(archive: zipfile.ZipFile, extract_root: Path) -> None:
    resolved_root = extract_root.resolve()
    for member in archive.infolist():
        target = (extract_root / member.filename).resolve()
        if resolved_root != target and resolved_root not in target.parents:
            raise ValueError(f"unsafe_zip_member:{member.filename}")
    archive.extractall(extract_root)


def _iter_data_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return (path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in {".csv", ".json", ".jsonl"})


def _zip_entries(zip_path: Path) -> list[dict[str, Any]]:
    if not zip_path.exists():
        return []
    with zipfile.ZipFile(zip_path, "r") as archive:
        return [{"name": info.filename, "size": info.file_size} for info in archive.infolist()]


def _summarize_file(path: Path, raw_root: Path) -> dict[str, Any]:
    headers: list[str] = []
    row_count = 0
    if path.suffix.lower() == ".csv":
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = list(reader.fieldnames or [])
            row_count = sum(1 for _ in reader)
    elif path.suffix.lower() in {".json", ".jsonl"}:
        rows = list(_iter_records(path))
        row_count = len(rows)
        keys: set[str] = set()
        for row in rows[:20]:
            keys.update(row.keys())
        headers = sorted(keys)
    return {
        "path": str(path.relative_to(raw_root)) if path.is_relative_to(raw_root) else str(path),
        "format": path.suffix.lower().lstrip("."),
        "row_count": row_count,
        "fields": headers,
        "contains_body": any(field.lower() in {"body", "text", "selftext"} for field in headers),
        "contains_title": any(field.lower() == "title" for field in headers),
        "contains_subreddit": any(field.lower() == "subreddit" for field in headers),
        "contains_permalink": any(field.lower() == "permalink" for field in headers),
    }


def _looks_like_comment_file(summary: dict[str, Any]) -> bool:
    fields = {str(field).lower() for field in summary.get("fields", [])}
    path = str(summary.get("path", "")).lower()
    return "comment" in path and "body" in fields


def _looks_like_post_file(summary: dict[str, Any]) -> bool:
    fields = {str(field).lower() for field in summary.get("fields", [])}
    path = str(summary.get("path", "")).lower()
    return "post" in path and ("title" in fields or "body" in fields)


def _file_kind(path: Path) -> str:
    name = path.name.lower()
    if name == "comments.csv" or name.endswith("comments.json") or name.endswith("comments.jsonl"):
        return "comment"
    if name == "posts.csv" or name.endswith("posts.json") or name.endswith("posts.jsonl"):
        return "post"
    return "unknown"


def _iter_records(path: Path) -> Iterable[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            yield from csv.DictReader(handle)
        return
    if suffix == ".jsonl":
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if raw:
                    payload = json.loads(raw)
                    if isinstance(payload, dict):
                        yield payload
        return
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    yield item
        elif isinstance(payload, dict):
            for value in payload.values():
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            yield item
            if not any(isinstance(value, list) for value in payload.values()):
                yield payload


def _normalize_row(row: dict[str, Any], *, raw_file: Path, raw_root: Path, raw_index: int, kind: str) -> dict[str, Any] | None:
    title = _clean_text(_first_value(row, "title", "name"))
    body = _clean_text(_first_value(row, "body", "selftext", "text"))
    if _is_deleted_or_empty(body) and not _usable_text(title):
        return None
    permalink = _clean_text(_first_value(row, "permalink"))
    parent_id = _clean_text(_first_value(row, "parent", "parent_id"))
    link_id = _clean_text(_first_value(row, "link", "link_id"))
    subreddit = _clean_text(_first_value(row, "subreddit"))
    raw_record_id = _clean_text(_first_value(row, "id", "name")) or f"{raw_file.stem}_{raw_index}"
    record_id = f"reddit_{kind}_{raw_record_id}"
    reddit_kind = "post" if kind == "post" else ("reply" if parent_id else "comment")
    text_for_pressure = _join_text(title, body)
    if not _usable_text(text_for_pressure):
        return None
    return {
        "record_id": record_id,
        "source_platform": "reddit",
        "reddit_kind": reddit_kind,
        "subreddit": subreddit,
        "created_utc": _clean_text(_first_value(row, "created_utc", "date", "created")),
        "score": _as_int(_first_value(row, "score", "ups", "gildings"), 0),
        "title": title,
        "body": body,
        "parent_id": parent_id,
        "link_id": link_id,
        "permalink": permalink,
        "url": _clean_text(_first_value(row, "url", "link")),
        "raw_file": str(raw_file.relative_to(raw_root)) if raw_file.is_relative_to(raw_root) else str(raw_file),
        "raw_index": raw_index,
        "text_for_pressure_analysis": text_for_pressure,
        "external_action_allowed": False,
        "irreversible_action_allowed": False,
    }


def _candidate_to_seed(candidate: dict[str, Any]) -> dict[str, Any]:
    subreddit = str(candidate.get("subreddit") or "unknown")
    reasons = ", ".join(candidate.get("candidate_reasons") or [])
    raw_text = _limit_text(str(candidate.get("text_for_pressure_analysis") or ""))
    source_type = "post" if candidate.get("reddit_kind") == "post" else "comment"
    return {
        "source_platform": "reddit",
        "source_type": source_type,
        "raw_text": raw_text,
        "source_context": (
            f"Reddit archive interaction from r/{subreddit}. "
            f"Score: {candidate.get('score', 0)}. "
            f"Kind: {candidate.get('reddit_kind', 'unknown')}. "
            f"Candidate reasons: {reasons}."
        ),
        "group_or_channel": f"r/{subreddit}",
        "intended_spine": "reflective",
        "tags": ["pressure_seed", "reddit", "reddit_archive"],
        "notes": (
            f"Guessed pressure type: {candidate.get('guessed_pressure_type')}; "
            f"Guessed spine: {candidate.get('guessed_spine')}; "
            f"Candidate score: {candidate.get('candidate_score')}; "
            f"Original permalink if available: {candidate.get('permalink') or 'none'}"
        ),
    }


def _build_export_filters(
    *,
    min_score: float | None,
    pressure_type: str | None,
    spine: str | None,
    subreddit: str | None,
    contains: str | None,
    exclude_deleted: bool,
) -> dict[str, Any]:
    normalized_min_score = None
    if min_score is not None:
        normalized_min_score = float(min_score)
        if normalized_min_score < 0:
            raise ValueError(f"invalid_min_score:{min_score}")

    normalized_pressure_type = None
    if pressure_type:
        try:
            normalized_pressure_type = validate_taxonomy_value("pressure_type", pressure_type, PRESSURE_TYPES)
        except ValueError as exc:
            raise ValueError(f"invalid_pressure_type:{pressure_type}") from exc

    normalized_spine = None
    if spine:
        try:
            normalized_spine = validate_taxonomy_value("spine", spine, SPINES)
        except ValueError as exc:
            raise ValueError(f"invalid_spine:{spine}") from exc

    return {
        "min_score": normalized_min_score,
        "pressure_type": normalized_pressure_type,
        "spine": normalized_spine,
        "subreddit": _normalize_subreddit_filter(subreddit) if subreddit else None,
        "contains": _clean_text(contains).lower() if contains else None,
        "exclude_deleted": bool(exclude_deleted),
    }


def _candidate_matches_filters(candidate: dict[str, Any], filters: dict[str, Any]) -> bool:
    min_score = filters.get("min_score")
    if min_score is not None and _as_float(candidate.get("candidate_score"), 0.0) < float(min_score):
        return False

    pressure_type = filters.get("pressure_type")
    if pressure_type and str(candidate.get("guessed_pressure_type") or "") != pressure_type:
        return False

    spine = filters.get("spine")
    if spine and str(candidate.get("guessed_spine") or "") != spine:
        return False

    subreddit = filters.get("subreddit")
    if subreddit and _normalize_subreddit_filter(candidate.get("subreddit")) != subreddit:
        return False

    contains = filters.get("contains")
    if contains and contains not in str(candidate.get("text_for_pressure_analysis") or "").lower():
        return False

    if filters.get("exclude_deleted") and _has_deleted_removed_or_unavailable_content(candidate):
        return False

    return True


def _safe_derived_output_path(derived_root: Path, output_name: str) -> Path:
    name = _clean_text(output_name) or SEED_FILE
    candidate = Path(name)
    if candidate.is_absolute() or candidate.name != name or ".." in candidate.parts:
        raise ValueError(f"invalid_output_name:{output_name}")
    if candidate.suffix.lower() != ".jsonl":
        raise ValueError(f"output_name_must_end_jsonl:{output_name}")
    output_path = derived_root / candidate.name
    resolved_root = derived_root.resolve()
    resolved_output = output_path.resolve()
    if resolved_root != resolved_output.parent:
        raise ValueError(f"output_path_outside_derived:{output_name}")
    return output_path


def _counter_dict(rows: list[dict[str, Any]], field_name: str, *, limit: int = 15) -> dict[str, int]:
    counts = Counter(str(row.get(field_name) or "unknown") for row in rows)
    return dict(counts.most_common(limit))


def _normalize_subreddit_filter(value: object) -> str:
    text = _clean_text(value).lower()
    if text.startswith("/r/"):
        text = text[3:]
    elif text.startswith("r/"):
        text = text[2:]
    return text.strip()


def _has_deleted_removed_or_unavailable_content(candidate: dict[str, Any]) -> bool:
    text = _clean_text(candidate.get("text_for_pressure_analysis"))
    if not text:
        return True
    return any(
        _is_deleted_removed_or_unavailable_marker(candidate.get(field_name))
        for field_name in ("title", "body", "text_for_pressure_analysis")
    )


def _is_deleted_removed_or_unavailable_marker(value: object) -> bool:
    text = _clean_text(value).lower()
    if not text:
        return False
    if text in {
        "[deleted]",
        "[removed]",
        "[unavailable]",
        "deleted",
        "removed",
        "unavailable",
        "content unavailable",
    }:
        return True
    return "no longer available" in text or "content is unavailable" in text


def _write_report(
    path: Path,
    *,
    raw_records_found: int,
    normalized_count: int,
    candidates: list[dict[str, Any]],
    filtered_candidates: list[dict[str, Any]],
    exported_candidates: list[dict[str, Any]],
    seeds: list[dict[str, Any]],
    filters: dict[str, Any],
    seed_path: Path,
    copied_to: Path | None,
) -> None:
    subreddit_counts = Counter(str(row.get("subreddit") or "unknown") for row in exported_candidates)
    pressure_counts = Counter(str(row.get("guessed_pressure_type") or "unknown") for row in exported_candidates)
    lines = [
        "# Reddit Pressure Seed Report",
        "",
        f"Total raw records found: {raw_records_found}",
        f"Normalized records count: {normalized_count}",
        f"Candidate count before filtering: {len(candidates)}",
        f"Candidates after filtering: {len(filtered_candidates)}",
        f"Exported seed count: {len(seeds)}",
        f"Skipped count: {len(candidates) - len(seeds)}",
        f"Copied to repo: {copied_to or 'not requested'}",
        "",
        "## Filters Applied",
        "",
    ]
    lines.extend(f"- `{key}`: {json.dumps(value, ensure_ascii=False)}" for key, value in filters.items())
    lines.extend(["", "## Top Subreddits In Exported Set", ""])
    lines.extend(f"- r/{name}: {count}" for name, count in subreddit_counts.most_common(15))
    lines.extend(["", "## Top Guessed Pressure Types In Exported Set", ""])
    lines.extend(f"- `{name}`: {count}" for name, count in pressure_counts.most_common(15))
    lines.extend(["", "## Top 25 Exported Candidate Summaries", ""])
    for candidate in exported_candidates[:25]:
        excerpt = _limit_text(str(candidate.get("text_for_pressure_analysis") or ""), limit=220)
        lines.extend(
            [
                f"### {candidate.get('record_id')} - score {candidate.get('candidate_score')}",
                "",
                f"- Subreddit: r/{candidate.get('subreddit') or 'unknown'}",
                f"- Pressure: `{candidate.get('guessed_pressure_type')}`",
                f"- Reasons: {', '.join(candidate.get('candidate_reasons') or [])}",
                f"- Excerpt: {excerpt}",
                "",
            ]
        )
    lines.extend(
        [
            "## Warnings Or Skipped Files",
            "",
            "Normalization skips deleted, removed, or empty interactions unless a title remains useful.",
            "",
            "## Import Command",
            "",
            "```powershell",
            rf".\.venv\Scripts\python.exe -m app.reflective_pressure.cli rp-import-inputs --path data/inputs/reflective_pressure/{seed_path.name} --classify",
            "```",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _copy_seed_to_repo(seed_path: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(seed_path, destination)
    return destination


def _count_raw_relevant_records(raw_root: Path) -> int:
    total = 0
    for raw_file in sorted(_iter_data_files(raw_root)):
        if _file_kind(raw_file) not in {"comment", "post"}:
            continue
        try:
            total += sum(1 for _ in _iter_records(raw_file))
        except (OSError, UnicodeError, csv.Error, json.JSONDecodeError):
            continue
    return total


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if raw:
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    rows.append(payload)
    return rows


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _first_value(row: dict[str, Any], *keys: str) -> Any:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return value
    return ""


def _clean_text(value: Any) -> str:
    text = str(value or "").replace("\x00", "")
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text.strip()


def _is_deleted_or_empty(value: str) -> bool:
    normalized = _clean_text(value).strip().lower()
    return normalized in {"", "[deleted]", "[removed]", "deleted", "removed"}


def _usable_text(value: object) -> bool:
    return bool(_clean_text(value).strip())


def _join_text(title: str, body: str) -> str:
    if title and body:
        return f"{title}\n\n{body}"
    return title or body


def _as_int(value: Any, default: int) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        if value in (None, ""):
            return default
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _guess_pressure_type(record: dict[str, Any]) -> str:
    text = str(record.get("text_for_pressure_analysis") or "").lower()
    if _contains_any_term(text, ("god", "bible", "jesus", "church", "sin", "gospel")):
        return "spiritual_reductionism"
    if _contains_any_term(text, ("hypocrisy", "double standard", "wrong", "right", "truth", "false")):
        return "moral_contradiction_exposure"
    if _contains_any_term(text, ("offended", "intent", "misunderstood", "accusation", "you missed")):
        return "peace_vs_escalation"
    if _contains_any_term(text, ("government", "authority", "system", "power", "ai")):
        return "authority_confusion"
    if _contains_any_term(text, ("lol", "lmao", "yeah right", "sure")):
        return "humor_as_shield"
    if _contains_any_term(text, ("nobody", "unseen", "ignored")):
        return "recognition_deprivation"
    return "unknown"


def _guess_spine(record: dict[str, Any]) -> str:
    pressure_type = _guess_pressure_type(record)
    if pressure_type == "spiritual_reductionism":
        return "theological"
    if pressure_type == "humor_as_shield":
        return "humor"
    if pressure_type == "authority_confusion":
        return "governance"
    return "reflective"


def _recommended_output_type(record: dict[str, Any]) -> str:
    if _guess_pressure_type(record) == "spiritual_reductionism":
        return "theological_reflection"
    if str(record.get("reddit_kind")) in {"comment", "reply"}:
        return "reply"
    return "pressure_log_entry"


def _limit_text(text: str, limit: int = 6000) -> str:
    normalized = _clean_text(text)
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _contains_any_term(text: str, terms: Iterable[str]) -> bool:
    return any(_contains_term(text, term) for term in terms)


def _contains_term(text: str, term: str) -> bool:
    normalized = term.lower().strip()
    if not normalized:
        return False
    if " " in normalized or normalized.startswith("/") or "'" in normalized:
        return normalized in text
    return re.search(rf"\b{re.escape(normalized)}\b", text) is not None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert a local Reddit archive into Reflective Pressure seed JSONL.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("inspect", "normalize", "filter-candidates", "export-seeds"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--dataset-root", required=True)
        if command == "export-seeds":
            subparser.add_argument("--limit", type=int, default=100)
            subparser.add_argument("--min-score", type=float)
            subparser.add_argument("--pressure-type")
            subparser.add_argument("--spine")
            subparser.add_argument("--subreddit")
            subparser.add_argument("--contains")
            subparser.add_argument("--exclude-deleted", action="store_true")
            subparser.add_argument("--output-name", default=SEED_FILE)
            subparser.add_argument("--copy-to-repo")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "inspect":
        payload = inspect_dataset(args.dataset_root)
    elif args.command == "normalize":
        payload = normalize_dataset(args.dataset_root)
    elif args.command == "filter-candidates":
        payload = filter_candidates(args.dataset_root)
    elif args.command == "export-seeds":
        try:
            payload = export_seeds(
                args.dataset_root,
                limit=args.limit,
                min_score=args.min_score,
                pressure_type=args.pressure_type,
                spine=args.spine,
                subreddit=args.subreddit,
                contains=args.contains,
                exclude_deleted=args.exclude_deleted,
                output_name=args.output_name,
                copy_to_repo=args.copy_to_repo,
            )
        except ValueError as exc:
            parser.exit(2, f"error: {exc}\n")
    else:
        parser.error(f"unsupported_command:{args.command}")
        return 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
