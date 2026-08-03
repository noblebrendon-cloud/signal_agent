from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


_DEFAULT_REGISTRY_PATH = Path("data/state/module_artifacts.jsonl")
_ACTIVE_STATUS = "active"
_DEPRECATED_STATUS = "deprecated"
_STRICT_EXPORT_PATHS = frozenset(
    {
        "app/audit/runtime_audit.py",
        "app/audit/runtime_audit_reports.py",
        "app/audit/task_contract.py",
        "app/hq/governance/__init__.py",
    }
)
_FORBIDDEN_FILE_EDGES = frozenset(
    {
        ("app/audit/task_contract.py", "app/audit/runtime_audit.py"),
        ("app/audit/runtime_audit_evidence.py", "app/audit/runtime_audit_reports.py"),
    }
)


@dataclass(frozen=True)
class ModuleArtifact:
    module_id: str
    status: str
    current_paths: tuple[str, ...]
    public_interface: tuple[str, ...]
    state_files_touched: tuple[str, ...]


@dataclass(frozen=True)
class InvariantIssue:
    code: str
    module_id: str | None
    path: str | None
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "module_id": self.module_id,
            "path": self.path,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class InvariantCheckerOptions:
    strict_export_paths: frozenset[str] = _STRICT_EXPORT_PATHS
    forbidden_file_edges: frozenset[tuple[str, str]] = _FORBIDDEN_FILE_EDGES


@dataclass
class InvariantReport:
    failures: list[InvariantIssue] = field(default_factory=list)
    warnings: list[InvariantIssue] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "failures": [failure.to_dict() for failure in self.failures],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "summary": dict(self.summary),
        }


def run_checker(
    repo_root: Path,
    *,
    registry_path: Path | None = None,
    options: InvariantCheckerOptions | None = None,
) -> InvariantReport:
    repo_root = Path(repo_root).resolve()
    options = options or InvariantCheckerOptions()
    registry_path = (registry_path or (repo_root / _DEFAULT_REGISTRY_PATH)).resolve()

    failures: list[InvariantIssue] = []
    warnings: list[InvariantIssue] = []

    artifacts = _load_registry(registry_path, repo_root, failures)
    active_artifacts = [artifact for artifact in artifacts if artifact.status == _ACTIVE_STATUS]
    deprecated_artifacts = [artifact for artifact in artifacts if artifact.status == _DEPRECATED_STATUS]

    file_owners = _build_file_owner_map(artifacts)
    ast_cache = _build_ast_cache(repo_root, active_artifacts)

    _check_active_current_paths_exist(repo_root, active_artifacts, failures)
    _check_deprecated_imports(repo_root, active_artifacts, file_owners, ast_cache, failures)
    _check_forbidden_edges(repo_root, active_artifacts, ast_cache, options, failures)
    _check_jsonl_append_governance(repo_root, active_artifacts, ast_cache, failures)
    _check_export_alignment(repo_root, active_artifacts, ast_cache, options, failures, warnings)

    summary = {
        "registry_path": _normalize_path(registry_path, repo_root),
        "module_records": len(artifacts),
        "active_modules": len(active_artifacts),
        "deprecated_modules": len(deprecated_artifacts),
        "files_scanned": len(ast_cache),
        "failure_count": len(failures),
        "warning_count": len(warnings),
    }
    return InvariantReport(failures=failures, warnings=warnings, summary=summary)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="invariant_checker")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--registry", default=str(_DEFAULT_REGISTRY_PATH))
    args = parser.parse_args(argv)

    report = run_checker(
        Path(args.repo_root),
        registry_path=Path(args.registry),
    )
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.ok else 1


def _load_registry(registry_path: Path, repo_root: Path, failures: list[InvariantIssue]) -> list[ModuleArtifact]:
    artifacts: list[ModuleArtifact] = []
    seen_module_ids: set[str] = set()

    if not registry_path.exists():
        failures.append(
            InvariantIssue(
                code="registry_parse_error",
                module_id=None,
                path=_normalize_path(registry_path, repo_root),
                detail="registry file does not exist",
            )
        )
        return artifacts

    for lineno, raw_line in enumerate(registry_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            failures.append(
                InvariantIssue(
                    code="registry_parse_error",
                    module_id=None,
                    path=f"{_normalize_path(registry_path, repo_root)}:{lineno}",
                    detail=str(exc),
                )
            )
            continue

        module_id = str(payload.get("module_id") or "")
        if module_id in seen_module_ids:
            failures.append(
                InvariantIssue(
                    code="duplicate_module_id",
                    module_id=module_id or None,
                    path=f"{_normalize_path(registry_path, repo_root)}:{lineno}",
                    detail=f"duplicate module_id '{module_id}'",
                )
            )
            continue
        seen_module_ids.add(module_id)

        artifacts.append(
            ModuleArtifact(
                module_id=module_id,
                status=str(payload.get("status") or ""),
                current_paths=tuple(str(item) for item in payload.get("current_paths", []) if isinstance(item, str)),
                public_interface=tuple(
                    str(item) for item in payload.get("public_interface", []) if isinstance(item, str)
                ),
                state_files_touched=tuple(
                    str(item) for item in payload.get("state_files_touched", []) if isinstance(item, str)
                ),
            )
        )

    return artifacts


def _build_file_owner_map(artifacts: Iterable[ModuleArtifact]) -> dict[str, list[ModuleArtifact]]:
    owners: dict[str, list[ModuleArtifact]] = {}
    for artifact in artifacts:
        for path in artifact.current_paths:
            normalized = path.replace("\\", "/")
            owners.setdefault(normalized, []).append(artifact)
    return owners


def _build_ast_cache(repo_root: Path, artifacts: Iterable[ModuleArtifact]) -> dict[str, ast.AST]:
    ast_cache: dict[str, ast.AST] = {}
    for artifact in artifacts:
        for relative_path in artifact.current_paths:
            normalized = relative_path.replace("\\", "/")
            if normalized in ast_cache:
                continue
            abs_path = repo_root / normalized
            if not abs_path.exists() or abs_path.suffix != ".py":
                continue
            ast_cache[normalized] = ast.parse(abs_path.read_text(encoding="utf-8"), filename=str(abs_path))
    return ast_cache


def _check_active_current_paths_exist(
    repo_root: Path,
    active_artifacts: Iterable[ModuleArtifact],
    failures: list[InvariantIssue],
) -> None:
    for artifact in active_artifacts:
        for relative_path in artifact.current_paths:
            abs_path = repo_root / relative_path
            if not abs_path.exists():
                failures.append(
                    InvariantIssue(
                        code="missing_current_path",
                        module_id=artifact.module_id,
                        path=relative_path,
                        detail="current_paths entry does not exist",
                    )
                )


def _check_deprecated_imports(
    repo_root: Path,
    active_artifacts: Iterable[ModuleArtifact],
    file_owners: dict[str, list[ModuleArtifact]],
    ast_cache: dict[str, ast.AST],
    failures: list[InvariantIssue],
) -> None:
    for artifact in active_artifacts:
        for source_rel in artifact.current_paths:
            tree = ast_cache.get(source_rel.replace("\\", "/"))
            if tree is None:
                continue
            source_module_name = _module_name_for_relpath(source_rel)
            for imported_rel in _iter_imported_relpaths(tree, source_module_name, repo_root):
                owners = file_owners.get(imported_rel)
                if not owners:
                    continue
                if owners and all(owner.status == _DEPRECATED_STATUS for owner in owners):
                    failures.append(
                        InvariantIssue(
                            code="deprecated_module_dependency",
                            module_id=artifact.module_id,
                            path=source_rel,
                            detail=f"imports deprecated-owned path '{imported_rel}'",
                        )
                    )


def _check_forbidden_edges(
    repo_root: Path,
    active_artifacts: Iterable[ModuleArtifact],
    ast_cache: dict[str, ast.AST],
    options: InvariantCheckerOptions,
    failures: list[InvariantIssue],
) -> None:
    forbidden = set(options.forbidden_file_edges)
    for artifact in active_artifacts:
        for source_rel in artifact.current_paths:
            tree = ast_cache.get(source_rel.replace("\\", "/"))
            if tree is None:
                continue
            source_module_name = _module_name_for_relpath(source_rel)
            for imported_rel in _iter_imported_relpaths(tree, source_module_name, repo_root):
                edge = (source_rel.replace("\\", "/"), imported_rel)
                if edge in forbidden:
                    failures.append(
                        InvariantIssue(
                            code="forbidden_reverse_authority_edge",
                            module_id=artifact.module_id,
                            path=source_rel,
                            detail=f"forbidden import edge to '{imported_rel}'",
                        )
                    )


def _check_jsonl_append_governance(
    repo_root: Path,
    active_artifacts: Iterable[ModuleArtifact],
    ast_cache: dict[str, ast.AST],
    failures: list[InvariantIssue],
) -> None:
    del repo_root
    for artifact in active_artifacts:
        if not any(path.endswith(".jsonl") for path in artifact.state_files_touched):
            continue
        for source_rel in artifact.current_paths:
            tree = ast_cache.get(source_rel.replace("\\", "/"))
            if tree is None:
                continue
            raw_append_lines = _find_raw_append_lines(tree)
            if not raw_append_lines:
                continue
            failures.append(
                InvariantIssue(
                    code="ungoverned_jsonl_append",
                    module_id=artifact.module_id,
                    path=source_rel,
                    detail=f"raw append-mode file write at line(s): {', '.join(str(line) for line in raw_append_lines)}",
                )
            )


def _check_export_alignment(
    repo_root: Path,
    active_artifacts: Iterable[ModuleArtifact],
    ast_cache: dict[str, ast.AST],
    options: InvariantCheckerOptions,
    failures: list[InvariantIssue],
    warnings: list[InvariantIssue],
) -> None:
    del repo_root
    strict_paths = set(options.strict_export_paths)
    for artifact in active_artifacts:
        declared = set(artifact.public_interface)
        for source_rel in artifact.current_paths:
            normalized = source_rel.replace("\\", "/")
            tree = ast_cache.get(normalized)
            if tree is None:
                continue
            exports = _extract___all__(tree)
            if exports is None:
                continue

            # Some package __init__.py files publish contract constants instead of
            # the promoted runtime interface. Only enforce alignment when the file
            # is clearly participating in the declared public surface.
            if not (set(exports) & declared or normalized in strict_paths):
                continue

            missing = sorted(declared - set(exports))
            extra = sorted(set(exports) - declared)

            if missing:
                failures.append(
                    InvariantIssue(
                        code="public_interface_export_missing",
                        module_id=artifact.module_id,
                        path=source_rel,
                        detail=f"declared public interface missing from __all__: {', '.join(missing)}",
                    )
                )

            if extra:
                issue = InvariantIssue(
                    code="public_interface_export_leak",
                    module_id=artifact.module_id,
                    path=source_rel,
                    detail=f"__all__ exports undeclared names: {', '.join(extra)}",
                )
                if normalized in strict_paths:
                    failures.append(issue)
                else:
                    warnings.append(issue)


def _iter_imported_relpaths(tree: ast.AST, source_module_name: str, repo_root: Path) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                rel = _resolve_module_to_relpath(alias.name, repo_root)
                if rel is not None:
                    imported.add(rel)
        elif isinstance(node, ast.ImportFrom):
            base_name = _resolve_import_from_module_name(source_module_name, node.module, node.level)
            if not base_name:
                continue
            for alias in node.names:
                candidate_name = f"{base_name}.{alias.name}" if alias.name != "*" else base_name
                candidate_rel = _resolve_module_to_relpath(candidate_name, repo_root)
                if candidate_rel is not None:
                    imported.add(candidate_rel)
                    continue
                base_rel = _resolve_module_to_relpath(base_name, repo_root)
                if base_rel is not None:
                    imported.add(base_rel)
    return imported


def _resolve_import_from_module_name(source_module_name: str, module: str | None, level: int) -> str | None:
    if level == 0:
        return module

    parts = source_module_name.split(".")
    if level > len(parts):
        return None
    prefix = parts[: len(parts) - level]
    if module:
        prefix.append(module)
    return ".".join(part for part in prefix if part)


def _resolve_module_to_relpath(module_name: str, repo_root: Path) -> str | None:
    if not module_name:
        return None
    rel = Path(*module_name.split("."))
    candidates = (rel.with_suffix(".py"), rel / "__init__.py")
    for candidate in candidates:
        full = repo_root / candidate
        if full.exists():
            return candidate.as_posix()
    return None


def _module_name_for_relpath(relative_path: str) -> str:
    path = Path(relative_path.replace("\\", "/"))
    if path.name == "__init__.py":
        return ".".join(path.parent.parts)
    return ".".join(path.with_suffix("").parts)


def _find_raw_append_lines(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        mode = _extract_open_mode(node)
        if mode is None or "a" not in mode:
            continue
        if _is_builtin_open(node) or _is_path_open(node):
            lines.append(node.lineno)
    return sorted(set(lines))


def _extract_open_mode(node: ast.Call) -> str | None:
    if len(node.args) >= 2:
        return _literal_str(node.args[1])
    for keyword in node.keywords:
        if keyword.arg == "mode":
            return _literal_str(keyword.value)
    return None


def _is_builtin_open(node: ast.Call) -> bool:
    return isinstance(node.func, ast.Name) and node.func.id == "open"


def _is_path_open(node: ast.Call) -> bool:
    return isinstance(node.func, ast.Attribute) and node.func.attr == "open"


def _extract___all__(tree: ast.AST) -> list[str] | None:
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                return _literal_string_list(node.value)
    return None


def _literal_string_list(node: ast.AST) -> list[str] | None:
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return None
    values: list[str] = []
    for item in node.elts:
        text = _literal_str(item)
        if text is None:
            return None
        values.append(text)
    return values


def _literal_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _normalize_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return str(path.resolve())

