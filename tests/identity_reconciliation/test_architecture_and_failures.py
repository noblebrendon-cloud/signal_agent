from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

from signal_agent.identity_reconciliation import generate_identity_candidates
from signal_agent.identity_reconciliation.errors import IdentityArtifactCollisionError
from signal_agent.identity_reconciliation.projections import (
    build_reconciled_identity_projection,
)

from .conftest import FIXED_CLOCK
from .test_decisions import _authority, _candidate, _rationale
from signal_agent.identity_reconciliation import record_identity_decision


PROTECTED_HASHES = {
    "signal_agent/relationship_signals/relationship_pipeline.py": (
        "967df45db658ea28200a093385b82f85b98f265781c7232516890312cccdff44"
    ),
    "signal_agent/corpus_import/linkedin/adapter.py": (
        "44d001c43ebd374bfd4688fd9db5d0ef1d389bb41b1ba420c0111f65a392e01d"
    ),
    "signal_agent/corpus_import/interaction_events/adapter.py": (
        "76954c789a92c313c297cfe8c4745b322e02453482f5573c7e20e6d7cb4d0589"
    ),
    "schemas/relationship_signals/relationship_record.v1.schema.json": (
        "32a6d191d16dee34f1b6ac563d87dbd8597072d731c99dd0260200819c0d1ee1"
    ),
    "tests/fixtures/linkedin_connections/compatibility_witness_v1.json": (
        "00755207eb9dc889951e9c751a58bc4e359cdecfac7a843a032370056dd9ce02"
    ),
    "tests/fixtures/interaction_events/compatibility_witness_v1.json": (
        "823940b686bc7f0c0d6ccb5d348412ee7a39c2c15ea5ae2d457f62143146a14d"
    ),
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
        elif isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
    return imports


def test_milestone_2_protected_artifacts_remain_byte_identical() -> None:
    repository = Path(__file__).resolve().parents[2]
    for relative, expected in PROTECTED_HASHES.items():
        assert hashlib.sha256((repository / relative).read_bytes()).hexdigest() == expected


def test_reconciliation_boundaries_are_additive_offline_and_programmatic() -> None:
    repository = Path(__file__).resolve().parents[2]
    source_adapters = [
        repository / "signal_agent/corpus_import/linkedin/adapter.py",
        repository / "signal_agent/corpus_import/interaction_events/adapter.py",
    ]
    assert all(
        "identity_reconciliation" not in path.read_text(encoding="utf-8")
        for path in source_adapters
    )
    forbidden_import_prefixes = (
        "requests",
        "urllib",
        "httpx",
        "socket",
        "signal_agent.interaction",
        "signal_agent.interactions",
        "signal_agent.campaign",
        "signal_agent.messaging",
        "signal_agent.publishing",
        "signal_agent.governance",
    )
    package = repository / "signal_agent/identity_reconciliation"
    for path in package.glob("*.py"):
        assert not any(
            module.startswith(forbidden_import_prefixes) for module in _imports(path)
        ), path
    cli = (repository / "signal_agent/corpus_import/cli.py").read_text("utf-8")
    assert "identity_reconciliation" not in cli
    package_source = "\n".join(path.read_text("utf-8") for path in package.glob("*.py"))
    assert "00_original" not in package_source
    assert "automatic_merge_performed\": True" not in package_source
    assert "fuzzy" not in package_source.casefold()


def test_candidate_failure_never_writes_completed_manifest(
    completed_source_runs, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import signal_agent.identity_reconciliation.candidates as module

    def fail_promotion(*_args, **_kwargs):
        raise OSError("injected candidate artifact promotion failure")

    monkeypatch.setattr(module, "promote_artifacts", fail_promotion)
    output = tmp_path / "failed-candidate-run"
    with pytest.raises(OSError, match="injected"):
        generate_identity_candidates(
            completed_source_runs["linkedin"],
            completed_source_runs["interaction"],
            output,
            completed_source_runs["repository"]
            / "config/identity_reconciliation/linkedin_interaction_attribute_v1.json",
            lambda: FIXED_CLOCK,
        )
    assert not (output / "05_receipts/candidate_generation_manifest.json").exists()
    assert not (output / "03_review").exists()
    assert not (output / "04_projections").exists()


def test_projection_manifest_failure_preserves_inputs_and_is_not_completed(
    candidate_run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import signal_agent.identity_reconciliation.projections as module

    candidate_path, bundle_path = _candidate(candidate_run)
    _result, source_runs = candidate_run
    decision = record_identity_decision(
        candidate_path,
        bundle_path,
        tmp_path / "review",
        _authority(),
        "approved",
        _rationale(),
        source_run_roots={
            "linkedin_connections_csv": source_runs["linkedin"],
            "interaction_event_export.v1": source_runs["interaction"],
        },
    )
    candidate_before = candidate_path.read_bytes()
    decision_before = decision.receipt_path.read_bytes()

    def fail_manifest(*_args, **_kwargs):
        raise IdentityArtifactCollisionError("injected reconciliation manifest failure")

    monkeypatch.setattr(module, "write_exclusive_json", fail_manifest)
    output = tmp_path / "failed-projection"
    with pytest.raises(IdentityArtifactCollisionError, match="injected"):
        build_reconciled_identity_projection(
            candidate_path,
            bundle_path,
            decision.receipt_path,
            output,
            clock=lambda: FIXED_CLOCK,
            source_run_roots={
                "linkedin_connections_csv": source_runs["linkedin"],
                "interaction_event_export.v1": source_runs["interaction"],
            },
        )
    assert candidate_path.read_bytes() == candidate_before
    assert decision.receipt_path.read_bytes() == decision_before
    assert list((output / "04_projections").rglob("*.json"))
    assert not list((output / "05_receipts/reconciliation_manifests").glob("*.json"))
