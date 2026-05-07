from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

from app.utils.io_contract import append_jsonl_atomic, atomic_write_text
from signal_agent.operator.invariant_checker import run_checker


SCHEMA_VERSION = "daily-witness-v1"
WITNESS_RELATIVE_ROOT = Path("data/state/witness")
EXIT_CODES = {"healthy": 0, "degraded": 1, "failed": 2, "unverified": 3}
STATUS_MEANINGS = {
    "healthy": "no hard failures or known drift warnings",
    "degraded": "review required, not emergency; core authority is readable but drift or soft degradation exists",
    "failed": "hard failure; intervene before trusting downstream daily automation",
    "unverified": "visibility incomplete; rerun or inspect the environment before trusting the result",
}
NEXT_OPERATOR_ACTIONS = {
    "healthy": "review_summary_no_intervention_required",
    "degraded": "review_report_and_plan_remediation_if_repeated",
    "failed": "inspect_failures_before_trusting_downstream_automation",
    "unverified": "rerun_or_inspect_environment_before_trusting_result",
}
CLASSIFICATION_RULES = (
    "hard failures classify the run as failed",
    "unverified stages classify the run as unverified only when no hard failure exists",
    "dirty worktree, registry split, runtime drift, optional evidence gaps, and soft failures classify as degraded",
    "healthy requires no hard failures, no unverified stages, no soft degradation, and no known drift warnings",
)
DEFAULT_TEST_PROFILE = (
    "tests/test_invariant_checker_v1.py",
    "tests/test_operator_write_contract.py",
    "tests/test_operator_write_denial.py",
)
CANONICAL_JSONL_PATHS = (
    "data/state/module_artifacts.jsonl",
    "data/state/transition_gate_events.jsonl",
    "data/state/artifact_registry.jsonl",
    "data/state/event_log.jsonl",
    "data/state/provider_events.jsonl",
    "data/state/release_registry.jsonl",
    "data/state/inference_cache_registry.jsonl",
    "data/state/contacts.jsonl",
    "data/state/events.jsonl",
    "data/state/transitions.jsonl",
    "data/state/content_dispatch.jsonl",
)
AMBIGUOUS_JSONL_PATHS = ("data/artifact_registry.jsonl",)
REQUIRED_AUTHORITY_PATHS = (
    "docs/operator/OPERATOR_INDEX.md",
    "docs/operator/repo_zone_classification.md",
    "docs/operator/daily_witness_node_reconciliation_contract.md",
    "config/state_machine.yaml",
    "config/operator/intents.yaml",
    "config/operator/tools.yaml",
    "config/operator/workflows.yaml",
    "data/state/module_artifacts.jsonl",
)
PROHIBITED_OPERATIONS = (
    "auto-commit",
    "auto-push",
    "auto-merge",
    "autonomous refactor",
    "unrestricted agent execution",
    "automatic repair",
    "production-state mutation",
    "external delivery",
)


@dataclass
class StageResult:
    name: str
    status: str
    hard_failures: list[str] = field(default_factory=list)
    soft_failures: list[str] = field(default_factory=list)
    drift_warnings: list[str] = field(default_factory=list)
    informational: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "hard_failures": list(self.hard_failures),
            "soft_failures": list(self.soft_failures),
            "drift_warnings": list(self.drift_warnings),
            "informational": list(self.informational),
            "data": self.data,
        }


@dataclass(frozen=True)
class WitnessPaths:
    root: Path
    reports: Path
    snapshots: Path
    manifests: Path
    logs: Path
    markers: Path
    locks: Path
    ledger: Path
    lock: Path

    @classmethod
    def build(cls, repo_root: Path) -> "WitnessPaths":
        root = repo_root / WITNESS_RELATIVE_ROOT
        return cls(
            root=root,
            reports=root / "reports",
            snapshots=root / "snapshots",
            manifests=root / "manifests",
            logs=root / "logs",
            markers=root / "markers",
            locks=root / "locks",
            ledger=root / "witness_daily.jsonl",
            lock=root / "locks" / "daily_check.lock",
        )

    def directories(self) -> tuple[Path, ...]:
        return (self.root, self.reports, self.snapshots, self.manifests, self.logs, self.markers, self.locks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m signal_agent.health.daily_check")
    parser.add_argument("--repo-root", default=".", help="Signal Agent repository root")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
        help="Per-command timeout for bounded subprocess checks",
    )
    parser.add_argument(
        "--test",
        action="append",
        dest="tests",
        help="Override targeted pytest path. Repeat for multiple paths.",
    )
    parser.add_argument(
        "--no-tests",
        action="store_true",
        help="Skip pytest only when bootstrapping a broken local environment. Emits unverified.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    report = run_daily_check(
        repo_root=repo_root,
        timeout_seconds=args.timeout_seconds,
        tests=tuple(args.tests) if args.tests else DEFAULT_TEST_PROFILE,
        skip_tests=args.no_tests,
    )
    _print_compact_summary(report)
    return EXIT_CODES[report["status"]]


def run_daily_check(
    *,
    repo_root: Path,
    timeout_seconds: int = 120,
    tests: tuple[str, ...] = DEFAULT_TEST_PROFILE,
    skip_tests: bool = False,
) -> dict[str, Any]:
    started_at = _utc_now()
    run_stamp = _run_stamp(started_at)
    run_id = f"daily-witness-{run_stamp}"
    paths = WitnessPaths.build(repo_root)

    _ensure_witness_layout(paths)
    _write_layout_readme(paths)

    lock_handle = None
    try:
        lock_handle = _acquire_lock(paths.lock)
        stage_results: list[StageResult] = []
        command_logs: list[dict[str, Any]] = []
        write_paths: list[Path] = []

        git_stage = _stage_git_state(repo_root, timeout_seconds)
        stage_results.append(git_stage)

        verification_stage = _stage_verification(repo_root)
        stage_results.append(verification_stage)

        test_stage, test_logs = _stage_targeted_tests(
            repo_root=repo_root,
            tests=tests,
            timeout_seconds=timeout_seconds,
            run_stamp=run_stamp,
            logs_dir=paths.logs,
            skip_tests=skip_tests,
        )
        stage_results.append(test_stage)
        command_logs.extend(test_logs)

        ledger_stage = _stage_ledger_validation(repo_root)
        stage_results.append(ledger_stage)

        runtime_stage = _stage_runtime_health(repo_root)
        stage_results.append(runtime_stage)

        final_status = _classify(stage_results)
        finished_at = _utc_now()

        snapshot_path = paths.snapshots / f"{run_stamp}.json"
        report_path = paths.reports / f"{run_stamp}.md"
        manifest_path = paths.manifests / f"{run_stamp}.manifest.json"

        snapshot = _build_snapshot(
            repo_root=repo_root,
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            status=final_status,
            stages=stage_results,
            command_logs=command_logs,
        )
        planned_writes = [snapshot_path, report_path, manifest_path, paths.ledger]
        snapshot["artifacts"]["snapshot"] = {"path": _relative(snapshot_path, repo_root)}
        snapshot["artifacts"]["report"] = {"path": _relative(report_path, repo_root)}
        snapshot["artifacts"]["manifest"] = {"path": _relative(manifest_path, repo_root)}
        snapshot["artifacts"]["witness_ledger"] = {"path": _relative(paths.ledger, repo_root)}
        snapshot["safe_execution_boundaries"]["witness_owned_writes"] = [
            _relative(path, repo_root) for path in planned_writes
        ]
        _write_witness_text(paths.root, snapshot_path, _stable_json(snapshot))
        write_paths.append(snapshot_path)

        report_md = _render_markdown_report(snapshot)
        _write_witness_text(paths.root, report_path, report_md)
        write_paths.append(report_path)

        manifest = _build_manifest(
            repo_root=repo_root,
            run_id=run_id,
            created_at=_utc_now(),
            artifacts=tuple(write_paths) + tuple(repo_root / item["path"] for item in command_logs),
        )
        _write_witness_text(paths.root, manifest_path, _stable_json(manifest))
        write_paths.append(manifest_path)

        ledger_record = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "started_at": started_at,
            "finished_at": finished_at,
            "status": final_status,
            "git_revision": snapshot["git"].get("revision"),
            "snapshot_path": _relative(snapshot_path, repo_root),
            "snapshot_sha256": _sha256_file(snapshot_path),
            "report_path": _relative(report_path, repo_root),
            "report_sha256": _sha256_file(report_path),
            "manifest_path": _relative(manifest_path, repo_root),
            "manifest_sha256": _sha256_file(manifest_path),
        }
        _append_witness_ledger(paths.root, paths.ledger, ledger_record)
        write_paths.append(paths.ledger)

        return snapshot
    except Exception as exc:
        failure = _failure_snapshot(repo_root, paths, run_id, started_at, exc)
        failure_path = paths.reports / f"{run_stamp}.failure.md"
        try:
            _write_witness_text(paths.root, failure_path, _render_failure_report(failure))
        except Exception:
            pass
        return failure
    finally:
        if lock_handle is not None:
            _release_lock(lock_handle, paths.lock)


def _stage_git_state(repo_root: Path, timeout_seconds: int) -> StageResult:
    result = StageResult(name="git_state", status="healthy")
    commands = {
        "revision": ["git", "rev-parse", "HEAD"],
        "branch": ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        "status_short": ["git", "status", "--short"],
    }
    for key, command in commands.items():
        completed = _run_command(command, repo_root, timeout_seconds)
        result.data[key] = completed
        if completed["status"] == "timeout":
            result.status = "failed"
            result.hard_failures.append(f"git command timed out: {' '.join(command)}")
        elif completed["returncode"] != 0:
            result.status = "failed"
            result.hard_failures.append(f"git command failed: {' '.join(command)}")

    status_text = str(result.data.get("status_short", {}).get("stdout", "")).strip()
    dirty_paths = [line for line in status_text.splitlines() if line.strip()]
    dirty_count = len(dirty_paths)
    result.data["dirty_count"] = dirty_count
    if "status_short" in result.data:
        result.data["status_short"]["stdout"] = "\n".join(dirty_paths[:100])
        result.data["status_short"]["stdout_truncated"] = dirty_count > 100
        result.data["status_short"]["dirty_path_sample_count"] = min(dirty_count, 100)
    if result.status == "healthy" and dirty_count:
        result.status = "degraded"
        result.drift_warnings.append(f"working tree has {dirty_count} changed or untracked paths")
    if result.status == "healthy":
        result.informational.append("git metadata captured")
    return result


def _stage_verification(repo_root: Path) -> StageResult:
    result = StageResult(name="verification", status="healthy")
    missing = [path for path in REQUIRED_AUTHORITY_PATHS if not (repo_root / path).exists()]
    result.data["required_authority_paths"] = {
        "checked": list(REQUIRED_AUTHORITY_PATHS),
        "missing": missing,
    }
    if missing:
        result.status = "failed"
        result.hard_failures.append("missing required authority paths: " + ", ".join(missing))

    try:
        invariant_report = run_checker(repo_root)
        result.data["invariant_checker"] = invariant_report.to_dict()
        if not invariant_report.ok:
            result.status = "failed"
            result.hard_failures.append("invariant checker reported failures")
        elif invariant_report.warnings and result.status == "healthy":
            result.status = "degraded"
            result.drift_warnings.append("invariant checker reported warnings")
    except Exception as exc:
        result.status = "failed"
        result.hard_failures.append(f"invariant checker crashed: {type(exc).__name__}: {exc}")
    return result


def _stage_targeted_tests(
    *,
    repo_root: Path,
    tests: tuple[str, ...],
    timeout_seconds: int,
    run_stamp: str,
    logs_dir: Path,
    skip_tests: bool,
) -> tuple[StageResult, list[dict[str, Any]]]:
    result = StageResult(name="targeted_tests", status="healthy")
    if skip_tests:
        result.status = "unverified"
        result.soft_failures.append("targeted tests skipped by explicit operator flag")
        return result, []

    existing_tests = [test for test in tests if (repo_root / test).exists()]
    missing_tests = [test for test in tests if not (repo_root / test).exists()]
    result.data["requested_tests"] = list(tests)
    result.data["existing_tests"] = existing_tests
    result.data["missing_tests"] = missing_tests
    if missing_tests:
        result.status = "failed"
        result.hard_failures.append("missing targeted test files: " + ", ".join(missing_tests))
        return result, []

    command = [sys.executable, "-B", "-m", "pytest", "-p", "no:cacheprovider", *existing_tests, "-q"]
    completed = _run_command(command, repo_root, timeout_seconds)
    result.data["command"] = command
    result.data["returncode"] = completed["returncode"]
    result.data["duration_seconds"] = completed["duration_seconds"]
    result.data["stdout_line_count"] = len(str(completed["stdout"]).splitlines())
    result.data["stderr_line_count"] = len(str(completed["stderr"]).splitlines())

    log_base = logs_dir / f"{run_stamp}.targeted_tests"
    stdout_path = log_base.with_suffix(".stdout.txt")
    stderr_path = log_base.with_suffix(".stderr.txt")
    _write_witness_text(logs_dir.parent, stdout_path, str(completed["stdout"]))
    _write_witness_text(logs_dir.parent, stderr_path, str(completed["stderr"]))
    logs = [_artifact_entry(stdout_path, repo_root), _artifact_entry(stderr_path, repo_root)]

    if completed["status"] == "timeout":
        result.status = "unverified"
        result.hard_failures.append(f"targeted tests timed out after {timeout_seconds}s")
    elif completed["returncode"] != 0:
        result.status = "failed"
        result.hard_failures.append("targeted tests failed")
    else:
        result.informational.append("targeted tests passed")
    return result, logs


def _stage_ledger_validation(repo_root: Path) -> StageResult:
    result = StageResult(name="ledger_validation", status="healthy")
    checked: list[dict[str, Any]] = []
    for rel_path in CANONICAL_JSONL_PATHS:
        path = repo_root / rel_path
        check = _validate_jsonl(path, repo_root)
        checked.append(check)
        if check["status"] == "missing":
            result.status = "failed"
            result.hard_failures.append(f"missing canonical ledger: {rel_path}")
        elif check["status"] == "malformed":
            result.status = "failed"
            result.hard_failures.append(f"malformed canonical ledger: {rel_path}")

    ambiguous: list[dict[str, Any]] = []
    for rel_path in AMBIGUOUS_JSONL_PATHS:
        path = repo_root / rel_path
        if path.exists():
            check = _validate_jsonl(path, repo_root)
            ambiguous.append(check)
            if check["status"] == "malformed" and result.status == "healthy":
                result.status = "degraded"
                result.drift_warnings.append(f"ambiguous registry path is malformed: {rel_path}")

    if (repo_root / "data/artifact_registry.jsonl").exists() and (
        repo_root / "data/state/artifact_registry.jsonl"
    ).exists():
        if result.status == "healthy":
            result.status = "degraded"
        result.drift_warnings.append(
            "content artifact registry authority is split between data/artifact_registry.jsonl and data/state/artifact_registry.jsonl"
        )

    result.data["canonical_ledgers"] = checked
    result.data["ambiguous_ledgers"] = ambiguous
    return result


def _stage_runtime_health(repo_root: Path) -> StageResult:
    result = StageResult(name="runtime_health", status="healthy")
    try:
        previous_root = os.environ.get("SIGNAL_AGENT_ROOT")
        os.environ["SIGNAL_AGENT_ROOT"] = str(repo_root)
        try:
            from shared.health import system_health_report

            health = system_health_report()
        finally:
            if previous_root is None:
                os.environ.pop("SIGNAL_AGENT_ROOT", None)
            else:
                os.environ["SIGNAL_AGENT_ROOT"] = previous_root
        result.data["system_health"] = _compact_runtime_health(health)
        summary = health.get("summary", {})
        if summary.get("reconciliation_issue_count", 0):
            result.status = "degraded"
            result.drift_warnings.append("runtime health reports reconciliation issues")
        if summary.get("recent_coherence_failure_count", 0):
            result.status = "degraded"
            result.drift_warnings.append("runtime health reports recent coherence failures")
        if summary.get("blocked_or_failed_transition_count", 0):
            result.status = "degraded"
            result.drift_warnings.append("runtime health reports blocked or failed transitions")
        if result.status == "healthy":
            result.informational.append("runtime health inspected")
    except Exception as exc:
        result.status = "unverified"
        result.hard_failures.append(f"runtime health unavailable: {type(exc).__name__}: {exc}")
    return result


def _compact_runtime_health(health: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": health.get("summary", {}),
        "reconciliation_issue_sample": list(health.get("reconciliation", {}).get("issues", []))[:10],
        "recent_coherence_failure_sample": list(health.get("recent_coherence_failures", []))[:10],
        "blocked_or_failed_transition_sample": list(health.get("blocked_or_failed_transitions", []))[:10],
        "unprocessed_event_sample": list(health.get("unprocessed_events", []))[:10],
    }


def _validate_jsonl(path: Path, repo_root: Path) -> dict[str, Any]:
    rel_path = _relative(path, repo_root)
    if not path.exists():
        return {"path": rel_path, "status": "missing", "line_count": 0, "errors": []}

    errors: list[dict[str, Any]] = []
    line_count = 0
    try:
        for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw_line.strip():
                continue
            line_count += 1
            try:
                json.loads(raw_line)
            except json.JSONDecodeError as exc:
                errors.append({"line": lineno, "error": str(exc)})
    except UnicodeDecodeError as exc:
        errors.append({"line": None, "error": f"unicode_decode_error: {exc}"})
    except OSError as exc:
        errors.append({"line": None, "error": f"os_error: {exc}"})
    return {
        "path": rel_path,
        "status": "malformed" if errors else "ok",
        "line_count": line_count,
        "errors": errors[:10],
        "error_count": len(errors),
        "sha256": _sha256_file(path) if not errors else None,
    }


def _build_snapshot(
    *,
    repo_root: Path,
    run_id: str,
    started_at: str,
    finished_at: str,
    status: str,
    stages: list[StageResult],
    command_logs: list[dict[str, Any]],
) -> dict[str, Any]:
    stage_payload = [stage.to_dict() for stage in stages]
    git_stage = next((stage for stage in stages if stage.name == "git_state"), None)
    git_data = git_stage.data if git_stage else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": finished_at,
        "started_at": started_at,
        "finished_at": finished_at,
        "repo_root": str(repo_root),
        "status": status,
        "status_meaning": STATUS_MEANINGS[status],
        "next_operator_action": NEXT_OPERATOR_ACTIONS[status],
        "classification_rules": list(CLASSIFICATION_RULES),
        "git": {
            "revision": _stdout_line(git_data.get("revision", {})),
            "branch": _stdout_line(git_data.get("branch", {})),
            "dirty_count": git_data.get("dirty_count"),
            "status": git_stage.status if git_stage else "unverified",
        },
        "stages": stage_payload,
        "summary": _summary_from_stages(stages),
        "findings": _findings_from_stages(stages),
        "artifacts": {
            "command_logs": command_logs,
        },
        "safe_execution_boundaries": {
            "read_only_operations": [
                "git metadata inspection",
                "authority file existence checks",
                "invariant checker execution",
                "bounded pytest execution",
                "canonical JSONL parse validation",
                "runtime health inspection",
            ],
            "witness_owned_root": WITNESS_RELATIVE_ROOT.as_posix(),
            "witness_owned_writes": [],
            "prohibited_operations": list(PROHIBITED_OPERATIONS),
            "network_actions": [],
            "production_state_mutations": [],
        },
    }


def _summary_from_stages(stages: list[StageResult]) -> dict[str, Any]:
    status_counts = {status: 0 for status in EXIT_CODES}
    for stage in stages:
        status_counts[stage.status] = status_counts.get(stage.status, 0) + 1
    return {
        "hard_failure_count": sum(len(stage.hard_failures) for stage in stages),
        "soft_failure_count": sum(len(stage.soft_failures) for stage in stages),
        "soft_degradation_count": sum(len(stage.soft_failures) for stage in stages),
        "drift_warning_count": sum(len(stage.drift_warnings) for stage in stages),
        "informational_count": sum(len(stage.informational) for stage in stages),
        "failed_stage_count": status_counts.get("failed", 0),
        "degraded_stage_count": status_counts.get("degraded", 0),
        "unverified_stage_count": status_counts.get("unverified", 0),
        "status_counts": status_counts,
        "stage_statuses": {stage.name: stage.status for stage in stages},
    }


def _findings_from_stages(stages: list[StageResult]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for stage in stages:
        for message in stage.hard_failures:
            findings.append({"stage": stage.name, "class": "hard_failure", "message": message})
        for message in stage.soft_failures:
            findings.append({"stage": stage.name, "class": "soft_degradation", "message": message})
        for message in stage.drift_warnings:
            findings.append({"stage": stage.name, "class": "drift_warning", "message": message})
    return findings


def _classify(stages: list[StageResult]) -> str:
    if any(stage.status == "failed" or stage.hard_failures for stage in stages):
        return "failed"
    if any(stage.status == "unverified" for stage in stages):
        return "unverified"
    if any(stage.status == "degraded" or stage.soft_failures or stage.drift_warnings for stage in stages):
        return "degraded"
    return "healthy"


def _build_manifest(*, repo_root: Path, run_id: str, created_at: str, artifacts: tuple[Path, ...]) -> dict[str, Any]:
    entries = []
    for artifact in artifacts:
        if not artifact.exists():
            continue
        entries.append(_artifact_entry(artifact, repo_root))
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": created_at,
        "artifact_count": len(entries),
        "artifacts": entries,
    }


def _render_markdown_report(snapshot: dict[str, Any]) -> str:
    summary = snapshot["summary"]
    git = snapshot["git"]
    lines = [
        "# Daily Witness Report",
        "",
        f"Run ID: `{snapshot['run_id']}`",
        f"Generated: `{snapshot['generated_at']}`",
        f"Status: `{snapshot['status']}`",
        f"Meaning: {snapshot['status_meaning']}",
        f"Next operator action: `{snapshot['next_operator_action']}`",
        "",
        "## Compact Summary",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| git_revision | `{git.get('revision')}` |",
        f"| git_branch | `{git.get('branch')}` |",
        f"| git_dirty_count | `{git.get('dirty_count')}` |",
        f"| hard_failures | `{summary['hard_failure_count']}` |",
        f"| soft_degradations | `{summary['soft_degradation_count']}` |",
        f"| drift_warnings | `{summary['drift_warning_count']}` |",
        f"| unverified_stages | `{summary['unverified_stage_count']}` |",
        f"| degraded_stages | `{summary['degraded_stage_count']}` |",
        f"| failed_stages | `{summary['failed_stage_count']}` |",
        "",
        "## Classification Rules",
        "",
    ]
    for rule in snapshot["classification_rules"]:
        lines.append(f"- {rule}")
    lines.extend(
        [
        "",
        "## Stage Status",
        "",
        "| Stage | Status | Hard failures | Soft failures | Drift warnings |",
        "|---|---|---:|---:|---:|",
        ]
    )
    for stage in snapshot["stages"]:
        lines.append(
            f"| {stage['name']} | `{stage['status']}` | {len(stage['hard_failures'])} | {len(stage['soft_failures'])} | {len(stage['drift_warnings'])} |"
        )
    lines.extend(["", "## Findings", ""])
    for stage in snapshot["stages"]:
        findings = stage["hard_failures"] + stage["soft_failures"] + stage["drift_warnings"]
        if not findings:
            continue
        lines.append(f"### {stage['name']}")
        for finding in findings:
            lines.append(f"- {finding}")
        lines.append("")
    lines.extend(
        [
            "## Safe Execution Boundaries",
            "",
            "- Read-only operations only inspect repo state, ledgers, configs, tests, and runtime health.",
            f"- Witness-owned root: `{snapshot['safe_execution_boundaries']['witness_owned_root']}`",
            "- Network actions: none.",
            "- Production-state mutations: none.",
            "- Prohibited operations remain prohibited: auto-commit, auto-push, auto-merge, autonomous repair, unrestricted agents, and external delivery.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_failure_report(snapshot: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Daily Witness Failure Report",
            "",
            f"Run ID: `{snapshot['run_id']}`",
            f"Generated: `{snapshot['generated_at']}`",
            "Status: `failed`",
            f"Meaning: {snapshot['status_meaning']}",
            f"Next operator action: `{snapshot['next_operator_action']}`",
            "",
            snapshot["failure"],
            "",
        ]
    )


def _failure_snapshot(repo_root: Path, paths: WitnessPaths, run_id: str, started_at: str, exc: Exception) -> dict[str, Any]:
    generated_at = _utc_now()
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": generated_at,
        "started_at": started_at,
        "finished_at": generated_at,
        "repo_root": str(repo_root),
        "status": "failed",
        "status_meaning": STATUS_MEANINGS["failed"],
        "next_operator_action": NEXT_OPERATOR_ACTIONS["failed"],
        "classification_rules": list(CLASSIFICATION_RULES),
        "failure": f"{type(exc).__name__}: {exc}",
        "summary": {
            "hard_failure_count": 1,
            "soft_failure_count": 0,
            "soft_degradation_count": 0,
            "drift_warning_count": 0,
            "informational_count": 0,
            "failed_stage_count": 1,
            "degraded_stage_count": 0,
            "unverified_stage_count": 0,
        },
        "safe_execution_boundaries": {
            "witness_owned_root": _relative(paths.root, repo_root),
            "network_actions": [],
            "production_state_mutations": [],
            "prohibited_operations": list(PROHIBITED_OPERATIONS),
        },
    }


def _print_compact_summary(report: dict[str, Any]) -> None:
    artifacts = report.get("artifacts", {})
    summary = report.get("summary", {})
    print(f"final_status={report.get('status')}")
    print(f"daily_witness_status={report.get('status')}")
    print(f"status_meaning={report.get('status_meaning')}")
    print(f"next_operator_action={report.get('next_operator_action')}")
    print(f"run_id={report.get('run_id')}")
    print(f"git_revision={report.get('git', {}).get('revision')}")
    print(f"git_dirty_count={report.get('git', {}).get('dirty_count')}")
    print(f"hard_failures={summary.get('hard_failure_count')}")
    print(f"soft_degradations={summary.get('soft_degradation_count')}")
    print(f"drift_warnings={summary.get('drift_warning_count')}")
    print(f"unverified_stages={summary.get('unverified_stage_count')}")
    print(f"degraded_stages={summary.get('degraded_stage_count')}")
    print(f"failed_stages={summary.get('failed_stage_count')}")
    if "snapshot" in artifacts:
        print(f"snapshot={artifacts['snapshot']['path']}")
    if "report" in artifacts:
        print(f"report={artifacts['report']['path']}")
    if "manifest" in artifacts:
        print(f"manifest={artifacts['manifest']['path']}")


def _ensure_witness_layout(paths: WitnessPaths) -> None:
    for directory in paths.directories():
        _assert_within(paths.root, directory)
        directory.mkdir(parents=True, exist_ok=True)


def _write_layout_readme(paths: WitnessPaths) -> None:
    readme_path = paths.root / "README.md"
    if readme_path.exists():
        return
    text = """# Daily Witness Node Artifacts

This directory is owned by `python -m signal_agent.health.daily_check`.

Layout:
- `reports/` stores timestamped operator-readable Markdown reports.
- `snapshots/` stores timestamped machine-readable JSON snapshots.
- `manifests/` stores checksums for replay and audit continuity.
- `logs/` stores bounded command output captured by witness checks.
- `markers/` is reserved for future witness-owned state markers.
- `locks/` stores local execution locks.
- `witness_daily.jsonl` is the append-only witness continuity ledger.

Ownership boundary:
- The daily witness runtime may write here.
- The daily witness runtime must not mutate production ledgers, source code, config, or docs outside this directory.
- Reports and snapshots are evidence, not transition approval.
- Operators should run with Python bytecode writes disabled, for example `python -B -m signal_agent.health.daily_check`.

Status meanings:
- `healthy`: no hard failures or known drift warnings.
- `degraded`: review required, not emergency.
- `failed`: hard failure; inspect before trusting downstream automation.
- `unverified`: visibility incomplete; rerun or inspect environment.
"""
    _write_witness_text(paths.root, readme_path, text)


def _write_witness_text(witness_root: Path, path: Path, text: str) -> None:
    _assert_within(witness_root, path)
    atomic_write_text(path, text)


def _append_witness_ledger(witness_root: Path, path: Path, record: dict[str, Any]) -> None:
    _assert_within(witness_root, path)
    append_jsonl_atomic(path, record)


def _assert_within(root: Path, path: Path) -> None:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"witness_write_outside_owned_root:{resolved_path}") from exc


def _acquire_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        handle = os.open(lock_path, flags)
    except FileExistsError as exc:
        raise RuntimeError(f"daily witness lock already exists: {lock_path}") from exc
    os.write(handle, _utc_now().encode("utf-8"))
    os.fsync(handle)
    return handle


def _release_lock(handle, lock_path: Path) -> None:
    try:
        os.close(handle)
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _run_command(command: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            env=_safe_subprocess_env(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
        status = "completed"
        returncode = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        status = "timeout"
        returncode = 124
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
    except OSError as exc:
        status = "os_error"
        returncode = 127
        stdout = ""
        stderr = str(exc)
    duration = round(time.monotonic() - started, 3)
    return {
        "command": command,
        "status": status,
        "returncode": returncode,
        "duration_seconds": duration,
        "stdout": stdout,
        "stderr": stderr,
    }


def _safe_subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = env.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    return env


def _artifact_entry(path: Path, repo_root: Path) -> dict[str, Any]:
    return {
        "path": _relative(path, repo_root),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def _stable_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run_stamp(timestamp: str) -> str:
    return timestamp.replace("-", "").replace(":", "").replace("Z", "Z")


def _stdout_line(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    stdout = str(payload.get("stdout", "")).strip()
    return stdout.splitlines()[0] if stdout else None


if __name__ == "__main__":
    raise SystemExit(main())
