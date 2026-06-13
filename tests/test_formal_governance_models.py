from __future__ import annotations

import json
from pathlib import Path

from signal_agent.formal_governance import (
    ArchitectureNode,
    ArtifactPocket,
    BranchVector,
    ConsolidationPass,
    DecisionOutcome,
    HumanTrigger,
    Invariant,
    InvariantArchitecture,
    InvariantPath,
    RollbackPath,
    State,
    TransitionProposal,
    UnresolvedTension,
    VariantPocket,
    deterministic_transition_id,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "formal_governance"
SCHEMAS = ROOT / "schemas" / "formal_governance"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_all_required_schema_files_are_present_and_parseable() -> None:
    expected = {
        "architecture_node.v1.schema.json",
        "artifact_pocket.v1.schema.json",
        "branch_vector.v1.schema.json",
        "consolidation_pass.v1.schema.json",
        "governed_transition_ledger_entry.v1.schema.json",
        "human_trigger.v1.schema.json",
        "invariant.v1.schema.json",
        "invariant_architecture.v1.schema.json",
        "invariant_path.v1.schema.json",
        "promotion_decision.v1.schema.json",
        "rollback_path.v1.schema.json",
        "state.v1.schema.json",
        "unresolved_tension.v1.schema.json",
        "variant_pocket.v1.schema.json",
    }

    actual = {path.name for path in SCHEMAS.glob("*.json")}
    assert expected <= actual

    for schema_name in expected:
        schema = json.loads((SCHEMAS / schema_name).read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["type"] == "object"


def test_decision_outcome_enum_contains_required_outcomes() -> None:
    expected = {
        "ADMIT_ARTIFACT",
        "CONSOLIDATE_ONLY",
        "PROMOTE_TO_STATE",
        "DEFER_UNRESOLVED_TENSION",
        "REJECT_INVALID_LINEAGE",
        "REJECT_MISSING_INVARIANT",
        "REJECT_RAW_ARTIFACT_SELF_PROMOTION",
        "REJECT_MISSING_EVIDENCE",
        "REJECT_MISSING_AUTHORITY",
        "REJECT_SELF_CERTIFICATION",
        "REJECT_MISSING_ROLLBACK",
        "BLOCK_DUPLICATE",
        "MANUAL_REVIEW_REQUIRED",
    }

    assert expected == {item.value for item in DecisionOutcome}


def test_valid_fixture_materializes_all_required_primitives() -> None:
    proposal = TransitionProposal.from_fixture(_load_fixture("valid_promotion.json"))

    assert isinstance(proposal.origin_state, State)
    assert isinstance(proposal.proposed_state, State)
    assert isinstance(proposal.root_invariant, Invariant)
    assert isinstance(proposal.invariant_path, InvariantPath)
    assert isinstance(proposal.branch_vector, BranchVector)
    assert isinstance(proposal.artifact_pocket, ArtifactPocket)
    assert isinstance(proposal.variant_pocket, VariantPocket)
    assert isinstance(proposal.human_trigger, HumanTrigger)
    assert isinstance(proposal.rollback_path, RollbackPath)
    assert isinstance(proposal.unresolved_tensions[0], UnresolvedTension)
    assert isinstance(proposal.architecture_nodes[0], ArchitectureNode)
    assert isinstance(proposal.invariant_architecture, InvariantArchitecture)
    assert isinstance(proposal.consolidation_pass, ConsolidationPass)

    assert proposal.root_invariant.invariant_id == "invariant.governed_transition"
    assert proposal.invariant_path.binds(proposal.root_invariant)
    assert proposal.human_trigger is not None
    assert proposal.human_trigger.is_approved_human() is True
    assert proposal.rollback_path is not None
    assert proposal.rollback_path.satisfies_state_mutation() is True


def test_duplicate_fixture_has_same_deterministic_transition_identity_as_valid_fixture() -> None:
    valid = TransitionProposal.from_fixture(_load_fixture("valid_promotion.json"))
    duplicate = TransitionProposal.from_fixture(_load_fixture("duplicate_transition.json"))

    assert valid.proposal_id != duplicate.proposal_id
    assert deterministic_transition_id(valid) == deterministic_transition_id(duplicate)

