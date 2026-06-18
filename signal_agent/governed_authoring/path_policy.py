from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ALLOWED_WORKSPACE_PATH = "allowed_workspace_path"
ALLOWED_TEMP_PATH = "allowed_temp_path"
ALLOWED_EXPLICIT_LEDGER_PATH = "allowed_explicit_ledger_path"
FORBIDDEN_REPO_DATA_PATH = "forbidden_repo_data_path"
FORBIDDEN_PRODUCTION_LEDGER_PATH = "forbidden_production_ledger_path"
FORBIDDEN_PRODUCTION_ARTIFACT_PATH = "forbidden_production_artifact_path"
FORBIDDEN_PARENT_TRAVERSAL = "forbidden_parent_traversal"
AMBIGUOUS_PATH = "ambiguous_path"
UNKNOWN_PATH = "unknown_path"

DENIED_CLASSIFICATIONS = {
    FORBIDDEN_REPO_DATA_PATH,
    FORBIDDEN_PRODUCTION_LEDGER_PATH,
    FORBIDDEN_PRODUCTION_ARTIFACT_PATH,
    FORBIDDEN_PARENT_TRAVERSAL,
    AMBIGUOUS_PATH,
    UNKNOWN_PATH,
}

KNOWN_CLASSIFICATIONS = {
    ALLOWED_WORKSPACE_PATH,
    ALLOWED_TEMP_PATH,
    ALLOWED_EXPLICIT_LEDGER_PATH,
    *DENIED_CLASSIFICATIONS,
}


@dataclass(frozen=True)
class PathClassification:
    classification: str
    resolved_path: Path
    repo_root: Path
    repo_data_root: Path
    workspace_root: Path | None
    temp_root: Path | None
    reason: str
    may_write: bool
    may_append: bool = False

    def to_dict(self) -> dict[str, str | bool | None]:
        return {
            "classification": self.classification,
            "resolved_path": str(self.resolved_path),
            "repo_root": str(self.repo_root),
            "repo_data_root": str(self.repo_data_root),
            "workspace_root": str(self.workspace_root) if self.workspace_root else None,
            "temp_root": str(self.temp_root) if self.temp_root else None,
            "reason": self.reason,
            "may_write": self.may_write,
            "may_append": self.may_append,
        }


class PathPolicyError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        path: Path | None = None,
        classification: PathClassification | None = None,
        category: str = "path",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.category = category
        self.path = path
        self.classification = classification

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "category": self.category,
            "message": str(self),
            "path": str(self.path) if self.path else None,
            "classification": self.classification.to_dict() if self.classification else None,
            "recoverable": True,
            "safe_to_retry": False,
        }


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _has_parent_traversal(path: Path) -> bool:
    return ".." in path.parts


def _has_glob_ambiguity(path: Path) -> bool:
    return any("*" in part or "?" in part for part in path.parts)


def _has_symlink_ambiguity(path: Path) -> bool:
    current = path
    while True:
        if current.exists() and current.is_symlink():
            return True
        parent = current.parent
        if parent == current:
            return False
        current = parent


def _resolve_roots(
    *,
    repo_root: Path | None,
    workspace_root: Path | None,
    temp_root: Path | None,
) -> tuple[Path, Path | None, Path | None]:
    resolved_repo = _resolve(repo_root or default_repo_root())
    resolved_workspace = _resolve(workspace_root) if workspace_root is not None else None
    resolved_temp = _resolve(temp_root) if temp_root is not None else None
    return resolved_repo, resolved_workspace, resolved_temp


def _candidate_path(path: Path | str, *, workspace_root: Path | None, temp_root: Path | None) -> Path:
    raw = Path(path)
    if raw.is_absolute():
        return raw
    if workspace_root is not None:
        return workspace_root / raw
    if temp_root is not None:
        return temp_root / raw
    return raw


def _default_production_artifact_roots(repo_root: Path) -> tuple[Path, ...]:
    data_root = repo_root / "data"
    return (
        data_root / "governed_authoring",
        data_root / "authoring",
        data_root / "outputs" / "governed_authoring",
        data_root / "outputs" / "authoring",
    )


def _resolve_many(paths: Iterable[Path] | None) -> tuple[Path, ...]:
    if paths is None:
        return ()
    return tuple(_resolve(path) for path in paths)


def classify_path(
    path: Path | str,
    *,
    repo_root: Path | None = None,
    workspace_root: Path | None = None,
    temp_root: Path | None = None,
    path_kind: str = "generic",
    production_ledger_paths: Iterable[Path] | None = None,
    production_artifact_roots: Iterable[Path] | None = None,
) -> PathClassification:
    resolved_repo, resolved_workspace, resolved_temp = _resolve_roots(
        repo_root=repo_root,
        workspace_root=workspace_root,
        temp_root=temp_root,
    )
    repo_data_root = resolved_repo / "data"
    raw = Path(path)
    candidate = _candidate_path(raw, workspace_root=resolved_workspace, temp_root=resolved_temp)
    resolved = _resolve(candidate)

    def result(classification: str, reason: str, *, may_write: bool = False, may_append: bool = False) -> PathClassification:
        return PathClassification(
            classification=classification,
            resolved_path=resolved,
            repo_root=resolved_repo,
            repo_data_root=repo_data_root,
            workspace_root=resolved_workspace,
            temp_root=resolved_temp,
            reason=reason,
            may_write=may_write,
            may_append=may_append,
        )

    if _has_glob_ambiguity(raw):
        return result(AMBIGUOUS_PATH, "path contains wildcard-like ambiguity")

    if _has_symlink_ambiguity(candidate):
        return result(AMBIGUOUS_PATH, "path contains symlink-like ambiguity")

    escaped_workspace = resolved_workspace is not None and not _is_relative_to(resolved, resolved_workspace)
    escaped_temp = resolved_temp is not None and not _is_relative_to(resolved, resolved_temp)
    if _has_parent_traversal(raw) and (escaped_workspace or (resolved_workspace is None and escaped_temp)):
        return result(FORBIDDEN_PARENT_TRAVERSAL, "parent traversal escapes approved root")

    ledger_paths = _resolve_many(production_ledger_paths)
    if resolved in ledger_paths or (
        path_kind == "ledger" and resolved.suffix.lower() == ".jsonl" and _is_relative_to(resolved, repo_data_root)
    ):
        return result(FORBIDDEN_PRODUCTION_LEDGER_PATH, "path resolves to a production ledger location")

    artifact_roots = _resolve_many(production_artifact_roots) or _default_production_artifact_roots(resolved_repo)
    if any(resolved == root or _is_relative_to(resolved, root) for root in artifact_roots):
        return result(FORBIDDEN_PRODUCTION_ARTIFACT_PATH, "path resolves to a production authoring artifact location")

    if resolved == repo_data_root or _is_relative_to(resolved, repo_data_root):
        return result(FORBIDDEN_REPO_DATA_PATH, "path resolves under repo data/")

    if path_kind == "ledger":
        if resolved_workspace is not None and _is_relative_to(resolved, resolved_workspace / "ledgers"):
            return result(
                ALLOWED_EXPLICIT_LEDGER_PATH,
                "explicit ledger path is inside approved workspace ledgers/",
                may_write=True,
                may_append=True,
            )
        if resolved_temp is not None and _is_relative_to(resolved, resolved_temp):
            return result(
                ALLOWED_EXPLICIT_LEDGER_PATH,
                "explicit ledger path is inside approved temp root",
                may_write=True,
                may_append=True,
            )

    if resolved_workspace is not None and _is_relative_to(resolved, resolved_workspace):
        return result(ALLOWED_WORKSPACE_PATH, "path is inside approved workspace", may_write=True)

    if resolved_temp is not None and _is_relative_to(resolved, resolved_temp):
        return result(ALLOWED_TEMP_PATH, "path is inside approved temp root", may_write=True)

    return result(UNKNOWN_PATH, "path is outside approved workspace and temp roots")


def require_allowed(
    classification: PathClassification,
    *,
    allow_append: bool = False,
) -> PathClassification:
    if classification.classification in DENIED_CLASSIFICATIONS:
        raise PathPolicyError(
            _error_code_for_classification(classification.classification),
            classification.reason,
            path=classification.resolved_path,
            classification=classification,
            category="ledger" if "ledger" in classification.classification else "path",
        )
    if allow_append and not classification.may_append:
        raise PathPolicyError(
            "LEDGER_PATH_FORBIDDEN",
            "path is not approved for append",
            path=classification.resolved_path,
            classification=classification,
            category="ledger",
        )
    if not allow_append and not classification.may_write:
        raise PathPolicyError(
            "FORBIDDEN_OUTPUT_PATH",
            "path is not approved for writing",
            path=classification.resolved_path,
            classification=classification,
        )
    return classification


def reject_existing_file(path: Path, *, allow_overwrite: bool = False) -> None:
    resolved = _resolve(path)
    if resolved.exists() and not allow_overwrite:
        raise PathPolicyError(
            "OVERWRITE_DENIED",
            f"output file already exists: {resolved}",
            path=resolved,
            category="path",
        )


def _error_code_for_classification(classification: str) -> str:
    if classification == AMBIGUOUS_PATH:
        return "AMBIGUOUS_PATH"
    if classification == FORBIDDEN_PRODUCTION_LEDGER_PATH:
        return "LEDGER_PATH_FORBIDDEN"
    if classification == FORBIDDEN_PRODUCTION_ARTIFACT_PATH:
        return "ATTEMPTED_PRODUCTION_WRITE"
    if classification == FORBIDDEN_REPO_DATA_PATH:
        return "FORBIDDEN_OUTPUT_PATH"
    if classification == FORBIDDEN_PARENT_TRAVERSAL:
        return "FORBIDDEN_OUTPUT_PATH"
    return "FORBIDDEN_OUTPUT_PATH"
