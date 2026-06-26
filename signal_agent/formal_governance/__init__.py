"""Isolated formal-governance proof pack for Signal Agent.

This package is intentionally parallel to existing HQ/operator runtimes. It
formalizes the missing proof primitives and provides a fixture-driven proof
surface without writing to production ledgers.
"""

from .decision import deterministic_transition_id, evaluate_transition
from .canonical_ledger import append_canonical_ledger_entry
from .models import (
    ArchitectureNode,
    ArtifactPocket,
    BranchVector,
    ConsolidationPass,
    DecisionOutcome,
    HumanTrigger,
    Invariant,
    InvariantArchitecture,
    InvariantPath,
    LedgerEntry,
    PromotionDecision,
    RollbackPath,
    State,
    TransitionProposal,
    UnresolvedTension,
    VariantPocket,
)

__all__ = [
    "ArchitectureNode",
    "ArtifactPocket",
    "BranchVector",
    "ConsolidationPass",
    "DecisionOutcome",
    "HumanTrigger",
    "Invariant",
    "InvariantArchitecture",
    "InvariantPath",
    "LedgerEntry",
    "PromotionDecision",
    "RollbackPath",
    "State",
    "TransitionProposal",
    "UnresolvedTension",
    "VariantPocket",
    "append_canonical_ledger_entry",
    "deterministic_transition_id",
    "evaluate_transition",
]
