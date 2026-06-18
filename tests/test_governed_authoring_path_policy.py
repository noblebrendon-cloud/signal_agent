from __future__ import annotations

from pathlib import Path

import pytest

from signal_agent.governed_authoring.path_policy import (
    ALLOWED_EXPLICIT_LEDGER_PATH,
    ALLOWED_TEMP_PATH,
    ALLOWED_WORKSPACE_PATH,
    AMBIGUOUS_PATH,
    FORBIDDEN_PARENT_TRAVERSAL,
    FORBIDDEN_PRODUCTION_ARTIFACT_PATH,
    FORBIDDEN_PRODUCTION_LEDGER_PATH,
    FORBIDDEN_REPO_DATA_PATH,
    UNKNOWN_PATH,
    PathPolicyError,
    classify_path,
    reject_existing_file,
    require_allowed,
)


ROOT = Path(__file__).resolve().parents[1]


def test_allowed_temp_workspace_is_accepted(tmp_path: Path) -> None:
    temp_workspace = tmp_path / "router-run"

    result = classify_path(temp_workspace, repo_root=ROOT, temp_root=tmp_path)

    assert result.classification == ALLOWED_TEMP_PATH
    assert result.may_write is True


def test_allowed_explicit_workspace_outside_repo_data_is_accepted(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    result = classify_path(workspace, repo_root=ROOT, workspace_root=workspace)

    assert result.classification == ALLOWED_WORKSPACE_PATH
    assert result.may_write is True


def test_required_workspace_output_subdirs_are_accepted(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    for subdir, filename in [
        ("results", "result.json"),
        ("summaries", "summary.md"),
        ("validation", "validation.json"),
        ("metadata", "metadata.json"),
        ("drafts", "draft.md"),
    ]:
        result = classify_path(workspace / subdir / filename, repo_root=ROOT, workspace_root=workspace)
        assert result.classification == ALLOWED_WORKSPACE_PATH
        assert result.may_write is True


def test_explicit_ledger_path_under_workspace_ledgers_is_accepted(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    result = classify_path(
        workspace / "ledgers" / "canonical.jsonl",
        repo_root=ROOT,
        workspace_root=workspace,
        path_kind="ledger",
    )

    assert result.classification == ALLOWED_EXPLICIT_LEDGER_PATH
    assert result.may_append is True


def test_repo_data_workspace_is_rejected() -> None:
    result = classify_path(ROOT / "data", repo_root=ROOT, workspace_root=ROOT / "data")

    assert result.classification == FORBIDDEN_REPO_DATA_PATH
    with pytest.raises(PathPolicyError) as exc:
        require_allowed(result)
    assert exc.value.code == "FORBIDDEN_OUTPUT_PATH"


def test_repo_data_result_path_is_rejected(tmp_path: Path) -> None:
    result = classify_path(
        ROOT / "data" / "outputs" / "result.json",
        repo_root=ROOT,
        workspace_root=tmp_path / "workspace",
    )

    assert result.classification == FORBIDDEN_REPO_DATA_PATH


def test_production_ledger_path_is_rejected() -> None:
    result = classify_path(ROOT / "data" / "artifact_registry.jsonl", repo_root=ROOT, path_kind="ledger")

    assert result.classification == FORBIDDEN_PRODUCTION_LEDGER_PATH


def test_production_artifact_path_is_rejected_with_explicit_artifact_root(tmp_path: Path) -> None:
    artifact_root = tmp_path / "production_authoring_artifacts"

    result = classify_path(
        artifact_root / "output.json",
        repo_root=ROOT,
        workspace_root=tmp_path / "workspace",
        production_artifact_roots=[artifact_root],
    )

    assert result.classification == FORBIDDEN_PRODUCTION_ARTIFACT_PATH


def test_parent_traversal_outside_workspace_is_rejected(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    result = classify_path(Path("results") / ".." / ".." / "outside.json", repo_root=ROOT, workspace_root=workspace)

    assert result.classification == FORBIDDEN_PARENT_TRAVERSAL


def test_ambiguous_or_unknown_paths_fail_closed(tmp_path: Path) -> None:
    ambiguous = classify_path("*", repo_root=ROOT, workspace_root=tmp_path / "workspace")
    unknown = classify_path(tmp_path / "outside" / "result.json", repo_root=ROOT, workspace_root=tmp_path / "workspace")

    assert ambiguous.classification == AMBIGUOUS_PATH
    assert unknown.classification == UNKNOWN_PATH
    with pytest.raises(PathPolicyError):
        require_allowed(ambiguous)
    with pytest.raises(PathPolicyError):
        require_allowed(unknown)


def test_overwrite_attempt_is_rejected_by_default(tmp_path: Path) -> None:
    existing = tmp_path / "workspace" / "results" / "result.json"
    existing.parent.mkdir(parents=True)
    existing.write_text("existing\n", encoding="utf-8")

    with pytest.raises(PathPolicyError) as exc:
        reject_existing_file(existing)

    assert exc.value.code == "OVERWRITE_DENIED"
    assert existing.read_text(encoding="utf-8") == "existing\n"
