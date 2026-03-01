from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

REQUIRED_KEYS = {
    "objective",
    "constraints",
    "acceptance",
    "required_artifacts",
    "stop_conditions",
    "run_mode",
}
ALLOWED_RUN_MODES = {"one_shot", "interval", "scheduled"}
ACCEPTANCE_PREFIXES = {"path_exists", "file_contains", "json_key_equals"}


def load_task_contract(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("task contract must be a mapping")
    return data


def validate_task_contract(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    missing = sorted(REQUIRED_KEYS - set(contract.keys()))
    if missing:
        errors.append(f"missing required keys: {', '.join(missing)}")

    objective = contract.get("objective")
    if not isinstance(objective, str) or not objective.strip():
        errors.append("objective must be a non-empty string")

    constraints = contract.get("constraints")
    if not _is_string_list(constraints):
        errors.append("constraints must be a list of strings")

    acceptance = contract.get("acceptance")
    if not _is_string_list(acceptance):
        errors.append("acceptance must be a list of strings")
    elif not all(_is_machine_checkable(item) for item in acceptance):
        errors.append(
            "acceptance entries must use supported checks: "
            "path_exists:, file_contains:, json_key_equals:"
        )

    required_artifacts = contract.get("required_artifacts")
    if not _is_string_list(required_artifacts):
        errors.append("required_artifacts must be a list of strings")

    stop_conditions = contract.get("stop_conditions")
    if not isinstance(stop_conditions, dict):
        errors.append("stop_conditions must be a mapping")
    else:
        phi_threshold = stop_conditions.get("phi_threshold")
        breaker_open = stop_conditions.get("breaker_open")
        max_retries = stop_conditions.get("max_retries")

        if not isinstance(phi_threshold, (int, float)) or not (0.0 <= float(phi_threshold) <= 1.0):
            errors.append("stop_conditions.phi_threshold must be a float in [0, 1]")
        if not isinstance(breaker_open, bool):
            errors.append("stop_conditions.breaker_open must be boolean")
        if not isinstance(max_retries, int) or max_retries < 0:
            errors.append("stop_conditions.max_retries must be an integer >= 0")

    run_mode = contract.get("run_mode")
    if run_mode not in ALLOWED_RUN_MODES:
        errors.append("run_mode must be one of: one_shot, interval, scheduled")

    return errors


def evaluate_contract(
    contract: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    validation_errors = validate_task_contract(contract)
    result: dict[str, Any] = {
        "contract_valid": not validation_errors,
        "validation_errors": validation_errors,
        "required_artifacts": [],
        "acceptance": [],
        "passed": False,
    }

    required_artifacts = contract.get("required_artifacts", [])
    if isinstance(required_artifacts, list):
        for raw_path in required_artifacts:
            resolved = _resolve_path(repo_root, str(raw_path))
            result["required_artifacts"].append(
                {
                    "path": str(raw_path),
                    "resolved_path": str(resolved),
                    "exists": resolved.exists(),
                }
            )

    acceptance = contract.get("acceptance", [])
    if isinstance(acceptance, list):
        for check in acceptance:
            eval_item = _evaluate_acceptance_check(repo_root, str(check))
            result["acceptance"].append(eval_item)

    required_ok = all(item["exists"] for item in result["required_artifacts"])
    acceptance_ok = all(item["passed"] for item in result["acceptance"])
    result["passed"] = result["contract_valid"] and required_ok and acceptance_ok
    return result


def _evaluate_acceptance_check(repo_root: Path, check: str) -> dict[str, Any]:
    if check.startswith("path_exists:"):
        raw_path = check.split(":", 1)[1].strip()
        target = _resolve_path(repo_root, raw_path)
        return {
            "check": check,
            "type": "path_exists",
            "path": raw_path,
            "resolved_path": str(target),
            "passed": target.exists(),
        }

    if check.startswith("file_contains:"):
        body = check.split(":", 1)[1]
        parts = body.split("::", 1)
        if len(parts) != 2:
            return _failed_check(check, "invalid file_contains format")
        raw_path, needle = parts[0].strip(), parts[1]
        target = _resolve_path(repo_root, raw_path)
        if not target.exists() or not target.is_file():
            return _failed_check(check, "target file missing")
        try:
            text = target.read_text(encoding="utf-8")
        except Exception as exc:
            return _failed_check(check, f"read_error:{exc}")
        return {
            "check": check,
            "type": "file_contains",
            "path": raw_path,
            "resolved_path": str(target),
            "needle": needle,
            "passed": needle in text,
        }

    if check.startswith("json_key_equals:"):
        body = check.split(":", 1)[1]
        parts = body.split("::", 2)
        if len(parts) != 3:
            return _failed_check(check, "invalid json_key_equals format")
        raw_path, key_path, expected_raw = parts[0].strip(), parts[1].strip(), parts[2]
        target = _resolve_path(repo_root, raw_path)
        if not target.exists() or not target.is_file():
            return _failed_check(check, "target json missing")
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except Exception as exc:
            return _failed_check(check, f"json_parse_error:{exc}")
        actual = _get_json_key(payload, key_path)
        expected = _parse_expected_value(expected_raw)
        return {
            "check": check,
            "type": "json_key_equals",
            "path": raw_path,
            "resolved_path": str(target),
            "key_path": key_path,
            "expected": expected,
            "actual": actual,
            "passed": actual == expected,
        }

    return _failed_check(check, "unsupported_check")


def _failed_check(check: str, reason: str) -> dict[str, Any]:
    return {
        "check": check,
        "passed": False,
        "reason": reason,
    }


def _get_json_key(payload: Any, dotted_key: str) -> Any:
    current = payload
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _parse_expected_value(raw: str) -> Any:
    text = raw.strip()
    try:
        return json.loads(text)
    except Exception:
        return text


def _resolve_path(repo_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def _is_machine_checkable(check: str) -> bool:
    if not isinstance(check, str):
        return False
    prefix = check.split(":", 1)[0]
    if prefix not in ACCEPTANCE_PREFIXES:
        return False
    if prefix == "path_exists":
        return ":" in check and bool(check.split(":", 1)[1].strip())
    if prefix == "file_contains":
        body = check.split(":", 1)[1]
        return len(body.split("::", 1)) == 2
    if prefix == "json_key_equals":
        body = check.split(":", 1)[1]
        return len(body.split("::", 2)) == 3
    return False


def _is_string_list(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    return all(isinstance(item, str) for item in value)
