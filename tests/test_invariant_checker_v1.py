from __future__ import annotations

import json
from pathlib import Path

from signal_agent.operator.invariant_checker import (
    InvariantCheckerOptions,
    run_checker,
)


def test_registry_loader_accepts_live_registry() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    report = run_checker(repo_root)
    records = [
        json.loads(line)
        for line in (repo_root / "data" / "state" / "module_artifacts.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    active_count = sum(1 for record in records if record.get("status") == "active")
    deprecated_count = sum(1 for record in records if record.get("status") == "deprecated")

    assert report.ok, report.to_dict()
    assert report.summary["active_modules"] == active_count
    assert report.summary["deprecated_modules"] == deprecated_count
    assert report.summary["module_records"] == len(records)
    assert not any(
        warning.code == "public_interface_export_leak" and warning.module_id == "runtime_audit_evidence"
        for warning in report.warnings
    ), report.to_dict()


def test_registry_loader_rejects_duplicate_module_id(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    module_path = _write_python(repo_root, "app/example/a.py", "VALUE = 1\n")
    _write_registry(
        repo_root,
        [
            _record("dup_mod", "active", [module_path]),
            _record("dup_mod", "active", [module_path]),
        ],
    )

    report = run_checker(repo_root)

    assert not report.ok
    assert _has_failure(report, "duplicate_module_id")


def test_registry_loader_rejects_missing_current_path(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    _write_registry(
        repo_root,
        [
            _record("missing_mod", "active", ["app/missing.py"]),
        ],
    )

    report = run_checker(repo_root)

    assert not report.ok
    assert _has_failure(report, "missing_current_path")


def test_forbidden_reverse_authority_edge_is_detected(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    task_contract_path = _write_python(
        repo_root,
        "app/audit/task_contract.py",
        "from app.audit import runtime_audit\n",
    )
    runtime_audit_path = _write_python(
        repo_root,
        "app/audit/runtime_audit.py",
        "__all__ = ['run_preflight']\nrun_preflight = object()\n",
    )
    _write_registry(
        repo_root,
        [
            _record("task_contract", "active", [task_contract_path]),
            _record("runtime_audit", "active", [runtime_audit_path], public_interface=["run_preflight"]),
        ],
    )

    report = run_checker(repo_root)

    assert not report.ok
    assert _has_failure(report, "forbidden_reverse_authority_edge")


def test_deprecated_module_import_is_detected(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    active_path = _write_python(
        repo_root,
        "app/example/active_mod.py",
        "from app.legacy import old_mod\n",
    )
    deprecated_path = _write_python(
        repo_root,
        "app/legacy/old_mod.py",
        "VALUE = 1\n",
    )
    _write_registry(
        repo_root,
        [
            _record("active_mod", "active", [active_path]),
            _record("old_mod", "deprecated", [deprecated_path]),
        ],
    )

    report = run_checker(repo_root)

    assert not report.ok
    assert _has_failure(report, "deprecated_module_dependency")


def test_jsonl_append_requires_governed_helper(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    source_path = _write_python(
        repo_root,
        "app/example/ledger_mod.py",
        "def write_log(path):\n"
        "    with open(path, 'a', encoding='utf-8') as handle:\n"
        "        handle.write('x\\n')\n",
    )
    _write_registry(
        repo_root,
        [
            _record(
                "ledger_mod",
                "active",
                [source_path],
                state_files_touched=["data/state/ledger.jsonl"],
            ),
        ],
    )

    report = run_checker(repo_root)

    assert not report.ok
    assert _has_failure(report, "ungoverned_jsonl_append")


def test_export_leak_detected_when___all___exceeds_public_interface(tmp_path: Path) -> None:
    repo_root = _make_repo_root(tmp_path)
    source_path = _write_python(
        repo_root,
        "app/example/export_mod.py",
        "__all__ = ['foo', 'bar']\n"
        "def foo():\n"
        "    return 1\n"
        "def bar():\n"
        "    return 2\n",
    )
    _write_registry(
        repo_root,
        [
            _record(
                "export_mod",
                "active",
                [source_path],
                public_interface=["foo"],
            ),
        ],
    )

    report = run_checker(
        repo_root,
        options=InvariantCheckerOptions(strict_export_paths=frozenset({source_path})),
    )

    assert not report.ok
    assert _has_failure(report, "public_interface_export_leak")


def _make_repo_root(tmp_path: Path) -> Path:
    (tmp_path / "data" / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / "app").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_registry(repo_root: Path, records: list[dict]) -> None:
    registry_path = repo_root / "data" / "state" / "module_artifacts.jsonl"
    lines = [json.dumps(record, separators=(",", ":")) for record in records]
    registry_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_python(repo_root: Path, relative_path: str, content: str) -> str:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return relative_path.replace("\\", "/")


def _record(
    module_id: str,
    status: str,
    current_paths: list[str],
    *,
    public_interface: list[str] | None = None,
    state_files_touched: list[str] | None = None,
) -> dict:
    return {
        "schema_version": "module_artifact_v1",
        "module_id": module_id,
        "module_name": module_id,
        "module_type": "test_module",
        "current_paths": current_paths,
        "responsibility": "test",
        "inputs": [],
        "outputs": [],
        "state_files_touched": state_files_touched or [],
        "public_interface": public_interface or [],
        "governance_requirements": [],
        "risk_flags": [],
        "status": status,
        "created_at": "2026-05-01T00:00:00Z",
        "updated_at": "2026-05-01T00:00:00Z",
        "source": "test",
    }


def _has_failure(report, code: str) -> bool:
    return any(failure.code == code for failure in report.failures)
