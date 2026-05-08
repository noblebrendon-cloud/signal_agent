from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_pi_witness_project_tracking_artifacts_exist() -> None:
    project_root = REPO_ROOT / "docs" / "operator" / "pi_witness_node"

    assert project_root.is_dir()
    assert (project_root / "PROJECT.md").is_file()
    assert (project_root / "IMPLEMENTATION_PLAN.md").is_file()
    assert (project_root / "TASK_LEDGER.md").is_file()
    assert (project_root / "DECISION_LOG.md").is_file()


def test_pi_witness_scripts_exist() -> None:
    assert (REPO_ROOT / "scripts" / "run_pi_witness_check.sh").is_file()
    assert (REPO_ROOT / "scripts" / "run_pi_witness_check.ps1").is_file()


def test_pi_witness_scripts_do_not_declare_prohibited_git_or_delete_actions() -> None:
    script_paths = [
        REPO_ROOT / "scripts" / "run_pi_witness_check.sh",
        REPO_ROOT / "scripts" / "run_pi_witness_check.ps1",
    ]
    prohibited_fragments = [
        "git push",
        "git commit",
        "git merge",
        "git reset",
        "git checkout",
        "rm -",
        "Remove-Item",
        "Invoke-WebRequest",
        "curl ",
    ]

    for script_path in script_paths:
        text = script_path.read_text(encoding="utf-8")
        for fragment in prohibited_fragments:
            assert fragment not in text, f"{fragment!r} found in {script_path}"
