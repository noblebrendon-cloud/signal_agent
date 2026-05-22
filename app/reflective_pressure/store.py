from __future__ import annotations

from pathlib import Path
from typing import Any

from app.reflective_pressure.models import (
    CLASSIFICATION_RECORD_TYPE,
    CORRECTION_RECORD_TYPE,
    DRAFT_RECORD_TYPE,
    GOLDEN_EXAMPLE_RECORD_TYPE,
    INPUT_RECORD_TYPE,
    OBSERVATION_RECORD_TYPE,
    build_event_record,
    validate_classification_record,
    validate_correction_record,
    validate_draft_record,
    validate_golden_example_record,
    validate_input_record,
    validate_observation_record,
)
from app.retention.jsonl_store import append_record, iter_jsonl


INPUTS_FILE = "reflective_pressure_inputs.jsonl"
CLASSIFICATIONS_FILE = "reflective_pressure_classifications.jsonl"
DRAFTS_FILE = "reflective_pressure_drafts.jsonl"
OBSERVATIONS_FILE = "reflective_pressure_observations.jsonl"
CORRECTIONS_FILE = "reflective_pressure_corrections.jsonl"
GOLDEN_EXAMPLES_FILE = "reflective_pressure_golden_examples.jsonl"
EVENTS_FILE = "reflective_pressure_events.jsonl"

REFLECTIVE_PRESSURE_LEDGER_FILES = (
    INPUTS_FILE,
    CLASSIFICATIONS_FILE,
    DRAFTS_FILE,
    OBSERVATIONS_FILE,
    CORRECTIONS_FILE,
    GOLDEN_EXAMPLES_FILE,
    EVENTS_FILE,
)


def append_input(record: dict[str, Any], *, repo_root: Path | None = None) -> dict[str, Any]:
    validate_input_record(record)
    if get_input_by_id(str(record["input_id"]), repo_root=repo_root) is not None:
        raise ValueError(f"duplicate_input:{record['input_id']}")
    written = append_record(INPUTS_FILE, record, repo_root=repo_root, recorded_at=record["created_at"])
    _append_event(
        event_type="input_appended",
        linked_record_type=INPUT_RECORD_TYPE,
        linked_record_id=written["input_id"],
        created_at=written["created_at"],
        input_id=written["input_id"],
        repo_root=repo_root,
    )
    return written


def append_classification(record: dict[str, Any], *, repo_root: Path | None = None) -> dict[str, Any]:
    validate_classification_record(record)
    if get_input_by_id(str(record["input_id"]), repo_root=repo_root) is None:
        raise ValueError(f"unknown_input:{record['input_id']}")
    if get_classification_by_id(str(record["classification_id"]), repo_root=repo_root) is not None:
        raise ValueError(f"duplicate_classification:{record['classification_id']}")
    written = append_record(CLASSIFICATIONS_FILE, record, repo_root=repo_root, recorded_at=record["created_at"])
    _append_event(
        event_type="classification_appended",
        linked_record_type=CLASSIFICATION_RECORD_TYPE,
        linked_record_id=written["classification_id"],
        created_at=written["created_at"],
        input_id=written["input_id"],
        classification_id=written["classification_id"],
        repo_root=repo_root,
    )
    return written


def append_draft(record: dict[str, Any], *, repo_root: Path | None = None) -> dict[str, Any]:
    validate_draft_record(record)
    if get_input_by_id(str(record["input_id"]), repo_root=repo_root) is None:
        raise ValueError(f"unknown_input:{record['input_id']}")
    classification = get_classification_by_id(str(record["classification_id"]), repo_root=repo_root)
    if classification is None:
        raise ValueError(f"unknown_classification:{record['classification_id']}")
    if classification["input_id"] != record["input_id"]:
        raise ValueError("draft_input_classification_mismatch")
    if get_draft_by_id(str(record["draft_id"]), repo_root=repo_root) is not None:
        raise ValueError(f"duplicate_draft:{record['draft_id']}")
    written = append_record(DRAFTS_FILE, record, repo_root=repo_root, recorded_at=record["created_at"])
    _append_event(
        event_type="draft_appended",
        linked_record_type=DRAFT_RECORD_TYPE,
        linked_record_id=written["draft_id"],
        created_at=written["created_at"],
        input_id=written["input_id"],
        classification_id=written["classification_id"],
        draft_id=written["draft_id"],
        repo_root=repo_root,
    )
    return written


def append_observation(record: dict[str, Any], *, repo_root: Path | None = None) -> dict[str, Any]:
    validate_observation_record(record)
    if get_input_by_id(str(record["input_id"]), repo_root=repo_root) is None:
        raise ValueError(f"unknown_input:{record['input_id']}")
    draft = get_draft_by_id(str(record["draft_id"]), repo_root=repo_root)
    if draft is None:
        raise ValueError(f"unknown_draft:{record['draft_id']}")
    if draft["input_id"] != record["input_id"]:
        raise ValueError("observation_input_draft_mismatch")
    if get_observation_by_id(str(record["observation_id"]), repo_root=repo_root) is not None:
        raise ValueError(f"duplicate_observation:{record['observation_id']}")
    written = append_record(OBSERVATIONS_FILE, record, repo_root=repo_root, recorded_at=record["created_at"])
    _append_event(
        event_type="observation_appended",
        linked_record_type=OBSERVATION_RECORD_TYPE,
        linked_record_id=written["observation_id"],
        created_at=written["created_at"],
        input_id=written["input_id"],
        draft_id=written["draft_id"],
        observation_id=written["observation_id"],
        repo_root=repo_root,
    )
    return written


def append_correction(record: dict[str, Any], *, repo_root: Path | None = None) -> dict[str, Any]:
    validate_correction_record(record)
    if get_input_by_id(str(record["input_id"]), repo_root=repo_root) is None:
        raise ValueError(f"unknown_input:{record['input_id']}")
    _validate_target_reference(record, repo_root=repo_root)
    if get_correction_by_id(str(record["correction_id"]), repo_root=repo_root) is not None:
        raise ValueError(f"duplicate_correction:{record['correction_id']}")
    written = append_record(CORRECTIONS_FILE, record, repo_root=repo_root, recorded_at=record["created_at"])
    _append_event(
        event_type="correction_appended",
        linked_record_type=CORRECTION_RECORD_TYPE,
        linked_record_id=written["correction_id"],
        created_at=written["created_at"],
        input_id=written["input_id"],
        correction_id=written["correction_id"],
        repo_root=repo_root,
    )
    return written


def append_golden_example(record: dict[str, Any], *, repo_root: Path | None = None) -> dict[str, Any]:
    validate_golden_example_record(record)
    if get_input_by_id(str(record["input_id"]), repo_root=repo_root) is None:
        raise ValueError(f"unknown_input:{record['input_id']}")
    classification = get_classification_by_id(str(record["classification_id"]), repo_root=repo_root)
    if classification is None:
        raise ValueError(f"unknown_classification:{record['classification_id']}")
    if classification["input_id"] != record["input_id"]:
        raise ValueError("golden_input_classification_mismatch")
    if record.get("correction_id"):
        correction = get_correction_by_id(str(record["correction_id"]), repo_root=repo_root)
        if correction is None:
            raise ValueError(f"unknown_correction:{record['correction_id']}")
        if correction["input_id"] != record["input_id"]:
            raise ValueError("golden_input_correction_mismatch")
    if record.get("draft_id"):
        draft = get_draft_by_id(str(record["draft_id"]), repo_root=repo_root)
        if draft is None:
            raise ValueError(f"unknown_draft:{record['draft_id']}")
        if draft["input_id"] != record["input_id"]:
            raise ValueError("golden_input_draft_mismatch")
    if get_golden_example_by_id(str(record["golden_id"]), repo_root=repo_root) is not None:
        raise ValueError(f"duplicate_golden_example:{record['golden_id']}")
    written = append_record(GOLDEN_EXAMPLES_FILE, record, repo_root=repo_root, recorded_at=record["created_at"])
    _append_event(
        event_type="golden_example_appended",
        linked_record_type=GOLDEN_EXAMPLE_RECORD_TYPE,
        linked_record_id=written["golden_id"],
        created_at=written["created_at"],
        input_id=written["input_id"],
        classification_id=written["classification_id"],
        draft_id=written.get("draft_id"),
        correction_id=written.get("correction_id"),
        golden_id=written["golden_id"],
        repo_root=repo_root,
    )
    return written


def list_inputs(limit: int | None = None, *, repo_root: Path | None = None) -> list[dict[str, Any]]:
    rows = [row for row in iter_jsonl(INPUTS_FILE, repo_root=repo_root) if row.get("record_type") == INPUT_RECORD_TYPE]
    for row in rows:
        validate_input_record(row)
    return _apply_limit(_sort_rows(rows, "created_at", "input_id"), limit)


def list_classifications(
    input_id: str | None = None,
    limit: int | None = None,
    *,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    rows = [
        row
        for row in iter_jsonl(CLASSIFICATIONS_FILE, repo_root=repo_root)
        if row.get("record_type") == CLASSIFICATION_RECORD_TYPE
    ]
    for row in rows:
        validate_classification_record(row)
    if input_id:
        rows = [row for row in rows if row["input_id"] == input_id]
    return _apply_limit(_sort_rows(rows, "created_at", "classification_id"), limit)


def list_drafts(
    input_id: str | None = None,
    limit: int | None = None,
    *,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    rows = [row for row in iter_jsonl(DRAFTS_FILE, repo_root=repo_root) if row.get("record_type") == DRAFT_RECORD_TYPE]
    for row in rows:
        validate_draft_record(row)
    if input_id:
        rows = [row for row in rows if row["input_id"] == input_id]
    return _apply_limit(_sort_rows(rows, "created_at", "draft_id"), limit)


def list_observations(
    input_id: str | None = None,
    draft_id: str | None = None,
    limit: int | None = None,
    *,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    rows = [
        row
        for row in iter_jsonl(OBSERVATIONS_FILE, repo_root=repo_root)
        if row.get("record_type") == OBSERVATION_RECORD_TYPE
    ]
    for row in rows:
        validate_observation_record(row)
    if input_id:
        rows = [row for row in rows if row["input_id"] == input_id]
    if draft_id:
        rows = [row for row in rows if row["draft_id"] == draft_id]
    return _apply_limit(_sort_rows(rows, "created_at", "observation_id"), limit)


def list_corrections(
    input_id: str | None = None,
    target_record_id: str | None = None,
    limit: int | None = None,
    *,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    rows = [
        row
        for row in iter_jsonl(CORRECTIONS_FILE, repo_root=repo_root)
        if row.get("record_type") == CORRECTION_RECORD_TYPE
    ]
    for row in rows:
        validate_correction_record(row)
    if input_id:
        rows = [row for row in rows if row["input_id"] == input_id]
    if target_record_id:
        rows = [row for row in rows if row["target_record_id"] == target_record_id]
    return _apply_limit(_sort_rows(rows, "created_at", "correction_id"), limit)


def list_golden_examples(
    pressure_type: str | None = None,
    approved_only: bool = False,
    limit: int | None = None,
    *,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    rows = [
        row
        for row in iter_jsonl(GOLDEN_EXAMPLES_FILE, repo_root=repo_root)
        if row.get("record_type") == GOLDEN_EXAMPLE_RECORD_TYPE
    ]
    for row in rows:
        validate_golden_example_record(row)
    if pressure_type:
        rows = [row for row in rows if row["pressure_type"] == pressure_type]
    if approved_only:
        rows = [row for row in rows if row["approved_for_prompt_export"] is True]
    return _apply_limit(_sort_rows(rows, "created_at", "golden_id"), limit)


def get_input_by_id(input_id: str, *, repo_root: Path | None = None) -> dict[str, Any] | None:
    return _find_latest(list_inputs(repo_root=repo_root), "input_id", input_id)


def get_classification_by_id(
    classification_id: str,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any] | None:
    return _find_latest(list_classifications(repo_root=repo_root), "classification_id", classification_id)


def get_draft_by_id(draft_id: str, *, repo_root: Path | None = None) -> dict[str, Any] | None:
    return _find_latest(list_drafts(repo_root=repo_root), "draft_id", draft_id)


def get_observation_by_id(
    observation_id: str,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any] | None:
    return _find_latest(list_observations(repo_root=repo_root), "observation_id", observation_id)


def get_correction_by_id(
    correction_id: str,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any] | None:
    return _find_latest(list_corrections(repo_root=repo_root), "correction_id", correction_id)


def get_golden_example_by_id(
    golden_id: str,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any] | None:
    return _find_latest(list_golden_examples(repo_root=repo_root), "golden_id", golden_id)


def _validate_target_reference(record: dict[str, Any], *, repo_root: Path | None = None) -> None:
    target_type = record["target_record_type"]
    target_id = str(record["target_record_id"])
    input_id = str(record["input_id"])
    if target_type == "input":
        target = get_input_by_id(target_id, repo_root=repo_root)
        if target is None:
            raise ValueError(f"unknown_target_input:{target_id}")
        if target["input_id"] != input_id:
            raise ValueError("correction_input_target_mismatch")
        return
    if target_type == "classification":
        target = get_classification_by_id(target_id, repo_root=repo_root)
        if target is None:
            raise ValueError(f"unknown_target_classification:{target_id}")
        if target["input_id"] != input_id:
            raise ValueError("correction_input_target_mismatch")
        return
    if target_type == "draft":
        target = get_draft_by_id(target_id, repo_root=repo_root)
        if target is None:
            raise ValueError(f"unknown_target_draft:{target_id}")
        if target["input_id"] != input_id:
            raise ValueError("correction_input_target_mismatch")
        return
    if target_type == "observation":
        target = get_observation_by_id(target_id, repo_root=repo_root)
        if target is None:
            raise ValueError(f"unknown_target_observation:{target_id}")
        if target["input_id"] != input_id:
            raise ValueError("correction_input_target_mismatch")
        return
    raise ValueError(f"unsupported_target_record_type:{target_type}")


def _append_event(
    *,
    event_type: str,
    linked_record_type: str,
    linked_record_id: str,
    created_at: str,
    repo_root: Path | None = None,
    input_id: str | None = None,
    classification_id: str | None = None,
    draft_id: str | None = None,
    observation_id: str | None = None,
    correction_id: str | None = None,
    golden_id: str | None = None,
) -> dict[str, Any]:
    event = build_event_record(
        event_type=event_type,
        linked_record_type=linked_record_type,
        linked_record_id=linked_record_id,
        created_at=created_at,
        input_id=input_id,
        classification_id=classification_id,
        draft_id=draft_id,
        observation_id=observation_id,
    )
    if correction_id:
        event["correction_id"] = correction_id
    if golden_id:
        event["golden_id"] = golden_id
    return append_record(EVENTS_FILE, event, repo_root=repo_root, recorded_at=event["created_at"])


def _find_latest(rows: list[dict[str, Any]], field: str, value: str) -> dict[str, Any] | None:
    target = str(value or "").strip()
    matched = None
    for row in rows:
        if row.get(field) == target:
            matched = row
    return matched


def _sort_rows(rows: list[dict[str, Any]], date_field: str, id_field: str) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: (str(row.get(date_field) or ""), str(row.get(id_field) or "")))


def _apply_limit(rows: list[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    if limit is None:
        return rows
    parsed = int(limit)
    if parsed < 0:
        raise ValueError("limit_must_be_non_negative")
    if parsed == 0:
        return []
    return rows[-parsed:]
