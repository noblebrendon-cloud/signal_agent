from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from app.reflective_corpus.models import (
    ESSAY_CANDIDATE_RECORD_TYPE,
    FRAGMENT_RECORD_TYPE,
    PRESSURE_RECORD_TYPE,
    THEME_RECORD_TYPE,
    validate_essay_candidate_record,
    validate_fragment_record,
    validate_pressure_record,
    validate_theme_record,
)
from app.reflective_corpus.store import (
    ESSAY_CANDIDATES_FILE,
    FRAGMENTS_FILE,
    PRESSURES_FILE,
    THEMES_FILE,
)
from app.retention.identity import get_repo_root, get_state_root


LEDGER_FILES = (
    FRAGMENTS_FILE,
    THEMES_FILE,
    PRESSURES_FILE,
    ESSAY_CANDIDATES_FILE,
)
LEDGER_ORDER = {name: index for index, name in enumerate(LEDGER_FILES)}
EXPECTED_RECORD_TYPES = {
    FRAGMENTS_FILE: FRAGMENT_RECORD_TYPE,
    THEMES_FILE: THEME_RECORD_TYPE,
    PRESSURES_FILE: PRESSURE_RECORD_TYPE,
    ESSAY_CANDIDATES_FILE: ESSAY_CANDIDATE_RECORD_TYPE,
}
VALIDATORS: dict[str, Callable[[dict[str, Any]], None]] = {
    FRAGMENT_RECORD_TYPE: validate_fragment_record,
    THEME_RECORD_TYPE: validate_theme_record,
    PRESSURE_RECORD_TYPE: validate_pressure_record,
    ESSAY_CANDIDATE_RECORD_TYPE: validate_essay_candidate_record,
}
ID_FIELDS = {
    FRAGMENTS_FILE: "fragment_id",
    THEMES_FILE: "theme_id",
    PRESSURES_FILE: "pressure_id",
    ESSAY_CANDIDATES_FILE: "candidate_id",
}


def reconcile_reflective_corpus_state(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or get_repo_root()
    state_root = get_state_root(root)
    rows_by_ledger: dict[str, list[dict[str, Any]]] = {}
    ledgers: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for ledger_name in LEDGER_FILES:
        rows, load_failures, stats = _load_ledger(state_root, ledger_name)
        rows_by_ledger[ledger_name] = rows
        ledgers.append(stats)
        failures.extend(load_failures)

    failures.extend(_validate_records(rows_by_ledger))
    failures.extend(_detect_duplicate_ids(rows_by_ledger))
    failures.extend(_detect_reference_issues(rows_by_ledger))

    failures = _sort_issues(failures)
    summary = {
        "fragment_count": len(rows_by_ledger.get(FRAGMENTS_FILE, [])),
        "theme_count": len(rows_by_ledger.get(THEMES_FILE, [])),
        "pressure_count": len(rows_by_ledger.get(PRESSURES_FILE, [])),
        "essay_candidate_count": len(rows_by_ledger.get(ESSAY_CANDIDATES_FILE, [])),
        "failure_count": len(failures),
    }
    return {
        "schema_version": "1.0",
        "command": "corpus-reconcile",
        "clean": not failures,
        "summary": summary,
        "failures": failures,
        "warnings": [],
        "ledgers": ledgers,
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
                failures.append(_issue("malformed_jsonl_record", ledger_name, line_number=line_number, error=str(exc)))
                continue
            if not isinstance(record, dict):
                failures.append(_issue("non_dict_jsonl_record", ledger_name, line_number=line_number))
                continue
            rows.append({"ledger": ledger_name, "line_number": line_number, "record": record})
    return rows, failures, {"ledger": ledger_name, "exists": True, "row_count": len(rows), "path": str(path)}


def _validate_records(rows_by_ledger: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for ledger_name, rows in rows_by_ledger.items():
        expected_type = EXPECTED_RECORD_TYPES[ledger_name]
        for row in rows:
            record = row["record"]
            record_type = str(record.get("record_type") or "")
            if record_type != expected_type:
                failures.append(
                    _issue(
                        "record_type_ledger_mismatch",
                        ledger_name,
                        line_number=row["line_number"],
                        expected_record_type=expected_type,
                        observed_record_type=record_type,
                        record_id=_record_id(record),
                    )
                )
                continue

            validator = VALIDATORS.get(record_type)
            if validator is None:
                failures.append(
                    _issue(
                        "unsupported_record_type",
                        ledger_name,
                        line_number=row["line_number"],
                        record_type=record_type,
                        record_id=_record_id(record),
                    )
                )
                continue
            try:
                validator(record)
            except (TypeError, ValueError) as exc:
                failures.append(
                    _issue(
                        _validation_issue_type(str(exc)),
                        ledger_name,
                        line_number=row["line_number"],
                        detail=str(exc),
                        record_id=_record_id(record),
                    )
                )
            failures.extend(_detect_field_issues(ledger_name, row))
    return failures


def _detect_field_issues(ledger_name: str, row: dict[str, Any]) -> list[dict[str, Any]]:
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

    if ledger_name == FRAGMENTS_FILE and not str(record.get("text") or "").strip():
        failures.append(
            _issue(
                "empty_fragment_text",
                ledger_name,
                line_number=row["line_number"],
                record_id=_record_id(record),
            )
        )

    if ledger_name == THEMES_FILE and not str(record.get("name") or "").strip():
        failures.append(
            _issue(
                "empty_theme_name",
                ledger_name,
                line_number=row["line_number"],
                record_id=_record_id(record),
            )
        )

    if ledger_name == ESSAY_CANDIDATES_FILE and not record.get("fragment_ids"):
        failures.append(
            _issue(
                "essay_candidate_without_supporting_fragments",
                ledger_name,
                line_number=row["line_number"],
                record_id=_record_id(record),
            )
        )

    return failures


def _detect_duplicate_ids(rows_by_ledger: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for ledger_name, id_field in ID_FIELDS.items():
        seen: dict[str, int] = {}
        for row in rows_by_ledger.get(ledger_name, []):
            value = str(row["record"].get(id_field) or "").strip()
            if not value:
                continue
            if value in seen:
                failures.append(
                    _issue(
                        "duplicate_id",
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
    fragment_ids = _ids(rows_by_ledger, FRAGMENTS_FILE, "fragment_id")
    theme_ids = _ids(rows_by_ledger, THEMES_FILE, "theme_id")
    pressure_ids = _ids(rows_by_ledger, PRESSURES_FILE, "pressure_id")
    failures: list[dict[str, Any]] = []

    for row in rows_by_ledger.get(PRESSURES_FILE, []):
        record = row["record"]
        for fragment_id in _list_values(record.get("fragment_ids")):
            if fragment_id not in fragment_ids:
                failures.append(
                    _issue(
                        "missing_fragment_reference",
                        PRESSURES_FILE,
                        line_number=row["line_number"],
                        record_id=_record_id(record),
                        fragment_id=fragment_id,
                    )
                )
        for theme_id in _list_values(record.get("related_theme_ids")):
            if theme_id not in theme_ids:
                failures.append(
                    _issue(
                        "missing_theme_reference",
                        PRESSURES_FILE,
                        line_number=row["line_number"],
                        record_id=_record_id(record),
                        theme_id=theme_id,
                    )
                )

    for row in rows_by_ledger.get(ESSAY_CANDIDATES_FILE, []):
        record = row["record"]
        for pressure_id in _list_values(record.get("pressure_ids")):
            if pressure_id not in pressure_ids:
                failures.append(
                    _issue(
                        "missing_pressure_reference",
                        ESSAY_CANDIDATES_FILE,
                        line_number=row["line_number"],
                        record_id=_record_id(record),
                        pressure_id=pressure_id,
                    )
                )
        for fragment_id in _list_values(record.get("fragment_ids")):
            if fragment_id not in fragment_ids:
                failures.append(
                    _issue(
                        "missing_fragment_reference",
                        ESSAY_CANDIDATES_FILE,
                        line_number=row["line_number"],
                        record_id=_record_id(record),
                        fragment_id=fragment_id,
                    )
                )
        for theme_id in _list_values(record.get("theme_ids")):
            if theme_id not in theme_ids:
                failures.append(
                    _issue(
                        "missing_theme_reference",
                        ESSAY_CANDIDATES_FILE,
                        line_number=row["line_number"],
                        record_id=_record_id(record),
                        theme_id=theme_id,
                    )
                )
    return failures


def _ids(rows_by_ledger: dict[str, list[dict[str, Any]]], ledger_name: str, id_field: str) -> set[str]:
    return {str(row["record"].get(id_field)) for row in rows_by_ledger.get(ledger_name, []) if row["record"].get(id_field)}


def _list_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _record_id(record: dict[str, Any]) -> str | None:
    for key in ("fragment_id", "theme_id", "pressure_id", "candidate_id"):
        value = record.get(key)
        if value:
            return str(value)
    return None


def _validation_issue_type(detail: str) -> str:
    if "unsupported_theme_status" in detail or "unsupported_candidate_status" in detail:
        return "invalid_status"
    if "external_action_allowed_not_allowed" in detail:
        return "external_action_boundary_violation"
    if "missing_text" in detail:
        return "empty_fragment_text"
    if "missing_fragment_ids" in detail:
        return "essay_candidate_without_supporting_fragments"
    return "schema_validation_failed"


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
            str(issue.get("fragment_id") or ""),
            str(issue.get("theme_id") or ""),
            str(issue.get("pressure_id") or ""),
        ),
    )
