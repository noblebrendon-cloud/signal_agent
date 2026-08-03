from __future__ import annotations

import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PYPDF_REQUIREMENT = "pypdf==6.7.0"


def test_pypdf_version_is_exact_and_agrees_across_dependency_contracts() -> None:
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project_requirements = project["project"]["dependencies"]
    project_pypdf = [
        requirement
        for requirement in project_requirements
        if requirement.lower().startswith("pypdf")
    ]
    lock_requirements = {
        line.strip()
        for line in (REPO_ROOT / "environment" / "requirements.lock")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert project_pypdf == [EXPECTED_PYPDF_REQUIREMENT]
    assert EXPECTED_PYPDF_REQUIREMENT in lock_requirements
