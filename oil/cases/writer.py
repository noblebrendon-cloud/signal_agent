"""
OIL Cases -- Case File Bundle Writer (v0.7)

write_case(run_id, artifact_path, memory_line, outcomes_for_run_id,
           human_block, cases_dir) -> Path

Creates oil/cases/<run_id>/ containing:
  incident.json   -- copy of the incident artifact (atomic overwrite)
  memory.json     -- single JSON object from memory index (atomic overwrite)
  outcomes.jsonl  -- all outcomes for run_id (append-only, deduped by created_utc+kind)
  summary.txt     -- human-readable block (atomic overwrite)

Idempotent: repeated calls with the same run_id overwrite incident/memory/summary
atomically but only append NEW outcomes.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

_OIL_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CASES_DIR = _OIL_ROOT / "cases"

_OUTCOME_DEDUP_KEY = lambda e: (e.get("created_utc", ""), e.get("outcome_kind", ""))


def _atomic_write_text(path: Path, text: str) -> None:
    """Write text to path atomically (write temp then replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        os.write(fd, text.encode("utf-8"))
        os.close(fd)
        os.replace(tmp, str(path))
    except Exception:
        os.close(fd)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _atomic_write_json(path: Path, data: object) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    _atomic_write_text(path, text)


def _load_case_outcomes(outcomes_path: Path) -> set[tuple[str, str]]:
    """Return the set of (created_utc, outcome_kind) already in case outcomes.jsonl."""
    if not outcomes_path.exists():
        return set()
    seen: set[tuple[str, str]] = set()
    for line in outcomes_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
            seen.add(_OUTCOME_DEDUP_KEY(e))
        except json.JSONDecodeError:
            continue
    return seen


def _sync_case_outcomes(
    case_outcomes_path: Path,
    new_entries: list[dict],
) -> None:
    """Append entries not already present in case outcomes.jsonl (dedup by created_utc+kind)."""
    existing_keys = _load_case_outcomes(case_outcomes_path)
    case_outcomes_path.parent.mkdir(parents=True, exist_ok=True)

    # Sort chronologically before appending
    to_append = sorted(
        [e for e in new_entries if _OUTCOME_DEDUP_KEY(e) not in existing_keys],
        key=lambda e: e.get("created_utc", ""),
    )
    if not to_append:
        return
    fd = os.open(str(case_outcomes_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        for entry in to_append:
            line = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
            os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def write_case(
    run_id: str,
    artifact_path: Path | str,
    memory_line: dict,
    outcomes_for_run: list[dict],
    human_block: str,
    cases_dir: Path | None = None,
) -> Path:
    """Write (or update) a case bundle for run_id.

    Args:
        run_id:            Run identifier.
        artifact_path:     Path to the incident artifact JSON.
        memory_line:       Single dict from the memory index for this run.
        outcomes_for_run:  List of outcome entries for run_id (may be empty).
        human_block:       Plain-text explanation block (from format_human_block).
        cases_dir:         Parent directory for case folders.
                           Defaults to oil/cases/.

    Returns:
        Path to the case directory (oil/cases/<run_id>/).
    """
    base = cases_dir or _DEFAULT_CASES_DIR
    case_dir = base / run_id
    case_dir.mkdir(parents=True, exist_ok=True)

    # 1. incident.json -- atomic copy from artifact
    artifact_path = Path(artifact_path)
    if artifact_path.exists():
        incident_data = json.loads(artifact_path.read_text(encoding="utf-8"))
        _atomic_write_json(case_dir / "incident.json", incident_data)

    # 2. memory.json -- single object
    _atomic_write_json(case_dir / "memory.json", memory_line)

    # 3. outcomes.jsonl -- append-only, deduped
    _sync_case_outcomes(case_dir / "outcomes.jsonl", outcomes_for_run)

    # 4. summary.txt -- atomic overwrite
    _atomic_write_text(case_dir / "summary.txt", human_block)

    return case_dir
