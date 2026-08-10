from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from signal_agent.operational_ingestion.checkpoints import (
    commit_checkpoint,
    create_checkpoint_candidate,
    resolve_current_checkpoint,
)
from signal_agent.operational_ingestion.canonical import canonical_json_bytes, seal
from signal_agent.operational_ingestion.errors import (
    CheckpointConflictError,
    OperationalArtifactError,
)
from signal_agent.operational_ingestion.models import (
    CompletedRunReference,
    PersistedArtifact,
    thaw_json,
)

from .simulated_test_support import SECOND_TIME, run_case


class InjectedM4BFailure(RuntimeError):
    pass


def _raise_at(expected: str):
    def inject(stage: str) -> None:
        if stage == expected:
            raise InjectedM4BFailure(stage)

    return inject


@pytest.mark.parametrize(
    "stage",
    [
        "after_session",
        "after_attempts",
        "after_captures",
        "after_bounded_material",
        "after_boundary",
        "after_processor",
        "after_manifest_verification",
        "after_observation_index",
        "after_checkpoint_candidate",
        "after_completion_authority",
        "before_checkpoint_commit",
    ],
)
def test_every_kernel_failure_keeps_prior_checkpoint_current(
    tmp_path: Path, repository_root: Path, stage: str
) -> None:
    store = tmp_path / "store"
    seed = run_case(
        repository_root,
        tmp_path / "seed",
        operational_store_root=store,
    )
    prior = seed.execution.ingestion.checkpoint_commit
    with pytest.raises(InjectedM4BFailure, match=stage):
        run_case(
            repository_root,
            tmp_path / "failed",
            start=SECOND_TIME,
            prior_checkpoint=prior,
            operational_store_root=store,
            kernel_failure_injector=_raise_at(stage),
        )
    current = resolve_current_checkpoint(seed.execution.ingestion.source_root)
    assert current.payload["checkpoint_id"] == prior.payload["checkpoint_id"]
    successor = seed.execution.ingestion.source_root / f"checkpoints/from-{prior.payload['checkpoint_id']}/checkpoint-commit.json"
    assert not successor.exists()


@pytest.mark.parametrize(
    "stage",
    [
        "preservation_failure",
        "after_preservation_failure",
        "normalization_failure",
        "downstream_processing_failure",
        "generic_manifest_promotion_failure",
        "after_downstream_output_before_completed_manifest",
        "manifest_verification_failure",
    ],
)
def test_every_governed_failure_keeps_prior_checkpoint_current(
    tmp_path: Path, repository_root: Path, stage: str
) -> None:
    store = tmp_path / "store"
    seed = run_case(repository_root, tmp_path / "seed", operational_store_root=store)
    prior = seed.execution.ingestion.checkpoint_commit
    with pytest.raises(Exception):
        run_case(
            repository_root,
            tmp_path / "failed",
            start=SECOND_TIME,
            prior_checkpoint=prior,
            operational_store_root=store,
            processor_failure_stage=stage,
        )
    assert resolve_current_checkpoint(seed.execution.ingestion.source_root).payload["checkpoint_id"] == prior.payload["checkpoint_id"]
    if stage != "manifest_verification_failure":
        assert not list(
            (tmp_path / "failed" / "governed").rglob(
                "operational_completed_manifest.json"
            )
        )


@pytest.mark.parametrize(
    "stage",
    ["after_session", "after_attempt_persist", "before_capture_persist", "after_capture_persist"],
)
def test_acquisition_persistence_failure_never_creates_checkpoint(
    tmp_path: Path, repository_root: Path, stage: str
) -> None:
    with pytest.raises(InjectedM4BFailure, match=stage):
        run_case(
            repository_root,
            tmp_path,
            acquisition_failure_injector=_raise_at(stage),
        )
    assert not list((tmp_path / "store").rglob("checkpoint-commit.json"))


def test_capture_body_corruption_after_processing_blocks_candidate(
    tmp_path: Path, repository_root: Path
) -> None:
    def corrupt(stage: str) -> None:
        if stage == "after_processor":
            body = next((tmp_path / "store").rglob("*.body"))
            body.write_bytes(body.read_bytes() + b"corrupt")

    with pytest.raises(OperationalArtifactError, match="capture_body_hash_mismatch"):
        run_case(repository_root, tmp_path, kernel_failure_injector=corrupt)
    assert not list((tmp_path / "store").rglob("*.checkpoint-candidate.json"))


def test_bounded_material_corruption_after_processing_blocks_candidate(
    tmp_path: Path, repository_root: Path
) -> None:
    def corrupt(stage: str) -> None:
        if stage == "after_processor":
            bounded = next((tmp_path / "store").rglob("*.source.json"))
            bounded.write_bytes(bounded.read_bytes() + b"corrupt")

    with pytest.raises(Exception):
        run_case(repository_root, tmp_path, kernel_failure_injector=corrupt)
    assert not list((tmp_path / "store").rglob("*.checkpoint-candidate.json"))


def test_exact_checkpoint_replay_returns_existing_bytes(
    tmp_path: Path, repository_root: Path
) -> None:
    result = run_case(repository_root, tmp_path).execution.ingestion
    before = result.checkpoint_commit.path.read_bytes()
    first_committed_at = result.checkpoint_commit.payload["committed_at"]
    replay = commit_checkpoint(
        result.source_root,
        candidate=result.checkpoint_candidate,
        authority=result.completion_authority,
        completed=result.completed_run,
        committed_at=SECOND_TIME,
    )
    assert replay.idempotent_replay is True
    assert replay.path.read_bytes() == before
    assert replay.payload["committed_at"] == first_committed_at


def test_checkpoint_candidate_replay_returns_existing_immutable_bytes(
    tmp_path: Path, repository_root: Path
) -> None:
    result = run_case(repository_root, tmp_path).execution.ingestion
    before = result.checkpoint_candidate.path.read_bytes()
    replay = create_checkpoint_candidate(
        result.source_root,
        intent=result.intent,
        boundary=result.boundary,
        bounded_material=result.bounded_material,
        observation_index=result.observation_index,
        completed=result.completed_run,
    )
    assert replay.idempotent_replay is True
    assert replay.path.read_bytes() == before
    assert replay.payload == result.checkpoint_candidate.payload


def test_invalid_verifier_authority_cannot_commit(tmp_path: Path, repository_root: Path) -> None:
    result = run_case(repository_root, tmp_path).execution.ingestion
    authority = thaw_json(result.completion_authority.payload)
    authority["verifier_version"] = "unsupported"
    authority = seal({key: value for key, value in authority.items() if key != "artifact_hash"})
    altered_path = result.completion_authority.path.with_name("altered.authority.json")
    altered_path.write_bytes(canonical_json_bytes(authority))
    altered = PersistedArtifact(altered_path, authority, False)
    with pytest.raises(CheckpointConflictError):
        commit_checkpoint(
            result.source_root,
            candidate=result.checkpoint_candidate,
            authority=altered,
            completed=result.completed_run,
            committed_at=SECOND_TIME,
        )


def _load_uncommitted(source_root: Path, governed_root: Path):
    candidate_path = max(source_root.glob("checkpoint_candidates/*.json"), key=lambda p: p.stat().st_mtime_ns)
    authority_path = max(source_root.glob("completion_authorities/*.json"), key=lambda p: p.stat().st_mtime_ns)
    candidate_payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    authority_payload = json.loads(authority_path.read_text(encoding="utf-8"))
    manifest = json.loads((governed_root / "05_receipts/operational_completed_manifest.json").read_text(encoding="utf-8"))
    completed = CompletedRunReference(
        run_id=manifest["run_id"],
        run_root=governed_root,
        run_root_ref=f"simulated-operational-governed-run:{manifest['run_id']}",
        manifest_relative_path="05_receipts/operational_completed_manifest.json",
        preservation_receipt_relative_path="05_receipts/simulated_operational_source_receipt.json",
    )
    return (
        PersistedArtifact(candidate_path, candidate_payload, True),
        PersistedArtifact(authority_path, authority_payload, True),
        completed,
    )


def test_completed_manifest_and_authority_can_resume_missing_commit(
    tmp_path: Path, repository_root: Path
) -> None:
    with pytest.raises(InjectedM4BFailure, match="before_checkpoint_commit"):
        run_case(
            repository_root,
            tmp_path,
            kernel_failure_injector=_raise_at("before_checkpoint_commit"),
        )
    source_root = next(path for path in (tmp_path / "store").iterdir() if path.is_dir())
    assert resolve_current_checkpoint(source_root) is None
    candidate, authority, completed = _load_uncommitted(source_root, tmp_path / "governed")
    commit = commit_checkpoint(
        source_root,
        candidate=candidate,
        authority=authority,
        completed=completed,
        committed_at=SECOND_TIME,
    )
    assert resolve_current_checkpoint(source_root).payload["checkpoint_id"] == commit.payload["checkpoint_id"]


def test_foreign_bootstrap_successor_is_rejected(tmp_path: Path, repository_root: Path) -> None:
    first = run_case(repository_root, tmp_path / "first").execution.ingestion
    second = run_case(repository_root, tmp_path / "second").execution.ingestion
    with pytest.raises(CheckpointConflictError, match="completion_authority_outside_source_root"):
        commit_checkpoint(
            first.source_root,
            candidate=second.checkpoint_candidate,
            authority=second.completion_authority,
            completed=second.completed_run,
            committed_at=SECOND_TIME,
        )


def test_candidate_stale_after_another_successor_commits(
    tmp_path: Path, repository_root: Path
) -> None:
    store = tmp_path / "store"
    seed = run_case(repository_root, tmp_path / "seed", operational_store_root=store).execution.ingestion
    prior = seed.checkpoint_commit
    uncommitted = []
    for label, start in (("a", "2026-08-10T13:00:00Z"), ("b", "2026-08-10T14:00:00Z")):
        governed = tmp_path / label / "governed"
        with pytest.raises(InjectedM4BFailure):
            run_case(
                repository_root,
                tmp_path / label,
                operational_store_root=store,
                governed_run_root=governed,
                prior_checkpoint=prior,
                start=start,
                kernel_failure_injector=_raise_at("before_checkpoint_commit"),
            )
        uncommitted.append(_load_uncommitted(seed.source_root, governed))
    winner = commit_checkpoint(
        seed.source_root,
        candidate=uncommitted[0][0],
        authority=uncommitted[0][1],
        completed=uncommitted[0][2],
        committed_at="2026-08-10T15:00:00Z",
    )
    with pytest.raises(CheckpointConflictError, match="divergent_checkpoint_successor"):
        commit_checkpoint(
            seed.source_root,
            candidate=uncommitted[1][0],
            authority=uncommitted[1][1],
            completed=uncommitted[1][2],
            committed_at="2026-08-10T16:00:00Z",
        )
    assert resolve_current_checkpoint(seed.source_root).payload["checkpoint_id"] == winner.payload["checkpoint_id"]


def test_m4b_kernel_has_no_network_or_relationship_imports(repository_root: Path) -> None:
    simulator = repository_root / "signal_agent/operational_ingestion/simulator.py"
    tree_node = ast.parse(simulator.read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree_node):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    forbidden = ("requests", "httpx", "urllib", "socket", "relationship_signals", "gmail", "github")
    assert not [name for name in imports if name.startswith(forbidden)]


def test_protected_m4a_tree_and_m1_to_m3_files_remain_exact(repository_root: Path) -> None:
    protected = {
        "signal_agent/relationship_signals/relationship_pipeline.py": "967df45db658ea28200a093385b82f85b98f265781c7232516890312cccdff44",
        "signal_agent/corpus_import/linkedin/adapter.py": "44d001c43ebd374bfd4688fd9db5d0ef1d389bb41b1ba420c0111f65a392e01d",
        "signal_agent/corpus_import/interaction_events/adapter.py": "76954c789a92c313c297cfe8c4745b322e02453482f5573c7e20e6d7cb4d0589",
        "schemas/relationship_signals/relationship_record.v1.schema.json": "32a6d191d16dee34f1b6ac563d87dbd8597072d731c99dd0260200819c0d1ee1",
        "tests/fixtures/linkedin_connections/compatibility_witness_v1.json": "00755207eb9dc889951e9c751a58bc4e359cdecfac7a843a032370056dd9ce02",
        "tests/fixtures/interaction_events/compatibility_witness_v1.json": "823940b686bc7f0c0d6ccb5d348412ee7a39c2c15ea5ae2d457f62143146a14d",
        "tests/fixtures/identity_reconciliation/compatibility_witness_v1.json": "80a3790f8c88e5e5ed3a827c37052f9572c8a6783dbfaa3de79cc96567fe862b",
    }
    actual = {
        path: hashlib.sha256((repository_root / path).read_bytes()).hexdigest()
        for path in protected
    }
    assert actual == protected

    command = [
        "git",
        "-c",
        f"safe.directory={repository_root.as_posix()}",
        "diff",
        "--name-only",
        "6c533cf",
        "95d642ef2b520e13c6eeeff4c1648594cf8adc0a",
        "--",
    ]
    paths = subprocess.run(
        command,
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert len(paths) == 31
    material = "".join(
        f"{path}={hashlib.sha256((repository_root / path).read_bytes()).hexdigest()}\n"
        for path in sorted(paths, key=str.casefold)
    ).encode("utf-8")
    assert hashlib.sha256(material).hexdigest() == "53deba75f109b071c1eebf300510f163f1ad779c3ff6543df466f52129cc11be"


def test_m4b_additions_expose_no_cli_network_or_automatic_merge_path(repository_root: Path) -> None:
    additions = [
        repository_root / "signal_agent/operational_ingestion/simulator.py",
        repository_root / "signal_agent/corpus_import/simulated_operational/adapter.py",
        repository_root / "signal_agent/relationship_signals/simulated_operational_pipeline.py",
    ]
    text = "\n".join(path.read_text(encoding="utf-8").casefold() for path in additions)
    for forbidden in (
        "import requests",
        "import httpx",
        "import socket",
        "gmail",
        "oauth",
        "automatic_merge_performed\": true",
        "argparse",
        "click.command",
    ):
        assert forbidden not in text
