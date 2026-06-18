from __future__ import annotations

from pathlib import Path

import pytest

from signal_agent.governed_authoring.path_policy import PathPolicyError
from signal_agent.governed_authoring.workspace import LocalAuthoringWorkspace, WORKSPACE_SUBDIRS


ROOT = Path(__file__).resolve().parents[1]


def test_workspace_validation_accepts_explicit_workspace_without_writing(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"

    workspace = LocalAuthoringWorkspace.validate(workspace_root, repo_root=ROOT)

    assert workspace.root == workspace_root.resolve()
    assert not workspace_root.exists()


def test_create_layout_creates_only_known_workspace_subdirs(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace = LocalAuthoringWorkspace.validate(workspace_root, repo_root=ROOT)

    workspace.create_layout()

    assert {path.name for path in workspace_root.iterdir()} == set(WORKSPACE_SUBDIRS)
    assert all((workspace_root / subdir).is_dir() for subdir in WORKSPACE_SUBDIRS)


def test_workspace_rejects_repo_data_root() -> None:
    with pytest.raises(PathPolicyError) as exc:
        LocalAuthoringWorkspace.validate(ROOT / "data", repo_root=ROOT)

    assert exc.value.code == "FORBIDDEN_OUTPUT_PATH"


def test_workspace_validates_known_output_file_types(tmp_path: Path) -> None:
    workspace = LocalAuthoringWorkspace.validate(tmp_path / "workspace", repo_root=ROOT)

    assert workspace.validate_result_path(workspace.root / "results" / "result.json").name == "result.json"
    assert workspace.validate_summary_path(workspace.root / "summaries" / "summary.md").name == "summary.md"
    assert workspace.validate_validation_path(workspace.root / "validation" / "report.json").name == "report.json"
    assert workspace.validate_metadata_path(workspace.root / "metadata" / "run.json").name == "run.json"
    assert workspace.validate_draft_path(workspace.root / "drafts" / "draft.md").name == "draft.md"


def test_workspace_rejects_output_path_in_wrong_subdir(tmp_path: Path) -> None:
    workspace = LocalAuthoringWorkspace.validate(tmp_path / "workspace", repo_root=ROOT)

    with pytest.raises(PathPolicyError) as exc:
        workspace.validate_result_path(workspace.root / "summaries" / "result.json")

    assert exc.value.code == "FORBIDDEN_OUTPUT_PATH"


def test_workspace_rejects_parent_traversal_outside_root(tmp_path: Path) -> None:
    workspace = LocalAuthoringWorkspace.validate(tmp_path / "workspace", repo_root=ROOT)

    with pytest.raises(PathPolicyError) as exc:
        workspace.validate_result_path(Path("results") / ".." / ".." / "outside.json")

    assert exc.value.code == "FORBIDDEN_OUTPUT_PATH"


def test_workspace_rejects_repo_data_result_path(tmp_path: Path) -> None:
    workspace = LocalAuthoringWorkspace.validate(tmp_path / "workspace", repo_root=ROOT)

    with pytest.raises(PathPolicyError):
        workspace.validate_result_path(ROOT / "data" / "outputs" / "result.json")


def test_workspace_validates_explicit_ledger_path_under_ledgers(tmp_path: Path) -> None:
    workspace = LocalAuthoringWorkspace.validate(tmp_path / "workspace", repo_root=ROOT)

    ledger_path = workspace.validate_ledger_path(
        workspace.root / "ledgers" / "canonical.jsonl",
        ledger_requested=True,
    )

    assert ledger_path == workspace.root / "ledgers" / "canonical.jsonl"


def test_workspace_rejects_implicit_ledger_path_when_requested(tmp_path: Path) -> None:
    workspace = LocalAuthoringWorkspace.validate(tmp_path / "workspace", repo_root=ROOT)

    with pytest.raises(PathPolicyError) as exc:
        workspace.validate_ledger_path(None, ledger_requested=True)

    assert exc.value.code == "LEDGER_PATH_REQUIRED"


def test_workspace_rejects_production_ledger_path(tmp_path: Path) -> None:
    workspace = LocalAuthoringWorkspace.validate(tmp_path / "workspace", repo_root=ROOT)

    with pytest.raises(PathPolicyError) as exc:
        workspace.validate_ledger_path(ROOT / "data" / "artifact_registry.jsonl", ledger_requested=True)

    assert exc.value.code == "LEDGER_PATH_FORBIDDEN"


def test_workspace_rejects_existing_output_without_overwrite(tmp_path: Path) -> None:
    workspace = LocalAuthoringWorkspace.validate(tmp_path / "workspace", repo_root=ROOT)
    existing = workspace.root / "results" / "result.json"
    existing.parent.mkdir(parents=True)
    existing.write_text("existing\n", encoding="utf-8")

    with pytest.raises(PathPolicyError) as exc:
        workspace.validate_result_path(existing)

    assert exc.value.code == "OVERWRITE_DENIED"
    assert existing.read_text(encoding="utf-8") == "existing\n"
