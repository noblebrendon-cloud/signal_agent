from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from signal_agent.relationship_signals.interaction_event_pipeline import (
    run_interaction_event_relationship_slice,
)
from signal_agent.relationship_signals import (
    run_interaction_event_relationship_slice as public_run_interaction_event_slice,
)


FIXED_CLOCK = "2026-08-02T12:00:00Z"
TEST_ONLY_KEY = bytes.fromhex(
    "6f4cda45d36a935e170c901da31c50f1"
    "ab2e248b823fc8354603c92f35d6f23e"
)
EXPECTED_ARTIFACTS = {
    "00_original/interaction_events.jsonl",
    "00_original/interaction_events.jsonl.sha256.txt",
    "01_normalized/relationship_records.jsonl",
    "02_analysis/related_work.json",
    "02_analysis/topic_cluster.json",
    "02_analysis/unresolved_matches.json",
    "04_packets/campaign_context_packet.json",
    "04_packets/signal_packet.json",
    "05_receipts/run_manifest.json",
    "05_receipts/source_receipt.json",
}


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    key_file = tmp_path / "interaction-event.relationship-hmac.key"
    key_file.write_bytes(TEST_ONLY_KEY)
    source = Path(__file__).resolve().parent / "fixtures/interaction_events/events.jsonl"
    return fake_repo, key_file, source


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _run(tmp_path: Path, name: str):
    repository_root = Path(__file__).resolve().parents[1]
    fake_repo, key_file, source = _inputs(tmp_path)
    return run_interaction_event_relationship_slice(
        source=source,
        run_root=tmp_path / name,
        hmac_key_file=key_file,
        hmac_key_id="interaction-event-test-key-v1",
        repo_root=fake_repo,
        content_library_root=repository_root / "docs/operator/content_library",
        taxonomy_path=repository_root
        / "config/relationship_topics/governed_systems_v1.json",
        clock=lambda: FIXED_CLOCK,
    )


def test_programmatic_slice_completes_all_stages_and_ten_artifacts(tmp_path: Path) -> None:
    assert public_run_interaction_event_slice is run_interaction_event_relationship_slice
    result = _run(tmp_path, "run")
    tree = _tree(result.run_root)

    assert result.success is True
    assert result.record_count == 6
    assert result.candidate_group_count == 1
    assert result.cluster_confidence_state == "high"
    assert set(tree) == EXPECTED_ARTIFACTS
    assert len(tree) == 10
    assert not (result.run_root / ".staging").exists()
    manifest = json.loads(tree["05_receipts/run_manifest.json"])
    signal = json.loads(tree["04_packets/signal_packet.json"])
    campaign = json.loads(tree["04_packets/campaign_context_packet.json"])
    assert manifest["completion_state"] == "completed"
    assert manifest["identifier_protection"]["version"] == (
        "interaction_event_actor_identity_token.v1"
    )
    assert signal["status"] == "pending_human_approval"
    assert campaign["authorization"]["authorized"] is False


def test_two_independent_runs_are_byte_identical(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    repository_root = Path(__file__).resolve().parents[1]
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    key_file = tmp_path / "key.bin"
    key_file.write_bytes(TEST_ONLY_KEY)
    source = Path(__file__).resolve().parent / "fixtures/interaction_events/events.jsonl"
    kwargs = {
        "source": source,
        "hmac_key_file": key_file,
        "hmac_key_id": "interaction-event-test-key-v1",
        "repo_root": fake_repo,
        "content_library_root": repository_root / "docs/operator/content_library",
        "taxonomy_path": repository_root
        / "config/relationship_topics/governed_systems_v1.json",
        "clock": lambda: FIXED_CLOCK,
    }
    run_interaction_event_relationship_slice(run_root=first_root, **kwargs)
    run_interaction_event_relationship_slice(run_root=second_root, **kwargs)

    assert _tree(first_root) == _tree(second_root)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def test_import_and_branch_boundaries_remain_neutral_and_cli_is_deferred() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    generic = repository_root / "signal_agent/relationship_signals/relationship_pipeline.py"
    generic_imports = _imports(generic)
    generic_source = generic.read_text(encoding="utf-8")
    source_root = repository_root / "signal_agent/corpus_import/interaction_events"

    assert not any(
        module.startswith("signal_agent.corpus_import.interaction_events")
        for module in generic_imports
    )
    assert "interaction_event" not in generic_source.casefold()
    assert "linkedin" not in generic_source.casefold()
    for path in source_root.glob("*.py"):
        imports = _imports(path)
        assert not any(
            module.startswith("signal_agent.relationship_signals")
            for module in imports
        ), path
        assert not any(
            module.startswith("signal_agent.interactions")
            or module.startswith("signal_agent.interaction")
            for module in imports
        ), path
    cli_source = (repository_root / "signal_agent/corpus_import/cli.py").read_text(
        encoding="utf-8"
    )
    assert "interaction_event" not in cli_source.casefold()


def test_relationship_schema_is_unchanged_from_baseline() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    schema = repository_root / "schemas/relationship_signals/relationship_record.v1.schema.json"
    assert hashlib.sha256(schema.read_bytes()).hexdigest() == (
        "32a6d191d16dee34f1b6ac563d87dbd8597072d731c99dd0260200819c0d1ee1"
    )
