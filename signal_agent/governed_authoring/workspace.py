from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .path_policy import (
    ALLOWED_EXPLICIT_LEDGER_PATH,
    ALLOWED_TEMP_PATH,
    ALLOWED_WORKSPACE_PATH,
    PathClassification,
    PathPolicyError,
    classify_path,
    default_repo_root,
    reject_existing_file,
    require_allowed,
)


WORKSPACE_SUBDIRS = (
    "inputs",
    "results",
    "summaries",
    "ledgers",
    "validation",
    "drafts",
    "metadata",
)


@dataclass(frozen=True)
class LocalAuthoringWorkspace:
    root: Path
    repo_root: Path
    temp_root: Path | None = None

    @classmethod
    def validate(
        cls,
        root: Path | str,
        *,
        repo_root: Path | None = None,
        temp_root: Path | None = None,
    ) -> "LocalAuthoringWorkspace":
        resolved_repo = (repo_root or default_repo_root()).resolve(strict=False)
        resolved_root = Path(root).expanduser().resolve(strict=False)
        resolved_temp = Path(temp_root).expanduser().resolve(strict=False) if temp_root else None
        classification = classify_path(
            resolved_root,
            repo_root=resolved_repo,
            workspace_root=resolved_root,
            temp_root=resolved_temp,
        )
        if classification.classification not in {ALLOWED_WORKSPACE_PATH, ALLOWED_TEMP_PATH}:
            require_allowed(classification)
        return cls(root=resolved_root, repo_root=resolved_repo, temp_root=resolved_temp)

    def classify(self, path: Path | str, *, path_kind: str = "generic") -> PathClassification:
        return classify_path(
            path,
            repo_root=self.repo_root,
            workspace_root=self.root,
            temp_root=self.temp_root,
            path_kind=path_kind,
        )

    def create_layout(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for subdir in WORKSPACE_SUBDIRS:
            (self.root / subdir).mkdir(parents=True, exist_ok=True)

    def subdir(self, name: str) -> Path:
        if name not in WORKSPACE_SUBDIRS:
            raise ValueError(f"unknown workspace subdir: {name}")
        return self.root / name

    def validate_result_path(self, path: Path | str, *, allow_overwrite: bool = False) -> Path:
        return self._validate_output_path(path, subdir="results", allow_overwrite=allow_overwrite)

    def validate_summary_path(self, path: Path | str, *, allow_overwrite: bool = False) -> Path:
        return self._validate_output_path(path, subdir="summaries", allow_overwrite=allow_overwrite)

    def validate_validation_path(self, path: Path | str, *, allow_overwrite: bool = False) -> Path:
        return self._validate_output_path(path, subdir="validation", allow_overwrite=allow_overwrite)

    def validate_metadata_path(self, path: Path | str, *, allow_overwrite: bool = False) -> Path:
        return self._validate_output_path(path, subdir="metadata", allow_overwrite=allow_overwrite)

    def validate_draft_path(self, path: Path | str, *, allow_overwrite: bool = False) -> Path:
        return self._validate_output_path(path, subdir="drafts", allow_overwrite=allow_overwrite)

    def validate_ledger_path(
        self,
        path: Path | str | None,
        *,
        ledger_requested: bool,
    ) -> Path | None:
        if path is None:
            if ledger_requested:
                raise PathPolicyError(
                    "LEDGER_PATH_REQUIRED",
                    "ledger output was requested without an explicit ledger path",
                    category="ledger",
                )
            return None

        classification = self.classify(path, path_kind="ledger")
        if classification.classification != ALLOWED_EXPLICIT_LEDGER_PATH:
            require_allowed(classification, allow_append=True)
            raise PathPolicyError(
                "LEDGER_PATH_FORBIDDEN",
                "ledger path must be inside approved workspace ledgers/",
                path=classification.resolved_path,
                classification=classification,
                category="ledger",
            )
        return require_allowed(classification, allow_append=True).resolved_path

    def _validate_output_path(self, path: Path | str, *, subdir: str, allow_overwrite: bool) -> Path:
        classification = require_allowed(self.classify(path))
        expected_root = (self.root / subdir).resolve(strict=False)
        if not _is_relative_to(classification.resolved_path, expected_root):
            raise PathPolicyError(
                "FORBIDDEN_OUTPUT_PATH",
                f"output path must be inside workspace {subdir}/",
                path=classification.resolved_path,
                classification=classification,
            )
        reject_existing_file(classification.resolved_path, allow_overwrite=allow_overwrite)
        return classification.resolved_path


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
