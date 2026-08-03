from __future__ import annotations

import json
from pathlib import Path

import pytest

from signal_agent.corpus_import.linkedin.key_verifier import (
    ensure_key_verifier,
    load_key_context,
)
from signal_agent.identity_reconciliation import generate_identity_candidates
from signal_agent.relationship_signals.interaction_event_pipeline import (
    run_interaction_event_relationship_slice,
)
from signal_agent.relationship_signals.pipeline import run_linkedin_relationship_slice


FIXED_CLOCK = "2026-08-03T12:00:00Z"
TEST_ONLY_KEY = bytes.fromhex(
    "6f4cda45d36a935e170c901da31c50f1"
    "ab2e248b823fc8354603c92f35d6f23e"
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.fixture
def completed_source_runs(tmp_path: Path) -> dict[str, Path]:
    repository_root = Path(__file__).resolve().parents[2]
    key_file = tmp_path / "outside-repository.key"
    key_file.write_bytes(TEST_ONLY_KEY)
    linkedin_repo = tmp_path / "linkedin-repo"
    interaction_repo = tmp_path / "interaction-repo"
    linkedin_repo.mkdir()
    interaction_repo.mkdir()
    linkedin_context = load_key_context(
        key_file,
        "acceptance-test-key-v1",
        repo_root=linkedin_repo,
    )
    ensure_key_verifier(
        linkedin_context,
        repo_root=linkedin_repo,
        clock=lambda: "2000-01-01T00:00:00Z",
    )
    linkedin_root = tmp_path / "linkedin-run"
    interaction_root = tmp_path / "interaction-run"
    run_linkedin_relationship_slice(
        source=repository_root / "tests/fixtures/linkedin_connections/Connections.csv",
        run_root=linkedin_root,
        hmac_key_file=key_file,
        hmac_key_id="acceptance-test-key-v1",
        repo_root=linkedin_repo,
        content_library_root=repository_root / "docs/operator/content_library",
        clock=lambda: "2026-08-02T12:00:00Z",
    )
    run_interaction_event_relationship_slice(
        source=repository_root / "tests/fixtures/interaction_events/events.jsonl",
        run_root=interaction_root,
        hmac_key_file=key_file,
        hmac_key_id="interaction-event-test-key-v1",
        repo_root=interaction_repo,
        content_library_root=repository_root / "docs/operator/content_library",
        taxonomy_path=repository_root
        / "config/relationship_topics/governed_systems_v1.json",
        clock=lambda: "2026-08-02T12:00:00Z",
    )
    return {
        "repository": repository_root,
        "linkedin": linkedin_root,
        "interaction": interaction_root,
    }


@pytest.fixture
def candidate_run(tmp_path: Path, completed_source_runs: dict[str, Path]):
    root = tmp_path / "candidate-run"
    result = generate_identity_candidates(
        completed_source_runs["linkedin"],
        completed_source_runs["interaction"],
        root,
        completed_source_runs["repository"]
        / "config/identity_reconciliation/linkedin_interaction_attribute_v1.json",
        lambda: FIXED_CLOCK,
    )
    return result, completed_source_runs
