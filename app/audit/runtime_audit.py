from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Tuple, Dict

import tomllib

from app.audit.task_contract import evaluate_contract, load_task_contract, validate_task_contract

EXIT_CODE_RE = re.compile(r"Exit code:\s*(-?\d+)")


def run_preflight(
    *,
    repo_root: Path,
    contract_path: Path | None = None,
    output_path: Path | None = None,
    codex_home: Path | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    contract_path = (contract_path or (repo_root / "task_contract.yaml")).resolve()
    output_path = (output_path or (repo_root / "data" / "state" / "preflight.json")).resolve()
    codex_home = (codex_home or (Path.home() / ".codex")).resolve()

    runtime = _collect_runtime_metadata(codex_home)

    python_cmd = [sys.executable, "--version"]
    pytest_cmd = [sys.executable, "-m", "pytest", "--version"]
    git_cmd = ["git", "--version"]

    python_check = _run_cmd(python_cmd, cwd=repo_root)
    pytest_check = _run_cmd(pytest_cmd, cwd=repo_root)
    git_check = _run_cmd(git_cmd, cwd=repo_root)

    path_checks = {
        "repo_root_exists": repo_root.exists(),
        "app_dir_exists": (repo_root / "app").exists(),
        "tests_dir_exists": (repo_root / "tests").exists(),
        "contract_exists": contract_path.exists(),
    }
    venv_path = repo_root / ".venv"
    venv_python = _venv_python_path(venv_path)
    venv_check = {
        "ok": venv_path.exists() and venv_python.exists(),
        "venv_path": str(venv_path),
        "venv_python": str(venv_python),
    }

    contract_valid = False
    contract_errors: list[str] = []
    if contract_path.exists():
        try:
            contract = load_task_contract(contract_path)
            contract_errors = validate_task_contract(contract)
            contract_valid = not contract_errors
        except Exception as exc:
            contract_errors = [f"contract_load_error:{exc}"]

    payload = {
        "generated_at_utc": _utc_now(),
        "repo_root": str(repo_root),
        "codex_home": str(codex_home),
        "runtime": runtime,
        "versions": {
            "python": _extract_first_line(python_check.get("stdout", "")) or _extract_first_line(python_check.get("stderr", "")),
            "pytest": _extract_first_line(pytest_check.get("stdout", "")) or _extract_first_line(pytest_check.get("stderr", "")),
            "git": _extract_first_line(git_check.get("stdout", "")) or _extract_first_line(git_check.get("stderr", "")),
        },
        "checks": {
            "python": python_check,
            "pytest": pytest_check,
            "git": git_check,
            "venv": venv_check,
            "paths": path_checks,
        },
        "contract": {
            "path": str(contract_path),
            "valid": contract_valid,
            "errors": contract_errors,
        },
    }

    _write_json(output_path, payload)
    return payload


def run_postflight(
    *,
    repo_root: Path,
    contract_path: Path | None = None,
    preflight_path: Path | None = None,
    postflight_path: Path | None = None,
    contract_eval_path: Path | None = None,
    codex_home: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    repo_root = repo_root.resolve()
    contract_path = (contract_path or (repo_root / "task_contract.yaml")).resolve()
    preflight_path = (preflight_path or (repo_root / "data" / "state" / "preflight.json")).resolve()
    postflight_path = (postflight_path or (repo_root / "data" / "state" / "postflight.json")).resolve()
    contract_eval_path = (contract_eval_path or (repo_root / "data" / "state" / "contract_eval.json")).resolve()
    codex_home = (codex_home or (Path.home() / ".codex")).resolve()

    latest_rollout = _find_latest_rollout(codex_home)
    metrics = _compute_rollout_metrics(latest_rollout)

    runtime = _collect_runtime_metadata(codex_home)
    baseline_preflight = _load_json(preflight_path)
    baseline_runtime = baseline_preflight.get("runtime", {}) if isinstance(baseline_preflight, dict) else {}
    drift = _compute_drift_markers(baseline_runtime, runtime)

    codex_log_counts = _count_log_levels(codex_home / "log" / "codex-tui.log")
    sandbox_log_counts = _count_log_levels(codex_home / ".sandbox" / "sandbox.log")

    postflight = {
        "generated_at_utc": _utc_now(),
        "repo_root": str(repo_root),
        "codex_home": str(codex_home),
        "latest_rollout": str(latest_rollout) if latest_rollout else None,
        "metrics": metrics,
        "drift_markers": drift,
        "log_counts": {
            "codex_tui": codex_log_counts,
            "sandbox": sandbox_log_counts,
        },
    }
    _write_json(postflight_path, postflight)

    contract_eval = _evaluate_contract_file(contract_path, repo_root)
    contract_eval["generated_at_utc"] = _utc_now()
    contract_eval["contract_path"] = str(contract_path)
    _write_json(contract_eval_path, contract_eval)

    return postflight, contract_eval


def _evaluate_contract_file(contract_path: Path, repo_root: Path) -> dict[str, Any]:
    if not contract_path.exists():
        return {
            "contract_valid": False,
            "validation_errors": ["contract_not_found"],
            "required_artifacts": [],
            "acceptance": [],
            "passed": False,
        }

    try:
        contract = load_task_contract(contract_path)
    except Exception as exc:
        return {
            "contract_valid": False,
            "validation_errors": [f"contract_load_error:{exc}"],
            "required_artifacts": [],
            "acceptance": [],
            "passed": False,
        }

    return evaluate_contract(contract, repo_root)


def _compute_rollout_metrics(latest_rollout: Path | None) -> dict[str, Any]:
    outputs: list[str] = []
    parsed_lines = 0
    parse_errors = 0
    if latest_rollout and latest_rollout.exists():
        for line in latest_rollout.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            parsed_lines += 1
            try:
                payload = json.loads(line)
            except Exception:
                parse_errors += 1
                continue
            if payload.get("type") != "response_item":
                continue
            item = payload.get("payload", {})
            if item.get("type") == "function_call_output":
                output_text = item.get("output")
                if isinstance(output_text, str):
                    outputs.append(output_text)

    with_exit_code = 0
    success_count = 0
    nonzero_count = 0
    exit_code_histogram: dict[str, int] = {}
    taxonomy_counts: dict[str, int] = {}
    for output in outputs:
        code = _extract_exit_code(output)
        if code is None:
            continue
        with_exit_code += 1
        exit_key = str(code)
        exit_code_histogram[exit_key] = exit_code_histogram.get(exit_key, 0) + 1
        if code == 0:
            success_count += 1
        else:
            nonzero_count += 1
            category = _categorize_failure(code, output)
            taxonomy_counts[category] = taxonomy_counts.get(category, 0) + 1

    rate = (float(nonzero_count) / float(with_exit_code)) if with_exit_code else 0.0
    return {
        "rollout_lines_seen": parsed_lines,
        "rollout_parse_errors": parse_errors,
        "function_call_outputs": len(outputs),
        "outputs_with_exit_code": with_exit_code,
        "exit_code_success_count": success_count,
        "exit_code_nonzero_count": nonzero_count,
        "exit_code_nonzero_rate": rate,
        "exit_code_histogram": dict(sorted(exit_code_histogram.items(), key=lambda item: item[0])),
        "failure_taxonomy_counts": dict(sorted(taxonomy_counts.items(), key=lambda item: item[0])),
    }


def _categorize_failure(code: int, output: str) -> str:
    text = output.lower()
    if code == 124 or "timed out" in text:
        return "timeout"
    if "no module named" in text:
        return "missing_module"
    if "not recognized as the name of a cmdlet" in text or "commandnotfoundexception" in text:
        return "command_not_found"
    if "parsererror" in text or "missing ')' in method call" in text or "missing the terminator" in text:
        return "parser_error"
    if "could not read from remote repository" in text or "acquirecredentialshandle failed" in text:
        return "git_remote_auth"
    if "permissiondenied" in text or "unauthorizedaccessexception" in text or "access is denied" in text:
        return "permission"
    if "fatal: unable to access" in text:
        return "git_transport"
    body = _extract_output_body(output)
    if not body:
        return "empty_nonzero_output"
    return "other_nonzero"


def _extract_exit_code(output: str) -> int | None:
    match = EXIT_CODE_RE.search(output)
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _extract_output_body(output: str) -> str:
    lines = output.splitlines()
    for idx, line in enumerate(lines):
        if line.strip() == "Output:":
            for trailing in lines[idx + 1 :]:
                if trailing.strip():
                    return trailing.strip()
    return ""


def _compute_drift_markers(baseline_runtime: dict[str, Any], current_runtime: dict[str, Any]) -> dict[str, Any]:
    baseline_model = baseline_runtime.get("model_id")
    baseline_config_hash = baseline_runtime.get("config_hash")
    baseline_rules_hash = baseline_runtime.get("rules_hash")
    baseline_cli_version = baseline_runtime.get("cli_version")

    current_model = current_runtime.get("model_id")
    current_config_hash = current_runtime.get("config_hash")
    current_rules_hash = current_runtime.get("rules_hash")
    current_cli_version = current_runtime.get("cli_version")

    return {
        "baseline": {
            "model_id": baseline_model,
            "config_hash": baseline_config_hash,
            "rules_hash": baseline_rules_hash,
            "cli_version": baseline_cli_version,
        },
        "current": {
            "model_id": current_model,
            "config_hash": current_config_hash,
            "rules_hash": current_rules_hash,
            "cli_version": current_cli_version,
        },
        "changed": {
            "model_id": _changed(baseline_model, current_model),
            "config_hash": _changed(baseline_config_hash, current_config_hash),
            "rules_hash": _changed(baseline_rules_hash, current_rules_hash),
            "cli_version": _changed(baseline_cli_version, current_cli_version),
        },
    }


def _collect_runtime_metadata(codex_home: Path) -> dict[str, Any]:
    config_path = codex_home / "config.toml"
    version_path = codex_home / "version.json"
    rules_path = codex_home / "rules" / "default.rules"

    model_id = None
    if config_path.exists():
        try:
            config_obj = tomllib.loads(config_path.read_text(encoding="utf-8"))
            model_id = config_obj.get("model")
        except Exception:
            model_id = None

    cli_version = None
    if version_path.exists():
        try:
            version_obj = json.loads(version_path.read_text(encoding="utf-8"))
            cli_version = version_obj.get("latest_version")
        except Exception:
            cli_version = None

    return {
        "model_id": model_id,
        "cli_version": cli_version,
        "config_path": str(config_path),
        "version_path": str(version_path),
        "rules_path": str(rules_path),
        "config_hash": _sha256_file(config_path),
        "rules_hash": _sha256_file(rules_path),
    }


def _find_latest_rollout(codex_home: Path) -> Path | None:
    sessions_root = codex_home / "sessions"
    if not sessions_root.exists():
        return None
    latest: Path | None = None
    latest_mtime = -1.0
    for file_path in sessions_root.rglob("*.jsonl"):
        try:
            if file_path.stat().st_size <= 0:
                continue
            mtime = file_path.stat().st_mtime
        except Exception:
            continue
        if mtime > latest_mtime:
            latest = file_path
            latest_mtime = mtime
    return latest


def _run_cmd(cmd: list[str], *, cwd: Path) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "command": cmd,
        }
    except Exception as exc:
        return {
            "ok": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(exc),
            "command": cmd,
        }


def _count_log_levels(path: Path) -> dict[str, int]:
    if not path.exists():
        return {"warn": 0, "error": 0}
    warn_count = 0
    error_count = 0
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                if " WARN " in line:
                    warn_count += 1
                if " ERROR " in line:
                    error_count += 1
    except Exception:
        return {"warn": 0, "error": 0}
    return {"warn": warn_count, "error": error_count}


def _sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(data, dict):
        return data
    return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _extract_first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _changed(old: Any, new: Any) -> bool:
    if old is None:
        return False
    return old != new


def _venv_python_path(venv_path: Path) -> Path:
    if sys.platform.startswith("win"):
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="runtime_audit")
    sub = parser.add_subparsers(dest="command", required=True)

    pre = sub.add_parser("preflight")
    pre.add_argument("--repo-root", default=".")
    pre.add_argument("--contract", default="task_contract.yaml")
    pre.add_argument("--output", default="data/state/preflight.json")
    pre.add_argument("--codex-home", default=str(Path.home() / ".codex"))

    post = sub.add_parser("postflight")
    post.add_argument("--repo-root", default=".")
    post.add_argument("--contract", default="task_contract.yaml")
    post.add_argument("--preflight", default="data/state/preflight.json")
    post.add_argument("--postflight", default="data/state/postflight.json")
    post.add_argument("--contract-eval", default="data/state/contract_eval.json")
    post.add_argument("--codex-home", default=str(Path.home() / ".codex"))

    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    if args.command == "preflight":
        run_preflight(
            repo_root=repo_root,
            contract_path=Path(args.contract),
            output_path=Path(args.output),
            codex_home=Path(args.codex_home),
        )
        return 0

    run_postflight(
        repo_root=repo_root,
        contract_path=Path(args.contract),
        preflight_path=Path(args.preflight),
        postflight_path=Path(args.postflight),
        contract_eval_path=Path(args.contract_eval),
        codex_home=Path(args.codex_home),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

def verify_contract(contract: dict, preflight: dict, postflight: dict) -> Tuple[bool, Dict[str, Any]]:
    # Minimal deterministic verifier. Tighten later against task_contract.yaml.
    ok = bool(postflight.get("cycle_ok")) and not postflight.get("cycle_stats", {}).get("diagnostics", {}).get("errors")
    return ok, {"minimal_verify": True, "cycle_ok": bool(postflight.get("cycle_ok"))}
