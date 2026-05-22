from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.reflective_pressure.models import (
    CLASSIFICATION_RECORD_TYPE,
    CORRECTION_RECORD_TYPE,
    DRAFT_RECORD_TYPE,
    EVENT_RECORD_TYPE,
    GOLDEN_EXAMPLE_RECORD_TYPE,
    INPUT_RECORD_TYPE,
    OBSERVATION_RECORD_TYPE,
    validate_classification_record,
    validate_correction_record,
    validate_draft_record,
    validate_event_record,
    validate_golden_example_record,
    validate_input_record,
    validate_observation_record,
)
from app.reflective_pressure.store import (
    CLASSIFICATIONS_FILE,
    CORRECTIONS_FILE,
    DRAFTS_FILE,
    EVENTS_FILE,
    GOLDEN_EXAMPLES_FILE,
    INPUTS_FILE,
    OBSERVATIONS_FILE,
    REFLECTIVE_PRESSURE_LEDGER_FILES,
)
from app.retention.identity import get_repo_root, get_state_root
from app.retention.jsonl_store import compute_record_hash


LEDGER_ORDER = {name: index for index, name in enumerate(REFLECTIVE_PRESSURE_LEDGER_FILES)}
VALIDATORS = {
    INPUT_RECORD_TYPE: validate_input_record,
    CLASSIFICATION_RECORD_TYPE: validate_classification_record,
    DRAFT_RECORD_TYPE: validate_draft_record,
    OBSERVATION_RECORD_TYPE: validate_observation_record,
    CORRECTION_RECORD_TYPE: validate_correction_record,
    GOLDEN_EXAMPLE_RECORD_TYPE: validate_golden_example_record,
    EVENT_RECORD_TYPE: validate_event_record,
}


def reconcile_reflective_pressure_state(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or get_repo_root()
    state_root = get_state_root(root)
    rows_by_ledger: dict[str, list[dict[str, Any]]] = {}
    ledger_stats: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for ledger_name in REFLECTIVE_PRESSURE_LEDGER_FILES:
        rows, load_failures, stats = _load_ledger(state_root, ledger_name)
        rows_by_ledger[ledger_name] = rows
        ledger_stats.append(stats)
        failures.extend(load_failures)

    if not failures:
        failures.extend(_validate_records(rows_by_ledger))
    if not failures:
        failures.extend(_detect_hash_issues(rows_by_ledger))
        failures.extend(_detect_duplicate_ids(rows_by_ledger))
        failures.extend(_detect_reference_issues(rows_by_ledger))

    failures = _sort_issues(failures)
    summary = {
        "input_count": len(rows_by_ledger.get(INPUTS_FILE, [])),
        "classification_count": len(rows_by_ledger.get(CLASSIFICATIONS_FILE, [])),
        "draft_count": len(rows_by_ledger.get(DRAFTS_FILE, [])),
        "observation_count": len(rows_by_ledger.get(OBSERVATIONS_FILE, [])),
        "correction_count": len(rows_by_ledger.get(CORRECTIONS_FILE, [])),
        "golden_example_count": len(rows_by_ledger.get(GOLDEN_EXAMPLES_FILE, [])),
        "event_count": len(rows_by_ledger.get(EVENTS_FILE, [])),
        "failure_count": len(failures),
    }
    return {
        "schema_version": "1.0",
        "command": "rp-reconcile",
        "clean": not failures,
        "summary": summary,
        "failures": failures,
        "warnings": [],
        "ledgers": ledger_stats,
        "state_root": str(state_root.resolve()),
    }


def _load_ledger(state_root: Path, ledger_name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    path = state_root / ledger_name
    if not path.exists():
        return [], [], {"ledger": ledger_name, "exists": False, "row_count": 0, "path": str(path)}

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as exc:
                failures.append(_issue("invalid_jsonl_record", ledger_name, line_number=line_number, error=str(exc)))
                continue
            if not isinstance(record, dict):
                failures.append(_issue("non_dict_jsonl_record", ledger_name, line_number=line_number))
                continue
            rows.append({"ledger": ledger_name, "line_number": line_number, "record": record})
    return rows, failures, {"ledger": ledger_name, "exists": True, "row_count": len(rows), "path": str(path)}


def _validate_records(rows_by_ledger: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for ledger_name, rows in rows_by_ledger.items():
        for row in rows:
            record = row["record"]
            record_type = str(record.get("record_type") or "")
            validator = VALIDATORS.get(record_type)
            if validator is None:
                failures.append(
                    _issue(
                        "unsupported_record_type",
                        ledger_name,
                        line_number=row["line_number"],
                        record_type=record_type,
                    )
                )
                continue
            expected_type = _expected_record_type_for_ledger(ledger_name)
            if record_type != expected_type:
                failures.append(
                    _issue(
                        "record_type_ledger_mismatch",
                        ledger_name,
                        line_number=row["line_number"],
                        expected_record_type=expected_type,
                        observed_record_type=record_type,
                    )
                )
                continue
            try:
                validator(record)
            except ValueError as exc:
                failures.append(
                    _issue(
                        "schema_validation_failed",
                        ledger_name,
                        line_number=row["line_number"],
                        detail=str(exc),
                        record_id=_record_id(record),
                    )
                )
            failures.extend(_detect_flag_issues(ledger_name, row))
    return failures


def _detect_hash_issues(rows_by_ledger: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for ledger_name in REFLECTIVE_PRESSURE_LEDGER_FILES:
        previous_record_hash: str | None = None
        for row in rows_by_ledger.get(ledger_name, []):
            record = row["record"]
            expected_record_hash = compute_record_hash(record)
            observed_record_hash = record.get("record_hash")
            if observed_record_hash != expected_record_hash:
                failures.append(
                    _issue(
                        "record_hash_mismatch",
                        ledger_name,
                        line_number=row["line_number"],
                        expected_record_hash=expected_record_hash,
                        observed_record_hash=observed_record_hash,
                    )
                )
            observed_prev_hash = record.get("prev_hash")
            if observed_prev_hash != previous_record_hash:
                failures.append(
                    _issue(
                        "prev_hash_mismatch",
                        ledger_name,
                        line_number=row["line_number"],
                        expected_prev_hash=previous_record_hash,
                        observed_prev_hash=observed_prev_hash,
                    )
                )
            previous_record_hash = observed_record_hash if isinstance(observed_record_hash, str) else expected_record_hash
    return failures


def _detect_duplicate_ids(rows_by_ledger: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    id_fields = {
        INPUTS_FILE: "input_id",
        CLASSIFICATIONS_FILE: "classification_id",
        DRAFTS_FILE: "draft_id",
        OBSERVATIONS_FILE: "observation_id",
        CORRECTIONS_FILE: "correction_id",
        GOLDEN_EXAMPLES_FILE: "golden_id",
        EVENTS_FILE: "event_id",
    }
    failures: list[dict[str, Any]] = []
    for ledger_name, id_field in id_fields.items():
        seen: dict[str, int] = {}
        for row in rows_by_ledger.get(ledger_name, []):
            value = str(row["record"].get(id_field) or "").strip()
            if not value:
                continue
            if value in seen:
                failures.append(
                    _issue(
                        "duplicate_record_id",
                        ledger_name,
                        line_number=row["line_number"],
                        record_id=value,
                        first_line_number=seen[value],
                    )
                )
            else:
                seen[value] = row["line_number"]
    return failures


def _detect_reference_issues(rows_by_ledger: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    inputs = {row["record"]["input_id"]: row["record"] for row in rows_by_ledger.get(INPUTS_FILE, [])}
    classifications = {
        row["record"]["classification_id"]: row["record"]
        for row in rows_by_ledger.get(CLASSIFICATIONS_FILE, [])
    }
    drafts = {row["record"]["draft_id"]: row["record"] for row in rows_by_ledger.get(DRAFTS_FILE, [])}
    observations = {
        row["record"]["observation_id"]: row["record"]
        for row in rows_by_ledger.get(OBSERVATIONS_FILE, [])
    }
    corrections = {
        row["record"]["correction_id"]: row["record"]
        for row in rows_by_ledger.get(CORRECTIONS_FILE, [])
    }
    failures: list[dict[str, Any]] = []

    for row in rows_by_ledger.get(CLASSIFICATIONS_FILE, []):
        record = row["record"]
        input_id = record.get("input_id")
        if input_id not in inputs:
            failures.append(
                _issue(
                    "classification_unknown_input",
                    CLASSIFICATIONS_FILE,
                    line_number=row["line_number"],
                    input_id=input_id,
                    record_id=record.get("classification_id"),
                )
            )

    for row in rows_by_ledger.get(DRAFTS_FILE, []):
        record = row["record"]
        input_id = record.get("input_id")
        classification_id = record.get("classification_id")
        classification = classifications.get(classification_id)
        if input_id not in inputs:
            failures.append(
                _issue(
                    "draft_unknown_input",
                    DRAFTS_FILE,
                    line_number=row["line_number"],
                    input_id=input_id,
                    record_id=record.get("draft_id"),
                )
            )
        if classification is None:
            failures.append(
                _issue(
                    "draft_unknown_classification",
                    DRAFTS_FILE,
                    line_number=row["line_number"],
                    classification_id=classification_id,
                    record_id=record.get("draft_id"),
                )
            )
        elif classification.get("input_id") != input_id:
            failures.append(
                _issue(
                    "draft_input_classification_mismatch",
                    DRAFTS_FILE,
                    line_number=row["line_number"],
                    input_id=input_id,
                    classification_id=classification_id,
                    record_id=record.get("draft_id"),
                )
            )

    for row in rows_by_ledger.get(OBSERVATIONS_FILE, []):
        record = row["record"]
        input_id = record.get("input_id")
        draft_id = record.get("draft_id")
        draft = drafts.get(draft_id)
        if input_id not in inputs:
            failures.append(
                _issue(
                    "observation_unknown_input",
                    OBSERVATIONS_FILE,
                    line_number=row["line_number"],
                    input_id=input_id,
                    record_id=record.get("observation_id"),
                )
            )
        if draft is None:
            failures.append(
                _issue(
                    "observation_unknown_draft",
                    OBSERVATIONS_FILE,
                    line_number=row["line_number"],
                    draft_id=draft_id,
                    record_id=record.get("observation_id"),
                )
            )
        elif draft.get("input_id") != input_id:
            failures.append(
                _issue(
                    "observation_input_draft_mismatch",
                    OBSERVATIONS_FILE,
                    line_number=row["line_number"],
                    input_id=input_id,
                    draft_id=draft_id,
                    record_id=record.get("observation_id"),
                )
            )
    for row in rows_by_ledger.get(CORRECTIONS_FILE, []):
        record = row["record"]
        input_id = record.get("input_id")
        target_type = record.get("target_record_type")
        target_id = record.get("target_record_id")
        if input_id not in inputs:
            failures.append(
                _issue(
                    "correction_unknown_input",
                    CORRECTIONS_FILE,
                    line_number=row["line_number"],
                    input_id=input_id,
                    record_id=record.get("correction_id"),
                )
            )
            continue
        target = None
        if target_type == "input":
            target = inputs.get(target_id)
        elif target_type == "classification":
            target = classifications.get(target_id)
        elif target_type == "draft":
            target = drafts.get(target_id)
        elif target_type == "observation":
            target = observations.get(target_id)
        if target is None:
            failures.append(
                _issue(
                    "correction_unknown_target",
                    CORRECTIONS_FILE,
                    line_number=row["line_number"],
                    target_record_type=target_type,
                    target_record_id=target_id,
                    record_id=record.get("correction_id"),
                )
            )
        elif target.get("input_id") != input_id:
            failures.append(
                _issue(
                    "correction_input_target_mismatch",
                    CORRECTIONS_FILE,
                    line_number=row["line_number"],
                    input_id=input_id,
                    target_record_id=target_id,
                    record_id=record.get("correction_id"),
                )
            )
    for row in rows_by_ledger.get(GOLDEN_EXAMPLES_FILE, []):
        record = row["record"]
        input_id = record.get("input_id")
        classification_id = record.get("classification_id")
        correction_id = record.get("correction_id")
        draft_id = record.get("draft_id")
        classification = classifications.get(classification_id)
        if input_id not in inputs:
            failures.append(
                _issue(
                    "golden_unknown_input",
                    GOLDEN_EXAMPLES_FILE,
                    line_number=row["line_number"],
                    input_id=input_id,
                    record_id=record.get("golden_id"),
                )
            )
        if classification is None:
            failures.append(
                _issue(
                    "golden_unknown_classification",
                    GOLDEN_EXAMPLES_FILE,
                    line_number=row["line_number"],
                    classification_id=classification_id,
                    record_id=record.get("golden_id"),
                )
            )
        elif classification.get("input_id") != input_id:
            failures.append(
                _issue(
                    "golden_input_classification_mismatch",
                    GOLDEN_EXAMPLES_FILE,
                    line_number=row["line_number"],
                    input_id=input_id,
                    classification_id=classification_id,
                    record_id=record.get("golden_id"),
                )
            )
        if correction_id and correction_id not in corrections:
            failures.append(
                _issue(
                    "golden_unknown_correction",
                    GOLDEN_EXAMPLES_FILE,
                    line_number=row["line_number"],
                    correction_id=correction_id,
                    record_id=record.get("golden_id"),
                )
            )
        elif correction_id and corrections[correction_id].get("input_id") != input_id:
            failures.append(
                _issue(
                    "golden_input_correction_mismatch",
                    GOLDEN_EXAMPLES_FILE,
                    line_number=row["line_number"],
                    input_id=input_id,
                    correction_id=correction_id,
                    record_id=record.get("golden_id"),
                )
            )
        if draft_id and draft_id not in drafts:
            failures.append(
                _issue(
                    "golden_unknown_draft",
                    GOLDEN_EXAMPLES_FILE,
                    line_number=row["line_number"],
                    draft_id=draft_id,
                    record_id=record.get("golden_id"),
                )
            )
        elif draft_id and drafts[draft_id].get("input_id") != input_id:
            failures.append(
                _issue(
                    "golden_input_draft_mismatch",
                    GOLDEN_EXAMPLES_FILE,
                    line_number=row["line_number"],
                    input_id=input_id,
                    draft_id=draft_id,
                    record_id=record.get("golden_id"),
                )
            )
    return failures


def _detect_flag_issues(ledger_name: str, row: dict[str, Any]) -> list[dict[str, Any]]:
    record = row["record"]
    failures: list[dict[str, Any]] = []
    if record.get("external_action_allowed") is not False:
        failures.append(
            _issue(
                "external_action_boundary_violation",
                ledger_name,
                line_number=row["line_number"],
                record_id=_record_id(record),
            )
        )
    if record.get("irreversible_action_allowed") is not False:
        failures.append(
            _issue(
                "irreversible_action_boundary_violation",
                ledger_name,
                line_number=row["line_number"],
                record_id=_record_id(record),
            )
        )
    return failures


def _expected_record_type_for_ledger(ledger_name: str) -> str:
    return {
        INPUTS_FILE: INPUT_RECORD_TYPE,
        CLASSIFICATIONS_FILE: CLASSIFICATION_RECORD_TYPE,
        DRAFTS_FILE: DRAFT_RECORD_TYPE,
        OBSERVATIONS_FILE: OBSERVATION_RECORD_TYPE,
        CORRECTIONS_FILE: CORRECTION_RECORD_TYPE,
        GOLDEN_EXAMPLES_FILE: GOLDEN_EXAMPLE_RECORD_TYPE,
        EVENTS_FILE: EVENT_RECORD_TYPE,
    }[ledger_name]


def _record_id(record: dict[str, Any]) -> str | None:
    for key in (
        "input_id",
        "classification_id",
        "draft_id",
        "observation_id",
        "correction_id",
        "golden_id",
        "event_id",
    ):
        value = record.get(key)
        if value:
            return str(value)
    return None


def _issue(issue_type: str, ledger: str, *, line_number: int | None = None, **fields: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "issue_type": issue_type,
        "ledger": ledger,
    }
    if line_number is not None:
        payload["line_number"] = int(line_number)
    payload.update(fields)
    return payload


def _sort_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        issues,
        key=lambda issue: (
            LEDGER_ORDER.get(str(issue.get("ledger") or ""), len(LEDGER_ORDER)),
            int(issue.get("line_number") or -1),
            str(issue.get("issue_type") or ""),
            str(issue.get("record_id") or ""),
            str(issue.get("input_id") or ""),
            str(issue.get("classification_id") or ""),
            str(issue.get("draft_id") or ""),
        ),
    )
