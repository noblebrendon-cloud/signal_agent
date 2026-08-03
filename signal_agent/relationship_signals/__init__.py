"""Governed relationship analysis and packet construction."""

from typing import Any


__all__ = [
    "InteractionEventRelationshipSliceResult",
    "RelationshipPipelineResult",
    "RelationshipSliceResult",
    "run_interaction_event_relationship_slice",
    "run_linkedin_relationship_slice",
    "run_relationship_signal_pipeline",
]


def __getattr__(name: str) -> Any:
    if name in {"RelationshipPipelineResult", "run_relationship_signal_pipeline"}:
        from .relationship_pipeline import (
            RelationshipPipelineResult,
            run_relationship_signal_pipeline,
        )

        return {
            "RelationshipPipelineResult": RelationshipPipelineResult,
            "run_relationship_signal_pipeline": run_relationship_signal_pipeline,
        }[name]
    if name in {"RelationshipSliceResult", "run_linkedin_relationship_slice"}:
        from .pipeline import RelationshipSliceResult, run_linkedin_relationship_slice

        return {
            "RelationshipSliceResult": RelationshipSliceResult,
            "run_linkedin_relationship_slice": run_linkedin_relationship_slice,
        }[name]
    if name in {
        "InteractionEventRelationshipSliceResult",
        "run_interaction_event_relationship_slice",
    }:
        from .interaction_event_pipeline import (
            InteractionEventRelationshipSliceResult,
            run_interaction_event_relationship_slice,
        )

        return {
            "InteractionEventRelationshipSliceResult": (
                InteractionEventRelationshipSliceResult
            ),
            "run_interaction_event_relationship_slice": (
                run_interaction_event_relationship_slice
            ),
        }[name]
    raise AttributeError(name)
